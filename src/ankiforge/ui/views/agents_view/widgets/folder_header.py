from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ankiforge.ui.components import Badge
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class FolderHeaderWidget(QWidget):
    """Widget représentant la ligne d'un dossier ou sous-dossier dans l'arbre."""

    def __init__(self, name: str, count: int, is_root: bool = False, is_subfolder: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(30)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 6, 3)
        layout.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(18, 18)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if is_root:
            icon_name = "ph.tray"
            icon_color = DesignTokens.TEXT_MUTED
        elif is_subfolder:
            icon_name = "ph.folder-simple"
            icon_color = DesignTokens.ACCENT_PRIMARY
        else:
            icon_name = "ph.folder"
            icon_color = DesignTokens.COLOR_YELLOW

        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(15, 15))
        layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        lbl_name = QLabel(name)
        font_weight = "bold" if not is_subfolder else "600"
        font_size = "12px" if not is_subfolder else "11.5px"
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: {font_weight}; font-size: {font_size}; background: transparent;")
        layout.addWidget(lbl_name, 1)

        badge_count = Badge(f"{count}", variant="neutral")
        badge_count.setFixedHeight(18)
        layout.addWidget(badge_count, alignment=Qt.AlignmentFlag.AlignVCenter)
