from typing import Any

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class CardEditDialog(QDialog):
    """Dialogue d'édition dynamique d'une carte générée supportant tous ses champs."""

    METADATA_KEYS: set[str] = {"model", "note_type", "status", "chunk_id", "source_doc_id", "tags"}

    def __init__(
        self,
        front: str = "",
        back: str = "",
        card_data: dict[str, Any] | None = None,
        field_names: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Éditer la carte")
        self.setMinimumWidth(560)
        self.resize(620, 520)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        # Résolution des champs ordonnés et des valeurs initiales
        self.card_data: dict[str, Any] = dict(card_data) if card_data is not None else {}
        if not self.card_data and (front or back):
            self.card_data = {"Front": front, "Back": back}

        ordered_fields: list[str] = []
        if field_names:
            for f in field_names:
                if f not in self.METADATA_KEYS and f not in ordered_fields:
                    ordered_fields.append(f)

        for k in self.card_data:
            if k not in self.METADATA_KEYS and k not in ordered_fields:
                ordered_fields.append(k)

        if not ordered_fields:
            ordered_fields = ["Front", "Back"]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # En-tête avec modèle
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)
        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        header_layout.addWidget(ico)

        model_name = self.card_data.get("model") or self.card_data.get("note_type") or "Carte"
        title_lbl = QLabel(f"Éditer la carte — {model_name}")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 14px; font-weight: 700; border: none; background: transparent;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Zone scrollable pour héberger dynamiquement N champs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        fields_layout = QVBoxLayout(scroll_content)
        fields_layout.setContentsMargins(0, 0, 8, 0)
        fields_layout.setSpacing(10)

        self.field_edits: dict[str, StyledTextEdit] = {}

        for i, field_name in enumerate(ordered_fields):
            lbl = QLabel(f"{field_name} :")
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px; border: none; background: transparent;")
            fields_layout.addWidget(lbl)

            edit = StyledTextEdit()
            raw_val = self.card_data.get(field_name, "")
            edit.setPlainText(str(raw_val) if raw_val is not None else "")
            edit.setFixedHeight(95)
            self.field_edits[field_name] = edit
            fields_layout.addWidget(edit)

            # Rétrocompatibilité pour edit_front et edit_back
            if i == 0:
                self.edit_front = edit
            elif i == 1:
                self.edit_back = edit

        if "Front" not in self.field_edits and not hasattr(self, "edit_front"):
            self.edit_front = list(self.field_edits.values())[0] if self.field_edits else StyledTextEdit()
        if "Back" not in self.field_edits and not hasattr(self, "edit_back"):
            self.edit_back = list(self.field_edits.values())[1] if len(self.field_edits) > 1 else self.edit_front

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        btn_save = PrimaryButton("Enregistrer")
        btn_save.setIcon(load_phosphor_icon("ph.check", color="white"))
        btn_save.clicked.connect(self.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def get_fields(self) -> dict[str, str]:
        """Retourne l'ensemble des champs modifiés sous forme de dictionnaire."""
        return {f_name: edit.toPlainText().strip() for f_name, edit in self.field_edits.items()}

    def get_data(self) -> tuple[str, str]:
        """Méthode rétrocompatible retournant le premier et le second champ."""
        vals = list(self.get_fields().values())
        return (vals[0] if len(vals) > 0 else "", vals[1] if len(vals) > 1 else "")
