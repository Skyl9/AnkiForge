from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsDropShadowEffect, QApplication

from ankiforge.ui.components.components import PrimaryButton, ActionButton


class TourBubble(QWidget):
    """La bulle d'information flottante qui guide l'utilisateur."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(350)

        self.current_step = 0
        self.steps = []

        self._setup_ui()
        self.hide()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        self.bg_frame = QWidget()
        self.bg_frame.setStyleSheet("""
            QWidget {
                background-color: palette(base);
                border: 2px solid palette(highlight);
                border-radius: 10px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 100))
        shadow.setOffset(0, 5)
        self.bg_frame.setGraphicsEffect(shadow)

        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(20, 20, 20, 20)
        bg_layout.setSpacing(15)

        self.lbl_title = QLabel("Titre")
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: palette(text); border: none;")
        bg_layout.addWidget(self.lbl_title)

        self.lbl_text = QLabel("Description...")
        self.lbl_text.setStyleSheet("font-size: 13px; color: palette(text); border: none; line-height: 1.4;")
        self.lbl_text.setWordWrap(True)
        bg_layout.addWidget(self.lbl_text)

        btn_layout = QHBoxLayout()
        self.btn_skip = ActionButton("fa5s.times", "Quitter le tour")
        self.btn_skip.clicked.connect(self.end_tour)

        self.lbl_counter = QLabel("1/x")
        self.lbl_counter.setStyleSheet("color: palette(placeholder-text); font-weight: bold; border: none;")

        self.btn_next = PrimaryButton("Suivant")
        self.btn_next.clicked.connect(self.next_step)

        btn_layout.addWidget(self.btn_skip)
        btn_layout.addStretch()
        btn_layout.addWidget(self.lbl_counter)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_next)

        bg_layout.addLayout(btn_layout)
        layout.addWidget(self.bg_frame)

    def set_scenario(self, steps: list[dict]):
        self.steps = steps
        self.current_step = 0

    def start_tour(self):
        if not self.steps:
            return
        self.show()
        self.play_step()

    def play_step(self):
        if self.current_step >= len(self.steps):
            self.end_tour()
            return

        step_data = self.steps[self.current_step]

        self.lbl_title.setText(step_data["title"])
        self.lbl_text.setText(step_data["text"])
        self.lbl_counter.setText(f"{self.current_step + 1}/{len(self.steps)}")

        if self.current_step == len(self.steps) - 1:
            self.btn_next.setText("Terminer")
        else:
            self.btn_next.setText("Suivant")

        if "action" in step_data and callable(step_data["action"]):
            step_data["action"]()

        # Force Qt à recalculer les layouts avant de chercher les coordonnées
        QApplication.processEvents()

        self._position_bubble(step_data.get("target_widget"))

    def _position_bubble(self, target_widget):
        self.adjustSize()

        if target_widget is None:
            parent_geom = self.main_window.geometry()
            x = parent_geom.x() + (parent_geom.width() - self.width()) // 2
            y = parent_geom.y() + (parent_geom.height() - self.height()) // 2
            self.move(x, y)
        else:
            target_pos = target_widget.mapToGlobal(QPoint(0, 0))

            # Position par défaut : à droite du widget cible
            x = target_pos.x() + target_widget.width() + 15
            y = target_pos.y()

            # Sécurité : Si la bulle sort de l'écran par la droite, on la place en dessous
            screen_rect = self.screen().availableGeometry()
            if x + self.width() > screen_rect.right():
                x = target_pos.x()
                y = target_pos.y() + target_widget.height() + 15

            self.move(x, y)

    def next_step(self):
        self.current_step += 1
        self.play_step()

    def end_tour(self):
        self.hide()
        self.main_window.settings.setValue("app/tour_completed", True)
