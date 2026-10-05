"""Dialogue unifié pour ajouter ou modifier les paramètres d'un modèle IA (LLMConfigModel)."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel, db
from ankiforge.services.ai.model_catalog import ModelCatalog, ModelSpec
from ankiforge.ui.components import (
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ModelConfigDialog(QDialog):
    """Boîte de dialogue permettant d'ajouter ou de modifier la configuration d'un moteur IA."""

    def __init__(
        self,
        config: LLMConfigModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._is_new = config is None
        self._setup_ui()
        self._populate_fields()

    def _setup_ui(self) -> None:
        title = "Nouveau Moteur IA" if self._is_new else f"Modifier le Moteur — {self.config.display_name if self.config else ''}"
        self.setWindowTitle(title)
        self.setMinimumWidth(540)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # ── En-tête ──
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.cpu", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        lbl_title = QLabel(self.tr("Configuration du Moteur IA"))
        lbl_title.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(lbl_title)

        lbl_sub = QLabel(self.tr("Paramétrez les identifiants, capacités et plafonds d'inférence du modèle."))
        lbl_sub.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(lbl_sub)
        header_row.addLayout(title_col, 1)

        # Menu préréglages depuis catalogue
        self.btn_preset = SecondaryButton("Pré-remplir ▾")
        self.btn_preset.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.TEXT_PRIMARY))
        self.btn_preset.setToolTip(self.tr("Remplir automatiquement les champs avec un modèle du catalogue officiel"))
        self._setup_preset_menu()
        header_row.addWidget(self.btn_preset)

        layout.addLayout(header_row)

        # ── Formulaire principal ──
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Nom affiché
        self.le_display_name = StyledLineEdit(placeholder=self.tr("Ex: Google Gemini 2.5 Flash Lite"))
        form.addRow(self._make_label("Nom affiché :"), self.le_display_name)

        # Fournisseur
        self.cb_provider = StyledComboBox()
        self.cb_provider.setEditable(True)
        providers = [
            ("Google Gemini", "gemini"),
            ("OpenAI", "openai"),
            ("Anthropic", "anthropic"),
            ("Ollama (Local)", "ollama"),
            ("Groq", "groq"),
            ("OpenCode", "opencode"),
            ("OpenRouter", "openrouter"),
        ]
        for label, p_id in providers:
            self.cb_provider.addItem(label, p_id)
        form.addRow(self._make_label("Fournisseur :"), self.cb_provider)

        # Identifiant Modèle
        self.le_model_id = StyledLineEdit(placeholder=self.tr("Ex: gemini-2.5-flash-lite"))
        form.addRow(self._make_label("ID Modèle (API) :"), self.le_model_id)

        # Grille Contexte & Tokens & Température
        metrics_grid = QGridLayout()
        metrics_grid.setHorizontalSpacing(12)
        metrics_grid.setVerticalSpacing(4)
        spin_style = f"background-color: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 2px 6px;"

        # Limite Contexte
        lbl_ctx = QLabel(self.tr("Limite Contexte (tokens) :"))
        lbl_ctx.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        self.spin_context = QSpinBox()
        self.spin_context.setRange(1024, 10_000_000)
        self.spin_context.setSingleStep(4096)
        self.spin_context.setValue(128000)
        self.spin_context.setFixedHeight(30)
        self.spin_context.setStyleSheet(spin_style)
        metrics_grid.addWidget(lbl_ctx, 0, 0)
        metrics_grid.addWidget(self.spin_context, 1, 0)

        # Max Tokens Génération
        lbl_max = QLabel(self.tr("Plafond Génération (max tokens) :"))
        lbl_max.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        self.spin_max_tokens = QSpinBox()
        self.spin_max_tokens.setRange(256, 1_000_000)
        self.spin_max_tokens.setSingleStep(1024)
        self.spin_max_tokens.setValue(16384)
        self.spin_max_tokens.setFixedHeight(30)
        self.spin_max_tokens.setStyleSheet(spin_style)
        metrics_grid.addWidget(lbl_max, 0, 1)
        metrics_grid.addWidget(self.spin_max_tokens, 1, 1)

        # Température
        lbl_temp = QLabel(self.tr("Température par défaut :"))
        lbl_temp.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; font-weight: 500;")
        self.spin_temp = QDoubleSpinBox()
        self.spin_temp.setRange(0.0, 2.0)
        self.spin_temp.setSingleStep(0.05)
        self.spin_temp.setValue(0.70)
        self.spin_temp.setDecimals(2)
        self.spin_temp.setFixedHeight(30)
        self.spin_temp.setStyleSheet(spin_style)
        metrics_grid.addWidget(lbl_temp, 0, 2)
        metrics_grid.addWidget(self.spin_temp, 1, 2)

        form.addRow(self._make_label("Paramètres d'inférence :"), metrics_grid)

        # Options et Capacités (Checkboxes)
        caps_grid = QGridLayout()
        caps_grid.setHorizontalSpacing(16)
        caps_grid.setVerticalSpacing(8)

        self.chk_vision = QCheckBox(self.tr("Vision multimodale (analyse d'images)"))
        self.chk_vision.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        caps_grid.addWidget(self.chk_vision, 0, 0)

        self.chk_thinking = QCheckBox(self.tr("Raisonnement approfondi (Thinking / CoT)"))
        self.chk_thinking.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        caps_grid.addWidget(self.chk_thinking, 0, 1)

        self.chk_free = QCheckBox(self.tr("Modèle gratuit / inclus / local"))
        self.chk_free.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        caps_grid.addWidget(self.chk_free, 1, 0)

        self.chk_json = QCheckBox(self.tr("Sorties structurées JSON"))
        self.chk_json.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px;")
        self.chk_json.setChecked(True)
        caps_grid.addWidget(self.chk_json, 1, 1)

        form.addRow(self._make_label("Capacités supportées :"), caps_grid)

        # Description / Cas d'usage
        self.le_description = StyledLineEdit(placeholder=self.tr("Ex: Modèle rapide et économique pour l'extraction de fiches."))
        form.addRow(self._make_label("Description / Notes :"), self.le_description)

        layout.addLayout(form)

        # Label d'erreur
        self.lbl_error = QLabel()
        self.lbl_error.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 11px; font-weight: bold;")
        self.lbl_error.hide()
        layout.addWidget(self.lbl_error)

        layout.addStretch()

        # ── Boutons d'action ──
        btn_box = QHBoxLayout()
        btn_box.setSpacing(10)
        btn_box.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        save_label = "Ajouter le Moteur" if self._is_new else "Enregistrer les modifications"
        btn_save = PrimaryButton(save_label)
        btn_save.clicked.connect(self._on_save)
        btn_box.addWidget(btn_save)

        layout.addLayout(btn_box)

    def _setup_preset_menu(self) -> None:
        """Construit le menu déroulant des préréglages depuis le catalogue officiel."""
        menu = QMenu(self)
        menu.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY};")

        curated = ModelCatalog.get_curated_catalog()
        by_provider: dict[str, list[ModelSpec]] = {}
        for spec in curated:
            by_provider.setdefault(spec.provider, []).append(spec)

        for prov, specs in by_provider.items():
            prov_menu = menu.addMenu(prov.upper())
            for spec in specs:
                action = prov_menu.addAction(spec.display_name)
                action.triggered.connect(lambda _, s=spec: self._apply_spec(s))

        self.btn_preset.setMenu(menu)

    def _apply_spec(self, spec: ModelSpec) -> None:
        """Pré-remplit les champs avec la spécification choisie."""
        self.le_display_name.setText(spec.display_name)
        idx = self.cb_provider.findData(spec.provider)
        if idx >= 0:
            self.cb_provider.setCurrentIndex(idx)
        else:
            self.cb_provider.setEditText(spec.provider)
        self.le_model_id.setText(spec.model_id)
        self.spin_context.setValue(spec.context_window)
        self.spin_max_tokens.setValue(spec.max_tokens)
        self.chk_vision.setChecked(spec.supports_vision)
        self.chk_thinking.setChecked(spec.supports_thinking)
        self.chk_free.setChecked(spec.is_free or spec.provider == "ollama")
        self.chk_json.setChecked(spec.supports_json)
        self.le_description.setText(spec.ankiforge_use_case or spec.description)

    def _populate_fields(self) -> None:
        """Remplit les champs si une configuration existante est fournie."""
        if self.config is not None:
            self.le_display_name.setText(str(self.config.display_name or ""))
            prov = str(self.config.provider or "").lower()
            idx = self.cb_provider.findData(prov)
            if idx >= 0:
                self.cb_provider.setCurrentIndex(idx)
            else:
                self.cb_provider.setEditText(prov)
            self.le_model_id.setText(str(self.config.model_id or ""))
            self.spin_context.setValue(int(self.config.context_limit or 128000))
            self.spin_max_tokens.setValue(int(self.config.max_tokens or 16384))
            temp_val = float(self.config.temperature) if self.config.temperature is not None else 0.70
            self.spin_temp.setValue(temp_val)
            self.chk_vision.setChecked(bool(self.config.supports_vision))
            self.chk_thinking.setChecked(bool(self.config.supports_thinking))
            self.chk_free.setChecked(bool(self.config.is_free or prov == "ollama"))
            self.chk_json.setChecked(bool(self.config.supports_json if self.config.supports_json is not None else True))
            self.le_description.setText(str(self.config.description or ""))
        else:
            self.chk_json.setChecked(True)
            self.spin_context.setValue(128000)
            self.spin_max_tokens.setValue(16384)
            self.spin_temp.setValue(0.70)

    def _make_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        return lbl

    def _on_save(self) -> None:
        """Valide et enregistre la configuration en base de données."""
        display_name = self.le_display_name.text().strip()
        model_id = self.le_model_id.text().strip()
        provider = self.cb_provider.currentData() or self.cb_provider.currentText().strip().lower()

        if not display_name:
            self.lbl_error.setText(self.tr("Le nom affiché est obligatoire."))
            self.lbl_error.show()
            self.le_display_name.setFocus()
            return

        if not model_id:
            self.lbl_error.setText(self.tr("L'identifiant du modèle est obligatoire."))
            self.lbl_error.show()
            self.le_model_id.setFocus()
            return

        # Vérifier l'unicité du nom d'affichage
        if self._is_new:
            exists = LLMConfigModel.select().where(LLMConfigModel.display_name == display_name).exists()
        else:
            exists = LLMConfigModel.select().where((LLMConfigModel.display_name == display_name) & (LLMConfigModel.id != (self.config.id if self.config else 0))).exists()

        if exists:
            self.lbl_error.setText(tr("Un modèle nommé '%1' existe déjà.", display_name))
            self.lbl_error.show()
            return

        try:
            with db.atomic():
                if self._is_new:
                    spec = ModelCatalog.get_model_spec(provider, model_id)
                    self.config = LLMConfigModel.create(
                        display_name=display_name,
                        provider=provider,
                        model_id=model_id,
                        context_limit=self.spin_context.value(),
                        max_tokens=self.spin_max_tokens.value(),
                        temperature=round(self.spin_temp.value(), 2),
                        sort_order=50,
                        is_free=self.chk_free.isChecked(),
                        supports_vision=self.chk_vision.isChecked(),
                        supports_thinking=self.chk_thinking.isChecked(),
                        supports_json=self.chk_json.isChecked(),
                        speed_rating=spec.speed_rating if spec else "fast",
                        quality_tier=spec.quality_tier if spec else "standard",
                        recommended_tasks=",".join(spec.recommended_tasks) if spec else "[]",
                        description=self.le_description.text().strip() or (spec.description if spec else ""),
                    )
                elif self.config is not None:
                    self.config.display_name = display_name
                    self.config.provider = provider
                    self.config.model_id = model_id
                    self.config.context_limit = self.spin_context.value()
                    self.config.max_tokens = self.spin_max_tokens.value()
                    self.config.temperature = round(self.spin_temp.value(), 2)
                    self.config.is_free = self.chk_free.isChecked()
                    self.config.supports_vision = self.chk_vision.isChecked()
                    self.config.supports_thinking = self.chk_thinking.isChecked()
                    self.config.supports_json = self.chk_json.isChecked()
                    self.config.description = self.le_description.text().strip()
                    self.config.save()

            from ankiforge.utils.event_bus import LLMModelsChangedEvent, event_bus

            event_bus.publish(
                LLMModelsChangedEvent(
                    action="created" if self._is_new else "updated",
                    model_id=model_id,
                    provider=provider,
                )
            )

            self.accept()
        except Exception as e:
            logger.error("Erreur lors de l'enregistrement du modèle : %s", e)
            self.lbl_error.setText(tr("Erreur d'enregistrement : %1", e))
            self.lbl_error.show()

    def get_config(self) -> LLMConfigModel | None:
        """Retourne la configuration créée ou modifiée."""
        return self.config


__all__ = ["ModelConfigDialog"]
