import logging
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget

from ankiforge.ui.components.components import RoundedPanel, PrimaryButton
from ankiforge.ui.components.buttons import SecondaryButton

logger = logging.getLogger(__name__)


class DropZone(RoundedPanel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl = QLabel("Glissez-déposez vos fichiers ici\nou cliquez pour parcourir")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: palette(placeholder-text); font-size: 14px;")
        lbl.setContentsMargins(40, 40, 40, 40)
        layout.addWidget(lbl)


class BatchWizardView(QWidget):
    """
    Card Factory View (Batch Processing) - Wizard Variant.
    Allows processing documents via a step-by-step wizard.
    """

    def __init__(self, ai_manager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.current_step = 0
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(20)

        self.stepper_label = QLabel(self.tr("Step 1 (●)──(○)──(○)"))
        self.stepper_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stepper_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.main_layout.addWidget(self.stepper_label)
        self.main_layout.addSpacing(20)

        self.stack = QStackedWidget()

        # Step 1: Upload
        step1 = QWidget()
        s1_layout = QVBoxLayout(step1)
        self.drop_zone = DropZone()
        s1_layout.addWidget(self.drop_zone)
        self.stack.addWidget(step1)

        # Step 2: Config
        step2 = QWidget()
        s2_layout = QVBoxLayout(step2)
        s2_layout.addWidget(QLabel("Configuration des options AI..."))
        self.stack.addWidget(step2)

        # Step 3: Launch/Process
        step3 = QWidget()
        s3_layout = QVBoxLayout(step3)
        s3_layout.addWidget(QLabel("Traitement en cours / Terminé"))
        self.stack.addWidget(step3)

        self.main_layout.addWidget(self.stack)

        # Bottom controls
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_prev = SecondaryButton(self.tr("← Précédent"))
        self.btn_prev.clicked.connect(self.prev_step)
        self.btn_next = PrimaryButton(None, self.tr("Suivant →"))
        self.btn_next.clicked.connect(self.next_step)

        btn_layout.addWidget(self.btn_prev)
        btn_layout.addWidget(self.btn_next)
        self.main_layout.addLayout(btn_layout)

        self.update_step_ui()

    def update_step_ui(self) -> None:
        self.stack.setCurrentIndex(self.current_step)
        self.btn_prev.setVisible(self.current_step > 0)
        self.btn_next.setVisible(self.current_step < self.stack.count() - 1)

        dots = ["(○)"] * self.stack.count()
        dots[self.current_step] = "(●)"
        self.stepper_label.setText(f"Step {self.current_step + 1} " + "──".join(dots))

    def next_step(self) -> None:
        if self.current_step < self.stack.count() - 1:
            self.current_step += 1
            self.update_step_ui()

    def prev_step(self) -> None:
        if self.current_step > 0:
            self.current_step -= 1
            self.update_step_ui()

    @Slot()
    def refresh_data(self) -> None:
        pass
