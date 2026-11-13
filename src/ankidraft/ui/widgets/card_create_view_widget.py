"""Widget dédié à l'affichage et à l'édition de création de carte pour le Garde-Fou.

Destiné aux patches de création (`note_create`, `batch_note_create`) qui n'ont pas
d'état « avant » et ne méritent donc pas une comparaison champ par champ (diff).
Offre une séparation nette entre l'éditeur de champs (panneau gauche) et l'aperçu
dynamique de la carte rendue via CardPreviewWidget (panneau droit) dans un QSplitter
avec modes d'affichage segmentés (Côte à côte, Champs seuls, Aperçu seul).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QByteArray, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankidraft.database.models import DeckModel, NoteTypeModel
from ankidraft.ui.components import Badge, SecondaryButton
from ankidraft.ui.components.deck_select_window import DeckSelectWindow
from ankidraft.ui.components.model_select_window import ModelSelectWindow
from ankidraft.ui.theme import DesignTokens
from ankidraft.ui.widgets.card_preview_widget import CardPreviewWidget
from ankidraft.utils.environment import get_app_qsettings
from ankidraft.utils.i18n import tr
from ankidraft.utils.icon_loader import load_phosphor_icon
from ankidraft.utils.tags import split_tag_tokens

logger = logging.getLogger(__name__)


class TagBadgeButton(QPushButton):
    """Badge de tag cliquable avec croix de suppression."""

    tag_removed = Signal(str)

    def __init__(self, tag: str, parent: QWidget | None = None) -> None:
        super().__init__(f"✕ {tag}", parent)
        self.tag = tag
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.COLOR_PURPLE_BG};
                color: {DesignTokens.COLOR_PURPLE_TEXT};
                border: 1px solid {DesignTokens.COLOR_PURPLE_BORDER};
                border-radius: 9999px;
                padding: 0 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.COLOR_PURPLE_BORDER};
                color: white;
            }}
        """)
        self.clicked.connect(lambda: self.tag_removed.emit(self.tag))


class CardCreateFieldRow(QFrame):
    """Champ éditable d'une nouvelle carte (nom + valeur modifiable + compteur de mots)."""

    value_changed = Signal(str, str)  # field_name, new_value

    def __init__(self, field_name: str, field_value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.field_name = field_name

        self.setObjectName("CardCreateFieldRow")
        self.setStyleSheet(f"""
            QFrame#CardCreateFieldRow {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 8px;
            }}
            QFrame#CardCreateFieldRow:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self._setup_ui(field_value)

    def _setup_ui(self, field_value: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        lbl_name = QLabel(self.field_name.upper())
        lbl_name.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: {DesignTokens.ACCENT_PRIMARY};
            border: none;
            background: transparent;
        """)
        header.addWidget(lbl_name)

        word_count = len(field_value.split()) if field_value else 0
        self.badge_words = Badge(tr("%1 mots", word_count), variant="neutral")
        header.addWidget(self.badge_words)
        header.addStretch()
        layout.addLayout(header)

        self.value_edit = QPlainTextEdit()
        self.value_edit.setPlainText(field_value)
        self.value_edit.setMinimumHeight(75)
        self.value_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                font-family: {DesignTokens.FONT_CODE};
                padding: 6px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.value_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.value_edit, 1)

    def _on_text_changed(self) -> None:
        text = self.value_edit.toPlainText()
        word_count = len(text.split()) if text else 0
        self.badge_words.setText(tr("%1 mots", word_count))
        self.value_changed.emit(self.field_name, text)

    @property
    def value(self) -> str:
        """Retourne la valeur courante du champ."""
        return self.value_edit.toPlainText()


