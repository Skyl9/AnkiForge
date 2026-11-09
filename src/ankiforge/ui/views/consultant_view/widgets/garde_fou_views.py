"""Vues spécialisées pour la zone de détail polymorphe du Garde-Fou MCP.

Fournit les 5 vues dédiées intégrées dans le QStackedWidget polymorphe :
- DeckOperationWidget : Arborescence de paquets avec badges parent/enfant (deck_create, deck_rename)
- TagDiffWidget : Tableau comparatif des tags ajoutés/retirés (set_tags, set_tags_bulk)
- DeletionImpactWidget : Bannière rouge vif avec décompte d'impact (card_delete, deck_delete)
- NoteCreationWidget : Affichage de création de note(s) sans diff (note_create, batch_note_create)
- NoteTypePatchWidget : Prévisualisation de note réelle Recto / Verso pour les types de notes
  (note_type_create, note_type_refactor, note_type_change, propose_note_type_refactor)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedPatchModel,
)
from ankiforge.services.ai.staged_patch_registry import staged_payload_of
from ankiforge.ui.components import Badge, SecondaryButton, StyledComboBox
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.tags import split_tag_tokens

logger = logging.getLogger(__name__)


class DeckOperationWidget(QWidget):
    """Vue de détail polymorphe pour les opérations sur les paquets (création et renommage)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch: StagedPatchModel | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # En-tête d'opération
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(8)

        self.icon_badge = QLabel()
        self.icon_badge.setPixmap(load_phosphor_icon("ph.folder-plus", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        h_layout.addWidget(self.icon_badge)

        self.lbl_op_title = QLabel(tr("Opération sur les paquets"))
        self.lbl_op_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(self.lbl_op_title, 1)

        self.badge_mode = Badge(tr("PAQUET"), variant="warning")
        h_layout.addWidget(self.badge_mode)
        layout.addWidget(header_card)

        # Zone d'arborescence visuelle
        self.tree_frame = QFrame()
        self.tree_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        self.tree_layout = QVBoxLayout(self.tree_frame)
        self.tree_layout.setContentsMargins(12, 12, 12, 12)
        self.tree_layout.setSpacing(6)
        layout.addWidget(self.tree_frame)

        # Zone d'édition directe
        edit_group = QFrame()
        edit_group.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        eg_layout = QVBoxLayout(edit_group)
        eg_layout.setContentsMargins(12, 12, 12, 12)
        eg_layout.setSpacing(8)

        lbl_edit_name = QLabel(tr("Nom du paquet (modifiable) :"))
        lbl_edit_name.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        eg_layout.addWidget(lbl_edit_name)

        self.deck_name_input = QLineEdit()
        self.deck_name_input.setFixedHeight(32)
        self.deck_name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        eg_layout.addWidget(self.deck_name_input)

        lbl_edit_desc = QLabel(tr("Description du paquet :"))
        lbl_edit_desc.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        eg_layout.addWidget(lbl_edit_desc)

        self.desc_input = QTextEdit()
        self.desc_input.setMinimumHeight(60)
        self.desc_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 6px 10px;
            }}
            QTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        eg_layout.addWidget(self.desc_input)

        layout.addWidget(edit_group)
        layout.addStretch()

    def set_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les métadonnées et alimente l'arborescence des segments."""
        self._patch = patch
        payload = staged_payload_of(patch)
        p_type = patch.patch_type.lower().strip()

        # Nettoyage des segments précédents
        while self.tree_layout.count():
            item = self.tree_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if p_type in ("deck_rename", "rename_deck"):
            self.lbl_op_title.setText(tr("Renommage de paquet"))
            self.badge_mode.setText(tr("RENOMMAGE"))
            self.badge_mode.set_variant("warning")
            self.icon_badge.setPixmap(load_phosphor_icon("ph.arrows-left-right", color=DesignTokens.COLOR_YELLOW).pixmap(24, 24))

            old_name = str(payload.get("old_name") or payload.get("deck_name") or "")
            new_name = str(payload.get("new_name") or "")

            row_old = QHBoxLayout()
            row_old.setSpacing(8)
            lbl_from = QLabel(tr("Ancien chemin : %1", old_name))
            lbl_from.setWordWrap(True)
            lbl_from.setStyleSheet(f"color: {DesignTokens.COLOR_RED_TEXT}; font-weight: 600; font-size: 12px;")
            row_old.addWidget(lbl_from, 1)
            badge_old = Badge(tr("Actuel"), variant="danger")
            row_old.addWidget(badge_old)
            self.tree_layout.addLayout(row_old)

            row_new = QHBoxLayout()
            row_new.setSpacing(8)
            lbl_to = QLabel(tr("Nouveau chemin : %1", new_name))
            lbl_to.setWordWrap(True)
            lbl_to.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN_TEXT}; font-weight: 600; font-size: 12px;")
            row_new.addWidget(lbl_to, 1)
            badge_new = Badge(tr("Proposé"), variant="success")
            row_new.addWidget(badge_new)
            self.tree_layout.addLayout(row_new)

            self.deck_name_input.setText(new_name)
            self.desc_input.setPlainText("")
        else:
            self.lbl_op_title.setText(tr("Création de nouveau paquet"))
            self.badge_mode.setText(tr("CRÉATION"))
            self.badge_mode.set_variant("accent")
            self.icon_badge.setPixmap(load_phosphor_icon("ph.folder-plus", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))

            deck_name = str(payload.get("deck_name") or payload.get("deck") or "")
            description = str(payload.get("description") or "")

            parts = [p.strip() for p in deck_name.split("::") if p.strip()]
            if not parts:
                parts = [deck_name]

            # Construction des segments parent/enfant
            for idx, part in enumerate(parts):
                seg_row = QHBoxLayout()
                seg_row.setContentsMargins(idx * 16, 2, 0, 2)
                seg_row.setSpacing(8)

                icon_seg = QLabel()
                icon_name = "ph.folder" if idx < len(parts) - 1 else "ph.folder-plus"
                icon_color = DesignTokens.TEXT_MUTED if idx < len(parts) - 1 else DesignTokens.COLOR_GREEN
                icon_seg.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(16, 16))
                seg_row.addWidget(icon_seg)

                lbl_seg = QLabel(part)
                is_leaf = idx == len(parts) - 1
                color_seg = DesignTokens.TEXT_PRIMARY if is_leaf else DesignTokens.TEXT_SECONDARY
                lbl_seg.setStyleSheet(f"font-size: 12px; font-weight: {'700' if is_leaf else '500'}; color: {color_seg};")
                seg_row.addWidget(lbl_seg)
                seg_row.addStretch()

                badge_variant = "success" if is_leaf else "neutral"
                badge_text = tr("Nouveau") if is_leaf else tr("Parent")
                seg_row.addWidget(Badge(badge_text, variant=badge_variant))
                self.tree_layout.addLayout(seg_row)

            self.deck_name_input.setText(deck_name)
            self.desc_input.setPlainText(description)

    def get_deck_name(self) -> str:
        """Retourne le nom de paquet actuellement renseigné dans l'éditeur direct."""
        return self.deck_name_input.text().strip()

    def get_modified_content(self) -> dict[str, Any]:
        """Retourne le payload mis à jour pour sync_direct_edit."""
        if not self._patch:
            return {}
        payload = dict(staged_payload_of(self._patch))
        p_type = self._patch.patch_type.lower().strip()
        if p_type in ("deck_rename", "rename_deck"):
            payload["new_name"] = self.deck_name_input.text().strip()
        else:
            payload["deck_name"] = self.deck_name_input.text().strip()
            payload["description"] = self.desc_input.toPlainText().strip()
        return payload

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs au profil de thème."""
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        self.tree_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_panel};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
        """)
        self.deck_name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: 4px;
                color: {text_primary};
                font-size: 12px;
                padding: 0 8px;
            }}
        """)


class TagDiffWidget(QWidget):
    """Vue de détail polymorphe pour les opérations de marquage (set_tags, set_tags_bulk)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch: StagedPatchModel | None = None
        self._added_tags: list[str] = []
        self._removed_tags: list[str] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # En-tête
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(8)

        icon_tag = QLabel()
        icon_tag.setPixmap(load_phosphor_icon("ph.tag", color=DesignTokens.COLOR_GREEN).pixmap(24, 24))
        h_layout.addWidget(icon_tag)

        self.lbl_target = QLabel(tr("Opération de tagging"))
        self.lbl_target.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(self.lbl_target, 1)

        self.badge_mode = Badge(tr("AJOUT"), variant="accent")
        h_layout.addWidget(self.badge_mode)
        layout.addWidget(header_card)

        # Zone comparative
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.tags_container = QFrame()
        self.tags_container.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        self.tags_layout = QVBoxLayout(self.tags_container)
        self.tags_layout.setContentsMargins(12, 12, 12, 12)
        self.tags_layout.setSpacing(10)
        scroll.setWidget(self.tags_container)
        layout.addWidget(scroll, 1)

        # Édition directe
        edit_card = QFrame()
        edit_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        ec_layout = QVBoxLayout(edit_card)
        ec_layout.setContentsMargins(12, 12, 12, 12)
        ec_layout.setSpacing(6)

        lbl_edit = QLabel(tr("Tags ajoutés (séparés par des virgules) :"))
        lbl_edit.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        ec_layout.addWidget(lbl_edit)

        self.tags_input = QLineEdit()
        self.tags_input.setFixedHeight(32)
        self.tags_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        ec_layout.addWidget(self.tags_input)
        layout.addWidget(edit_card)

    def set_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données du patch de tags."""
        self._patch = patch
        payload = staged_payload_of(patch)

        # Décompte des notes
        note_ids = payload.get("note_ids") or ([patch.target_id] if patch.target_id else [])
        mode = str(payload.get("mode") or "add").upper()
        self.badge_mode.setText(mode)
        self.lbl_target.setText(tr("Marquage de %1 note(s) ciblée(s)", len(note_ids)))

        # Extraction des tags ajoutés et retirés
        raw_added = payload.get("tags_added") or payload.get("tags") or []
        self._added_tags = split_tag_tokens(raw_added)

        raw_removed = payload.get("tags_removed") or []
        self._removed_tags = split_tag_tokens(raw_removed)

        # Nettoyage
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Section Tags Ajoutés
        lbl_add = QLabel(tr("Tags ajoutés (+%1) :", len(self._added_tags)))
        lbl_add.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.COLOR_GREEN_TEXT};")
        self.tags_layout.addWidget(lbl_add)

        row_add = QHBoxLayout()
        row_add.setSpacing(6)
        if self._added_tags:
            for tag in self._added_tags:
                badge = Badge(f"+ {tag}", variant="success")
                row_add.addWidget(badge)
        else:
            lbl_none = QLabel(tr("Aucun tag ajouté"))
            lbl_none.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
            row_add.addWidget(lbl_none)
        row_add.addStretch()
        self.tags_layout.addLayout(row_add)

        # Section Tags Retirés
        lbl_rem = QLabel(tr("Tags retirés (-%1) :", len(self._removed_tags)))
        lbl_rem.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.COLOR_RED_TEXT};")
        self.tags_layout.addWidget(lbl_rem)

        row_rem = QHBoxLayout()
        row_rem.setSpacing(6)
        if self._removed_tags:
            for tag in self._removed_tags:
                badge = Badge(f"- {tag}", variant="danger")
                row_rem.addWidget(badge)
        else:
            lbl_none_rem = QLabel(tr("Aucun tag retiré"))
            lbl_none_rem.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
            row_rem.addWidget(lbl_none_rem)
        row_rem.addStretch()
        self.tags_layout.addLayout(row_rem)

        self.tags_layout.addStretch()
        self.tags_input.setText(", ".join(self._added_tags))

    def get_added_tags(self) -> list[str]:
        return list(self._added_tags)

    def get_removed_tags(self) -> list[str]:
        return list(self._removed_tags)

    def get_modified_content(self) -> dict[str, Any]:
        """Retourne le dictionnaire mis à jour avec la saisie de l'utilisateur."""
        if not self._patch:
            return {}
        payload = dict(staged_payload_of(self._patch))
        edited = split_tag_tokens(self.tags_input.text())
        payload["tags"] = edited
        payload["tags_added"] = edited
        return payload

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs de la vue de tags au profil de thème."""
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        self.tags_container.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_panel};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
        """)
        self.tags_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: 4px;
                color: {text_primary};
                font-size: 12px;
                padding: 0 8px;
            }}
        """)


class DeletionImpactWidget(QWidget):
    """Vue de détail polymorphe avec bannière rouge vif, décompte d'impact et aperçu de carte supprimée."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch: StagedPatchModel | None = None
        self._preview_items: list[tuple[int | None, str]] = []
        self._current_index: int = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── 1. Bannière rouge vif d'avertissement critique ─────────────
        self.alert_banner = QFrame()
        self.alert_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.COLOR_RED_BG};
                border: 2px solid {DesignTokens.COLOR_RED};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        banner_layout = QHBoxLayout(self.alert_banner)
        banner_layout.setContentsMargins(10, 10, 10, 10)
        banner_layout.setSpacing(12)

        icon_alert = QLabel()
        icon_alert.setPixmap(load_phosphor_icon("ph.warning-octagon", color=DesignTokens.TEXT_ON_ACCENT).pixmap(36, 36))
        banner_layout.addWidget(icon_alert)

        banner_text_layout = QVBoxLayout()
        banner_text_layout.setSpacing(2)

        lbl_danger_title = QLabel(tr("AVERTISSEMENT : SUPPRESSION DÉFINITIVE"))
        lbl_danger_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {DesignTokens.COLOR_RED_TEXT};")
        banner_text_layout.addWidget(lbl_danger_title)

        lbl_danger_desc = QLabel(tr("Cette action détruira définitivement les enregistrements sélectionnés de votre collection."))
        lbl_danger_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_PRIMARY};")
        lbl_danger_desc.setWordWrap(True)
        banner_text_layout.addWidget(lbl_danger_desc)

        banner_layout.addLayout(banner_text_layout, 1)
        layout.addWidget(self.alert_banner)

        # ── 2. Cadre de décompte d'impact ──────────────────────────────
        self.impact_frame = QFrame()
        self.impact_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        self.impact_layout = QVBoxLayout(self.impact_frame)
        self.impact_layout.setContentsMargins(10, 8, 10, 8)
        self.impact_layout.setSpacing(6)

        lbl_impact_header = QLabel(tr("Détail de l'impact calculé :"))
        lbl_impact_header.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        self.impact_layout.addWidget(lbl_impact_header)

        self.lbl_target_info = QLabel()
        self.lbl_target_info.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        self.lbl_target_info.setWordWrap(True)
        self.impact_layout.addWidget(self.lbl_target_info)

        self.lbl_cards_count = QLabel()
        self.lbl_cards_count.setStyleSheet(f"font-size: 11px; color: {DesignTokens.COLOR_RED_TEXT}; font-weight: 600;")
        self.lbl_cards_count.setWordWrap(True)
        self.impact_layout.addWidget(self.lbl_cards_count)

        self.lbl_reason = QLabel()
        self.lbl_reason.setStyleSheet(f"""
            font-size: 11px;
            color: {DesignTokens.TEXT_MUTED};
            font-style: italic;
            padding: 4px;
            background: {DesignTokens.BG_PANEL};
            border-radius: 4px;
        """)
        self.lbl_reason.setWordWrap(True)
        self.impact_layout.addWidget(self.lbl_reason)

        layout.addWidget(self.impact_frame)

        # ── 3. Conteneur d'aperçu de la carte ciblée pour destruction ──
        self.preview_card = QFrame()
        self.preview_card.setObjectName("DeletionPreviewCard")
        self.preview_card.setStyleSheet(f"""
            QFrame#DeletionPreviewCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        preview_card_layout = QVBoxLayout(self.preview_card)
        preview_card_layout.setContentsMargins(8, 8, 8, 8)
        preview_card_layout.setSpacing(6)

        # 3a. Bandeau d'affordance de suppression
        preview_header = QHBoxLayout()
        preview_header.setContentsMargins(0, 0, 0, 0)
        preview_header.setSpacing(8)

        ico_trash = QLabel()
        ico_trash.setPixmap(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED).pixmap(16, 16))
        preview_header.addWidget(ico_trash)

        self.lbl_preview_title = QLabel(tr("Contenu de la note ciblée pour destruction (Lecture seule)"))
        self.lbl_preview_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.COLOR_RED_TEXT};")
        preview_header.addWidget(self.lbl_preview_title)
        preview_header.addStretch()

        self.lbl_preview_badge = Badge(tr("Suppression"), variant="danger")
        preview_header.addWidget(self.lbl_preview_badge)

        preview_card_layout.addLayout(preview_header)

        # 3b. Barre de navigation séquentielle (lot ou échantillon)
        self.nav_widget = QWidget()
        self.nav_widget.setVisible(False)
        nav_row = QHBoxLayout(self.nav_widget)
        nav_row.setContentsMargins(0, 0, 0, 0)
        nav_row.setSpacing(6)

        self.btn_nav_prev = SecondaryButton(tr("Précédente"))
        self.btn_nav_prev.setIcon(load_phosphor_icon("ph.caret-left", color=DesignTokens.TEXT_PRIMARY))
        self.btn_nav_prev.setFixedHeight(32)
        self.btn_nav_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_prev.clicked.connect(self._go_prev)
        nav_row.addWidget(self.btn_nav_prev)

        self.combo_nav = StyledComboBox()
        self.combo_nav.setFixedHeight(32)
        self.combo_nav.setMinimumWidth(220)
        self.combo_nav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_nav.currentIndexChanged.connect(self._on_combo_index_changed)
        nav_row.addWidget(self.combo_nav)

        self.btn_nav_next = SecondaryButton(tr("Suivante"))
        self.btn_nav_next.setIcon(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_PRIMARY))
        self.btn_nav_next.setFixedHeight(32)
        self.btn_nav_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_nav_next.clicked.connect(self._go_next)
        nav_row.addWidget(self.btn_nav_next)

        self.lbl_nav_pos = QLabel()
        self.lbl_nav_pos.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE};")
        nav_row.addWidget(self.lbl_nav_pos)

        nav_row.addStretch()
        preview_card_layout.addWidget(self.nav_widget)

        # 3c. CardPreviewWidget
        self.preview_widget = CardPreviewWidget(parent=self, show_header=True)
        self.preview_widget.setMinimumHeight(240)
        preview_card_layout.addWidget(self.preview_widget, 1)

        layout.addWidget(self.preview_card, 1)

    def _go_prev(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._update_nav_state()

    def _go_next(self) -> None:
        if self._current_index < len(self._preview_items) - 1:
            self._current_index += 1
            self._update_nav_state()

    def _on_combo_index_changed(self, index: int) -> None:
        if 0 <= index < len(self._preview_items) and index != self._current_index:
            self._current_index = index
            self._update_nav_state()

    def _update_nav_state(self) -> None:
        total = len(self._preview_items)
        if total == 0:
            self.nav_widget.setVisible(False)
            self._display_note_preview(None)
            return

        self.nav_widget.setVisible(total > 1)
        self.btn_nav_prev.setEnabled(self._current_index > 0)
        self.btn_nav_next.setEnabled(self._current_index < total - 1)
        self.lbl_nav_pos.setText(tr("Carte %1 sur %2", self._current_index + 1, total))

        self.combo_nav.blockSignals(True)
        self.combo_nav.setCurrentIndex(self._current_index)
        self.combo_nav.blockSignals(False)

        current_note_id = self._preview_items[self._current_index][0]
        self._display_note_preview(current_note_id)

    @staticmethod
    def _resolve_note(note_id: int | None) -> NoteModel | None:
        """Résout une note par son identifiant propre ou par l'identifiant d'une carte fille."""
        if note_id is None:
            return None
        note = NoteModel.get_or_none(NoteModel.id == note_id)
        if note:
            return note
        card = CardModel.get_or_none(CardModel.id == note_id)
        if card and card.note:
            return card.note
        return None

    @staticmethod
    def _extract_active_fields(note: NoteModel) -> dict[str, str]:
        """Extrait les champs de la version active d'une note."""
        active_v = note.versions.where(NoteVersionModel.is_active).first()
        if not active_v or not active_v.content:
            return {}
        try:
            data = json.loads(active_v.content)
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _extract_payload_fallback_fields(self) -> dict[str, str] | None:
        """Extrait les champs de repli depuis le payload staged si la note a déjà disparu de la base."""
        if not self._patch:
            return None
        payload = staged_payload_of(self._patch)
        original = payload.get("original") or payload.get("fields") or {}
        if not isinstance(original, dict) or not original:
            return None
        raw_fields = original.get("fields") if isinstance(original.get("fields"), dict) else original
        if isinstance(raw_fields, dict):
            return {str(k): str(v) for k, v in raw_fields.items()}
        return None

    def _build_item_label(self, note_id: int) -> str:
        note = self._resolve_note(note_id)
        summary = ""
        if note:
            fields = self._extract_active_fields(note)
            if fields:
                summary = next(iter(fields.values())).replace("\n", " ")[:25]

        if summary:
            return tr("Note #%1 · %2", note_id, summary)
        return tr("Note #%1", note_id)

    def _display_note_preview(self, note_id: int | None) -> None:
        if note_id is None:
            self.preview_widget.set_empty_state(tr("Aucun enregistrement à prévisualiser."))
            return

        note = self._resolve_note(note_id)
        if note:
            fields = self._extract_active_fields(note)
            self.preview_widget.update_preview(note_type=note.note_type, fields_dict=fields)
            return

        fallback_fields = self._extract_payload_fallback_fields()
        if fallback_fields is not None:
            self.preview_widget.update_preview(
                note_type=None,
                fields_dict=fallback_fields,
                override_templates=[{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
            )
            return

        self.preview_widget.set_empty_state(tr("Contenu de la note introuvable ou déjà supprimé."))

    def set_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données d'impact pour la suppression."""
        self._patch = patch
        payload = staged_payload_of(patch)
        p_type = patch.patch_type.lower().strip()

        reason = str(payload.get("reason") or tr("Aucune justification fournie par l'agent."))
        self.lbl_reason.setText(tr("Motif formulé par l'agent : %1", reason))

        self._preview_items.clear()
        self._current_index = 0

        if p_type in ("deck_delete", "delete_deck", "propose_deck_deletion"):
            from ankiforge.repositories.deck_repository import DeckRepository

            deck_name = str(payload.get("deck_name") or payload.get("deck") or "")
            deck = DeckModel.get_or_none(DeckModel.name == deck_name)
            if deck:
                repo = DeckRepository()
                descendant_ids = [d.id for d in repo.get_descendant_decks(deck.name)]
                sample_cards = list(CardModel.select().where(CardModel.deck.in_(descendant_ids)).limit(5))
                card_count = CardModel.select().where(CardModel.deck.in_(descendant_ids)).count()
                sample_note_ids = list(dict.fromkeys(c.note_id for c in sample_cards if c.note_id))
            else:
                card_count = int(payload.get("cards_count") or 0)
                sample_note_ids = []

            self.lbl_target_info.setText(tr("Paquet ciblé : '%1'", deck_name))
            self.lbl_cards_count.setText(tr("Cartes contenues qui seront détruites ou déplacées : %1 carte(s)", card_count))

            for n_id in sample_note_ids:
                label = self._build_item_label(n_id)
                self._preview_items.append((n_id, label))

        elif p_type in ("empty_cards_delete", "delete_empty_cards"):
            card_ids = payload.get("card_ids") or []
            deck_name = str(payload.get("deck_name") or "")
            if deck_name:
                self.lbl_target_info.setText(tr("Cartes vides ciblées : %1 carte(s) dans le paquet '%2'", len(card_ids), deck_name))
            else:
                self.lbl_target_info.setText(tr("Cartes vides ciblées : %1 carte(s)", len(card_ids)))
            self.lbl_cards_count.setText(tr("Cartes physiques sans recto qui seront purgées : %1 carte(s)", len(card_ids)))

            sample_cards = list(CardModel.select().where(CardModel.id.in_(card_ids)).limit(10))
            sample_note_ids = list(dict.fromkeys(c.note_id for c in sample_cards if c.note_id))
            for n_id in sample_note_ids:
                label = self._build_item_label(n_id)
                self._preview_items.append((n_id, label))

        else:
            note_ids = payload.get("note_ids") or ([patch.target_id] if patch.target_id else [])
            cards_affected = CardModel.select().where(CardModel.note_id.in_(note_ids)).count() if note_ids else 1
            self.lbl_target_info.setText(tr("Notes ciblées : %1 note(s) (IDs: %2)", len(note_ids), ", ".join(str(i) for i in note_ids[:5])))
            self.lbl_cards_count.setText(tr("Cartes filles associées qui seront supprimées : %1 carte(s)", cards_affected))

            for n_id in note_ids:
                label = self._build_item_label(n_id)
                self._preview_items.append((n_id, label))

        self.combo_nav.blockSignals(True)
        self.combo_nav.clear()
        for _, lbl in self._preview_items:
            self.combo_nav.addItem(lbl)
        self.combo_nav.blockSignals(False)

        if not self._preview_items and p_type in ("deck_delete", "delete_deck", "propose_deck_deletion"):
            self.nav_widget.setVisible(False)
            self.preview_widget.set_empty_state(tr("Ce paquet ne contient aucune carte."))
        else:
            self._update_nav_state()

    def get_reason(self) -> str:
        """Retourne le texte affiché du motif de suppression."""
        return self.lbl_reason.text()

    def get_modified_content(self) -> dict[str, Any]:
        if not self._patch:
            return {}
        return dict(staged_payload_of(self._patch))

    def cleanup(self) -> None:
        """Libère les ressources WebEngine de la vue d'aperçu."""
        if hasattr(self, "preview_widget") and hasattr(self.preview_widget, "cleanup"):
            self.preview_widget.cleanup()

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs de l'alerte de suppression au profil de thème."""
        color_red = getattr(profile, "color_red", DesignTokens.COLOR_RED)
        color_red_bg = getattr(profile, "color_red_bg", DesignTokens.COLOR_RED_BG)
        self.alert_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {color_red_bg};
                border: 2px solid {color_red};
                border-radius: 8px;
                padding: 10px;
            }}
        """)
        if hasattr(self, "preview_card"):
            border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
            bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
            self.preview_card.setStyleSheet(f"""
                QFrame#DeletionPreviewCard {{
                    background-color: {bg_panel};
                    border: 1px solid {border_color};
                    border-radius: 6px;
                }}
            """)
        if hasattr(self, "impact_frame"):
            border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
            bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
            self.impact_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: {bg_panel};
                    border: 1px solid {border_color};
                    border-radius: 6px;
                    padding: 10px;
                }}
            """)


