import json
import logging
import urllib.request
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LLMConfigModel
from ankiforge.services.ai.vision_category_service import VisionCategory, VisionCategoryService
from ankiforge.services.settings_service import SettingsService
from ankiforge.ui.components import (
    DangerButton,
    SecondaryButton,
    StyledLineEdit,
    StyledTableWidget,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.settings_modal.components.password_line_edit import PasswordLineEdit
from ankiforge.ui.widgets.settings_modal.components.settings_card import (
    SettingsCard,
    apply_pill_badge_style,
)
from ankiforge.ui.widgets.settings_modal.dialogs.vision_category_dialog import VisionCategoryDialog
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class AIEnginesTab(QWidget):
    """Onglet Configuration des Moteurs IA, Clés API et Catégories de Vision d'Image."""

    def __init__(self, ai_manager: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.lbl_provider_labels: list[QLabel] = []
        self.vision_cards: list[SettingsCard] = []
        self._setup_ui()
        self.refresh_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Zone défilante pour garantir l'absence de débordement
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("background: transparent; border: none;")

        self.content_widget = QWidget()
        layout = QVBoxLayout(self.content_widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── SECTION 1 : CLÉS D'AUTHENTIFICATION CLOUD ────────────────────────
        self.lbl_sec_keys = QLabel("CLÉS D'AUTHENTIFICATION FOURNISSEURS CLOUD")
        self.lbl_sec_keys.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        layout.addWidget(self.lbl_sec_keys)

        self.card_keys = SettingsCard()
        keys_layout = QVBoxLayout(self.card_keys)
        keys_layout.setContentsMargins(14, 10, 14, 10)
        keys_layout.setSpacing(8)

        self.key_edits: dict[str, PasswordLineEdit] = {}
        self.key_status_badges: dict[str, QLabel] = {}

        providers_cfg = [
            ("openai", "OpenAI", "sk-proj-...", "ph.brain"),
            ("anthropic", "Anthropic", "sk-ant-...", "ph.sparkle"),
            ("gemini", "Gemini", "AIzaSy...", "ph.sparkle"),
            ("groq", "Groq", "gsk_...", "ph.lightning"),
        ]

        for p_id, p_name, placeholder, p_icon in providers_cfg:
            row = QHBoxLayout()
            row.setSpacing(8)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(load_phosphor_icon(p_icon, color=DesignTokens.ACCENT_PRIMARY).pixmap(15, 15))
            row.addWidget(icon_lbl)

            lbl = QLabel(f"{p_name} :")
            lbl.setMinimumWidth(85)
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
            row.addWidget(lbl)
            self.lbl_provider_labels.append(lbl)

            initial_key = str(SettingsService.get(f"keys/{p_id}", ""))
            p_edit = PasswordLineEdit(placeholder=placeholder, initial_text=initial_key)
            self.key_edits[p_id] = p_edit
            row.addWidget(p_edit, 1)

            btn_test = SecondaryButton("Tester")
            btn_test.setFixedHeight(28)
            btn_test.setIcon(load_phosphor_icon("ph.check-circle", color=DesignTokens.TEXT_MUTED))
            btn_test.clicked.connect(lambda _, pid=p_id, pname=p_name: self._test_cloud_key(pid, pname))
            row.addWidget(btn_test)

            badge_st = QLabel("")
            badge_st.hide()
            self.key_status_badges[p_id] = badge_st
            row.addWidget(badge_st)

            keys_layout.addLayout(row)

        layout.addWidget(self.card_keys)

        # ── SECTION 2 : SERVEUR LOCAL OLLAMA ─────────────────────────────────
        self.lbl_sec_ollama = QLabel("SERVEUR LOCAL OLLAMA (ZÉRO CLOUD)")
        self.lbl_sec_ollama.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_ollama)

        self.card_ollama = SettingsCard()
        ollama_layout = QHBoxLayout(self.card_ollama)
        ollama_layout.setContentsMargins(14, 10, 14, 10)
        ollama_layout.setSpacing(10)

        lbl_ol_icon = QLabel()
        lbl_ol_icon.setPixmap(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_GREEN).pixmap(16, 16))
        ollama_layout.addWidget(lbl_ol_icon)

        self.lbl_ol_url = QLabel("URL Serveur :")
        self.lbl_ol_url.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        ollama_layout.addWidget(self.lbl_ol_url)

        self.le_ollama_url = StyledLineEdit()
        self.le_ollama_url.setFixedHeight(28)
        self.le_ollama_url.setText(str(SettingsService.get("ollama/url", "http://localhost:11434")))
        ollama_layout.addWidget(self.le_ollama_url, 1)

        self.btn_scan_ollama = SecondaryButton("Scanner les modèles installés")
        self.btn_scan_ollama.setFixedHeight(28)
        self.btn_scan_ollama.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.COLOR_GREEN))
        self.btn_scan_ollama.clicked.connect(self._scan_ollama)
        ollama_layout.addWidget(self.btn_scan_ollama)

        self.badge_ollama_status = QLabel("")
        self.badge_ollama_status.hide()
        ollama_layout.addWidget(self.badge_ollama_status)

        layout.addWidget(self.card_ollama)

        # ── SECTION 3 : CATALOGUE DES MOTEURS IA ─────────────────────────────
        self.lbl_sec_cat = QLabel("CATALOGUE DES MOTEURS & MODÈLES TEXTUELS (Peewee ORM)")
        self.lbl_sec_cat.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        layout.addWidget(self.lbl_sec_cat)

        self.table_engines = StyledTableWidget(["Nom du Moteur", "Fournisseur", "Identifiant Modèle", "Gratuit / Local"])
        self.table_engines.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_engines.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table_engines.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table_engines.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table_engines.itemChanged.connect(self._on_table_item_changed)
        self.table_engines.setMinimumHeight(140)
        layout.addWidget(self.table_engines)

        # Barre d'outils Catalogue
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self.btn_add_ollama = SecondaryButton("+ Ollama Local")
        self.btn_add_ollama.setIcon(load_phosphor_icon("ph.cpu", color=DesignTokens.COLOR_GREEN))
        self.btn_add_ollama.clicked.connect(lambda: self._quick_add_engine("Ollama Local", "ollama", "llama3:latest", True))
        toolbar.addWidget(self.btn_add_ollama)

        self.btn_add_openai = SecondaryButton("+ GPT-4o")
        self.btn_add_openai.setIcon(load_phosphor_icon("ph.brain", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_openai.clicked.connect(lambda: self._quick_add_engine("GPT-4o (OpenAI)", "openai", "gpt-4o", False))
        toolbar.addWidget(self.btn_add_openai)

        self.btn_add_gemini = SecondaryButton("+ Gemini Flash")
        self.btn_add_gemini.setIcon(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_BLUE))
        self.btn_add_gemini.clicked.connect(lambda: self._quick_add_engine("Google Gemini 2.5 Flash", "gemini", "gemini-2.5-flash", True))
        toolbar.addWidget(self.btn_add_gemini)

        toolbar.addStretch()

        self.btn_del_engine = DangerButton("Supprimer", ghost=True)
        self.btn_del_engine.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_del_engine.clicked.connect(self._del_engine)
        toolbar.addWidget(self.btn_del_engine)

        layout.addLayout(toolbar)

        # ── SECTION 4 : CATÉGORIES D'IA DE RECONNAISSANCE D'IMAGE (VISION) ───
        self.lbl_sec_vision = QLabel("CATÉGORIES D'IA DE RECONNAISSANCE D'IMAGE (STANDARDS 2025-2026)")
        self.lbl_sec_vision.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 6px;")
        layout.addWidget(self.lbl_sec_vision)

        self.vision_container = QVBoxLayout()
        self.vision_container.setSpacing(8)
        layout.addLayout(self.vision_container)

        # Barre d'outils Vision
        vision_toolbar = QHBoxLayout()
        vision_toolbar.setSpacing(8)

        self.btn_add_vision_cat = SecondaryButton("+ Ajouter une catégorie")
        self.btn_add_vision_cat.setIcon(load_phosphor_icon("ph.plus-circle", color=DesignTokens.ACCENT_PRIMARY))
        self.btn_add_vision_cat.clicked.connect(self._add_vision_category)
        vision_toolbar.addWidget(self.btn_add_vision_cat)

        self.btn_reset_vision = SecondaryButton("Rétablir les préréglages")
        self.btn_reset_vision.setIcon(load_phosphor_icon("ph.arrow-counter-clockwise", color=DesignTokens.TEXT_MUTED))
        self.btn_reset_vision.clicked.connect(self._reset_vision_categories)
        vision_toolbar.addWidget(self.btn_reset_vision)

        vision_toolbar.addStretch()
        layout.addLayout(vision_toolbar)

        self.scroll.setWidget(self.content_widget)
        root_layout.addWidget(self.scroll)

    def _render_vision_categories(self) -> None:
        """Génère dynamiquement les cartes de chaque catégorie de vision configurée."""
        # Nettoyage des anciennes cartes
        while self.vision_container.count():
            item = self.vision_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.vision_cards.clear()
        categories = VisionCategoryService.get_categories()

        for cat in categories:
            card = SettingsCard()
            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(12, 10, 12, 10)
            card_layout.setSpacing(10)

            # Icône catégorie
            icon_lbl = QLabel()
            icon_color = DesignTokens.COLOR_GREEN if cat.provider in ("ollama", "native") else DesignTokens.COLOR_BLUE
            icon_lbl.setPixmap(load_phosphor_icon(cat.icon, color=icon_color).pixmap(20, 20))
            card_layout.addWidget(icon_lbl)

            # Contenu texte & badges
            content_col = QVBoxLayout()
            content_col.setSpacing(3)

            title_row = QHBoxLayout()
            title_row.setSpacing(6)

            title_lbl = QLabel(cat.name)
            title_lbl.setStyleSheet(f"font-size: 12.5px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
            title_row.addWidget(title_lbl)

            # Badge Fournisseur
            prov_badge = QLabel(cat.provider.upper())
            apply_pill_badge_style(prov_badge, DesignTokens.COLOR_GREEN if cat.provider in ("ollama", "native") else DesignTokens.COLOR_BLUE)
            title_row.addWidget(prov_badge)

            # Badge Modèle
            model_badge = QLabel(cat.model_id)
            apply_pill_badge_style(model_badge, DesignTokens.TEXT_MUTED)
            title_row.addWidget(model_badge)

            # Badge Thinking si actif
            if cat.thinking_budget > 0:
                thinking_badge = QLabel(f"🧠 {cat.thinking_budget}t")
                apply_pill_badge_style(thinking_badge, DesignTokens.ACCENT_PRIMARY)
                title_row.addWidget(thinking_badge)

            title_row.addStretch()
            content_col.addLayout(title_row)

            desc_lbl = QLabel(cat.description)
            desc_lbl.setWordWrap(True)
            desc_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
            content_col.addWidget(desc_lbl)

            card_layout.addLayout(content_col, 1)

            # Bouton Modifier
            btn_edit = SecondaryButton("Modifier")
            btn_edit.setFixedHeight(28)
            btn_edit.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
            btn_edit.clicked.connect(lambda _, c=cat: self._edit_vision_category(c))
            card_layout.addWidget(btn_edit)

            # Bouton Supprimer (uniquement pour les catégories personnalisées)
            if cat.id not in ("reasoning", "massive", "structured", "hardware"):
                btn_del = DangerButton(ghost=True)
                btn_del.setFixedSize(28, 28)
                btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
                btn_del.clicked.connect(lambda _, cid=cat.id: self._delete_vision_category(cid))
                card_layout.addWidget(btn_del)

            self.vision_container.addWidget(card)
            self.vision_cards.append(card)

    def _edit_vision_category(self, cat: VisionCategory) -> None:
        dialog = VisionCategoryDialog(category=cat, parent=self)
        if dialog.exec():
            updated = dialog.get_category()
            if updated:
                VisionCategoryService.save_category(updated)
                self._render_vision_categories()
                show_toast(self, f"Catégorie '{updated.name}' mise à jour !")

    def _add_vision_category(self) -> None:
        dialog = VisionCategoryDialog(category=None, parent=self)
        if dialog.exec():
            new_cat = dialog.get_category()
            if new_cat:
                VisionCategoryService.save_category(new_cat)
                self._render_vision_categories()
                show_toast(self, f"Catégorie '{new_cat.name}' créée avec succès !")

    def _delete_vision_category(self, cat_id: str) -> None:
        if VisionCategoryService.delete_category(cat_id):
            self._render_vision_categories()
            show_toast(self, "Catégorie de vision supprimée.")

    def _reset_vision_categories(self) -> None:
        VisionCategoryService.reset_to_defaults()
        self._render_vision_categories()
        show_toast(self, "Catégories de vision réinitialisées aux valeurs standard !")

    def _test_cloud_key(self, provider_id: str, provider_name: str) -> None:
        key_edit = self.key_edits.get(provider_id)
        badge = self.key_status_badges.get(provider_id)
        if not key_edit or not badge:
            return

        key_val = key_edit.text()
        if not key_val:
            badge.setText("⚠️ Clé vide")
            apply_pill_badge_style(badge, DesignTokens.COLOR_YELLOW)
            badge.show()
            show_toast(self, f"Veuillez saisir une clé {provider_name}.", is_error=True)
            return

        valid_format = False
        if (
            (provider_id == "openai" and (key_val.startswith("sk-") or len(key_val) > 20))
            or (provider_id == "anthropic" and (key_val.startswith("sk-ant-") or len(key_val) > 20))
            or (provider_id == "gemini" and (key_val.startswith("AIza") or len(key_val) >= 20))
            or (provider_id == "groq" and (key_val.startswith("gsk_") or len(key_val) > 20))
        ):
            valid_format = True
        else:
            valid_format = len(key_val) >= 16

        if valid_format:
            badge.setText("✅ Format valide")
            apply_pill_badge_style(badge, DesignTokens.COLOR_GREEN)
            badge.show()
            show_toast(self, f"Clé {provider_name} enregistrée et validée !")
        else:
            badge.setText("❌ Format suspect")
            apply_pill_badge_style(badge, DesignTokens.COLOR_RED)
            badge.show()

    def _scan_ollama(self) -> None:
        url = self.le_ollama_url.text().strip().rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"http://{url}"
        try:
            req = urllib.request.Request(f"{url}/api/tags", headers={"User-Agent": "AnkiForge"})
            with urllib.request.urlopen(req, timeout=1.2) as resp:  # nosec B310
                data = json.loads(resp.read().decode())
                models = [m.get("name") for m in data.get("models", [])]
                if models:
                    self.badge_ollama_status.setText(f"🟢 {len(models)} modèle(s) détecté(s)")
                    apply_pill_badge_style(self.badge_ollama_status, DesignTokens.COLOR_GREEN)
                    self.badge_ollama_status.show()

                    added_count = 0
                    for m_name in models:
                        if not LLMConfigModel.select().where(LLMConfigModel.model_id == m_name).exists():
                            LLMConfigModel.create(
                                display_name=f"Ollama {m_name}",
                                provider="ollama",
                                model_id=m_name,
                                context_limit=8192,
                                api_key="",
                                is_free=True,
                            )
                            added_count += 1
                    self.refresh_data()
                    show_toast(self, f"Ollama en ligne : {len(models)} modèles scannés (+{added_count} importés) !")
                else:
                    self.badge_ollama_status.setText("🟡 En ligne (0 modèle)")
                    apply_pill_badge_style(self.badge_ollama_status, DesignTokens.COLOR_YELLOW)
                    self.badge_ollama_status.show()
        except Exception:
            self.badge_ollama_status.setText("🔴 Hors ligne")
            apply_pill_badge_style(self.badge_ollama_status, DesignTokens.COLOR_RED)
            self.badge_ollama_status.show()
            show_toast(self, "Serveur Ollama inaccessible sur cette adresse.", is_error=True)

    def refresh_data(self) -> None:
        """Recharge les moteurs IA et les catégories de vision."""
        try:
            self.table_engines.blockSignals(True)
            engines = list(LLMConfigModel.select())
            self.table_engines.setRowCount(len(engines))

            for i, eg in enumerate(engines):
                item_name = QTableWidgetItem(getattr(eg, "display_name", "Inconnu"))
                item_name.setData(Qt.ItemDataRole.UserRole, eg.id)
                self.table_engines.setItem(i, 0, item_name)

                p_text = getattr(eg, "provider", "inconnu").upper()
                self.table_engines.setItem(i, 1, QTableWidgetItem(p_text))

                item_model = QTableWidgetItem(getattr(eg, "model_id", "default"))
                self.table_engines.setItem(i, 2, item_model)

                item_free = QTableWidgetItem()
                item_free.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                item_free.setCheckState(Qt.CheckState.Checked if getattr(eg, "is_free", False) else Qt.CheckState.Unchecked)
                self.table_engines.setItem(i, 3, item_free)

            self.table_engines.blockSignals(False)
        except Exception as e:
            logger.warning("Erreur refresh_data table_engines: %s", e)

        # Rafraîchissement des catégories de vision
        try:
            self._render_vision_categories()
        except Exception as e:
            logger.warning("Erreur refresh_data vision_categories: %s", e)

    def _quick_add_engine(self, name: str, provider: str, model_id: str, is_free: bool) -> None:
        try:
            existing = LLMConfigModel.select().where((LLMConfigModel.provider == provider) & (LLMConfigModel.model_id == model_id)).first()
            if existing:
                show_toast(self, f"Le modèle '{model_id}' est déjà configuré.", is_error=True)
                return

            api_key = self.key_edits.get(provider, PasswordLineEdit()).text() if provider != "ollama" else ""
            LLMConfigModel.create(display_name=name, provider=provider, model_id=model_id, context_limit=128000, api_key=api_key, is_free=is_free)
            self.refresh_data()
            if self.ai_manager and hasattr(self.ai_manager, "reload_provider"):
                self.ai_manager.reload_provider()
            show_toast(self, f"Moteur '{name}' ajouté au catalogue !")
        except Exception as e:
            show_toast(self, f"Erreur lors de l'ajout : {e}", is_error=True)

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        first_item = self.table_engines.item(item.row(), 0)
        if not first_item:
            return
        engine_id = first_item.data(Qt.ItemDataRole.UserRole)
        if not engine_id:
            return
        try:
            config = LLMConfigModel.get_by_id(engine_id)
            if item.column() == 0:
                config.display_name = item.text().strip()
            elif item.column() == 1:
                config.provider = item.text().strip().lower()
            elif item.column() == 2:
                config.model_id = item.text().strip()
            elif item.column() == 3:
                config.is_free = item.checkState() == Qt.CheckState.Checked
            config.save()
            if self.ai_manager and hasattr(self.ai_manager, "reload_provider"):
                self.ai_manager.reload_provider()
        except Exception as e:
            logger.error("Erreur modification moteur: %s", e)

    def _del_engine(self) -> None:
        selected = self.table_engines.selectedItems()
        if not selected:
            show_toast(self, "Veuillez sélectionner un moteur IA à supprimer.", is_error=True)
            return
        row = selected[0].row()
        item = self.table_engines.item(row, 0)
        if not item:
            return
        engine_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            LLMConfigModel.delete_by_id(engine_id)
            self.refresh_data()
            if self.ai_manager and hasattr(self.ai_manager, "reload_provider"):
                self.ai_manager.reload_provider()
            show_toast(self, "Moteur IA supprimé du catalogue.")
        except Exception as e:
            show_toast(self, f"Erreur suppression : {e}", is_error=True)

    def save_tab(self) -> None:
        """Sauvegarde les clés d'API et l'URL Ollama."""
        for p_id, edit in self.key_edits.items():
            SettingsService.set(f"keys/{p_id}", edit.text(), category="api_keys")
        SettingsService.set("ollama/url", self.le_ollama_url.text().strip(), category="ai")

    def refresh_theme(self, profile: Any) -> None:
        self.lbl_sec_keys.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px;")
        self.lbl_sec_ollama.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        self.lbl_sec_cat.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 2px;")
        if hasattr(self, "lbl_sec_vision"):
            self.lbl_sec_vision.setStyleSheet(f"color: {profile.text_muted}; font-size: 10.5px; font-weight: bold; letter-spacing: 0.5px; margin-top: 6px;")

        self.card_keys.refresh_theme(profile)
        self.card_ollama.refresh_theme(profile)

        for card in self.vision_cards:
            card.refresh_theme(profile)

        if hasattr(self, "lbl_ol_url"):
            self.lbl_ol_url.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        for lbl in self.lbl_provider_labels:
            lbl.setStyleSheet(f"color: {profile.text_primary}; font-size: 12px; font-weight: 500;")
        for edit in self.key_edits.values():
            edit.refresh_theme(profile)
        if hasattr(self, "table_engines") and hasattr(self.table_engines, "refresh_theme"):
            self.table_engines.refresh_theme(profile)