class CardCreateViewWidget(QWidget):
    """Vue d'affichage et d'édition de création de carte pour le Garde-Fou.

    Destiné aux patches de création (`note_create`, `batch_note_create`) qui n'ont pas
    d'état « avant » et ne méritent donc pas une comparaison champ par champ (diff).
    Sépare nettement les champs éditables (gauche) et l'aperçu dynamique rendu (droite)
    avec sélecteur de mode (Côte à côte, Champs seuls, Aperçu seul) et persistance d'état.
    """

    content_edited = Signal(object)  # dict[str, str] ou dict complet

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch_type: str = "note_create"
        self._fields: dict[str, str] = {}
        self._note_type: NoteTypeModel | None = None
        self._deck: DeckModel | None = None
        self._tags: list[str] = []
        self._field_rows: dict[str, CardCreateFieldRow] = {}
        self._notes_list: list[dict[str, Any]] = []
        self._current_note_index: int = 0
        self._tag_badges: list[TagBadgeButton] = []
        self._current_view_mode: str = "split"

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # ── 1. En-tête (titre, métadonnées, sélecteur de disposition) ────
        header = QFrame()
        header.setObjectName("CardCreateHeader")
        header.setStyleSheet(f"""
            QFrame#CardCreateHeader {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px 10px;
            }}
        """)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(6, 6, 6, 6)
        header_layout.setSpacing(6)

        # Ligne 1 : Titre + Sélecteur de mode d'affichage
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.plus-circle", color=DesignTokens.COLOR_GREEN).pixmap(18, 18))
        top_row.addWidget(ico)

        self.lbl_title = QLabel(tr("Nouvelle carte"))
        self.lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        top_row.addWidget(self.lbl_title)
        top_row.addStretch()

        # Sélecteur de mode d'affichage segmenté (Côte à côte / Champs / Aperçu)
        self.view_mode_group = QWidget()
        view_mode_layout = QHBoxLayout(self.view_mode_group)
        view_mode_layout.setContentsMargins(0, 0, 0, 0)
        view_mode_layout.setSpacing(2)

        self.btn_mode_split = QPushButton(tr("Côte à côte"))
        self.btn_mode_split.setIcon(load_phosphor_icon("ph.columns", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_split.setCheckable(True)
        self.btn_mode_split.setFixedHeight(26)
        self.btn_mode_split.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_split.setToolTip(tr("Affichage partagé : Champs à gauche, Aperçu à droite"))
        self.btn_mode_split.clicked.connect(lambda: self.set_view_mode("split"))

        self.btn_mode_fields = QPushButton(tr("Champs"))
        self.btn_mode_fields.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_fields.setCheckable(True)
        self.btn_mode_fields.setFixedHeight(26)
        self.btn_mode_fields.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_fields.setToolTip(tr("Plein écran : Édition complète des champs de la carte"))
        self.btn_mode_fields.clicked.connect(lambda: self.set_view_mode("fields"))

        self.btn_mode_preview = QPushButton(tr("Aperçu"))
        self.btn_mode_preview.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_mode_preview.setCheckable(True)
        self.btn_mode_preview.setFixedHeight(26)
        self.btn_mode_preview.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_mode_preview.setToolTip(tr("Plein écran : Prévisualisation WebView de la carte créée"))
        self.btn_mode_preview.clicked.connect(lambda: self.set_view_mode("preview"))

        self._apply_mode_button_styles()

        view_mode_layout.addWidget(self.btn_mode_split)
        view_mode_layout.addWidget(self.btn_mode_fields)
        view_mode_layout.addWidget(self.btn_mode_preview)
        top_row.addWidget(self.view_mode_group)
        header_layout.addLayout(top_row)

        # Ligne 2 : Métadonnées Paquet & Modèle avec boutons de changement compacts
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(0, 0, 0, 0)
        meta_row.setSpacing(8)

        self.lbl_deck = QLabel()
        self.lbl_deck.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        meta_row.addWidget(self.lbl_deck)

        self.btn_change_deck = SecondaryButton(tr("Changer"))
        self.btn_change_deck.setIcon(load_phosphor_icon("ph.folder", color=DesignTokens.TEXT_SECONDARY))
        self.btn_change_deck.setFixedHeight(26)
        self.btn_change_deck.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                font-size: 11px;
            }
        """)
        self.btn_change_deck.setToolTip(tr("Changer le paquet de destination"))
        self.btn_change_deck.clicked.connect(self._on_change_deck)
        meta_row.addWidget(self.btn_change_deck)

        lbl_sep = QLabel("•")
        lbl_sep.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        meta_row.addWidget(lbl_sep)

        self.lbl_note_type = QLabel()
        self.lbl_note_type.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        meta_row.addWidget(self.lbl_note_type)

        self.btn_change_note_type = SecondaryButton(tr("Changer"))
        self.btn_change_note_type.setIcon(load_phosphor_icon("ph.note", color=DesignTokens.TEXT_SECONDARY))
        self.btn_change_note_type.setFixedHeight(26)
        self.btn_change_note_type.setStyleSheet("""
            QPushButton {
                padding: 2px 8px;
                font-size: 11px;
            }
        """)
        self.btn_change_note_type.setToolTip(tr("Changer le modèle de note"))
        self.btn_change_note_type.clicked.connect(self._on_change_note_type)
        meta_row.addWidget(self.btn_change_note_type)

        meta_row.addStretch()
        header_layout.addLayout(meta_row)

        main_layout.addWidget(header)

        # ── 2. Navigation de lot (si batch_note_create) ────────────────
        self.nav_widget = QFrame()
        self.nav_widget.setObjectName("batch_nav_bar")
        self.nav_widget.setStyleSheet(f"""
            QFrame#batch_nav_bar {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
            }}
        """)
        self.nav_widget.setVisible(False)
        self.nav_row = QHBoxLayout(self.nav_widget)
        self.nav_row.setContentsMargins(8, 4, 8, 4)
        self.nav_row.setSpacing(8)

        icon_batch = QLabel()
        icon_batch.setPixmap(load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY).pixmap(16, 16))
        self.nav_row.addWidget(icon_batch)

        lbl_batch = QLabel(tr("Lot :"))
        lbl_batch.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {DesignTokens.ACCENT_PRIMARY};")
        self.nav_row.addWidget(lbl_batch)

        self.btn_nav_prev = SecondaryButton(tr("Précédent"))
        self.btn_nav_prev.setIcon(load_phosphor_icon("ph.caret-left", color=DesignTokens.TEXT_PRIMARY))
        self.btn_nav_prev.setFixedHeight(28)
        self.btn_nav_prev.clicked.connect(self._go_prev)
        self.nav_row.addWidget(self.btn_nav_prev)

        self.lbl_nav_pos = QLabel()
        self.lbl_nav_pos.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        self.nav_row.addWidget(self.lbl_nav_pos)

        self.btn_nav_next = SecondaryButton(tr("Suivant"))
        self.btn_nav_next.setIcon(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_PRIMARY))
        self.btn_nav_next.setFixedHeight(28)
        self.btn_nav_next.clicked.connect(self._go_next)
        self.nav_row.addWidget(self.btn_nav_next)

        self.nav_row.addStretch()
        main_layout.addWidget(self.nav_widget)

        # ── 3. Splitter Horizontal (Champs à gauche | Aperçu à droite) ──
        self.content_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.content_splitter.setChildrenCollapsible(False)

        # ── Panneau Gauche : Édition des champs et des tags ────────────
        self.left_panel = QFrame()
        self.left_panel.setObjectName("CardCreateLeftPanel")
        self.left_panel.setStyleSheet("""
            QFrame#CardCreateLeftPanel {
                background-color: transparent;
                border: none;
            }
        """)
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        # En-tête des champs
        fields_header = QHBoxLayout()
        fields_header.setContentsMargins(4, 2, 4, 2)
        fields_header.setSpacing(6)

        lbl_fields_title = QLabel(tr("CHAMPS DE LA CARTE"))
        lbl_fields_title.setStyleSheet(f"font-size: 11px; font-weight: 700; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        fields_header.addWidget(lbl_fields_title)

        self.badge_fields_count = Badge(tr("0 champ"), variant="neutral")
        fields_header.addWidget(self.badge_fields_count)
        fields_header.addStretch()
        left_layout.addLayout(fields_header)

        # Scroll des champs (pleine hauteur)
        self.fields_scroll = QScrollArea()
        self.fields_scroll.setWidgetResizable(True)
        self.fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fields_scroll.setStyleSheet("background-color: transparent;")

        self.fields_content = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_content)
        self.fields_layout.setContentsMargins(0, 0, 4, 0)
        self.fields_layout.setSpacing(0)
        self.fields_layout.addStretch()

        self.fields_scroll.setWidget(self.fields_content)
        left_layout.addWidget(self.fields_scroll, 1)

        # Tags en badges modifiables (intégré au volet gauche)
        self.tags_card = QFrame()
        self.tags_card.setObjectName("CardCreateTags")
        self.tags_card.setStyleSheet(f"""
            QFrame#CardCreateTags {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
            }}
        """)
        tags_layout = QHBoxLayout(self.tags_card)
        tags_layout.setContentsMargins(6, 4, 6, 4)
        tags_layout.setSpacing(6)

        lbl_tags_title = QLabel(tr("TAGS"))
        lbl_tags_title.setStyleSheet(f"font-size: 10px; font-weight: 700; letter-spacing: 0.5px; color: {DesignTokens.ACCENT_PRIMARY};")
        tags_layout.addWidget(lbl_tags_title)

        tags_scroll = QScrollArea()
        tags_scroll.setWidgetResizable(True)
        tags_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tags_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tags_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tags_scroll.setFixedHeight(34)
        tags_scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                height: 3px;
                background: transparent;
                border: none;
                margin: 0px;
            }
            QScrollBar::groove:horizontal {
                background: transparent;
                border: none;
            }
            QScrollBar::handle:horizontal {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 1px;
                min-width: 16px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                width: 0px;
                height: 0px;
                background: transparent;
                border: none;
            }
        """)

        self.tags_container = QWidget()
        self.tags_container.setStyleSheet("background: transparent; border: none;")
        self.tags_flow = QHBoxLayout(self.tags_container)
        self.tags_flow.setContentsMargins(0, 0, 0, 0)
        self.tags_flow.setSpacing(4)
        self.tags_flow.addStretch()
        tags_scroll.setWidget(self.tags_container)
        tags_layout.addWidget(tags_scroll, 1)

        self.new_tag_edit = QLineEdit()
        self.new_tag_edit.setPlaceholderText(tr("Ajouter un tag…"))
        self.new_tag_edit.setFixedHeight(24)
        self.new_tag_edit.setMinimumWidth(80)
        self.new_tag_edit.setMaximumWidth(120)
        self.new_tag_edit.returnPressed.connect(self._on_new_tag_added)
        self.new_tag_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 10px;
                padding: 0 6px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        tags_layout.addWidget(self.new_tag_edit)
        left_layout.addWidget(self.tags_card)

        self.content_splitter.addWidget(self.left_panel)

        # ── Panneau Droit : Aperçu dynamique de la carte Anki ──────────
        self.right_panel = QFrame()
        self.right_panel.setObjectName("CardCreateRightPanel")
        self.right_panel.setStyleSheet(f"""
            QFrame#CardCreateRightPanel {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(6, 6, 6, 6)
        right_layout.setSpacing(4)

        # Prévisualisation avec contrôles (Recto/Verso, modes appareils, zoom)
        self.preview_widget = CardPreviewWidget(parent=self, show_header=True)
        self.preview_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout.addWidget(self.preview_widget, 1)

        self.content_splitter.addWidget(self.right_panel)

        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 1)
        self.content_splitter.splitterMoved.connect(self._on_splitter_moved)

        main_layout.addWidget(self.content_splitter, 1)

        # Restaurer la configuration géométrique et le mode d'affichage
        self._restore_settings()

    def _apply_mode_button_styles(self) -> None:
        """Applique le style cohérent aux boutons du sélecteur de disposition."""
        for btn in (self.btn_mode_split, self.btn_mode_fields, self.btn_mode_preview):
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: 11px;
                    font-weight: 500;
                    padding: 0 8px;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
                QPushButton:checked {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.ACCENT_PRIMARY};
                    font-weight: 700;
                }}
            """)

    def set_view_mode(self, mode: str) -> None:
        """Bascule le mode d'affichage ('split', 'fields', 'preview')."""
        self._current_view_mode = mode
        self.btn_mode_split.setChecked(mode == "split")
        self.btn_mode_fields.setChecked(mode == "fields")
        self.btn_mode_preview.setChecked(mode == "preview")

        if mode == "fields":
            self.left_panel.setVisible(True)
            self.right_panel.setVisible(False)
        elif mode == "preview":
            self.left_panel.setVisible(False)
            self.right_panel.setVisible(True)
        else:  # split
            self.left_panel.setVisible(True)
            self.right_panel.setVisible(True)
            # Répartir équitablement si nécessaire
            half = max(200, self.content_splitter.width() // 2)
            if half > 200:
                self.content_splitter.setSizes([half, half])

        settings = get_app_qsettings()
        settings.setValue("mcp/card_create_view_mode", mode)

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Sauvegarde l'état du séparateur dans les préférences utilisateur."""
        settings = get_app_qsettings()
        settings.setValue("mcp/card_create_splitter_state", self.content_splitter.saveState())

    def _restore_settings(self) -> None:
        """Restaure les préférences de découpage et de mode d'affichage."""
        settings = get_app_qsettings()
        state = settings.value("mcp/card_create_splitter_state")
        if isinstance(state, (QByteArray, bytes)):
            self.content_splitter.restoreState(state)
        else:
            self.content_splitter.setSizes([420, 480])

        mode = str(settings.value("mcp/card_create_view_mode") or "split")
        if mode not in ("split", "fields", "preview"):
            mode = "split"
        self.set_view_mode(mode)

    def set_patch(self, patch: Any) -> None:
        """Configure l'affichage à partir d'un patch staged (`note_create` ou `batch_note_create`)."""
        from ankidraft.services.ai.staged_patch_registry import staged_payload_of

        if hasattr(patch, "patch_type"):
            p_type = patch.patch_type
            payload = staged_payload_of(patch)
        else:
            p_type = patch.get("patch_type") or patch.get("type", "note_create")
            raw_pl = patch.get("diff_payload") or patch
            if isinstance(raw_pl, str):
                try:
                    payload = json.loads(raw_pl)
                except Exception:
                    payload = {}
            elif isinstance(raw_pl, dict):
                payload = raw_pl
            else:
                payload = {}

        p_type = str(p_type).lower().strip()
        self._patch_type = p_type

        content = payload.get("modified") if isinstance(payload.get("modified"), dict) else payload
        if not isinstance(content, dict):
            content = {}

        is_batch = p_type == "batch_note_create"
        self.nav_widget.setVisible(is_batch)

        if is_batch:
            notes = payload.get("notes") or content.get("notes") or []
            self._display_batch(notes, payload)
        else:
            self._notes_list = []
            self._display_single(content, payload)

        self.lbl_title.setText(tr("Lot de création — %1 note(s)", len(self._notes_list)) if is_batch else tr("Nouvelle carte"))

    def _display_single(self, content: dict[str, Any], payload: dict[str, Any]) -> None:
        """Affiche une création de note unitaire."""
        fields = content.get("fields") or content.get("fields_dict") or {}
        if not isinstance(fields, dict):
            fields = {}
        self._fields = {str(k): str(v) for k, v in fields.items()}

        deck_name = content.get("deck_name") or content.get("deck") or payload.get("deck_name") or payload.get("deck") or ""
        self._deck = DeckModel.get_or_none(DeckModel.name == str(deck_name).strip()) if deck_name else None

        nt_name = content.get("note_type_name") or content.get("note_type") or payload.get("note_type_name") or payload.get("note_type") or ""
        self._note_type = NoteTypeModel.get_or_none(NoteTypeModel.name == str(nt_name).strip()) if nt_name else None

        raw_tags = content.get("tags") or payload.get("tags")
        self._tags = split_tag_tokens(raw_tags)

        self._refresh_fields()
        self._refresh_metadata()
        self._refresh_tags()
        self._refresh_preview()
        self._update_nav()

    def _display_batch(self, notes: list[dict[str, Any]], payload: dict[str, Any]) -> None:
        """Affiche un lot de création de notes avec navigation."""
        self._notes_list = notes
        self._current_note_index = 0
        if notes:
            self._display_single(notes[0], payload)
        else:
            self._fields = {}
            self._refresh_fields()
            self._refresh_metadata()
            self._refresh_tags()
            self._refresh_preview()
            self._update_nav()

    def _refresh_fields(self) -> None:
        """Construit les lignes de champs éditables."""
        while self.fields_layout.count() > 1:
            item = self.fields_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_rows.clear()

        count = len(self._fields)
        self.badge_fields_count.setText(tr("%1 champ(s)", count))

        if not self._fields:
            lbl_empty = QLabel(tr("Aucun champ défini pour cette carte."))
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic; padding: 12px;")
            self.fields_layout.insertWidget(self.fields_layout.count() - 1, lbl_empty)
            return

        for f_name in self._fields:
            row = CardCreateFieldRow(field_name=f_name, field_value=self._fields[f_name], parent=self.fields_content)
            row.value_changed.connect(self._on_field_changed)
            self._field_rows[f_name] = row
            self.fields_layout.insertWidget(self.fields_layout.count() - 1, row)

    def _refresh_metadata(self) -> None:
        """Met à jour les libellés de paquet et de type de note."""
        deck_name = self._deck.name if self._deck else tr("Non défini")
        nt_name = self._note_type.name if self._note_type else tr("Non défini")
        self.lbl_deck.setText(tr("Paquet : %1", deck_name))
        self.lbl_note_type.setText(tr("Type de note : %1", nt_name))

    def _refresh_tags(self) -> None:
        """Affiche les tags sous forme de badges cliquables."""
        for badge in self._tag_badges:
            self.tags_flow.removeWidget(badge)
            badge.setParent(None)
            badge.hide()
            badge.deleteLater()
        self._tag_badges.clear()

        for tag in self._tags:
            badge = TagBadgeButton(tag, parent=self.tags_container)
            badge.tag_removed.connect(self._on_tag_removed)
            self.tags_flow.insertWidget(self.tags_flow.count() - 1, badge)
            self._tag_badges.append(badge)

    def _refresh_preview(self) -> None:
        """Rend l'aperçu de la carte via CardPreviewWidget."""
        nt = self._note_type
        if nt is None:
            # Crée un modèle temporaire pour l'aperçu si aucun n'est trouvé
            fields = list(self._fields.keys()) or ["Front", "Back"]
            templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]
            nt = NoteTypeModel(
                name=tr("Aperçu temporaire"),
                fields_schema=json.dumps(fields, ensure_ascii=False),
                templates=json.dumps(templates, ensure_ascii=False),
                css_style="",
            )

        self.preview_widget.update_preview(note_type=nt, fields_dict=self._fields)

    def _on_field_changed(self, field_name: str, new_val: str) -> None:
        """Répercute la modification d'un champ et notifie le contenu modifié."""
        self._fields[field_name] = new_val
        self.content_edited.emit(self.get_modified_content())
        self._refresh_preview()

    def _on_tag_removed(self, tag: str) -> None:
        """Supprime un tag et notifie le contenu modifié."""
        if tag in self._tags:
            self._tags.remove(tag)
            self._refresh_tags()
            self.content_edited.emit(self.get_modified_content())

    def _on_new_tag_added(self) -> None:
        """Ajoute le tag saisi dans le champ d'ajout."""
        text = self.new_tag_edit.text().strip()
        new_tokens = split_tag_tokens(text)
        if not new_tokens:
            self.new_tag_edit.clear()
            return
        modified = False
        for tok in new_tokens:
            if tok not in self._tags:
                self._tags.append(tok)
                modified = True
        self.new_tag_edit.clear()
        if modified:
            self._refresh_tags()
            self.content_edited.emit(self.get_modified_content())

    def _update_nav(self) -> None:
        """Met à jour l'état des boutons de navigation et la position."""
        total = len(self._notes_list)
        self.lbl_nav_pos.setText(tr("%1 / %2", self._current_note_index + 1, max(1, total)))
        self.btn_nav_prev.setEnabled(total > 1 and self._current_note_index > 0)
        self.btn_nav_next.setEnabled(total > 1 and self._current_note_index < total - 1)

    def _go_prev(self) -> None:
        if self._current_note_index > 0:
            self._current_note_index -= 1
            self._display_single(self._notes_list[self._current_note_index], {})

    def _go_next(self) -> None:
        if self._current_note_index < len(self._notes_list) - 1:
            self._current_note_index += 1
            self._display_single(self._notes_list[self._current_note_index], {})

    def _on_change_deck(self) -> None:
        """Ouvre le sélecteur de paquet pour modifier le deck cible de la carte."""
        current_id = self._deck.id if self._deck else None
        dlg = DeckSelectWindow(selected_deck_id=current_id, parent=self)
        dlg.deck_selected.connect(self._on_deck_selected)
        dlg.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        """Applique le nouveau paquet sélectionné."""
        self._deck = DeckModel.get_or_none(DeckModel.id == deck_id)
        self._refresh_metadata()
        self._refresh_preview()
        self.content_edited.emit(self.get_modified_content())

    def _on_change_note_type(self) -> None:
        """Ouvre le sélecteur de type de note pour modifier le modèle cible."""
        current_id = self._note_type.id if self._note_type else None
        dlg = ModelSelectWindow(current_model_id=current_id, parent=self)
        dlg.model_selected.connect(self._on_note_type_selected)
        dlg.show()

    def _on_note_type_selected(self, model_id: int, model_name: str) -> None:
        """Applique le nouveau type de note sélectionné."""
        self._note_type = NoteTypeModel.get_or_none(NoteTypeModel.id == model_id)
        self._refresh_metadata()
        self._refresh_preview()
        self.content_edited.emit(self.get_modified_content())

    def get_modified_content(self) -> dict[str, Any]:
        """Retourne le contenu complet de la carte à créer (champs, tags, deck, note_type)."""
        content: dict[str, Any] = dict(self._fields)
        content["tags"] = list(self._tags)
        if self._deck:
            content["deck_name"] = self._deck.name
        if self._note_type:
            content["note_type_name"] = self._note_type.name
        return content

    def get_fields_dict(self) -> dict[str, str]:
        """Retourne le dictionnaire des champs de la carte."""
        return dict(self._fields)

    def get_tags(self) -> list[str]:
        """Retourne la liste des tags."""
        return list(self._tags)

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les styles au profil de thème actif."""
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)

        self.style().unpolish(self)
        self.style().polish(self)
        self._apply_mode_button_styles()

        if hasattr(self, "nav_widget"):
            self.nav_widget.setStyleSheet(f"""
                QFrame#batch_nav_bar {{
                    background-color: {bg_panel};
                    border: 1px solid {border_color};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 8px;
                }}
            """)
        if hasattr(self, "tags_card"):
            self.tags_card.setStyleSheet(f"""
                QFrame#CardCreateTags {{
                    background-color: {bg_panel};
                    border: 1px solid {border_color};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 4px 8px;
                }}
            """)
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "refresh_theme"):
            self.preview_widget.refresh_theme(profile)

    def cleanup(self) -> None:
        """Libère les ressources (CardPreviewWidget)."""
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "cleanup"):
            self.preview_widget.cleanup()
