import qtawesome as qta
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ankiforge.ui.components.components import ActionButton, PrimaryButton


class TourBubble(QWidget):
    """La bulle d'information flottante qui guide l'utilisateur."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window

        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(400)

        self.current_step = 0
        self.steps = []

        self._setup_ui()
        self.hide()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        self.bg_frame = QWidget()
        self.bg_frame.setObjectName("TourBubbleBg")  # CRUCIAL : Empêche le CSS de fuiter sur les enfants
        self.bg_frame.setStyleSheet("""
            QWidget#TourBubbleBg {
                background-color: palette(base);
                border: 2px solid palette(highlight);
                border-radius: 12px;
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 8)
        self.bg_frame.setGraphicsEffect(shadow)

        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(25, 25, 25, 20)
        bg_layout.setSpacing(15)

        self.lbl_title = QLabel("Titre")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: bold; color: palette(highlight); border: none;")
        bg_layout.addWidget(self.lbl_title)

        self.lbl_text = QLabel("Description...")
        self.lbl_text.setStyleSheet("font-size: 14px; color: palette(text); border: none;")
        self.lbl_text.setWordWrap(True)
        bg_layout.addWidget(self.lbl_text)
        bg_layout.addSpacing(10)

        # --- BARRE DE BOUTONS ---
        btn_layout = QHBoxLayout()

        self.btn_skip = ActionButton("fa5s.times", self.tr(" Quitter"))
        self.btn_skip.clicked.connect(self.end_tour)
        btn_layout.addWidget(self.btn_skip)

        btn_layout.addStretch()

        self.btn_prev = ActionButton("fa5s.arrow-left", self.tr(" Retour"))
        self.btn_prev.clicked.connect(self.prev_step)
        btn_layout.addWidget(self.btn_prev)

        self.lbl_counter = QLabel("1/x")
        self.lbl_counter.setStyleSheet("color: palette(placeholder-text); font-weight: bold; font-size: 12px; padding: 0 8px; border: none;")
        self.lbl_counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        btn_layout.addWidget(self.lbl_counter)

        self.btn_next = PrimaryButton("Suivant ")
        self.btn_next.clicked.connect(self.next_step)
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

        # --- Gestion de l'état des boutons ---
        self.btn_prev.setVisible(self.current_step > 0)

        if self.current_step == len(self.steps) - 1:
            self.btn_next.setText(self.tr(" Terminer"))
            self.btn_next.setIcon(qta.icon("fa5s.check", color="white"))
        else:
            self.btn_next.setText(self.tr(" Suivant"))
            self.btn_next.setIcon(qta.icon("fa5s.arrow-right", color="white"))

        if "action" in step_data and callable(step_data["action"]):
            step_data["action"]()

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

            x = target_pos.x() + target_widget.width() + 15
            y = target_pos.y()

            screen_rect = self.screen().availableGeometry()
            if y + self.height() > screen_rect.bottom():
                y = screen_rect.bottom() - self.height() - 15

            self.move(x, y)

    def prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self.play_step()

    def next_step(self):
        self.current_step += 1
        self.play_step()

    def end_tour(self):
        self.hide()
        self.main_window.settings.setValue("app/tour_completed", True)
