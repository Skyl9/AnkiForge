"""Vues spécialisées pour la zone de détail polymorphe du Garde-Fou MCP.

Fournit les 3 vues dédiées intégrées dans le QStackedWidget polymorphe :
- DeckOperationWidget : Arborescence de paquets avec badges parent/enfant (deck_create, deck_rename)
- TagDiffWidget : Tableau comparatif des tags ajoutés/retirés (set_tags, set_tags_bulk)
- DeletionImpactWidget : Bannière rouge vif avec décompte d'impact (card_delete, deck_delete)
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import CardModel, DeckModel, StagedPatchModel
from ankiforge.services.ai.staged_patch_registry import staged_payload_of
from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

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
                background-color: {DesignTokens.BG_INPUT};
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
                background-color: {DesignTokens.BG_INPUT};
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
        lbl_edit_name.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        eg_layout.addWidget(lbl_edit_name)

        self.deck_name_input = QLineEdit()
        self.deck_name_input.setFixedHeight(30)
        self.deck_name_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 0 8px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        eg_layout.addWidget(self.deck_name_input)

        lbl_edit_desc = QLabel(tr("Description du paquet :"))
        lbl_edit_desc.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        eg_layout.addWidget(lbl_edit_desc)

        self.desc_input = QTextEdit()
        self.desc_input.setFixedHeight(60)
        self.desc_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 11px;
                padding: 6px;
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
            lbl_from.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-weight: 600; font-size: 12px;")
            row_old.addWidget(lbl_from)
            row_old.addStretch()
            badge_old = Badge(tr("Actuel"), variant="danger")
            row_old.addWidget(badge_old)
            self.tree_layout.addLayout(row_old)

            row_new = QHBoxLayout()
            row_new.setSpacing(8)
            lbl_to = QLabel(tr("Nouveau chemin : %1", new_name))
            lbl_to.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-weight: 600; font-size: 12px;")
            row_new.addWidget(lbl_to)
            row_new.addStretch()
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
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        self.tree_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_input};
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
                background-color: {DesignTokens.BG_INPUT};
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
                background-color: {DesignTokens.BG_INPUT};
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
        lbl_edit.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {DesignTokens.TEXT_SECONDARY};")
        ec_layout.addWidget(lbl_edit)

        self.tags_input = QLineEdit()
        self.tags_input.setFixedHeight(30)
        self.tags_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 0 8px;
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
        if isinstance(raw_added, str):
            self._added_tags = [t.strip() for t in raw_added.split(",") if t.strip()]
        elif isinstance(raw_added, (list, tuple)):
            self._added_tags = [str(t).strip() for t in raw_added if str(t).strip()]
        else:
            self._added_tags = []

        raw_removed = payload.get("tags_removed") or []
        if isinstance(raw_removed, str):
            self._removed_tags = [t.strip() for t in raw_removed.split(",") if t.strip()]
        elif isinstance(raw_removed, (list, tuple)):
            self._removed_tags = [str(t).strip() for t in raw_removed if str(t).strip()]
        else:
            self._removed_tags = []

        # Nettoyage
        while self.tags_layout.count():
            item = self.tags_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Section Tags Ajoutés
        lbl_add = QLabel(tr("Tags ajoutés (+%1) :", len(self._added_tags)))
        lbl_add.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {DesignTokens.COLOR_GREEN};")
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
        lbl_rem.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {DesignTokens.COLOR_RED};")
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
        edited = [t.strip() for t in self.tags_input.text().split(",") if t.strip()]
        payload["tags"] = edited
        payload["tags_added"] = edited
        return payload

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les couleurs de la vue de tags au profil de thème."""
        bg_input = getattr(profile, "bg_input", DesignTokens.BG_INPUT)
        border_color = getattr(profile, "border_color", DesignTokens.BORDER_COLOR)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)
        self.tags_container.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_input};
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
    """Vue de détail polymorphe avec bannière rouge vif et décompte d'impact (card_delete, deck_delete)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch: StagedPatchModel | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Bannière rouge vif d'avertissement critique
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
        icon_alert.setPixmap(load_phosphor_icon("ph.warning-octagon", color=DesignTokens.COLOR_RED).pixmap(36, 36))
        banner_layout.addWidget(icon_alert)

        banner_text_layout = QVBoxLayout()
        banner_text_layout.setSpacing(2)

        lbl_danger_title = QLabel(tr("AVERTISSEMENT : SUPPRESSION DÉFINITIVE"))
        lbl_danger_title.setStyleSheet(f"font-size: 13px; font-weight: 800; color: {DesignTokens.COLOR_RED};")
        banner_text_layout.addWidget(lbl_danger_title)

        lbl_danger_desc = QLabel(tr("Cette action détruira définitivement les enregistrements sélectionnés de votre collection."))
        lbl_danger_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_PRIMARY};")
        banner_text_layout.addWidget(lbl_danger_desc)

        banner_layout.addLayout(banner_text_layout, 1)
        layout.addWidget(self.alert_banner)

        # Cadre de décompte d'impact
        impact_frame = QFrame()
        impact_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        self.impact_layout = QVBoxLayout(impact_frame)
        self.impact_layout.setContentsMargins(10, 10, 10, 10)
        self.impact_layout.setSpacing(8)

        lbl_impact_header = QLabel(tr("Détail de l'impact calculé :"))
        lbl_impact_header.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        self.impact_layout.addWidget(lbl_impact_header)

        self.lbl_target_info = QLabel()
        self.lbl_target_info.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        self.impact_layout.addWidget(self.lbl_target_info)

        self.lbl_cards_count = QLabel()
        self.lbl_cards_count.setStyleSheet(f"font-size: 11px; color: {DesignTokens.COLOR_RED}; font-weight: 600;")
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

        layout.addWidget(impact_frame)
        layout.addStretch()

    def set_patch(self, patch: StagedPatchModel) -> None:
        """Injecte les données d'impact pour la suppression."""
        self._patch = patch
        payload = staged_payload_of(patch)
        p_type = patch.patch_type.lower().strip()

        reason = str(payload.get("reason") or tr("Aucune justification fournie par l'agent."))
        self.lbl_reason.setText(tr("Motif formulé par l'agent : %1", reason))

        if p_type in ("deck_delete", "delete_deck"):
            deck_name = str(payload.get("deck_name") or payload.get("deck") or "")
            deck = DeckModel.get_or_none(DeckModel.name == deck_name)
            card_count = CardModel.select().where(CardModel.deck == deck).count() if deck else 0
            self.lbl_target_info.setText(tr("Paquet ciblé : '%1'", deck_name))
            self.lbl_cards_count.setText(tr("Cartes contenues qui seront détruites ou déplacées : %1 carte(s)", card_count))
        else:
            note_ids = payload.get("note_ids") or ([patch.target_id] if patch.target_id else [])
            cards_affected = CardModel.select().where(CardModel.note_id.in_(note_ids)).count() if note_ids else 1
            self.lbl_target_info.setText(tr("Notes ciblées : %1 note(s) (IDs: %2)", len(note_ids), ", ".join(str(i) for i in note_ids[:5])))
            self.lbl_cards_count.setText(tr("Cartes filles associées qui seront supprimées : %1 carte(s)", cards_affected))

    def get_reason(self) -> str:
        """Retourne le texte affiché du motif de suppression."""
        return self.lbl_reason.text()

    def get_modified_content(self) -> dict[str, Any]:
        if not self._patch:
            return {}
        return dict(staged_payload_of(self._patch))

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
