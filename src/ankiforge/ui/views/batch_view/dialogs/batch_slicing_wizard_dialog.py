"""Assistant de découpage interactif (Wizard) pour la Batch Factory."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteTypeModel,
    PipelineModel,
)
from ankiforge.services.batch.slicing_service import SliceUnit, SlicingService
from ankiforge.ui.components import PrimaryButton, SecondaryButton, StyledComboBox
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class BatchSlicingWizardDialog(QDialog):
    """Assistant guidé en 3 étapes pour sélectionner et calibrer les sections d'un document."""

    IGNORE_KEYWORDS = (
        "intro",
        "préface",
        "preface",
        "avant-propos",
        "sommaire",
        "table des matières",
        "remerciement",
        "annexe",
        "bibliographie",
        "glossaire",
        "index",
    )

    def __init__(
        self,
        doc: DocumentModel,
        decks: list[DeckModel],
        note_types: list[NoteTypeModel],
        engines: list[LLMConfigModel],
        pipelines: list[PipelineModel],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.doc = doc
        self.decks = decks
        self.note_types = note_types
        self.engines = engines
        self.pipelines = pipelines

        self.doc_content = getattr(doc, "content", "") or ""
        self.raw_slices = SlicingService.slice_by_headings(self.doc_content, max_depth=3, min_words=30)

        self._current_step = 0
        self.setWindowTitle("Assistant de Découpage du Document")
        self.resize(750, 580)
        self._setup_ui()
        self._populate_tree()
        self._update_step_view()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # En-tête des étapes du Wizard
        wizard_nav = QWidget()
        nav_layout = QHBoxLayout(wizard_nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)

        self.step_btn_1 = self._create_nav_chip("1. Arborescence & Sections", active=True)
        self.step_btn_2 = self._create_nav_chip("2. Cibles & Pipeline IA", active=False)
        self.step_btn_3 = self._create_nav_chip("3. Récapitulatif", active=False)

        nav_layout.addWidget(self.step_btn_1, 1)
        nav_layout.addWidget(self.step_btn_2, 1)
        nav_layout.addWidget(self.step_btn_3, 1)
        main_layout.addWidget(wizard_nav)

        # Corps avec QStackedWidget
        self.body_stack = QStackedWidget()

        # --- ÉTAPE 1 : ARBORESCENCE & SECTIONS ---
        step1_widget = QWidget()
        s1_layout = QVBoxLayout(step1_widget)
        s1_layout.setContentsMargins(0, 8, 0, 0)
        s1_layout.setSpacing(10)

        toolbar1 = QHBoxLayout()
        self.btn_check_all = SecondaryButton("Tout cocher")
        self.btn_check_all.clicked.connect(lambda: self._set_all_checked(True))
        self.btn_uncheck_all = SecondaryButton("Tout décocher")
        self.btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))
        self.btn_ignore_noise = SecondaryButton("Ignorer intros / annexes")
        self.btn_ignore_noise.setIcon(load_phosphor_icon("ph.funnel", color=DesignTokens.TEXT_PRIMARY))
        self.btn_ignore_noise.clicked.connect(self._ignore_noise_sections)

        self.lbl_selected_count = QLabel("0 section(s) sélectionnée(s)")
        self.lbl_selected_count.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-size: 11px;")

        toolbar1.addWidget(self.btn_check_all)
        toolbar1.addWidget(self.btn_uncheck_all)
        toolbar1.addWidget(self.btn_ignore_noise)
        toolbar1.addStretch()
        toolbar1.addWidget(self.lbl_selected_count)
        s1_layout.addLayout(toolbar1)

        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Section / Titre", "Page", "Mots", "Tokens"])
        self.tree_widget.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_widget.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tree_widget.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                font-size: 12px;
            }}
            QTreeWidget::item {{
                padding: 5px 0;
            }}
        """)
        self.tree_widget.itemChanged.connect(self._on_tree_item_changed)
        s1_layout.addWidget(self.tree_widget, 1)
        self.body_stack.addWidget(step1_widget)

        # --- ÉTAPE 2 : CIBLES & IA ---
        step2_widget = QWidget()
        s2_layout = QVBoxLayout(step2_widget)
        s2_layout.setContentsMargins(0, 16, 0, 0)
        s2_layout.setSpacing(16)

        card_config = QFrame()
        card_config.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 16px;
            }}
        """)
        c_layout = QVBoxLayout(card_config)
        c_layout.setSpacing(12)

        # Paquet Cible
        lbl_deck = QLabel("PAQUET ANKI CIBLE :")
        lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        c_layout.addWidget(lbl_deck)
        self.combo_deck = StyledComboBox()
        for d in self.decks:
            self.combo_deck.addItem(load_phosphor_icon("ph.folder", color=DesignTokens.COLOR_BLUE), d.name, userData=d)
        c_layout.addWidget(self.combo_deck)

        # Modèle de Note
        lbl_model = QLabel("MODÈLE DE NOTE :")
        lbl_model.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        c_layout.addWidget(lbl_model)
        self.combo_model = StyledComboBox()
        for nt in self.note_types:
            self.combo_model.addItem(load_phosphor_icon("ph.cards", color=DesignTokens.COLOR_PURPLE), nt.name, userData=nt)
        c_layout.addWidget(self.combo_model)

        # Pipeline IA
        lbl_pipeline = QLabel("PIPELINE D'EXTRACTION IA :")
        lbl_pipeline.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        c_layout.addWidget(lbl_pipeline)
        self.combo_pipeline = StyledComboBox()
        for p in self.pipelines:
            self.combo_pipeline.addItem(load_phosphor_icon("ph.tree-structure", color=DesignTokens.COLOR_GREEN), p.name, userData=p)
        c_layout.addWidget(self.combo_pipeline)

        # Moteur IA
        lbl_engine = QLabel("MOTEUR LLM :")
        lbl_engine.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        c_layout.addWidget(lbl_engine)
        self.combo_engine = StyledComboBox()
        for eg in self.engines:
            disp = getattr(eg, "display_name", getattr(eg, "name", str(eg)))
            self.combo_engine.addItem(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_YELLOW), disp, userData=eg)
        c_layout.addWidget(self.combo_engine)

        s2_layout.addWidget(card_config)
        s2_layout.addStretch()
        self.body_stack.addWidget(step2_widget)

        # --- ÉTAPE 3 : RÉCAPITULATIF & VALIDATION ---
        step3_widget = QWidget()
        s3_layout = QVBoxLayout(step3_widget)
        s3_layout.setContentsMargins(0, 16, 0, 0)
        s3_layout.setSpacing(16)

        recap_frame = QFrame()
        recap_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 20px;
            }}
        """)
        r_layout = QVBoxLayout(recap_frame)
        r_layout.setSpacing(10)

        title_recap = QLabel("Prêt pour la création de la file d'attente !")
        title_recap.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        r_layout.addWidget(title_recap)

        self.lbl_recap_sections = QLabel()
        self.lbl_recap_sections.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        r_layout.addWidget(self.lbl_recap_sections)

        self.lbl_recap_config = QLabel()
        self.lbl_recap_config.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        r_layout.addWidget(self.lbl_recap_config)

        self.lbl_recap_staging_info = QLabel(
            "ℹ️ Toutes les tâches créées seront exécutées en arrière-plan. Dès qu'une tranche est terminée, "
            "ses cartes seront disponibles dans la Zone de Staging pour inspection et validation avant ajout définitif."
        )
        self.lbl_recap_staging_info.setWordWrap(True)
        self.lbl_recap_staging_info.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; margin-top: 10px;")
        r_layout.addWidget(self.lbl_recap_staging_info)

        s3_layout.addWidget(recap_frame)
        s3_layout.addStretch()
        self.body_stack.addWidget(step3_widget)

        main_layout.addWidget(self.body_stack, 1)

        # Barre de navigation inférieure (Précédent / Suivant / Terminer)
        bottom_nav = QHBoxLayout()
        self.btn_back = SecondaryButton("Précédent")
        self.btn_back.clicked.connect(self._on_back)
        self.btn_next = PrimaryButton("Suivant")
        self.btn_next.clicked.connect(self._on_next)

        bottom_nav.addWidget(self.btn_back)
        bottom_nav.addStretch()
        bottom_nav.addWidget(self.btn_next)
        main_layout.addLayout(bottom_nav)

    def _create_nav_chip(self, label: str, active: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setEnabled(False)
        bg = DesignTokens.ACCENT_PRIMARY if active else DesignTokens.BG_INPUT
        color = DesignTokens.TEXT_ON_ACCENT if active else DesignTokens.TEXT_MUTED
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {color};
                font-weight: bold;
                font-size: 11px;
                padding: 6px 12px;
                border-radius: {DesignTokens.RADIUS_SM}px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        return btn

    def _update_step_view(self) -> None:
        self.body_stack.setCurrentIndex(self._current_step)
        chips = [self.step_btn_1, self.step_btn_2, self.step_btn_3]
        for i, chip in enumerate(chips):
            active = i == self._current_step
            bg = DesignTokens.ACCENT_PRIMARY if active else DesignTokens.BG_INPUT
            color = DesignTokens.TEXT_ON_ACCENT if active else DesignTokens.TEXT_MUTED
            chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {color};
                    font-weight: bold;
                    font-size: 11px;
                    padding: 6px 12px;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                }}
            """)

        self.btn_back.setEnabled(self._current_step > 0)
        if self._current_step == 2:
            self._update_recap_view()
            self.btn_next.setText(f"Générer les {len(self.get_selected_slices())} tâches dans la file")
            self.btn_next.setIcon(load_on_accent_icon("ph.check"))
        else:
            self.btn_next.setText("Suivant")
            self.btn_next.setIcon(load_on_accent_icon("ph.caret-right"))

    def _on_back(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            self._update_step_view()

    def _on_next(self) -> None:
        if self._current_step < 2:
            self._current_step += 1
            self._update_step_view()
        else:
            self.accept()

    def _populate_tree(self) -> None:
        self.tree_widget.blockSignals(True)
        self.tree_widget.clear()
        for s in self.raw_slices:
            item = QTreeWidgetItem()
            item.setText(0, s.title)
            item.setText(1, str(s.page_number) if s.page_number is not None else "-")
            item.setText(2, f"{s.words_estimate:,}".replace(",", " "))
            item.setText(3, f"{s.tokens_estimate:,}".replace(",", " "))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, s)
            self.tree_widget.addTopLevelItem(item)
        self.tree_widget.blockSignals(False)
        self._update_selected_count()

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.tree_widget.blockSignals(True)
        for i in range(self.tree_widget.topLevelItemCount()):
            self.tree_widget.topLevelItem(i).setCheckState(0, state)
        self.tree_widget.blockSignals(False)
        self._update_selected_count()

    def _ignore_noise_sections(self) -> None:
        self.tree_widget.blockSignals(True)
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            title_lower = item.text(0).casefold()
            if any(keyword in title_lower for keyword in self.IGNORE_KEYWORDS):
                item.setCheckState(0, Qt.CheckState.Unchecked)
        self.tree_widget.blockSignals(False)
        self._update_selected_count()

    def _on_tree_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        self._update_selected_count()

    def _update_selected_count(self) -> None:
        count = len([i for i in range(self.tree_widget.topLevelItemCount()) if self.tree_widget.topLevelItem(i).checkState(0) == Qt.CheckState.Checked])
        self.lbl_selected_count.setText(f"{count} section(s) sélectionnée(s)")

    def _update_recap_view(self) -> None:
        selected = self.get_selected_slices()
        total_tokens = sum(s.tokens_estimate for s in selected)
        total_words = sum(s.words_estimate for s in selected)
        self.lbl_recap_sections.setText(
            f"• <b>{len(selected)} section(s)</b> sélectionnée(s) sur {len(self.raw_slices)} au total.<br>• <b>~{total_words:,} mots</b> et <b>~{total_tokens:,} tokens</b> estimés.".replace(",", " ")
        )
        deck_name = self.combo_deck.currentText()
        model_name = self.combo_model.currentText()
        pipe_name = self.combo_pipeline.currentText()
        engine_name = self.combo_engine.currentText()
        self.lbl_recap_config.setText(f"Paquet : <b>{deck_name}</b> | Modèle : <b>{model_name}</b><br>Moteur : <b>{engine_name}</b> | Pipeline : <b>{pipe_name}</b>")

    def get_selected_slices(self) -> list[SliceUnit]:
        """Retourne la liste des SliceUnit cochées dans l'arbre."""
        selected: list[SliceUnit] = []
        for i in range(self.tree_widget.topLevelItemCount()):
            item = self.tree_widget.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                s = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(s, SliceUnit):
                    selected.append(s)
        return selected

    def get_configured_payloads(self) -> list[dict[str, Any]]:
        """Construit les dictionnaires complets de tâches pour l'injection directe dans la file d'attente."""
        selected_slices = self.get_selected_slices()
        deck = self.combo_deck.currentData()
        model = self.combo_model.currentData()
        pipeline = self.combo_pipeline.currentData()
        engine = self.combo_engine.currentData()

        deck_name = getattr(deck, "name", "Général") if deck else "Général"
        model_name = getattr(model, "name", "Basique") if model else "Basique"
        pipe_name = getattr(pipeline, "name", "Standard") if pipeline else "Standard"

        tasks: list[dict[str, Any]] = []
        for s in selected_slices:
            tasks.append(
                {
                    "doc": self.doc,
                    "doc_title": f"{self.doc.title} — {s.title}",
                    "doc_content": s.content,
                    "source_chunks": [s.as_dict()],
                    "chunk_label": s.title,
                    "chunk_index": s.index,
                    "tokens_est": s.tokens_estimate,
                    "deck": deck,
                    "deck_name": deck_name,
                    "note_type": model,
                    "model_name": model_name,
                    "engine": engine,
                    "pipeline": pipeline,
                    "pipeline_name": pipe_name,
                    "use_vision": False,
                    "auto_val": False,  # Staging par défaut !
                    "temperature": 0.7,
                    "max_tokens": 16384,
                    "status": "En attente",
                    "progress_pct": 0,
                    "cards_count": 0,
                    "pending_cards": [],
                }
            )
        return tasks
