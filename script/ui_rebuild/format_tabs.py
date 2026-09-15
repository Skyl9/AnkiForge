import re

with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/tabs.py", "r") as f:
    content = f.read()

# remove the duplicated imports from the bottom
content = re.sub(
    r"from PySide6\.QtWidgets import \(\n    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup, \n    QScrollArea, QApplication, QFrame\n\)\nfrom PySide6\.QtCore import Signal, Qt, QMimeData, QPoint, QPropertyAnimation\nfrom PySide6\.QtGui import QDrag, QDropEvent, QDragEnterEvent, QDragMoveEvent, QMouseEvent, QPainter, QColor, QPen\nfrom ankiforge\.ui\.theme import DesignTokens\nfrom ankiforge\.utils\.icon_loader import load_phosphor_icon\n",
    "",
    content,
)

# modify the top imports
content = content.replace(
    "from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup",
    "from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QButtonGroup, QScrollArea, QApplication, QFrame",
)
content = content.replace("from PySide6.QtCore import Signal, Qt", "from PySide6.QtCore import Signal, Qt, QMimeData, QPoint")
content = content.replace(
    "from ankiforge.ui.theme import DesignTokens",
    "from ankiforge.ui.theme import DesignTokens\nfrom ankiforge.utils.icon_loader import load_phosphor_icon\nfrom PySide6.QtGui import QDrag, QDropEvent, QDragEnterEvent, QDragMoveEvent, QMouseEvent, QPainter, QColor, QPen",
)

with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/tabs.py", "w") as f:
    f.write(content)
