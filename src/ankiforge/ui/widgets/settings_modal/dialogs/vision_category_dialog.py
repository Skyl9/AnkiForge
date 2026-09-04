import logging
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.vision_category_service import VisionCategory
from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class VisionCategoryDialog(QDialog):
    """Boîte de dialogue permettant d'ajouter ou modifier une catégorie d'IA de vision."""

    def __init__(
        self,
        category: VisionCategory | None = None,
        available_models: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.category = category
        self.available_models = available_models or []
        self._is_new = category is None
        self._setup_ui()
        self._populate_fields()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Modifier la Catégorie de Vision" if not self._is_new else "Nouvelle Catégorie de Vision")
        self.setMinimumWidth(520)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # En-tête
        header_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_name = self.category.icon if self.category else "ph.sparkle"
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Configuration de la Catégorie d'Analyse d'Image")
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        header_row.addWidget(title_lbl, 1)
        layout.addLayout(header_row)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Nom
        self.le_name = StyledLineEdit(placeholder="Ex: Raisonnement Visuel Complexe")
        form.addRow(self._make_label("Nom de la catégorie :"), self.le_name)

        # Description
        self.le_desc = StyledLineEdit(placeholder="Ex: Formules mathématiques et schémas scientifiques")
        form.addRow(self._make_label("Description :"), self.le_desc)

        # Fournisseur
        self.combo_provider = QComboBox()
        self.combo_provider.setFixedHeight(32)
        self.combo_provider.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 4px 8px;"
        )
        self.combo_provider.addItem("Anthropic (Claude 3.7)", "anthropic")
        self.combo_provider.addItem("Google Gemini (Flash / Pro)", "gemini")
        self.combo_provider.addItem("Ollama Local (Qwen2.5-VL)", "ollama")
        self.combo_provider.addItem("OpenAI (GPT-4o)", "openai")
        self.combo_provider.addItem("Natif Matériel macOS (Apple Vision)", "native")
        self.combo_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow(self._make_label("Fournisseur d'IA :"), self.combo_provider)

        # Identifiant Modèle
        self.le_model_id = StyledLineEdit(placeholder="Ex: claude-3-7-sonnet-20250219")
        form.addRow(self._make_label("Modèle Cible :"), self.le_model_id)

        # Budget de Réflexion (Thinking Tokens)
        self.spin_thinking = QSpinBox()
        self.spin_thinking.setRange(0, 16384)
        self.spin_thinking.setSingleStep(1024)
        self.spin_thinking.setFixedHeight(30)
        self.spin_thinking.setSuffix(" tokens")
        self.spin_thinking.setToolTip("Alloué pour le mode Thinking de Claude 3.7 (0 pour désactiver le raisonnement pas-à-pas)")
        self.spin_thinking.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 2px 6px;"
        )
        form.addRow(self._make_label("Budget Thinking :"), self.spin_thinking)

        # Température
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 1.0)
        self.spin_temp.setSingleStep(0.05)
        self.spin_temp.setFixedHeight(30)
        self.spin_temp.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 2px 6px;"
        )
        form.addRow(self._make_label("Température :"), self.spin_temp)

        # Directives spécialisées
        self.te_instructions = StyledTextEdit()
        self.te_instructions.setFixedHeight(80)
        self.te_instructions.setPlaceholderText("Instructions optionnelles injectées au prompt système pour cette catégorie...")
        form.addRow(self._make_label("Directives IA :"), self.te_instructions)

        layout.addLayout(form)

        # Boutons d'action
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = PrimaryButton("Enregistrer")
        self.btn_save.setIcon(load_phosphor_icon("ph.check", color="#ffffff"))
        self.btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"font-size: 11.5px; font-weight: 500; color: {DesignTokens.TEXT_MUTED};")
        return lbl

    def _populate_fields(self) -> None:
        if self.category:
            self.le_name.setText(self.category.name)
            self.le_desc.setText(self.category.description)
            idx = self.combo_provider.findData(self.category.provider)
            if idx >= 0:
                self.combo_provider.setCurrentIndex(idx)
            self.le_model_id.setText(self.category.model_id)
            self.spin_thinking.setValue(self.category.thinking_budget)
            self.spin_temp.setValue(self.category.temperature)
            self.te_instructions.setPlainText(self.category.custom_instructions)
        else:
            self.le_name.setText("")
            self.le_desc.setText("")
            self.combo_provider.setCurrentIndex(0)
            self.le_model_id.setText("claude-3-7-sonnet-20250219")
            self.spin_thinking.setValue(2048)
            self.spin_temp.setValue(0.2)
            self.te_instructions.setPlainText("")

    def _on_provider_changed(self, index: int) -> None:
        prov = self.combo_provider.currentData()
        if prov == "native":
            self.le_model_id.setText("apple_vision")
            self.le_model_id.setEnabled(False)
            self.spin_thinking.setValue(0)
            self.spin_thinking.setEnabled(False)
        else:
            self.le_model_id.setEnabled(True)
            self.spin_thinking.setEnabled(prov == "anthropic")
            if prov == "anthropic" and not self.le_model_id.text().startswith("claude"):
                self.le_model_id.setText("claude-3-7-sonnet-20250219")
                self.spin_thinking.setValue(2048)
            elif prov == "gemini" and not self.le_model_id.text().startswith("gemini"):
                self.le_model_id.setText("gemini-2.5-flash")
                self.spin_thinking.setValue(0)
            elif prov == "ollama" and not self.le_model_id.text().startswith("qwen"):
                self.le_model_id.setText("qwen2.5-vl:7b")
                self.spin_thinking.setValue(0)

    def _on_save(self) -> None:
        name = self.le_name.text().strip()
        if not name:
            self.le_name.setFocus()
            return

        cat_id = self.category.id if self.category else f"cat_{uuid.uuid4().hex[:8]}"
        icon = self.category.icon if self.category else "ph.sparkle"

        self.category = VisionCategory(
            id=cat_id,
            name=name,
            description=self.le_desc.text().strip(),
            icon=icon,
            provider=str(self.combo_provider.currentData()),
            model_id=self.le_model_id.text().strip(),
            thinking_budget=self.spin_thinking.value(),
            temperature=self.spin_temp.value(),
            custom_instructions=self.te_instructions.toPlainText().strip(),
        )
        self.accept()

    def get_category(self) -> VisionCategory | None:
        """Retourne la catégorie configurée après acceptation de la boîte de dialogue."""
        return self.category
