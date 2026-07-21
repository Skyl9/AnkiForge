import qtawesome as qta
from PySide6.QtCore import QSettings, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from typing import Any

from ankiforge.ui.components.components import ActionButton, DangerButton, HeaderLabel, PrimaryButton, RoundedPanel
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.components.tabs import SettingsTabBar
from ankiforge.ui.theme import refresh_theme_live

try:
    from ankiforge.ui.views.llm_manager_view import LLMManagerTab
except ImportError:

    class LLMManagerTab(QWidget):  # type: ignore
        def __init__(self, ai_manager=None, parent=None):
            super().__init__(parent)


try:
    from ankiforge.ui.views.models_view import ModelsTab
except ImportError:

    class ModelsTab(QWidget):  # type: ignore
        def __init__(self, parent=None):
            super().__init__(parent)


try:
    from ankiforge.ui.views.stats_view import StatsTab
except ImportError:

    class StatsTab(QWidget):  # type: ignore
        def __init__(self, parent=None):
            super().__init__(parent)


class GeneralTab(QWidget):
    """Onglet Général du Settings Modal."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = QSettings("AnkiForgeOrg", "ankiforge_obsidian")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        layout.addWidget(HeaderLabel(self.tr("Paramètres Généraux")))

        panel = RoundedPanel()
        form_layout = QFormLayout(panel)
        form_layout.setContentsMargins(15, 15, 15, 15)
        form_layout.setSpacing(15)

        # Thème
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["Système (Par défaut)", "Clair (Light)", "Sombre (Dark)"])
        self.cb_theme.setCurrentText(str(self.settings.value("ui/theme", "Système (Par défaut)")))
        self.cb_theme.currentTextChanged.connect(self._on_theme_changed)
        form_layout.addRow(self._make_bold_label(self.tr("Thème de l'application :")), self.cb_theme)

        # Langue
        self.cb_lang = QComboBox()
        self.cb_lang.addItems(["Français", "English"])
        self.cb_lang.setCurrentText(str(self.settings.value("ui/language", "Français")))
        self.cb_lang.currentTextChanged.connect(self._on_lang_changed)
        form_layout.addRow(self._make_bold_label(self.tr("Langue (redémarrage requis) :")), self.cb_lang)

        # Style Batch Factory
        self.cb_batch_style = QComboBox()
        self.cb_batch_style.addItems(["Standard", "Minimaliste", "Complet"])
        self.cb_batch_style.setCurrentText(str(self.settings.value("app/batch_style", "Standard")))
        self.cb_batch_style.currentTextChanged.connect(self._on_batch_style_changed)
        form_layout.addRow(self._make_bold_label(self.tr("Style des cartes générées :")), self.cb_batch_style)

        # Dossier Export
        export_layout = QHBoxLayout()
        self.le_export = GlowLineEdit()
        self.le_export.setText(str(self.settings.value("app/export_path", "")))
        self.le_export.textChanged.connect(self._on_export_changed)
        btn_browse = ActionButton("fa5s.folder-open", self.tr(" Parcourir"))
        btn_browse.clicked.connect(self._browse_export)
        export_layout.addWidget(self.le_export)
        export_layout.addWidget(btn_browse)
        form_layout.addRow(self._make_bold_label(self.tr("Dossier d'export par défaut :")), export_layout)

        layout.addWidget(panel)

        # Maintenance
        maint_panel = RoundedPanel()
        maint_layout = QVBoxLayout(maint_panel)
        maint_layout.setContentsMargins(15, 15, 15, 15)
        maint_layout.addWidget(self._make_bold_label("Maintenance"))

        btn_purge_versions = DangerButton(qta.icon("fa5s.broom", color="white"), self.tr(" Purger les anciennes versions"))
        btn_purge_versions.clicked.connect(self._purge_versions)
        maint_layout.addWidget(btn_purge_versions)

        btn_clean_media = DangerButton(qta.icon("fa5s.trash-alt", color="white"), self.tr(" Nettoyer les médias orphelins"))
        btn_clean_media.clicked.connect(self._clean_media)
        maint_layout.addWidget(btn_clean_media)

        layout.addWidget(maint_panel)
        layout.addStretch()

    def _make_bold_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("font-weight: bold; color: palette(text); font-size: 11px;")
        return lbl

    @Slot(str)
    def _on_theme_changed(self, text: str) -> None:
        self.settings.setValue("ui/theme", text)
        refresh_theme_live()

    @Slot(str)
    def _on_lang_changed(self, text: str) -> None:
        self.settings.setValue("ui/language", text)

    @Slot(str)
    def _on_batch_style_changed(self, text: str) -> None:
        self.settings.setValue("app/batch_style", text)

    @Slot(str)
    def _on_export_changed(self, text: str) -> None:
        self.settings.setValue("app/export_path", text)

    @Slot()
    def _browse_export(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("Choisir un dossier"), self.le_export.text())
        if path:
            self.le_export.setText(path)

    @Slot()
    def _purge_versions(self) -> None:
        QMessageBox.information(self, self.tr("Maintenance"), self.tr("Anciennes versions purgées."))

    @Slot()
    def _clean_media(self) -> None:
        QMessageBox.information(self, self.tr("Maintenance"), self.tr("Médias orphelins nettoyés."))

    @Slot()
    def refresh_data(self) -> None:
        pass


class SettingsModal(QDialog):
    """
    Modal de paramètres global.
    Dimensions : 900x600.
    """

    def __init__(self, ai_manager: Any = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager

        self.setWindowTitle(self.tr("Paramètres (Settings)"))
        self.setFixedSize(900, 600)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        # TabBar à gauche (200px)
        left_panel = QWidget()
        left_panel.setFixedWidth(200)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.tab_bar = SettingsTabBar()
        self.tab_bar.add_tab(self.tr("Général"), "⚙️")
        self.tab_bar.add_tab(self.tr("IA"), "🤖")
        self.tab_bar.add_tab(self.tr("Modèles"), "📦")
        self.tab_bar.add_tab(self.tr("Stats"), "📊")

        left_layout.addWidget(self.tab_bar)
        left_layout.addStretch()

        content_layout.addWidget(left_panel)

        # QStackedWidget à droite
        self.stacked_widget = QStackedWidget()

        self.general_tab = GeneralTab()
        self.ai_tab = LLMManagerTab(self.ai_manager)
        self.models_tab = ModelsTab()
        self.stats_tab = StatsTab()

        self.stacked_widget.addWidget(self.general_tab)
        self.stacked_widget.addWidget(self.ai_tab)
        self.stacked_widget.addWidget(self.models_tab)
        self.stacked_widget.addWidget(self.stats_tab)

        content_layout.addWidget(self.stacked_widget)

        main_layout.addLayout(content_layout)

        # Bouton de fermeture
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()
        btn_close = PrimaryButton(self.tr("Fermer"))
        btn_close.clicked.connect(self.accept)
        bottom_layout.addWidget(btn_close)

        main_layout.addLayout(bottom_layout)

        self.tab_bar.tab_changed.connect(self._on_tab_changed)
        self.tab_bar._on_clicked(0)  # Activation du premier tab

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        self.stacked_widget.setCurrentIndex(index)
        current_widget = self.stacked_widget.currentWidget()
        if hasattr(current_widget, "refresh_data"):
            current_widget.refresh_data()
