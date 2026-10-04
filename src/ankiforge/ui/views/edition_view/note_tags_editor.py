"""
Éditeur interactif de tags de note pour EditionView (AnkiForge).

Affiche les tags de la carte sélectionnée sous forme de jetons/puces (chips)
dans un conteneur fluide (FlowWidget). Permet l'ajout immédiat (y compris avec espaces),
le retrait, la réorganisation (gauche/droite) et la suppression contrôlée
des tags de provenance documentaire (annihilable avec rappel du lien affecté).
Conforme aux Règles 2, 8, 18, 19 et 20 de GEMINI.md et DESIGN.md.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteChunkLinkModel, NoteModel
from ankiforge.ui.components.flow_layout import FlowWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.utils.tags import (
    is_provenance_tag,
    parse_note_tags,
    serialize_note_tags,
)

logger = logging.getLogger(__name__)


class NoteTagChipWidget(QFrame):
    """Puce visuelle représentant un tag individuel avec réorganisation et suppression."""

    move_left_requested = Signal(str)
    move_right_requested = Signal(str)
    delete_requested = Signal(str)

    def __init__(
        self,
        tag: str,
        is_first: bool,
        is_last: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.tag = tag
        self.is_provenance = is_provenance_tag(tag)
        self._init_ui(is_first, is_last)

    def _init_ui(self, is_first: bool, is_last: bool) -> None:
        self.setObjectName("noteTagChip")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        if self.is_provenance:
            bg_color = DesignTokens.COLOR_PURPLE_BG
            border_color = DesignTokens.COLOR_PURPLE_BORDER
            text_color = DesignTokens.COLOR_PURPLE_TEXT
            icon_name = "file-text"
            icon_color = DesignTokens.COLOR_PURPLE
            self.setToolTip(f"Tag de traçabilité documentaire : {self.tag}")
        else:
            bg_color = DesignTokens.BG_INPUT
            border_color = DesignTokens.BORDER_COLOR
            text_color = DesignTokens.TEXT_PRIMARY
            icon_name = "tag"
            icon_color = DesignTokens.TEXT_MUTED
            self.setToolTip(self.tag)

        self.setStyleSheet(f"""
            QFrame#noteTagChip {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

        # Icône du tag
        ico_lbl = QLabel()
        ico_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(12, 12))
        ico_lbl.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(ico_lbl)

        # Texte du tag
        tag_lbl = QLabel(self.tag)
        tag_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9))
        tag_lbl.setStyleSheet(f"color: {text_color}; border: none; background: transparent;")
        layout.addWidget(tag_lbl)

        # Bouton déplacer à gauche
        self.btn_left = QToolButton(self)
        self.btn_left.setIcon(load_phosphor_icon("caret-left", color=DesignTokens.TEXT_MUTED))
        self.btn_left.setFixedSize(16, 16)
        self.btn_left.setToolTip("Déplacer vers la gauche")
        self.btn_left.setEnabled(not is_first)
        self.btn_left.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background: transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QToolButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QToolButton:disabled {{
                opacity: 0.3;
            }}
        """)
        self.btn_left.clicked.connect(lambda: self.move_left_requested.emit(self.tag))
        layout.addWidget(self.btn_left)

        # Bouton déplacer à droite
        self.btn_right = QToolButton(self)
        self.btn_right.setIcon(load_phosphor_icon("caret-right", color=DesignTokens.TEXT_MUTED))
        self.btn_right.setFixedSize(16, 16)
        self.btn_right.setToolTip("Déplacer vers la droite")
        self.btn_right.setEnabled(not is_last)
        self.btn_right.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background: transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QToolButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QToolButton:disabled {{
                opacity: 0.3;
            }}
        """)
        self.btn_right.clicked.connect(lambda: self.move_right_requested.emit(self.tag))
        layout.addWidget(self.btn_right)

        # Bouton supprimer
        btn_del = QToolButton(self)
        btn_del.setIcon(load_phosphor_icon("x", color=DesignTokens.TEXT_MUTED))
        btn_del.setFixedSize(16, 16)
        btn_del.setToolTip("Supprimer ce tag")
        btn_del.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background: transparent;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            QToolButton:hover {{
                background-color: {DesignTokens.COLOR_RED_BG};
            }}
        """)
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self.tag))
        layout.addWidget(btn_del)


class NoteTagsEditorWidget(QFrame):
    """Éditeur inline de tags pour la carte active d'EditionView."""

    tags_changed = Signal(list)
    provenance_tag_removed = Signal(str)

    def __init__(self, note: NoteModel | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._note = note
        self._tags: list[str] = parse_note_tags(note.tags) if note else []
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("noteTagsEditor")
        self.setStyleSheet(f"""
            QFrame#noteTagsEditor {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                margin-bottom: 6px;
            }}
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(6)

        # Ligne supérieure : Titre, compteur, champ d'ajout
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(8)

        ico_tags = QLabel()
        ico_tags.setPixmap(load_phosphor_icon("tag", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        ico_tags.setStyleSheet("border: none; background: transparent;")
        top_layout.addWidget(ico_tags)

        lbl_title = QLabel("Tags :")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        top_layout.addWidget(lbl_title)

        self.lbl_count = QLabel()
        self.lbl_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        top_layout.addWidget(self.lbl_count)

        top_layout.addStretch()

        # Champ de saisie d'un nouveau tag
        self.input_new_tag = QLineEdit()
        self.input_new_tag.setPlaceholderText("Ajouter un tag...")
        self.input_new_tag.setMaximumWidth(170)
        self.input_new_tag.setFixedHeight(24)
        self.input_new_tag.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 6px;
                font-size: 10px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.input_new_tag.returnPressed.connect(self._on_add_tag_clicked)
        top_layout.addWidget(self.input_new_tag)

        # Bouton d'ajout
        self.btn_add_tag = QPushButton("+")
        self.btn_add_tag.setFixedSize(24, 24)
        self.btn_add_tag.setToolTip("Ajouter le tag")
        self.btn_add_tag.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-size: 13px;
                font-weight: bold;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_add_tag.clicked.connect(self._on_add_tag_clicked)
        top_layout.addWidget(self.btn_add_tag)

        root_layout.addLayout(top_layout)

        # Conteneur des jetons (FlowWidget)
        self.chips_flow = FlowWidget(margin=0, h_spacing=6, v_spacing=4, parent=self)
        root_layout.addWidget(self.chips_flow)

        self._refresh_chips()

    def set_note(self, note: NoteModel | None) -> None:
        """Assigne une nouvelle note à l'éditeur et rafraîchit les tags."""
        self._note = note
        self._tags = parse_note_tags(note.tags) if note else []
        self._refresh_chips()

    def get_tags(self) -> list[str]:
        """Retourne la liste ordonnée des tags actuels."""
        return list(self._tags)

    def _refresh_chips(self) -> None:
        """Reconstruit les puces visuelles de tags."""
        self.chips_flow.clear()
        count = len(self._tags)
        self.lbl_count.setText(f"({count} tag{'s' if count > 1 else ''})")

        if not self._tags:
            lbl_empty = QLabel("Aucun tag associé à cette carte.")
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-style: italic; border: none; background: transparent;")
            self.chips_flow.add_widget(lbl_empty)
            return

        for idx, tag in enumerate(self._tags):
            chip = NoteTagChipWidget(
                tag=tag,
                is_first=(idx == 0),
                is_last=(idx == count - 1),
                parent=self.chips_flow,
            )
            chip.move_left_requested.connect(self._on_move_tag_left)
            chip.move_right_requested.connect(self._on_move_tag_right)
            chip.delete_requested.connect(self._on_delete_tag_requested)
            self.chips_flow.add_widget(chip)

    def _on_add_tag_clicked(self) -> None:
        """Ajoute un tag saisi par l'utilisateur."""
        raw_text = self.input_new_tag.text().strip()
        if not raw_text:
            return

        if raw_text in self._tags:
            self.input_new_tag.clear()
            return

        self._tags.append(raw_text)
        self._persist_tags()
        self.input_new_tag.clear()
        self._refresh_chips()
        self.tags_changed.emit(list(self._tags))

    def _on_move_tag_left(self, tag: str) -> None:
        """Déplace un tag vers la gauche (position précédente)."""
        if tag not in self._tags:
            return
        idx = self._tags.index(tag)
        if idx > 0:
            self._tags[idx], self._tags[idx - 1] = self._tags[idx - 1], self._tags[idx]
            self._persist_tags()
            self._refresh_chips()
            self.tags_changed.emit(list(self._tags))

    def _on_move_tag_right(self, tag: str) -> None:
        """Déplace un tag vers la droite (position suivante)."""
        if tag not in self._tags:
            return
        idx = self._tags.index(tag)
        if idx < len(self._tags) - 1:
            self._tags[idx], self._tags[idx + 1] = self._tags[idx + 1], self._tags[idx]
            self._persist_tags()
            self._refresh_chips()
            self.tags_changed.emit(list(self._tags))

    def _on_delete_tag_requested(self, tag: str) -> None:
        """Gère la demande de suppression d'un tag avec confirmation annihilable pour la provenance."""
        if tag not in self._tags:
            return

        if is_provenance_tag(tag):
            if not self._confirm_provenance_removal(tag):
                return
            self._tags.remove(tag)
            self._persist_tags()
            self._refresh_chips()
            self.tags_changed.emit(list(self._tags))
            self.provenance_tag_removed.emit(tag)
        else:
            self._tags.remove(tag)
            self._persist_tags()
            self._refresh_chips()
            self.tags_changed.emit(list(self._tags))

    def _confirm_provenance_removal(self, tag: str) -> bool:
        """Affiche un dialogue de confirmation annihilable explicitant le lien documentaire impacté."""
        link_desc = "Aucun lien documentaire actif actuellement."
        if self._note:
            link = NoteChunkLinkModel.select().where(NoteChunkLinkModel.note == self._note).first()
            if link and link.chunk:
                doc_title = link.chunk.document.title if link.chunk.document else "Document"
                heading = link.chunk.heading_path or (f"Page {link.chunk.page_number}" if link.chunk.page_number else f"Section #{link.chunk.chunk_index + 1}")
                link_desc = f"{doc_title} → {heading}"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Supprimer le tag de provenance ?")
        box.setText(f"Voulez-vous vraiment supprimer le tag de traçabilité documentaire « {tag} » ?")
        box.setInformativeText(f"Lien de couverture concerné :\n• {link_desc}\n\nCette action recalculera le rattachement de la carte au document source.")
        btn_delete = box.addButton("Supprimer le tag", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = box.addButton("Annuler", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()

        return box.clickedButton() == btn_delete

    def _persist_tags(self) -> None:
        """Persiste les tags mis à jour dans la base de données via le sérialiseur canonique."""
        if not self._note:
            return
        self._note.tags = serialize_note_tags(self._tags)
        self._note.save(only=[NoteModel.tags])