class NoteTypePatchWidget(QWidget):
    """Vue de détail polymorphe dédiée aux patches de types de notes.

    Permet de sélectionner une note réelle de la collection (ou d'utiliser des
    valeurs d'exemple pour une création pure) et d'en prévisualiser le rendu
    Recto / Verso avec le CSS du modèle, avant validation du patch.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch: StagedPatchModel | None = None
        self._note_type: NoteTypeModel | None = None
        self._notes: list[NoteModel] = []
        self._edited_fields: dict[str, str] = {}
        self._edited_css: str = ""
        self._fields_schema: list[str] = []
        self._templates: list[dict[str, Any]] = []
        self._field_edits: dict[str, QLineEdit] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ── En-tête d'opération ──────────────────────────────────────────
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(8, 8, 8, 8)
        h_layout.setSpacing(8)

        icon_note = QLabel()
        icon_note.setPixmap(load_phosphor_icon("ph.file-text", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        h_layout.addWidget(icon_note)

        self.lbl_title = QLabel(tr("Prévisualisation de type de note"))
        self.lbl_title.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        h_layout.addWidget(self.lbl_title, 1)

        self.badge_mode = Badge(tr("MODIFICATION"), variant="warning")
        h_layout.addWidget(self.badge_mode)
        layout.addWidget(header_card)

        # ── Sélecteur de note d'exemple ─────────────────────────────────
        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)

        lbl_selector = QLabel(tr("Note d'exemple :"))
        lbl_selector.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        selector_row.addWidget(lbl_selector)

        self.combo_note = StyledComboBox()
        self.combo_note.setFixedHeight(32)
        self.combo_note.setMinimumWidth(220)
        self.combo_note.setCursor(Qt.CursorShape.PointingHandCursor)
        self.combo_note.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 0 8px;
            }}
            QComboBox:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.combo_note.currentIndexChanged.connect(self._on_note_selected)
        selector_row.addWidget(self.combo_note)

        self.lbl_selector_hint = QLabel()
        self.lbl_selector_hint.setStyleSheet(f"font-size: 10px; color: {DesignTokens.TEXT_MUTED}; font-style: italic;")
        selector_row.addWidget(self.lbl_selector_hint)
        selector_row.addStretch()
        layout.addLayout(selector_row)

        # ── Éditeur des champs ──────────────────────────────────────────
        lbl_fields = QLabel(tr("Champs (modifiables) :"))
        lbl_fields.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        layout.addWidget(lbl_fields)

        self.fields_scroll = QScrollArea()
        self.fields_scroll.setWidgetResizable(True)
        self.fields_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.fields_scroll.setMinimumHeight(120)
        self.fields_scroll.setMaximumHeight(320)
        self.fields_container = QWidget()
        self.fields_container_layout = QVBoxLayout(self.fields_container)
        self.fields_container_layout.setContentsMargins(0, 0, 0, 0)
        self.fields_container_layout.setSpacing(4)
        self.fields_scroll.setWidget(self.fields_container)
        layout.addWidget(self.fields_scroll)

        # ── Éditeur du CSS ──────────────────────────────────────────────
        lbl_css = QLabel(tr("CSS du modèle :"))
        lbl_css.setStyleSheet(f"font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: {DesignTokens.TEXT_MUTED};")
        layout.addWidget(lbl_css)

        self.css_edit = QPlainTextEdit()
        self.css_edit.setMinimumHeight(80)
        self.css_edit.setMaximumHeight(160)
        self.css_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 6px 10px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.css_edit.textChanged.connect(self._on_css_changed)
        layout.addWidget(self.css_edit)

        # ── Aperçu Recto / Verso ────────────────────────────────────────
        self.preview = CardPreviewWidget(parent=self, show_header=True)
        self.preview.setMinimumHeight(300)
        layout.addWidget(self.preview, 1)

        layout.addStretch()

    # ── Données du patch ───────────────────────────────────────────────

    @staticmethod
    def _extract_active_fields(note: NoteModel) -> dict[str, str]:
        """Extrait les champs de la version active d'une note."""
        active_v = note.versions.where(NoteVersionModel.is_active).first()
        if not active_v or not active_v.content:
            return {}
        try:
            data = json.loads(active_v.content)
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _load_notes(self) -> list[NoteModel]:
        """Résout les notes candidates à prévisualiser pour le patch courant."""
        if not self._patch:
            return []
        payload = staged_payload_of(self._patch)
        note_ids = payload.get("note_ids") or []
        if note_ids:
            return list(NoteModel.select().where(NoteModel.id.in_(note_ids)))
        if self._note_type:
            return list(NoteModel.select().where(NoteModel.note_type == self._note_type))
        deck_name = str(payload.get("deck_name") or payload.get("deck") or "")
        if deck_name:
            deck = DeckModel.get_or_none(DeckModel.name == deck_name)
            if deck:
                return list(NoteModel.select().join(CardModel).where(CardModel.deck == deck).distinct())
        return []

    def _rebuild_selector(self) -> None:
        """Remplit le sélecteur de note avec les candidates du patch."""
        self.combo_note.blockSignals(True)
        self.combo_note.clear()
        self._notes = self._load_notes()
        if not self._notes:
            self.combo_note.addItem(tr("Aucune note disponible — valeurs d'exemple"), userData=None)
            self.combo_note.setEnabled(False)
            self.lbl_selector_hint.setText(tr("Utilisation de valeurs d'exemple"))
            self.lbl_selector_hint.setVisible(True)
        else:
            for note in self._notes:
                fields = self._extract_active_fields(note)
                summary = next(iter(fields.values())).replace("\n", " ")[:30] if fields else ""
                label = tr("Note #%1 · %2", note.id, summary) if summary else tr("Note #%1", note.id)
                self.combo_note.addItem(label, userData=note.id)
            self.combo_note.setEnabled(True)
            self.lbl_selector_hint.setVisible(False)
        self.combo_note.blockSignals(False)
        self._on_note_selected(self.combo_note.currentIndex())

    def _rebuild_fields(self) -> None:
        """Reconstruit les lignes d'édition des champs à partir des valeurs courantes."""
        while self.fields_container_layout.count():
            item = self.fields_container_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._field_edits = {}
        fields = self._edited_fields if self._edited_fields else {str(f): f"Exemple {f}" for f in self._fields_schema}
        for field_name, value in fields.items():
            row = QFrame()
            row.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                }}
            """)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(6, 4, 6, 4)
            row_layout.setSpacing(8)

            lbl = QLabel(field_name)
            lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
            lbl.setMinimumWidth(90)
            row_layout.addWidget(lbl)

            edit = QLineEdit(str(value))
            edit.setFixedHeight(32)
            edit.setStyleSheet(f"""
                QLineEdit {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 4px;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: 11px;
                    padding: 0 8px;
                }}
                QLineEdit:focus {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            edit.blockSignals(True)
            edit.setText(str(value))
            edit.blockSignals(False)
            edit.textChanged.connect(lambda text, name=field_name: self._on_field_changed(name, text))
            row_layout.addWidget(edit, 1)

            self.fields_container_layout.addWidget(row)
            self._field_edits[field_name] = edit

        self.fields_container_layout.addStretch()

    def _render_preview(self) -> None:
        """Rend l'aperçu Recto / Verso avec les champs et le CSS couramment édités."""
        fields = dict(self._edited_fields)
        if not fields and self._fields_schema:
            fields = {str(f): f"Exemple {f}" for f in self._fields_schema}
        if "Front" not in fields and fields:
            fields["Front"] = next(iter(fields.values()))
        if "Back" not in fields and len(fields) > 1:
            fields["Back"] = list(fields.values())[1]

        override_templates = self._templates if self._templates else None
        override_css = self._edited_css or None
        self.preview.update_preview(
            note_type=self._note_type,
            fields_dict=fields,
            override_templates=override_templates,
            override_css=override_css,
        )

    def set_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données du patch et configure l'aperçu associé."""
        self._patch = patch
        self._note_type = None
        self._edited_fields = {}
        self._edited_css = ""
        self._fields_schema = []
        self._templates = []

        payload = staged_payload_of(patch)
        p_type = patch.patch_type.lower().strip()

        if p_type == "note_type_create":
            self.lbl_title.setText(tr("Création de type de note"))
            self.badge_mode.setText(tr("CRÉATION"))
            self.badge_mode.set_variant("success")
            self._edited_css = str(payload.get("css_style") or "")
            raw_schema = payload.get("fields_schema") or []
            self._fields_schema = [str(f) for f in raw_schema] if isinstance(raw_schema, list) else []
            raw_templates = payload.get("templates") or []
            self._templates = raw_templates if isinstance(raw_templates, list) else []
        else:
            self.lbl_title.setText(tr("Prévisualisation de type de note"))
            self.badge_mode.setText(tr("MODIFICATION"))
            self.badge_mode.set_variant("warning")
            target = payload.get("target_model") or payload.get("target_model_name") or payload.get("target_model_id")
            if target is not None:
                if isinstance(target, int) or (isinstance(target, str) and str(target).isdigit()):
                    self._note_type = NoteTypeModel.get_or_none(NoteTypeModel.id == int(target))
                else:
                    self._note_type = NoteTypeModel.get_or_none(NoteTypeModel.name == str(target).strip())
            if self._note_type:
                try:
                    self._fields_schema = [str(f) for f in json.loads(self._note_type.fields_schema or "[]")]
                except Exception:
                    self._fields_schema = []
                try:
                    parsed_templates = json.loads(self._note_type.templates or "[]")
                    self._templates = parsed_templates if isinstance(parsed_templates, list) else []
                except Exception:
                    self._templates = []
                self._edited_css = self._note_type.css_style or ""

        self.css_edit.blockSignals(True)
        self.css_edit.setPlainText(self._edited_css)
        self.css_edit.blockSignals(False)

        self._rebuild_selector()

    def get_modified_content(self) -> dict[str, Any]:
        """Retourne le payload mis à jour avec les champs et le CSS édités par l'utilisateur."""
        if not self._patch:
            return {}
        payload = dict(staged_payload_of(self._patch))
        payload["fields"] = dict(self._edited_fields)
        payload["css_style"] = self._edited_css
        return payload

    # ── Réactions utilisateur ──────────────────────────────────────────

    def _on_note_selected(self, index: int) -> None:
        """Charge les champs de la note sélectionnée et rafraîchit l'aperçu."""
        if not self._notes or index < 0 or index >= len(self._notes):
            self._edited_fields = {}
            self._rebuild_fields()
            self._render_preview()
            return
        note = self._notes[index]
        self._edited_fields = dict(self._extract_active_fields(note))
        if not self._edited_fields:
            self._edited_fields = {str(f): f"Exemple {f}" for f in self._fields_schema}
        self._rebuild_fields()
        self._render_preview()

    def _on_field_changed(self, name: str, text: str) -> None:
        """Propagère la modification d'un champ vers l'aperçu."""
        self._edited_fields[name] = text
        self._render_preview()

    def _on_css_changed(self) -> None:
        """Propagère la modification du CSS vers l'aperçu."""
        self._edited_css = self.css_edit.toPlainText()
        self._render_preview()

    # ── Thème & nettoyage ──────────────────────────────────────────────

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs au profil de thème actif."""
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        bg_panel = getattr(profile, "bg_panel", DesignTokens.BG_PANEL)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        self.fields_scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: {bg_panel};
                border: none;
            }}
        """)
        self.css_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {bg_input};
                border: 1px solid {border_color};
                border-radius: 4px;
                color: {text_primary};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 6px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        if hasattr(self, "preview") and hasattr(self.preview, "refresh_theme"):
            self.preview.refresh_theme(profile)

    def cleanup(self) -> None:
        """Libère les ressources WebEngine de l'aperçu."""
        if hasattr(self, "preview") and hasattr(self.preview, "cleanup"):
            self.preview.cleanup()
