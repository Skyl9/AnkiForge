import qtawesome as qta
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QGraphicsOpacityEffect


class Toast(QWidget):
    def __init__(self, parent: QWidget, message: str, color: str = "#4CAF50", icon_name: str = "fa5s.check"):
        super().__init__(parent)

        # Le rend "flottant" (pas de bordure, passe au-dessus du reste)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Layout principal
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Le fond coloré
        self.bg_frame = QWidget(self)
        self.bg_frame.setStyleSheet(f"""
            QWidget {{
                background-color: {color};
                border-radius: 8px;
            }}
            QLabel {{
                color: white;
                font-weight: bold;
                font-size: 14px;
            }}
        """)

        bg_layout = QHBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(15, 10, 15, 10)

        # Icône
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon(icon_name, color="white").pixmap(20, 20))
        bg_layout.addWidget(icon_label)

        # Texte
        text_label = QLabel(message)
        bg_layout.addWidget(text_label)

        layout.addWidget(self.bg_frame)

        # Effet d'opacité pour l'animation
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0)

        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(300)  # 300 ms de fondu
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Timer d'auto-destruction
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.hide_toast)

    def show_toast(self, duration=2500):
        self.adjustSize()
        parent = self.parent()
        if parent:
            # 1. Calcul des coordonnées locales relatives à la fenêtre parente
            local_x = parent.width() // 2 - self.width() // 2
            local_y = parent.height() - self.height() - 40

            global_pos = parent.mapToGlobal(QPoint(local_x, local_y))
            self.move(global_pos)

        self.show()
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
        self.timer.start(duration)

    def hide_toast(self):
        self.timer.stop()
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.deleteLater)  # Nettoie la mémoire
        self.animation.start()


def show_toast(parent: QWidget, message: str, is_error: bool = False):
    """Fonction utilitaire à importer partout dans tes vues."""
    color = "#F44336" if is_error else "#4CAF50"
    icon = "fa5s.exclamation-triangle" if is_error else "fa5s.check"
    toast = Toast(parent, message, color, icon)
    toast.show_toast()
