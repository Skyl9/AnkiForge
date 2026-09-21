"""
Inspecteur de segments et de portée documentaire interactif (SegmentInspectorWidget).
Fusionne la définition de la portée (presets, plages personnalisées, steppers) et le découpage
en segments avec sélection granulaire (cocher / décocher des fragments) avant la génération
dans CreationView et BatchView.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentChunkModel, DocumentModel
from ankiforge.services.ai.context_compactor import ContextCompactor
from ankiforge.services.parsing.chunking_service import ChunkingService
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import IconButton, SecondaryButton
from ankiforge.ui.components.inputs import StyledComboBox, StyledLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.chunker import smart_chunk_text
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)


def _safe_int(val: Any, default: int = 1) -> int:
    """Convertit une valeur en entier de manière sécurisée en ignorant les MagicMocks."""
    if val is None:
        return default
    if hasattr(val, "_mock_name") or hasattr(val, "_mock_return_value") or type(val).__name__ in ("MagicMock", "Mock"):
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


class SegmentItemWidget(QWidget):
    """Carte graphique représentant un fragment documentaire individuel dans la liste avec case à cocher."""

    toggled = Signal(bool)

    def __init__(
        self,
        index: int,
        title: str,
        content: str,
        token_count: int,
        is_checked: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.index = index
        self.raw_content = content
        self._is_checked = is_checked

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Ligne d'en-tête (Checkbox + Numéro + Titre + Badge Tokens)
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        check_icon_path = str(get_resource_path("src", "ressources", "icons", "check_white.svg")).replace("\\", "/")
        self.checkbox = QCheckBox(self)
        self.checkbox.setChecked(is_checked)
        self.checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.checkbox.setToolTip("Inclure ou exclure ce fragment de la génération")
        self.checkbox.setStyleSheet(f"""
            QCheckBox {{
                spacing: 0px;
                background: transparent;
                border: none;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid {DesignTokens.TEXT_MUTED};
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                image: url({check_icon_path});
            }}
        """)
        self.checkbox.toggled.connect(self._on_checkbox_toggled)
        header_layout.addWidget(self.checkbox)

        idx_badge = QLabel(f"#{index + 1}")
        idx_badge.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY}; background: {DesignTokens.ACCENT_BG}; border-radius: 3px; padding: 1px 4px;")
        header_layout.addWidget(idx_badge)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY};")
        header_layout.addWidget(self.title_lbl, 1)

        token_col = DesignTokens.COLOR_GREEN if token_count < 2500 else (DesignTokens.COLOR_YELLOW if token_count < 5000 else DesignTokens.COLOR_RED)
        token_badge = QLabel(f"~{token_count:,} tok.")
        token_badge.setStyleSheet(f"font-size: 10px; color: {token_col}; font-family: '{DesignTokens.FONT_CODE}';")
        header_layout.addWidget(token_badge)

        layout.addLayout(header_layout)

        # Extrait textuel (2 lignes max nettoyées)
        preview_text = content.strip().replace("\n", " ")
        if len(preview_text) > 110:
            preview_text = preview_text[:107] + "..."

        self.preview_lbl = QLabel(preview_text or "Fragment sans texte visible")
        self.preview_lbl.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED};")
        self.preview_lbl.setWordWrap(True)
        layout.addWidget(self.preview_lbl)

        self._update_appearance(is_checked)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        self._is_checked = checked
        self._update_appearance(checked)
        self.toggled.emit(checked)

    def _update_appearance(self, checked: bool) -> None:
        if checked:
            self.title_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY};")
            self.preview_lbl.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED};")
        else:
            self.title_lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {DesignTokens.TEXT_MUTED}; text-decoration: line-through;")
            self.preview_lbl.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; opacity: 0.5;")

    def set_checked(self, checked: bool) -> None:
        if self.checkbox.isChecked() != checked:
            self.checkbox.blockSignals(True)
            self.checkbox.setChecked(checked)
            self.checkbox.blockSignals(False)
            self._is_checked = checked
            self._update_appearance(checked)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Clic sur la carte (hors checkbox) bascule la case à cocher
        if event.button() == Qt.MouseButton.LeftButton:
            chk_rect = self.checkbox.geometry()
            if not chk_rect.contains(event.pos()):
                self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)


class SegmentInspectorWidget(QFrame):
    """
    Inspecteur visuel interactif fusionnant la portée documentaire (presets, plages)
    et le découpage en segments granulaires sélectionnables pour la génération de cartes.
    """

    segments_updated = Signal(int, int)  # (active_count, total_count)
    segment_selected = Signal(int, str)  # (chunk_index, chunk_content)
    open_delimitation_requested = Signal()
    open_scope_dialog_requested = Signal()
    scope_changed = Signal(str)  # émis quand la saisie de portée change

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._doc: DocumentModel | None = None
        self._fallback_text: str = ""
        self._chunks: list[dict[str, Any]] = []
        self._last_scope_result: dict[str, Any] | None = None

        self._current_doc_total_units: int = 1
        self._current_doc_start_unit: int = 1
        self._current_doc_end_unit: int = 1
        self._current_doc_unit_singular: str = "page"
        self._current_doc_unit_plural: str = "pages"
        self._current_doc_unit_abbrev: str = "p"

        self.setObjectName("segmentInspectorWidget")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 1. En-tête : Titre, bouton délimiter (pas de badge de page)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        self.scope_ico = QLabel()
        self.scope_ico.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        self.scope_ico.setStyleSheet("border: none; background: transparent;")
        top_row.addWidget(self.scope_ico)

        self.lbl_scope = QLabel("PORTÉE DU DOCUMENT")
        self.lbl_scope.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 700; font-size: 11px; letter-spacing: 0.5px; border: none; background: transparent;")
        top_row.addWidget(self.lbl_scope)

        self.scope_badge = Badge("1 page", variant="neutral")
        self.scope_badge.hide()

        top_row.addStretch()

        self.btn_delimit = SecondaryButton("Délimiter...")
        self.btn_delimit.setFixedHeight(22)
        self.btn_delimit.setIcon(load_phosphor_icon("ph.crop", color=DesignTokens.TEXT_MUTED))
        self.btn_delimit.setToolTip("Ouvrir l'outil de délimitation visuelle du document")
        self.btn_delimit.setStyleSheet(f"font-size: 10px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_delimit.clicked.connect(self.open_delimitation_requested.emit)
        top_row.addWidget(self.btn_delimit)

        layout.addLayout(top_row)

        # 2. Section Portée — Carte résumée avec déclencheur de la modale visuelle
        self.scope_container = QWidget()
        scope_layout = QVBoxLayout(self.scope_container)
        scope_layout.setContentsMargins(0, 0, 0, 0)
        scope_layout.setSpacing(6)

        # Carte interactive ouvrant la modale de délimitation visuelle
        self.scope_trigger_card = QFrame()
        self.scope_trigger_card.setCursor(Qt.CursorShape.PointingHandCursor)
        self.scope_trigger_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QFrame:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        card_layout = QHBoxLayout(self.scope_trigger_card)
        card_layout.setContentsMargins(8, 6, 8, 6)
        card_layout.setSpacing(8)

        self.scope_card_icon = QLabel()
        self.scope_card_icon.setPixmap(load_phosphor_icon("ph.crop", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        self.scope_card_icon.setStyleSheet("border: none; background: transparent;")
        card_layout.addWidget(self.scope_card_icon)

        scope_text_col = QVBoxLayout()
        scope_text_col.setContentsMargins(0, 0, 0, 0)
        scope_text_col.setSpacing(2)

        self.lbl_active_scope_title = QLabel("Portée : Tout le document")
        self.lbl_active_scope_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        scope_text_col.addWidget(self.lbl_active_scope_title)

        self.lbl_scope_stats = QLabel("~1 200 mots • ~6 cartes estimées")
        self.lbl_scope_stats.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        scope_text_col.addWidget(self.lbl_scope_stats)
        card_layout.addLayout(scope_text_col, 1)

        self.btn_open_scope_modal = SecondaryButton("Modifier ↗")
        self.btn_open_scope_modal.setFixedHeight(24)
        self.btn_open_scope_modal.setStyleSheet(f"font-size: 10px; padding: 2px 8px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_open_scope_modal.clicked.connect(self.open_scope_dialog_requested.emit)
        card_layout.addWidget(self.btn_open_scope_modal)

        scope_layout.addWidget(self.scope_trigger_card)

        # Conteneur des anciens contrôles inline (masqués mais conservés pour rétro-compatibilité stricte)
        self.legacy_scope_controls = QWidget()
        legacy_layout = QVBoxLayout(self.legacy_scope_controls)
        legacy_layout.setContentsMargins(0, 0, 0, 0)

        preset_row = QHBoxLayout()
        self.btn_preset_all = QPushButton("Tout le doc")
        self.btn_preset_all.clicked.connect(self._on_preset_all)
        self.btn_preset_page = QPushButton("Page 1")
        self.btn_preset_page.clicked.connect(self._on_preset_single_page)
        self.btn_preset_range = QPushButton("1 – 10")
        self.btn_preset_range.clicked.connect(self._on_preset_range)
        preset_row.addWidget(self.btn_preset_all)
        preset_row.addWidget(self.btn_preset_page)
        preset_row.addWidget(self.btn_preset_range)
        legacy_layout.addLayout(preset_row)

        self.range_input_frame = QFrame()
        input_layout = QHBoxLayout(self.range_input_frame)
        self.input_page_scope = StyledLineEdit()
        self.input_page_scope.setText("1-10")
        self.input_page_scope.textChanged.connect(self._on_scope_text_changed)
        self.input_page_range = self.input_page_scope
        self.btn_scope_minus = IconButton("ph.minus", "Réduire", 16)
        self.btn_scope_minus.clicked.connect(self._on_scope_step_minus)
        self.btn_scope_plus = IconButton("ph.plus", "Élargir", 16)
        self.btn_scope_plus.clicked.connect(self._on_scope_step_plus)
        input_layout.addWidget(self.input_page_scope)
        input_layout.addWidget(self.btn_scope_minus)
        input_layout.addWidget(self.btn_scope_plus)
        legacy_layout.addWidget(self.range_input_frame)

        self.spin_page_start = QSpinBox(self)
        self.spin_page_end = QSpinBox(self)
        self.spin_page_start.setValue(1)
        self.spin_page_end.setValue(10)
        legacy_layout.addWidget(self.spin_page_start)
        legacy_layout.addWidget(self.spin_page_end)

        self.legacy_scope_controls.hide()
        scope_layout.addWidget(self.legacy_scope_controls)

        layout.addWidget(self.scope_container)

        # 3. Contrôles de découpage et liste de segments (masqués de l'interface sidebar pour un affichage épuré)
        self.cutting_controls_container = QWidget()
        cutting_layout = QVBoxLayout(self.cutting_controls_container)
        cutting_layout.setContentsMargins(0, 0, 0, 0)
        cutting_layout.setSpacing(6)

        strat_layout = QHBoxLayout()
        strat_layout.setContentsMargins(0, 0, 0, 0)
        strat_layout.setSpacing(6)

        lbl_strat = QLabel("Découpage :")
        lbl_strat.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-weight: 600;")
        strat_layout.addWidget(lbl_strat)

        self.combo_strategy = StyledComboBox()
        self.combo_strategy.setFixedHeight(28)
        self.combo_strategy.currentIndexChanged.connect(self._on_strategy_changed)
        strat_layout.addWidget(self.combo_strategy, 1)
        cutting_layout.addLayout(strat_layout)

        # Curseur de tokens (visible si stratégie = tokens)
        self.token_slider_frame = QWidget()
        slider_layout = QHBoxLayout(self.token_slider_frame)
        slider_layout.setContentsMargins(0, 0, 0, 0)
        slider_layout.setSpacing(6)

        self.lbl_token_size = QLabel("1 500 tok.")
        self.lbl_token_size.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}';")

        self.token_slider = QSlider(Qt.Orientation.Horizontal)
        self.token_slider.setRange(500, 5000)
        self.token_slider.setSingleStep(250)
        self.token_slider.setValue(1500)
        self.token_slider.valueChanged.connect(self._on_slider_value_changed)
        self.token_slider.sliderReleased.connect(self.recompute_segments)

        slider_layout.addWidget(QLabel("Taille :"))
        slider_layout.addWidget(self.token_slider, 1)
        slider_layout.addWidget(self.lbl_token_size)
        self.token_slider_frame.setVisible(False)
        cutting_layout.addWidget(self.token_slider_frame)

        # 4. Liste des segments interactifs avec case à cocher
        self.segments_list = QListWidget()
        self.segments_list.setMinimumHeight(110)
        self.segments_list.setMaximumHeight(210)
        self.segments_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 2px;
            }}
            QListWidget::indicator {{
                width: 0px;
                height: 0px;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
            }}
        """)
        self.segments_list.itemClicked.connect(self._on_list_item_clicked)
        self.segments_list.itemChanged.connect(self._on_item_check_changed)
        cutting_layout.addWidget(self.segments_list)

        # 5. Barre inférieure d'actions rapides et métriques
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(6)

        self.btn_check_all = SecondaryButton("Tout cocher")
        self.btn_check_all.setFixedHeight(22)
        self.btn_check_all.setStyleSheet(f"font-size: 10px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_check_all.clicked.connect(lambda: self._set_all_checked(True))
        bottom_row.addWidget(self.btn_check_all)

        self.btn_uncheck_all = SecondaryButton("Tout décocher")
        self.btn_uncheck_all.setFixedHeight(22)
        self.btn_uncheck_all.setStyleSheet(f"font-size: 10px; padding: 2px 6px; border: 1px solid {DesignTokens.BORDER_COLOR};")
        self.btn_uncheck_all.clicked.connect(lambda: self._set_all_checked(False))
        bottom_row.addWidget(self.btn_uncheck_all)

        bottom_row.addStretch()

        self.lbl_summary = QLabel("0 segment")
        self.lbl_summary.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {DesignTokens.ACCENT_PRIMARY};")
        bottom_row.addWidget(self.lbl_summary)

        cutting_layout.addLayout(bottom_row)

        self.cutting_controls_container.hide()
        layout.addWidget(self.cutting_controls_container)

        self.setStyleSheet(f"""
            QFrame#segmentInspectorWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

    def set_document(self, doc: DocumentModel | None, fallback_text: str = "") -> None:
        """Définit le document source ou texte brut à inspecter et ajuste la portée."""
        if doc is not None and getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id)
            except Exception as err:
                logger.debug("Rechargement du document inspecteur ignoré : %s", err)
        if self._doc is None or doc is None or getattr(self._doc, "id", None) != getattr(doc, "id", None):
            self._last_scope_result = None
        self._doc = doc
        self._fallback_text = fallback_text

        if doc is not None:
            ft = (getattr(doc, "file_type", "") or "md").lower()
            max_chunk_p = 1
            if getattr(doc, "id", None):
                chunk_pages = [c.page_number for c in DocumentChunkModel.select(DocumentChunkModel.page_number).where(DocumentChunkModel.document == doc) if c.page_number is not None]
                if chunk_pages:
                    max_chunk_p = max(chunk_pages)
            tot = max(_safe_int(getattr(doc, "total_pages", None), default=1), max_chunk_p)
            sp = _safe_int(getattr(doc, "start_page", None), default=1)
            ep = _safe_int(getattr(doc, "end_page", None), default=tot)

            if ft == "pdf":
                self.configure_scope("PORTÉE DU DOCUMENT", tot, sp, ep, "page", "pages", "p")
            elif ft == "album":
                self.configure_scope("PORTÉE DE L'ALBUM", tot, sp, ep, "planche", "planches", "pl")
            elif ft == "pptx":
                self.configure_scope("PORTÉE DU DIAPORAMA", tot, sp, ep, "diapositive", "diapos", "d")
            elif ft == "epub":
                self.configure_scope("PORTÉE DU LIVRE", tot, sp, ep, "chapitre", "chapitres", "c")
            elif ft in ("audio", "mp3", "m4a", "wav", "youtube", "video"):
                self.configure_scope("PORTÉE AUDIO", tot, sp, ep, "segment", "segments", "seg")
            else:
                self.configure_scope("PORTÉE DU CONTENU", tot, sp, ep, "section", "sections", "sec")
        else:
            self.scope_container.setVisible(False)
            self.lbl_scope.setText("DÉCOUPAGE & SEGMENTS")

        self._populate_strategies()
        self.recompute_segments()

    def configure_scope(
        self,
        scope_title: str,
        total_units: int,
        start_unit: int = 1,
        end_unit: int | None = None,
        unit_singular: str = "page",
        unit_plural: str = "pages",
        unit_abbrev: str = "p",
    ) -> None:
        """Configure les libellés, presets et limites de la section de portée."""
        total_u = _safe_int(total_units, default=1)
        start_u = _safe_int(start_unit, default=1)
        end_u = _safe_int(end_unit, default=total_u) if end_unit is not None else total_u

        self._current_doc_total_units = total_u
        self._current_doc_start_unit = start_u
        self._current_doc_end_unit = end_u
        self._current_doc_unit_singular = unit_singular
        self._current_doc_unit_plural = unit_plural
        self._current_doc_unit_abbrev = unit_abbrev

        self.lbl_scope.setText(scope_title)
        self.scope_container.setVisible(True)

        useful_count = end_u - start_u + 1
        if start_u > 1 or end_u < total_u:
            self.btn_preset_all.setText(f"Utile ({useful_count}{unit_abbrev})")
            self.btn_preset_page.setText(f"{unit_singular.capitalize()} {start_u}")
            self.btn_preset_range.setText(f"{start_u} – {min(start_u + 9, end_u)}")
            self.input_page_scope.blockSignals(True)
            self.input_page_scope.setText(f"{start_u}-{min(start_u + 9, end_u)}")
            self.input_page_scope.blockSignals(False)
        else:
            self.btn_preset_all.setText(f"Tout ({total_u}{unit_abbrev})")
            self.btn_preset_page.setText(f"{unit_singular.capitalize()} 1")
            self.btn_preset_range.setText(f"1 – {min(10, total_u)}")
            self.input_page_scope.blockSignals(True)
            self.input_page_scope.setText(f"1-{min(10, total_u)}")
            self.input_page_scope.blockSignals(False)

        self._update_scope_stats_and_badge()
        self.scope_badge.hide()

    @Slot()
    def _on_preset_all(self) -> None:
        total = getattr(self, "_current_doc_total_units", 10) or 10
        start_u = getattr(self, "_current_doc_start_unit", 1) or 1
        end_u = getattr(self, "_current_doc_end_unit", total) or total
        self.input_page_scope.setText(f"{start_u}-{end_u}" if end_u > start_u else str(start_u))

    @Slot()
    def _on_preset_single_page(self) -> None:
        start_u = getattr(self, "_current_doc_start_unit", 1) or 1
        self.input_page_scope.setText(str(start_u))

    @Slot()
    def _on_preset_range(self) -> None:
        total = getattr(self, "_current_doc_total_units", 10) or 10
        start_u = getattr(self, "_current_doc_start_unit", 1) or 1
        self.input_page_scope.setText(f"{start_u}-{min(start_u + 9, total)}")

    @Slot()
    def _on_scope_step_minus(self) -> None:
        pages = self._parse_page_range(self.input_page_scope.text(), 9999)
        if len(pages) > 1:
            sorted_p = sorted(list(pages))
            new_end = sorted_p[-2]
            self.input_page_scope.setText(f"{sorted_p[0]}-{new_end}" if new_end > sorted_p[0] else str(sorted_p[0]))

    @Slot()
    def _on_scope_step_plus(self) -> None:
        pages = self._parse_page_range(self.input_page_scope.text(), 9999)
        if pages:
            sorted_p = sorted(list(pages))
            total = getattr(self, "_current_doc_total_units", 9999) or 9999
            new_end = min(total, sorted_p[-1] + 1)
            self.input_page_scope.setText(f"{sorted_p[0]}-{new_end}")

    def _on_scope_text_changed(self, text: str) -> None:
        self._update_scope_stats_and_badge()
        self.scope_changed.emit(text)
        self.recompute_segments()

    def _update_scope_stats_and_badge(self) -> None:
        total = getattr(self, "_current_doc_total_units", 9999) or 9999
        pages = self._parse_page_range(self.input_page_scope.text().strip(), total)
        unit_sg = getattr(self, "_current_doc_unit_singular", "page")
        unit_pl = getattr(self, "_current_doc_unit_plural", "pages")

        if not pages:
            self.scope_badge.setText(f"0 {unit_pl}")
            self.scope_badge.set_variant("danger")
            self.lbl_scope_stats.setText(f"Aucune sélection ({unit_pl})")
            if hasattr(self, "lbl_active_scope_title"):
                self.lbl_active_scope_title.setText(f"Aucune sélection ({unit_pl})")
            return

        count = len(pages)
        if count == 1:
            self.scope_badge.setText(f"1 {unit_sg}")
            self.scope_badge.set_variant("neutral")
        else:
            self.scope_badge.setText(f"{count} {unit_pl}")
            self.scope_badge.set_variant("success")

        approx_words = count * 280
        approx_cards = max(1, count * 2)
        self.lbl_scope_stats.setText(f"~{approx_words:,} mots • ~{approx_cards} cartes estimées".replace(",", " "))

        sorted_pages = sorted(list(pages))
        self.spin_page_start.setValue(sorted_pages[0])
        self.spin_page_end.setValue(sorted_pages[-1])

        if hasattr(self, "lbl_active_scope_title"):
            if count == total:
                self.lbl_active_scope_title.setText(f"Tout le document ({count} {unit_pl})")
            elif count == 1:
                self.lbl_active_scope_title.setText(f"{unit_sg.capitalize()} {sorted_pages[0]}")
            else:
                self.lbl_active_scope_title.setText(f"{unit_pl.capitalize()} {sorted_pages[0]} à {sorted_pages[-1]} ({count} {unit_pl})")

    def _populate_strategies(self) -> None:
        """Remplit le ComboBox des stratégies adaptées au type de document."""
        self.combo_strategy.blockSignals(True)
        self.combo_strategy.clear()

        ft = (getattr(self._doc, "file_type", "") or "md").lower() if self._doc else "md"

        if ft in ("pdf", "album", "pptx", "epub"):
            self.combo_strategy.addItem(load_phosphor_icon("ph.file-text", color=DesignTokens.TEXT_SECONDARY), "Par Page (1 page = 1 segment)", "page")
            self.combo_strategy.addItem(load_phosphor_icon("ph.frame-corners", color=DesignTokens.TEXT_SECONDARY), "Plage complète en 1 bloc", "range")
            self.combo_strategy.addItem(load_phosphor_icon("ph.bookmarks", color=DesignTokens.TEXT_SECONDARY), "Par Chapitre (Titres / TOC)", "toc")
            self.combo_strategy.addItem(load_phosphor_icon("ph.ruler", color=DesignTokens.TEXT_SECONDARY), "Fenêtre de tokens fixe", "tokens")
        elif ft in ("audio", "mp3", "m4a", "wav", "youtube", "video"):
            self.combo_strategy.addItem(load_phosphor_icon("ph.timer", color=DesignTokens.TEXT_SECONDARY), "Par Intervalle (3 minutes)", "time_3m")
            self.combo_strategy.addItem(load_phosphor_icon("ph.timer", color=DesignTokens.TEXT_SECONDARY), "Par Intervalle (5 minutes)", "time_5m")
            self.combo_strategy.addItem(load_phosphor_icon("ph.film-strip", color=DesignTokens.TEXT_SECONDARY), "Par Chapitre / Section", "toc")
            self.combo_strategy.addItem(load_phosphor_icon("ph.frame-corners", color=DesignTokens.TEXT_SECONDARY), "Portée complète en 1 bloc", "range")
            self.combo_strategy.addItem(load_phosphor_icon("ph.ruler", color=DesignTokens.TEXT_SECONDARY), "Fenêtre de tokens", "tokens")
        else:
            # Markdown, Texte, Web
            self.combo_strategy.addItem(load_phosphor_icon("ph.text-h-two", color=DesignTokens.TEXT_SECONDARY), "Par Titre H2 (Recommandé)", "h2")
            self.combo_strategy.addItem(load_phosphor_icon("ph.text-h-one", color=DesignTokens.TEXT_SECONDARY), "Par Grand Chapitre (H1)", "h1")
            self.combo_strategy.addItem(load_phosphor_icon("ph.text-h-three", color=DesignTokens.TEXT_SECONDARY), "Par Sous-Section (H3)", "h3")
            self.combo_strategy.addItem(load_phosphor_icon("ph.square", color=DesignTokens.TEXT_SECONDARY), "Bloc unique (Tout en 1 bloc)", "range")
            self.combo_strategy.addItem(load_phosphor_icon("ph.arrows-split", color=DesignTokens.TEXT_SECONDARY), "Fenêtre glissante (Tokens + Overlap)", "tokens")

        self.combo_strategy.blockSignals(False)
        self._update_controls_visibility()

    def _on_strategy_changed(self) -> None:
        self._update_controls_visibility()
        self.recompute_segments()

    def _update_controls_visibility(self) -> None:
        strat_key = self.combo_strategy.currentData() or "page"
        self.token_slider_frame.setVisible(strat_key == "tokens")

    def _on_slider_value_changed(self, value: int) -> None:
        self.lbl_token_size.setText(f"{value:,} tok.")

    def recompute_segments(self) -> None:
        """Exécute le découpage selon la portée et la stratégie sélectionnée et recharge la liste."""
        raw_text = (getattr(self._doc, "content", "") or "") if self._doc else self._fallback_text
        if not raw_text or not raw_text.strip():
            self._chunks = []
            self._refresh_list_ui()
            return

        strat_key = self.combo_strategy.currentData() or "page"
        chunks_data: list[dict[str, Any]] = []
        ft = (getattr(self._doc, "file_type", "") or "md").lower() if self._doc else "md"

        if strat_key == "page":
            db_chunks = (
                list(DocumentChunkModel.select().where(DocumentChunkModel.document == self._doc).order_by(DocumentChunkModel.chunk_index)) if (self._doc and getattr(self._doc, "id", None)) else []
            )
            if db_chunks:
                max_p = getattr(self, "_current_doc_total_units", 9999) or 9999
                allowed_pages = self._parse_page_range(self.input_page_scope.text().strip(), max_p)
                for c in db_chunks:
                    p_num = c.page_number
                    if p_num is None or p_num in allowed_pages:
                        unit_sg = getattr(self, "_current_doc_unit_singular", "Page")
                        chunks_data.append(
                            {
                                "index": len(chunks_data),
                                "title": c.heading_path or f"{unit_sg.capitalize()} {p_num or len(chunks_data) + 1}",
                                "content": c.content,
                                "page_number": p_num,
                                "heading_path": c.heading_path,
                                "tokens": ContextCompactor.estimate_tokens(c.content or ""),
                            }
                        )
            else:
                raw_chunks = ChunkingService.extract_chunks(raw_text, file_type=ft if ft in ("pdf", "album", "pptx") else "pdf")
                max_p = len(raw_chunks) or getattr(self, "_current_doc_total_units", 9999) or 9999
                allowed_pages = self._parse_page_range(self.input_page_scope.text().strip(), max_p)
                for c in raw_chunks:
                    p_num = c.get("page_number") or (c["index"] + 1)
                    if p_num in allowed_pages:
                        unit_sg = getattr(self, "_current_doc_unit_singular", "Page")
                        chunks_data.append(
                            {
                                "index": len(chunks_data),
                                "title": f"{unit_sg.capitalize()} {p_num}",
                                "content": c["content"],
                                "page_number": p_num,
                                "heading_path": c.get("heading_path"),
                                "tokens": ContextCompactor.estimate_tokens(c["content"]),
                            }
                        )

        elif strat_key == "range":
            # Groupe toute la portée sélectionnée en 1 seul bloc unifié
            raw_chunks = ChunkingService.extract_chunks(raw_text, file_type=ft if ft in ("pdf", "album", "pptx") else "pdf")
            max_p = len(raw_chunks) or getattr(self, "_current_doc_total_units", 9999) or 9999
            allowed_pages = self._parse_page_range(self.input_page_scope.text().strip(), max_p)
            scoped_chunks = [c for c in raw_chunks if (c.get("page_number") or (c["index"] + 1)) in allowed_pages]
            if scoped_chunks:
                merged_content = "\n\n---\n\n".join(c["content"] for c in scoped_chunks)
                sorted_pages = sorted(list(allowed_pages))
                range_str = f"{sorted_pages[0]}-{sorted_pages[-1]}" if len(sorted_pages) > 1 else str(sorted_pages[0]) if sorted_pages else "1"
                unit_sg = getattr(self, "_current_doc_unit_singular", "Plage")
                chunks_data.append(
                    {
                        "index": 0,
                        "title": f"{unit_sg.capitalize()} {range_str} ({len(scoped_chunks)} {self._current_doc_unit_plural})",
                        "content": merged_content,
                        "page_number": sorted_pages[0] if sorted_pages else 1,
                        "heading_path": f"Plage {range_str}",
                        "tokens": ContextCompactor.estimate_tokens(merged_content),
                    }
                )
            else:
                chunks_data.append(
                    {
                        "index": 0,
                        "title": "Document Complet",
                        "content": raw_text,
                        "page_number": 1,
                        "heading_path": "Complet",
                        "tokens": ContextCompactor.estimate_tokens(raw_text),
                    }
                )

        elif strat_key in ("h1", "h2", "h3", "toc"):
            level_map = {"h1": 1, "h2": 2, "h3": 3, "toc": 2}
            target_level = level_map.get(strat_key, 2)
            pattern = rf"(^|\n)(#{{{1},{target_level}}})\s+(.+)"
            splits = [0] + [m.start() for m in re.finditer(pattern, raw_text)] + [len(raw_text)]
            splits = sorted(list(set(splits)))

            idx = 0
            for i in range(len(splits) - 1):
                part = raw_text[splits[i] : splits[i + 1]].strip()
                if len(part) > 40:
                    first_line = part.split("\n", 1)[0].replace("#", "").strip() or f"Section {idx + 1}"
                    chunks_data.append(
                        {
                            "index": idx,
                            "title": first_line[:40],
                            "content": part,
                            "page_number": None,
                            "heading_path": first_line,
                            "tokens": ContextCompactor.estimate_tokens(part),
                        }
                    )
                    idx += 1

        elif strat_key.startswith("time_"):
            # Découpage temporel audio/vidéo
            raw_chunks = ChunkingService.extract_chunks(raw_text, file_type="audio")
            for c in raw_chunks:
                st = c.get("start_time", 0.0) or 0.0
                mins, secs = int(st // 60), int(st % 60)
                chunks_data.append(
                    {
                        "index": c["index"],
                        "title": f"{mins:02d}:{secs:02d}",
                        "content": c["content"],
                        "page_number": None,
                        "heading_path": None,
                        "tokens": ContextCompactor.estimate_tokens(c["content"]),
                    }
                )

        else:
            # Tokens avec chevauchement
            target_tokens = self.token_slider.value()
            target_chars = int(target_tokens * 3.5)
            text_splits = smart_chunk_text(raw_text, strategy="Chevauchement (Overlap)", max_chars=target_chars, overlap=300)
            for idx, part in enumerate(text_splits):
                first_line = part.strip().split("\n", 1)[0].replace("#", "").strip() or f"Bloc {idx + 1}"
                chunks_data.append(
                    {
                        "index": idx,
                        "title": first_line[:35],
                        "content": part,
                        "page_number": None,
                        "heading_path": first_line,
                        "tokens": ContextCompactor.estimate_tokens(part),
                    }
                )

        # Repli si aucun découpage n'a abouti
        if not chunks_data and raw_text.strip():
            chunks_data = [
                {
                    "index": 0,
                    "title": "Document Complet",
                    "content": raw_text,
                    "page_number": 1,
                    "heading_path": "Complet",
                    "tokens": ContextCompactor.estimate_tokens(raw_text),
                }
            ]

        self._chunks = chunks_data
        self._refresh_list_ui()

    def _parse_page_range(self, range_str: str, max_pages: int) -> set[int]:
        """Convertit une chaîne du type '1-5, 8, 12-15' en ensemble d'entiers."""
        if not range_str:
            return set(range(1, max_pages + 1))
        pages: set[int] = set()
        parts = range_str.split(",")
        for part in parts:
            part = part.strip()
            if "-" in part:
                sub = part.split("-", 1)
                try:
                    start_p = int(sub[0].strip())
                    end_p = int(sub[1].strip())
                    pages.update(range(start_p, end_p + 1))
                except ValueError:
                    continue
            else:
                try:
                    pages.add(int(part))
                except ValueError:
                    continue
        return pages or set(range(1, max_pages + 1))

    def _refresh_list_ui(self) -> None:
        """Génère les items graphiques dans le QListWidget avec cases à cocher synchronisées."""
        self.segments_list.blockSignals(True)
        self.segments_list.clear()

        for i, chunk in enumerate(self._chunks):
            item = QListWidgetItem(self.segments_list)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, chunk)

            idx = chunk.get("index", i)
            title = chunk.get("title") or chunk.get("heading_path") or f"Segment {i + 1}"
            content = str(chunk.get("content", ""))
            tokens = chunk.get("tokens", len(content.split()))

            widget = SegmentItemWidget(
                index=idx,
                title=title,
                content=content,
                token_count=tokens,
                is_checked=True,
            )
            widget.toggled.connect(lambda chk, it=item: self._on_widget_toggled(it, chk))
            item.setSizeHint(widget.sizeHint())
            self.segments_list.setItemWidget(item, widget)

        self.segments_list.blockSignals(False)
        self._update_summary_label()

    def _on_widget_toggled(self, item: QListWidgetItem, checked: bool) -> None:
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._update_summary_label()

    def _on_item_check_changed(self, item: QListWidgetItem) -> None:
        is_chk = item.checkState() == Qt.CheckState.Checked
        w = self.segments_list.itemWidget(item)
        if isinstance(w, SegmentItemWidget) and w.is_checked() != is_chk:
            w.set_checked(is_chk)
        self._update_summary_label()

    def _on_list_item_clicked(self, item: QListWidgetItem) -> None:
        data: Any = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            idx = int(data.get("index", 0))
            content = str(data.get("content", ""))
            self.segment_selected.emit(idx, content)

    def _set_all_checked(self, checked: bool) -> None:
        self.segments_list.blockSignals(True)
        for i in range(self.segments_list.count()):
            it = self.segments_list.item(i)
            it.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            w = self.segments_list.itemWidget(it)
            if isinstance(w, SegmentItemWidget):
                w.set_checked(checked)
        self.segments_list.blockSignals(False)
        self._update_summary_label()

    def _update_summary_label(self) -> None:
        total = self.segments_list.count()
        active = sum(1 for i in range(total) if self.segments_list.item(i).checkState() == Qt.CheckState.Checked)
        total_tokens = sum(int(self.segments_list.item(i).data(Qt.ItemDataRole.UserRole).get("tokens", 0)) for i in range(total) if self.segments_list.item(i).checkState() == Qt.CheckState.Checked)
        self.lbl_summary.setText(f"{active}/{total} segment(s) (~{total_tokens:,} tok.)")
        self.segments_updated.emit(active, total)

    def get_active_segments(self) -> list[dict[str, Any]]:
        """Retourne la liste des fragments cochés par l'utilisateur."""
        active_chunks: list[dict[str, Any]] = []
        for i in range(self.segments_list.count()):
            it = self.segments_list.item(i)
            w = self.segments_list.itemWidget(it)
            is_chk = w.is_checked() if isinstance(w, SegmentItemWidget) else (it.checkState() == Qt.CheckState.Checked)
            if is_chk:
                data = it.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict):
                    active_chunks.append(data)
        return active_chunks

    def get_total_active_tokens(self) -> int:
        """Calcule le nombre total de tokens des segments activés."""
        return sum(c.get("tokens", 0) for c in self.get_active_segments())

    def apply_scope_result(self, result: dict[str, Any]) -> None:
        """Applique les résultats du DocumentScopeDialog (titre, stats, fragments)."""
        self._last_scope_result = dict(result)
        chunks = result.get("chunks", [])
        scope_title = result.get("scope_title", "Portée personnalisée")
        scope_stats = result.get("scope_stats", "")
        range_str = str(result.get("range_str", ""))

        if chunks:
            self._chunks = chunks
            self._refresh_list_ui()

        if hasattr(self, "lbl_active_scope_title"):
            self.lbl_active_scope_title.setText(scope_title)
        if hasattr(self, "lbl_scope_stats"):
            self.lbl_scope_stats.setText(scope_stats)
        if hasattr(self, "input_page_scope"):
            self.input_page_scope.blockSignals(True)
            self.input_page_scope.setText(range_str)
            self.input_page_scope.blockSignals(False)

        self.scope_changed.emit(range_str)

    def get_last_scope_result(self) -> dict[str, Any] | None:
        """Retourne la dernière sélection de portée appliquée."""
        return self._last_scope_result

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if hasattr(self, "scope_trigger_card") and self.scope_trigger_card.isVisible():
            card_pos = self.scope_trigger_card.mapFrom(self, event.pos())
            if self.scope_trigger_card.rect().contains(card_pos):
                self.open_scope_dialog_requested.emit()
                return
        super().mousePressEvent(event)
