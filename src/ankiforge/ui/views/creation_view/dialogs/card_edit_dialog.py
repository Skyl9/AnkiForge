from typing import Optional
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens


class CardEditDialog(QDialog):
    """Dialogue d'édition rapide d'une carte générée."""

    def __init__(self, front: str, back: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Éditer la carte")
        self.setMinimumWidth(500)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_front = QLabel("Recto :")
        lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.edit_front = StyledTextEdit()
        self.edit_front.setPlainText(front)
        self.edit_front.setFixedHeight(100)

        lbl_back = QLabel("Verso :")
        lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.edit_back = StyledTextEdit()
        self.edit_back.setPlainText(back)
        self.edit_back.setFixedHeight(120)

        layout.addWidget(lbl_front)
        layout.addWidget(self.edit_front)
        layout.addWidget(lbl_back)
        layout.addWidget(self.edit_back)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        btn_save = PrimaryButton("Enregistrer")
        btn_save.clicked.connect(self.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def get_data(self) -> tuple[str, str]:
        return self.edit_front.toPlainText().strip(), self.edit_back.toPlainText().strip()
