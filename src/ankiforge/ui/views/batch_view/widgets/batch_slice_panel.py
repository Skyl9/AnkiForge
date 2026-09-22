"""
Batch Slice Panel — Volet de composition de la file d'attente via 3 modes.

Contrôle segmenté des trois stratégies d'alimentation du Batch :
  - Mode Manuel (1 par 1)      : sélecteur de tranche + bouton « Ajouter la tranche ».
  - Découpage Auto (1-clic)    : déclenche AutoSliceConfigDialog (géré par BatchView).
  - Assistant Wizard           : déclenche BatchSlicingWizardDialog (géré par BatchView).

Le panneau émet des signaux vers BatchView qui détient le contexte applicatif
(documents, paquets, modèles, moteurs, pipelines) et l'append dans la queue.

Qt equivalent: QWidget (QVBoxLayout avec contrôle segmenté) — carte du panneau de build
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel
from ankiforge.services.batch.slicing_service import SliceUnit, SlicingService
from ankiforge.ui.components import SecondaryButton, StyledComboBox
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class BatchSlicePanel(QWidget):
    """
    Contrôle segmenté des 3 modes de composition de la file d'attente.

    Signaux émis :
      - auto_slice_requested()  → BatchView ouvre AutoSliceConfigDialog
      - wizard_requested()      → BatchView ouvre BatchSlicingWizardDialog
      - slices_ready(list)      → tâches prêtes à entrer dans la file d'attente

    Qt equivalent: QWidget (QVBoxLayout)
    """

    auto_slice_requested = Signal()
    wizard_requested = Signal()
    slices_ready = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("batchSlicePanel")

        self._doc: DocumentModel | None = None
        self._slices: list[SliceUnit] = []
        self._defaults_provider: Callable[[], dict[str, Any]] | None = None

        self._setup_ui()
        self._update_mode_specific_state()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.scissors", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        ico.setStyleSheet("border: none; background: transparent;")
        lbl_header = QLabel("COMPOSITION DE LA FILE (3 MODES)")
        lbl_header.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        header.addWidget(ico)
        header.addWidget(lbl_header)
        header.addStretch()
        main_layout.addLayout(header)

        # ── Contrôle segmenté des 3 modes ─────────────────────────────
        self.mode_group = QButtonGroup(self)

        self.rb_manual = QRadioButton("1 par 1")
        self.rb_auto = QRadioButton("Découpage Auto")
        self.rb_wizard = QRadioButton("Assistant Wizard")
        self.rb_manual.setChecked(True)

        for btn in (self.rb_manual, self.rb_auto, self.rb_wizard):
            btn.setStyleSheet(
                f"""
                QRadioButton {{
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-size: 10px;
                    font-weight: bold;
                    padding: 4px 10px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    background: {DesignTokens.BG_INPUT};
                }}
                QRadioButton::indicator {{
                    width: 0px;
                    height: 0px;
                }}
                QRadioButton:checked {{
                    color: {DesignTokens.TEXT_ON_ACCENT};
                    background: {DesignTokens.ACCENT_PRIMARY};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
                """
            )
            self.mode_group.addButton(btn)
            btn.toggled.connect(self._on_mode_changed)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        mode_row.addWidget(self.rb_manual, 1)
        mode_row.addWidget(self.rb_auto, 1)
        mode_row.addWidget(self.rb_wizard, 1)
        main_layout.addLayout(mode_row)

        # ── Stack des panneaux spécifiques ────────────────────────────
        self.stack = QStackedWidget()

        # Mode Manuel : sélecteur de tranche
        manual_widget = QWidget()
        manual_layout = QVBoxLayout(manual_widget)
        manual_layout.setContentsMargins(0, 6, 0, 0)
        manual_layout.setSpacing(6)

        self.lbl_manual_hint = QLabel("Sélectionnez une tranche du document à ajouter unitairement.")
        self.lbl_manual_hint.setWordWrap(True)
        self.lbl_manual_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        manual_layout.addWidget(self.lbl_manual_hint)

        self.slice_combo = StyledComboBox()
        self.slice_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        manual_layout.addWidget(self.slice_combo)

        self.btn_add_slice = SecondaryButton("Ajouter la tranche (1 par 1)")
        self.btn_add_slice.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_slice.clicked.connect(self._on_manual_add)
        manual_layout.addWidget(self.btn_add_slice)
        self.stack.addWidget(manual_widget)

        # Mode Auto : découpage par règle
        auto_widget = QWidget()
        auto_layout = QVBoxLayout(auto_widget)
        auto_layout.setContentsMargins(0, 6, 0, 0)
        auto_layout.setSpacing(6)

        self.lbl_auto_hint = QLabel("Partitionne automatiquement le document selon des règles paramétrables (titres H1/H2, blocs de tokens, tranches de pages).")
        self.lbl_auto_hint.setWordWrap(True)
        self.lbl_auto_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        auto_layout.addWidget(self.lbl_auto_hint)

        self.btn_open_auto = SecondaryButton("Configurer le Découpage Auto...")
        self.btn_open_auto.setIcon(load_on_accent_icon("ph.funnel"))
        self.btn_open_auto.clicked.connect(self.auto_slice_requested.emit)
        auto_layout.addWidget(self.btn_open_auto)
        self.stack.addWidget(auto_widget)

        # Mode Wizard : assistant interactif
        wizard_widget = QWidget()
        wizard_layout = QVBoxLayout(wizard_widget)
        wizard_layout.setContentsMargins(0, 6, 0, 0)
        wizard_layout.setSpacing(6)

        self.lbl_wizard_hint = QLabel("Parcourez l'arborescence du document, cochez/décochez les sections utiles (préfaces, annexes, bibliographie) puis générez les tâches groupées.")
        self.lbl_wizard_hint.setWordWrap(True)
        self.lbl_wizard_hint.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; background: transparent; border: none;")
        wizard_layout.addWidget(self.lbl_wizard_hint)

        self.btn_open_wizard = SecondaryButton("Ouvrir l'Assistant de Découpage...")
        self.btn_open_wizard.setIcon(load_on_accent_icon("ph.magic-wand"))
        self.btn_open_wizard.clicked.connect(self.wizard_requested.emit)
        wizard_layout.addWidget(self.btn_open_wizard)
        self.stack.addWidget(wizard_widget)

        main_layout.addWidget(self.stack)

    # ── API publique ────────────────────────────────────────────────────

    def set_document(self, doc: DocumentModel | None) -> None:
        """Met à jour le document source actif et rafraîchit la liste des tranches."""
        self._doc = doc
        self._refresh_slices()
        self._update_mode_specific_state()

    def set_defaults_provider(self, provider: Callable[[], dict[str, Any]]) -> None:
        """Fournit les cibles par défaut (paquet, modèle, moteur, pipeline, toggles)."""
        self._defaults_provider = provider

    def _refresh_slices(self) -> None:
        self.slice_combo.blockSignals(True)
        self.slice_combo.clear()
        self._slices = []
        if self._doc is None:
            self.slice_combo.addItem("Aucun document sélectionné", None)
            self.slice_combo.blockSignals(False)
            return
        content = getattr(self._doc, "content", "") or ""
        try:
            slices = SlicingService.slice_by_headings(content, max_depth=2, min_words=20) or [
                SliceUnit(
                    index=0,
                    title="Document Complet",
                    heading_path="Document Complet",
                    content=content,
                    tokens_estimate=SlicingService.estimate_tokens(content),
                    words_estimate=SlicingService.estimate_words(content),
                )
            ]
        except Exception as err:  # pragma: no cover - défensif
            logger.warning("Découpage de prévisualisation impossible : %s", err)
            slices = [
                SliceUnit(
                    index=0,
                    title="Document Complet",
                    heading_path="Document Complet",
                    content=content,
                    tokens_estimate=SlicingService.estimate_tokens(content),
                    words_estimate=SlicingService.estimate_words(content),
                )
            ]
        self._slices = slices
        for s in slices:
            label = s.title
            if s.page_number is not None:
                label = f"{label} (p.{s.page_number})"
            self.slice_combo.addItem(f"{label} — ~{s.tokens_estimate} tk", s)
        self.slice_combo.blockSignals(False)

    def _update_mode_specific_state(self) -> None:
        has_doc = self._doc is not None
        self.btn_add_slice.setEnabled(has_doc and bool(self._slices))
        self.btn_open_auto.setEnabled(has_doc)
        self.btn_open_wizard.setEnabled(has_doc)

    # ── Slots ───────────────────────────────────────────────────────────

    @Slot()
    def _on_mode_changed(self) -> None:
        if self.rb_manual.isChecked():
            self.stack.setCurrentIndex(0)
        elif self.rb_auto.isChecked():
            self.stack.setCurrentIndex(1)
        elif self.rb_wizard.isChecked():
            self.stack.setCurrentIndex(2)

    @Slot()
    def _on_manual_add(self) -> None:
        if self._doc is None:
            return
        selected = self.slice_combo.currentData()
        if not isinstance(selected, SliceUnit):
            return
        task = self._build_task(selected)
        if task:
            self.slices_ready.emit([task])

    # ── Construction de tâche ───────────────────────────────────────────

    def _build_task(self, s: SliceUnit) -> dict[str, Any] | None:
        if self._doc is None:
            return None
        defaults = self._defaults_provider() if self._defaults_provider else {}
        deck = defaults.get("deck")
        model = defaults.get("model")
        engine = defaults.get("engine")
        pipeline = defaults.get("pipeline")

        return {
            "doc": self._doc,
            "doc_title": f"{self._doc.title} — {s.title}",
            "doc_content": s.content,
            "source_chunks": [s.as_dict()],
            "chunk_label": s.title,
            "chunk_index": s.index,
            "tokens_est": s.tokens_estimate,
            "deck": deck,
            "deck_name": str(getattr(deck, "name", "Général")),
            "note_type": model,
            "model_name": str(getattr(model, "name", "Basique")),
            "engine": engine,
            "pipeline": pipeline,
            "pipeline_name": str(getattr(pipeline, "name", "Standard")),
            "use_vision": bool(defaults.get("use_vision", False)),
            "auto_val": bool(defaults.get("auto_val", True)),
            "temperature": float(defaults.get("temperature", 0.7)),
            "max_tokens": int(defaults.get("max_tokens", 16384)),
            "status": "En attente",
            "progress_pct": 0,
            "cards_count": 0,
            "pending_cards": [],
        }
