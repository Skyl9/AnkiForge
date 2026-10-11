"""Boîte de dialogue d'hygiène et de fusion des tags pour AnkiForge.

Permet de détecter les grappes de tags proches ou sensibles à la casse,
de sélectionner finement les variantes à fusionner et d'appliquer
la réécriture sous transaction atomique.
Conforme aux Règles 2, 8, 18, 19 et 20 de GEMINI.md et DESIGN.md.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DeckModel
from ankiforge.services.cards.bulk_hygiene_service import (
    BulkHygieneService,
    TagCluster,
    TagClustersReport,
    TagMergePlan,
    TagMergeResult,
)
from ankiforge.ui.components import ActionButton, PrimaryButton
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.deck_select_window import ALL_DECKS_NODE_ID, DeckSelectWindow
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class TagClusterCard(QFrame):
    """Carte interactive représentant une grappe de tags à fusionner."""

    changed = Signal()
    ignored = Signal(str)

    def __init__(self, cluster: TagCluster, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cluster = cluster
        self._variant_checkboxes: dict[str, QCheckBox] = {}
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("tagClusterCard")
        self.setStyleSheet(f"""
            QFrame#tagClusterCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#tagClusterCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QFrame#tagClusterCard QLabel,
            QFrame#tagClusterCard QCheckBox {{
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # 1. Ligne d'en-tête (Case globale, Badge de type, nombre de notes, bouton ignorer)
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        self.cluster_cb = QCheckBox(self)
        self.cluster_cb.setChecked(True)
        self.cluster_cb.setStyleSheet("border: none; background: transparent;")
        self.cluster_cb.toggled.connect(self._on_global_toggled)
        top_layout.addWidget(self.cluster_cb)

        if self.cluster.cluster_type == "case":
            badge = Badge(tr("Casse"), variant="info", color=DesignTokens.COLOR_BLUE, parent=self)
        else:
            badge = Badge(tr("Similarité"), variant="status", color=DesignTokens.COLOR_PURPLE, parent=self)
        top_layout.addWidget(badge)

        self.notes_lbl = QLabel(tr("%1 note(s) impactée(s)", self.cluster.total_notes_count), self)
        self.notes_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        top_layout.addWidget(self.notes_lbl)

        top_layout.addStretch()

        self.btn_ignore = QToolButton(self)
        self.btn_ignore.setIcon(load_phosphor_icon("x", color=DesignTokens.TEXT_MUTED))
        self.btn_ignore.setToolTip(tr("Ignorer cette grappe pour cette session"))
        self.btn_ignore.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background: transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px;
            }}
            QToolButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.btn_ignore.clicked.connect(lambda: self.ignored.emit(self.cluster.cluster_id))
        top_layout.addWidget(self.btn_ignore)

        layout.addLayout(top_layout)

        # 2. Sélecteur du tag canonique cible
        target_layout = QHBoxLayout()
        target_layout.setContentsMargins(0, 0, 0, 0)
        target_layout.setSpacing(8)

        target_lbl = QLabel(tr("Tag cible :"), self)
        target_lbl.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        target_layout.addWidget(target_lbl)

        self.target_combo = QComboBox(self)
        self.target_combo.setEditable(True)
        self.target_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.target_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 3px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-weight: bold;
            }}
            QComboBox:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Remplir le combo avec toutes les variantes connues
        for tf in self.cluster.tags:
            self.target_combo.addItem(tf.tag)
        # Sélectionner la cible canonique par défaut
        idx = self.target_combo.findText(self.cluster.canonical_tag)
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)
        else:
            self.target_combo.setEditText(self.cluster.canonical_tag)

        self.target_combo.currentTextChanged.connect(self._on_target_changed)
        target_layout.addWidget(self.target_combo)

        layout.addLayout(target_layout)

        # 3. Liste des variantes avec cases à cocher individuelles
        variants_box = QFrame(self)
        variants_box.setObjectName("variantsBox")
        variants_box.setStyleSheet(f"""
            QFrame#variantsBox {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame#variantsBox QLabel,
            QFrame#variantsBox QCheckBox {{
                border: none;
                background: transparent;
            }}
        """)
        variants_layout = QHBoxLayout(variants_box)
        variants_layout.setContentsMargins(8, 6, 8, 6)
        variants_layout.setSpacing(12)

        for tf in self.cluster.tags:
            cb = QCheckBox(f"{tf.tag} ({tf.count})", variants_box)
            cb.setChecked(True)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    font-size: 11px;
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: none;
                    background: transparent;
                }}
            """)
            cb.toggled.connect(self._on_variant_toggled)
            self._variant_checkboxes[tf.tag] = cb
            variants_layout.addWidget(cb)

        variants_layout.addStretch()
        layout.addWidget(variants_box)

    @Slot(bool)
    def _on_global_toggled(self, checked: bool) -> None:
        for cb in self._variant_checkboxes.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self.changed.emit()

    @Slot(bool)
    def _on_variant_toggled(self, _checked: bool) -> None:
        has_any_checked = any(cb.isChecked() for cb in self._variant_checkboxes.values())
        self.cluster_cb.blockSignals(True)
        self.cluster_cb.setChecked(has_any_checked)
        self.cluster_cb.blockSignals(False)
        self.changed.emit()

    @Slot(str)
    def _on_target_changed(self, _text: str) -> None:
        self.changed.emit()

    def is_included(self) -> bool:
        """Indique si la grappe est active et possède au moins un tag à remplacer."""
        if not self.cluster_cb.isChecked():
            return False
        plan = self.get_merge_plan()
        return plan is not None and len(plan.tags_to_merge) > 0

    def get_merge_plan(self) -> TagMergePlan | None:
        """Retourne le plan de fusion configuré pour cette grappe."""
        target = self.target_combo.currentText().strip()
        if not target:
            return None

        # Tags cochés qui diffèrent de la cible
        sources: list[str] = []
        for tag_str, cb in self._variant_checkboxes.items():
            if cb.isChecked() and tag_str != target:
                sources.append(tag_str)

        if not sources:
            return None

        return TagMergePlan(tags_to_merge=sources, target_tag=target)

    def matches_query(self, query: str) -> bool:
        """Vérifie si la grappe contient des tags correspondant au filtre textuel."""
        q = query.strip().lower()
        if not q:
            return True
        if q in self.cluster.canonical_tag.lower():
            return True
        return any(q in tf.tag.lower() for tf in self.cluster.tags)


class TagHygieneWorker(QThread):
    """Worker d'arrière-plan analysant la collection sans bloquer le thread principal."""

    analysis_finished = Signal(object)
    analysis_error = Signal(str)

    def __init__(
        self,
        note_ids: list[int] | None = None,
        deck_id: int | None = None,
        include_levenshtein: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.note_ids = note_ids
        self.deck_id = deck_id
        self.include_levenshtein = include_levenshtein

    def run(self) -> None:
        try:
            report = BulkHygieneService.analyze_tag_clusters(
                note_ids=self.note_ids,
                deck_id=self.deck_id,
                include_levenshtein=self.include_levenshtein,
            )
            self.analysis_finished.emit(report)
        except Exception as e:
            logger.exception("Erreur analyse tag hygiene: %s", e)
            self.analysis_error.emit(str(e))


class TagHygieneDialog(QDialog):
    """Boîte de dialogue modale d'analyse et de fusion des grappes de tags."""

    def __init__(
        self,
        selected_note_ids: list[int] | None = None,
        initial_deck_id: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.selected_note_ids = list(selected_note_ids) if selected_note_ids else None
        self.selected_deck_id: int | None = initial_deck_id if (initial_deck_id is not None and initial_deck_id != -1) else None
        self.selected_deck_name: str | None = None
        if self.selected_deck_id is not None:
            deck = DeckModel.get_or_none(DeckModel.id == self.selected_deck_id)
            if deck:
                self.selected_deck_name = deck.name

        self.report: TagClustersReport | None = None
        self.cards: list[TagClusterCard] = []
        self.applied_result: TagMergeResult | None = None
        self._current_filter_type: str = "all"  # "all", "case", "levenshtein"
        self._deck_modal: DeckSelectWindow | None = None

        self.setWindowTitle(tr("Hygiène et fusion des tags"))
        self.resize(780, 620)
        self.setMinimumSize(660, 480)
        self.setStyleSheet(f"QDialog {{ background-color: {DesignTokens.BG_PANEL}; }}")

        self._init_ui()
        self._start_analysis()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 1. En-tête
        header_card = QFrame(self)
        header_card.setObjectName("tagHygieneHeaderCard")
        header_card.setStyleSheet(f"""
            QFrame#tagHygieneHeaderCard {{
                background-color: {DesignTokens.BG_SIDEBAR};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#tagHygieneHeaderCard QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(12, 10, 12, 10)
        h_layout.setSpacing(12)

        icon_lbl = QLabel(header_card)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        icon_lbl.setPixmap(load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        h_layout.addWidget(icon_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        title_lbl = QLabel(tr("Hygiène et fusion des tags"), header_card)
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        info_layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            tr("Détection automatique des doublons de casse et variantes proches. Vous pouvez fusionner une sélection partielle : les grappes non sélectionnées restent intactes pour plus tard."),
            header_card,
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        info_layout.addWidget(desc_lbl)
        h_layout.addLayout(info_layout)
        h_layout.addStretch()

        layout.addWidget(header_card)

        # 2. Barre d'outils et filtres
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)

        # Sélecteur de portée
        self.scope_combo = QComboBox(self)
        self.scope_combo.addItem(tr("Toute la collection"), "all")
        if self.selected_note_ids:
            self.scope_combo.addItem(tr("Sélection active (%1 cartes)", len(self.selected_note_ids)), "selection")

        if self.selected_deck_name:
            self.scope_combo.addItem(tr("Paquet : %1", self.selected_deck_name), "deck")
        else:
            self.scope_combo.addItem(tr("Par paquet..."), "deck")

        if self.selected_note_ids:
            self.scope_combo.setCurrentIndex(1)
        elif self.selected_deck_id:
            deck_idx = self.scope_combo.findData("deck")
            if deck_idx >= 0:
                self.scope_combo.setCurrentIndex(deck_idx)
        else:
            self.scope_combo.setCurrentIndex(0)

        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        toolbar.addWidget(self.scope_combo)

        # Bouton d'accès rapide au sélecteur de paquet
        self.btn_select_deck = QPushButton(tr("Changer..."), self)
        self.btn_select_deck.setIcon(load_phosphor_icon("folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_select_deck.setToolTip(tr("Choisir un paquet via l'arborescence"))
        self.btn_select_deck.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 3px 8px;
                font-size: 11px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_select_deck.clicked.connect(self._open_deck_select_modal)
        self.btn_select_deck.setVisible(self.scope_combo.currentData() == "deck")
        toolbar.addWidget(self.btn_select_deck)

        # Séparateur vertical
        sep = QFrame(self)
        sep.setFixedSize(1, 18)
        sep.setStyleSheet(f"background-color: {DesignTokens.BORDER_COLOR}; border: none;")
        toolbar.addWidget(sep)

        # Pilules de filtrage
        self.btn_filter_all = QPushButton(tr("Toutes"), self)
        self.btn_filter_all.setCheckable(True)
        self.btn_filter_all.setChecked(True)
        self.btn_filter_all.clicked.connect(lambda: self._set_filter_type("all"))
        toolbar.addWidget(self.btn_filter_all)

        self.btn_filter_case = QPushButton(tr("Casse"), self)
        self.btn_filter_case.setCheckable(True)
        self.btn_filter_case.clicked.connect(lambda: self._set_filter_type("case"))
        toolbar.addWidget(self.btn_filter_case)

        self.btn_filter_lev = QPushButton(tr("Similarité"), self)
        self.btn_filter_lev.setCheckable(True)
        self.btn_filter_lev.clicked.connect(lambda: self._set_filter_type("levenshtein"))
        toolbar.addWidget(self.btn_filter_lev)

        for btn in (self.btn_filter_all, self.btn_filter_case, self.btn_filter_lev):
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 12px;
                    padding: 3px 10px;
                    font-size: 11px;
                    color: {DesignTokens.TEXT_SECONDARY};
                }}
                QPushButton:checked {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_ON_ACCENT};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    font-weight: bold;
                }}
            """)

        toolbar.addStretch()

        # Recherche textuelle rapide
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText(tr("Filtrer par tag..."))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(160)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 3px 8px;
                font-size: 11px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_input)

        # Actions globales Cocher / Décocher
        self.btn_toggle_all = ActionButton(tr("Tout décocher"), parent=self)
        self.btn_toggle_all.clicked.connect(self._toggle_all_selection)
        toolbar.addWidget(self.btn_toggle_all)

        layout.addLayout(toolbar)

        # 3. Zone de défilement des cartes
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("tagScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea#tagScrollArea {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: {DesignTokens.BG_SIDEBAR};
            }}
        """)
        self.scroll_area.viewport().setStyleSheet("background: transparent; border: none;")

        self.cards_container = QWidget()
        self.cards_container.setObjectName("cardsContainer")
        self.cards_container.setStyleSheet("background: transparent; border: none;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(10, 10, 10, 10)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()

        self.scroll_area.setWidget(self.cards_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # 4. Pied de page (Résumé + Boutons)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(12)

        self.status_lbl = QLabel(tr("Chargement de l'analyse..."), self)
        self.status_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        footer.addWidget(self.status_lbl)

        footer.addStretch()

        self.btn_cancel = ActionButton(tr("Annuler"), parent=self)
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        self.btn_apply = PrimaryButton(tr("Appliquer la fusion"), parent=self)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setToolTip(tr("Applique la fusion uniquement sur les grappes cochées. Les autres grappes restent intactes."))
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        footer.addWidget(self.btn_apply)

        layout.addLayout(footer)

    def _start_analysis(self) -> None:
        """Déclenche l'analyse en arrière-plan."""
        self.status_lbl.setText(tr("Analyse taxonomique des tags en cours..."))
        self.btn_apply.setEnabled(False)

        # Nettoyage des anciennes cartes
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()

        # Détermination du périmètre
        scope_data = self.scope_combo.currentData()
        target_ids: list[int] | None = None
        target_deck_id: int | None = None

        if scope_data == "selection":
            target_ids = self.selected_note_ids
        elif scope_data == "deck":
            target_deck_id = self.selected_deck_id

        self.worker = TagHygieneWorker(
            note_ids=target_ids,
            deck_id=target_deck_id,
            include_levenshtein=True,
            parent=self,
        )
        self.worker.analysis_finished.connect(self._on_analysis_finished)
        self.worker.analysis_error.connect(self._on_analysis_error)
        self.worker.start()

    @Slot(object)
    def _on_analysis_finished(self, report: TagClustersReport) -> None:
        self.report = report

        # Vider le conteneur
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        all_clusters = report.case_clusters + report.levenshtein_clusters
        self.cards.clear()

        if not all_clusters:
            empty_lbl = QLabel(tr("Aucun doublon ni variante proche détectée."), self.cards_container)
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED}; padding: 40px;")
            self.cards_layout.insertWidget(0, empty_lbl)
            self.status_lbl.setText(tr("0 grappe détectée sur %1 notes analysées.", report.inspected_notes_count))
            self.btn_apply.setEnabled(False)
            return

        for cluster in all_clusters:
            card = TagClusterCard(cluster, self.cards_container)
            card.changed.connect(self._on_cards_updated)
            card.ignored.connect(self._on_card_ignored)
            self.cards.append(card)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

        self._apply_display_filters()
        self._on_cards_updated()

    @Slot(str)
    def _on_analysis_error(self, err_msg: str) -> None:
        self.status_lbl.setText(tr("Erreur d'analyse : %1", err_msg))
        QMessageBox.warning(self, tr("Erreur"), tr("Impossible d'analyser les tags : %1", err_msg))

    @Slot()
    def _open_deck_select_modal(self) -> None:
        """Ouvre le dialogue modal de sélection de paquet (DeckSelectWindow)."""
        try:
            if self._deck_modal and self._deck_modal.isVisible():
                self._deck_modal.raise_()
                self._deck_modal.activateWindow()
                return
        except RuntimeError:
            self._deck_modal = None

        self._deck_modal = DeckSelectWindow(
            title=tr("Sélectionner un paquet pour l'hygiène des tags"),
            allow_all=True,
            selected_deck_id=self.selected_deck_id,
            parent=self,
        )
        self._deck_modal.deck_selected.connect(self._on_deck_selected_from_modal)
        self._deck_modal.destroyed.connect(self._on_deck_modal_closed)
        self._deck_modal.show()
        self._deck_modal.raise_()
        self._deck_modal.activateWindow()

    @Slot(int, str)
    def _on_deck_selected_from_modal(self, deck_id: int, deck_name: str) -> None:
        """Traite la sélection d'un paquet depuis DeckSelectWindow."""
        if deck_id == ALL_DECKS_NODE_ID or deck_id == -1:
            self.selected_deck_id = None
            self.selected_deck_name = None
            deck_idx = self.scope_combo.findData("deck")
            if deck_idx >= 0:
                self.scope_combo.setItemText(deck_idx, tr("Par paquet..."))
            all_idx = self.scope_combo.findData("all")
            if all_idx >= 0:
                self.scope_combo.setCurrentIndex(all_idx)
        else:
            self.selected_deck_id = deck_id
            self.selected_deck_name = deck_name
            deck_idx = self.scope_combo.findData("deck")
            if deck_idx >= 0:
                self.scope_combo.setItemText(deck_idx, tr("Paquet : %1", deck_name))
                self.scope_combo.setCurrentIndex(deck_idx)
            self.btn_select_deck.setVisible(True)
            self._start_analysis()

    def _on_deck_modal_closed(self) -> None:
        """Si la modale a été fermée sans valider et qu'aucun paquet n'était actif, repli sur toute la collection."""
        if self.selected_deck_id is None and self.scope_combo.currentData() == "deck":
            all_idx = self.scope_combo.findData("all")
            if all_idx >= 0:
                self.scope_combo.setCurrentIndex(all_idx)

    @Slot()
    def _on_scope_changed(self) -> None:
        is_deck = self.scope_combo.currentData() == "deck"
        self.btn_select_deck.setVisible(is_deck)
        if is_deck and self.selected_deck_id is None:
            self._open_deck_select_modal()
            return
        self._start_analysis()

    def _set_filter_type(self, filter_type: str) -> None:
        self._current_filter_type = filter_type
        self.btn_filter_all.setChecked(filter_type == "all")
        self.btn_filter_case.setChecked(filter_type == "case")
        self.btn_filter_lev.setChecked(filter_type == "levenshtein")
        self._apply_display_filters()

    @Slot(str)
    def _on_search_changed(self, _text: str) -> None:
        self._apply_display_filters()

    def _apply_display_filters(self) -> None:
        """Applique les filtres de type et de recherche sur les cartes."""
        q = self.search_input.text()
        for card in self.cards:
            type_match = (
                self._current_filter_type == "all"
                or (self._current_filter_type == "case" and card.cluster.cluster_type == "case")
                or (self._current_filter_type == "levenshtein" and card.cluster.cluster_type == "levenshtein")
            )
            text_match = card.matches_query(q)
            card.setVisible(type_match and text_match)

    @Slot(str)
    def _on_card_ignored(self, cluster_id: str) -> None:
        card = next((c for c in self.cards if c.cluster.cluster_id == cluster_id), None)
        if card:
            card.setVisible(False)
            self.cards.remove(card)
            card.deleteLater()
            self._on_cards_updated()

    @Slot()
    def _toggle_all_selection(self) -> None:
        visible_cards = [c for c in self.cards if c.isVisible()]
        all_checked = all(c.cluster_cb.isChecked() for c in visible_cards)
        new_state = not all_checked

        for card in visible_cards:
            card.cluster_cb.setChecked(new_state)

        self.btn_toggle_all.setText(tr("Tout cocher") if new_state is False else tr("Tout décocher"))
        self._on_cards_updated()

    @Slot()
    def _on_cards_updated(self) -> None:
        """Recalcule les statistiques actives et active/désactive le bouton d'application."""
        included_cards = [c for c in self.cards if c.is_included()]
        total_merges = len(included_cards)
        total_cards = len(self.cards)

        notes_count = sum(c.cluster.total_notes_count for c in included_cards)

        if 0 < total_merges < total_cards:
            self.status_lbl.setText(
                tr(
                    "%1 grappe(s) sélectionnée(s) sur %2 · ~%3 notes concernées (les non sélectionnées restent intactes pour plus tard)",
                    total_merges,
                    total_cards,
                    notes_count,
                )
            )
        else:
            self.status_lbl.setText(
                tr(
                    "%1 grappe(s) sélectionnée(s) sur %2 · ~%3 notes concernées",
                    total_merges,
                    total_cards,
                    notes_count,
                )
            )
        self.btn_apply.setEnabled(total_merges > 0)

    @Slot()
    def _on_apply_clicked(self) -> None:
        plans: list[TagMergePlan] = []
        for card in self.cards:
            if card.is_included():
                plan = card.get_merge_plan()
                if plan:
                    plans.append(plan)

        if not plans:
            return

        scope_data = self.scope_combo.currentData()
        target_ids = self.selected_note_ids if scope_data == "selection" else None
        target_deck_id = self.selected_deck_id if scope_data == "deck" else None

        res = BulkHygieneService.apply_tag_merges(
            merges=plans,
            note_ids=target_ids,
            deck_id=target_deck_id,
        )
        if res.success:
            self.applied_result = res
            self.accept()
        else:
            QMessageBox.critical(
                self,
                tr("Erreur de fusion"),
                tr("La fusion a échoué : %1", res.error_message or tr("Erreur inconnue")),
            )
