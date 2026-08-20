from typing import Any, Optional
from peewee import fn
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QSplitter, QScrollArea, QGridLayout, QSizePolicy, QFileDialog
from PySide6.QtCore import Qt, QThread, Slot, Signal
from PySide6.QtGui import QFont

from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.components import IdePanel, SecondaryButton
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.database.models import NoteModel, CardModel, DeckModel, TokenUsageModel, NoteVersionModel


class StatsWorker(QThread):
    stats_loaded = Signal(dict)
    feed_loaded = Signal(list)

    def run(self):
        try:
            notes_count = NoteModel.select().count()
            cards_count = CardModel.select().count()
            decks_count = DeckModel.select().count()
            cost_query = TokenUsageModel.select(fn.SUM(TokenUsageModel.estimated_cost_usd)).scalar()
            cost = cost_query if cost_query else 0.0

            self.stats_loaded.emit({"notes": notes_count, "cards": cards_count, "decks": decks_count, "cost": cost})

            feed_items = []
            recent_versions = NoteVersionModel.select(NoteVersionModel, NoteModel).join(NoteModel).order_by(NoteVersionModel.created_at.desc()).limit(10)

            for version in recent_versions:
                feed_items.append({"note_id": version.note.id, "source": version.source, "created_at": version.created_at.strftime("%Y-%m-%d %H:%M"), "version": version.version_number})
            self.feed_loaded.emit(feed_items)
        except Exception:
            # Si la DB n'est pas encore initialisée ou autre erreur
            pass  # nosec B110


class DashboardHeroBanner(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(180)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        self.icon_label = QLabel()
        icon = load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY)
        self.icon_label.setPixmap(icon.pixmap(48, 48))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_label)

        self.title = QLabel('Bienvenue dans <span style="color: %s;">AnkiForge</span>' % DesignTokens.ACCENT_PRIMARY)
        font = QFont(DesignTokens.FONT_MAIN, 24, QFont.Weight.Bold)
        self.title.setFont(font)
        self.title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.subtitle = QLabel("Le générateur de cartes intelligent et votre assistant d'apprentissage personnel.")
        self.subtitle.setFont(QFont(DesignTokens.FONT_MAIN, 13))
        self.subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        apply_shadow(self, blur=20, offset_y=4, color="rgba(0, 0, 0, 0.2)")

    def refresh_theme(self, profile: Any) -> None:
        self.icon_label.setPixmap(load_phosphor_icon("ph.stack", color=profile.accent_primary).pixmap(48, 48))
        self.title.setText('Bienvenue dans <span style="color: %s;">AnkiForge</span>' % profile.accent_primary)
        self.title.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class DashboardActionButton(QFrame):
    clicked = Signal()

    def __init__(self, title, subtitle, icon_name, color, bg_color, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_name = icon_name
        self.color = color
        self.bg_color = bg_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        self.icon_wrapper = QFrame()
        self.icon_wrapper.setFixedSize(48, 48)
        self.icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
                border: none;
            }}
        """)
        icon_layout = QVBoxLayout(self.icon_wrapper)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label = QLabel()
        icon = load_phosphor_icon(icon_name, color=color)
        self.icon_label.setPixmap(icon.pixmap(24, 24))
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        icon_layout.addWidget(self.icon_label)

        layout.addWidget(self.icon_wrapper)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont(DesignTokens.FONT_MAIN, 14, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        text_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(QFont(DesignTokens.FONT_MAIN, 12))
        self.subtitle_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        text_layout.addWidget(self.subtitle_label)

        layout.addLayout(text_layout)
        layout.addStretch()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def refresh_theme(self, profile: Any) -> None:
        self.title_label.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle_label.setStyleSheet(f"color: {profile.text_muted}; font-size: 12px; border: none; background: transparent;")


class ActivityItem(QFrame):
    clicked = Signal(int)

    def __init__(self, note_id: int, title: str, subtitle: str, icon_name: str, bg_color: str, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        icon_wrapper = QFrame()
        icon_wrapper.setFixedSize(32, 32)
        icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 16px;
                border: none;
            }}
        """)
        icon_layout = QVBoxLayout(icon_wrapper)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon = load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY)
        icon_label.setPixmap(icon.pixmap(16, 16))
        icon_label.setStyleSheet("border: none; background: transparent;")
        icon_layout.addWidget(icon_label)

        layout.addWidget(icon_wrapper)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        self.subtitle_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        text_layout.addWidget(self.subtitle_label)

        layout.addLayout(text_layout, 1)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.note_id)
        super().mouseReleaseEvent(event)

    def refresh_theme(self, profile: Any) -> None:
        self.title_label.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle_label.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class DashboardDropZone(QFrame):
    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        self.icon_label = QLabel()
        icon = load_phosphor_icon("ph.upload-simple", color=DesignTokens.ACCENT_PRIMARY)
        self.icon_label.setPixmap(icon.pixmap(40, 40))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_label)

        self.title = QLabel("Glissez un PDF ou Document ici")
        self.title.setFont(QFont(DesignTokens.FONT_MAIN, 16, QFont.Weight.Bold))
        self.title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.subtitle = QLabel("L'analyse sémantique et la génération démarreront automatiquement.")
        self.subtitle.setFont(QFont(DesignTokens.FONT_MAIN, 13))
        self.subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        self.btn = SecondaryButton("Parcourir les fichiers")
        self.btn.clicked.connect(self._browse_files)
        layout.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignCenter)

    def refresh_theme(self, profile: Any) -> None:
        self.icon_label.setPixmap(load_phosphor_icon("ph.upload-simple", color=profile.accent_primary).pixmap(40, 40))
        self.title.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")

    def _browse_files(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Sélectionner un document", "", "Documents (*.pdf *.txt *.md);;Tous les fichiers (*.*)")
        if file_path:
            self.file_selected.emit(file_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.file_selected.emit(urls[0].toLocalFile())


class StatItem(QFrame):
    def __init__(self, value, label, value_color=None, parent=None):
        super().__init__(parent)
        self.value_color = value_color

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)
        layout.setContentsMargins(16, 16, 16, 16)

        self.val_label = QLabel(value)
        self.val_label.setFont(QFont(DesignTokens.FONT_MAIN, 20, QFont.Weight.Bold))
        color = value_color if value_color else DesignTokens.TEXT_PRIMARY
        self.val_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        self.val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.val_label)

        self.lbl_label = QLabel(label.upper())
        self.lbl_label.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        self.lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.lbl_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_label)

    def set_value(self, value):
        self.val_label.setText(str(value))

    def refresh_theme(self, profile: Any) -> None:
        color = self.value_color if self.value_color else profile.text_primary
        self.val_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        self.lbl_label.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class DashboardView(QWidget):
    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.setup_ui()

    def _navigate(self, view_id: str, data: Optional[dict] = None) -> None:
        self.request_navigation.emit(view_id, data)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: transparent;
            }
        """)
        main_layout.addWidget(splitter)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_panel = IdePanel(detachable=True)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(24)

        self.hero_banner = DashboardHeroBanner()
        content_layout.addWidget(self.hero_banner)

        actions_header = QHBoxLayout()
        actions_icon = QLabel()
        actions_icon.setPixmap(load_phosphor_icon("ph.lightning", color=DesignTokens.TEXT_PRIMARY).pixmap(16, 16))
        actions_title = QLabel("Actions Rapides")
        actions_title.setFont(QFont(DesignTokens.FONT_MAIN, 16, QFont.Weight.Bold))
        actions_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        actions_header.addWidget(actions_icon)
        actions_header.addWidget(actions_title)
        actions_header.addStretch()
        content_layout.addLayout(actions_header)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(16)

        self.btn_forge = DashboardActionButton("Forger des cartes", "Depuis un document", "ph.hammer", DesignTokens.COLOR_BLUE, DesignTokens.BG_ACTIVE)
        self.btn_forge.clicked.connect(lambda: self._navigate("creation"))
        self.btn_library = DashboardActionButton("Bibliothèque", "Naviguer les paquets", "ph.books", DesignTokens.COLOR_GREEN, DesignTokens.BG_ACTIVE)
        self.btn_library.clicked.connect(lambda: self._navigate("documents"))
        self.btn_consultant = DashboardActionButton("Consulter l'IA", "Configurer les agents", "ph.robot", DesignTokens.ACCENT_PRIMARY, DesignTokens.BG_ACTIVE)
        self.btn_consultant.clicked.connect(lambda: self._navigate("consultant"))

        actions_layout.addWidget(self.btn_forge)
        actions_layout.addWidget(self.btn_library)
        actions_layout.addWidget(self.btn_consultant)
        content_layout.addLayout(actions_layout)

        self.drop_zone = DashboardDropZone()
        self.drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.drop_zone.file_selected.connect(self._on_file_selected)
        content_layout.addWidget(self.drop_zone, 1)

        scroll_area.setWidget(content_widget)
        left_panel.add_tab("Accueil", scroll_area, icon_name="ph.house", closable=True)
        left_panel.set_active_tab(0)

        left_layout.addWidget(left_panel)
        splitter.addWidget(left_container)

        right_container = QSplitter(Qt.Orientation.Vertical)
        right_container.setMinimumWidth(240)

        stats_panel = IdePanel(detachable=True)
        stats_widget = QWidget()
        stats_layout = QGridLayout(stats_widget)
        stats_layout.setContentsMargins(16, 16, 16, 16)
        stats_layout.setSpacing(12)

        self.stat_cards_forged = StatItem("1,245", "Cartes Forgées")
        self.stat_success_rate = StatItem("98%", "Taux Succès IA", DesignTokens.COLOR_GREEN)
        self.stat_docs_analyzed = StatItem("14", "Docs Analysés")
        self.stat_default_model = StatItem("3.5", "Modèle par défaut", DesignTokens.ACCENT_PRIMARY)

        stats_layout.addWidget(self.stat_cards_forged, 0, 0)
        stats_layout.addWidget(self.stat_success_rate, 0, 1)
        stats_layout.addWidget(self.stat_docs_analyzed, 1, 0)
        stats_layout.addWidget(self.stat_default_model, 1, 1)

        stats_panel.add_tab("Statistiques", stats_widget, icon_name="ph.chart-line-up", closable=True)
        stats_panel.set_active_tab(0)
        right_container.addWidget(stats_panel)

        activity_panel = IdePanel(detachable=True)
        activity_widget = QWidget()
        activity_layout = QVBoxLayout(activity_widget)
        activity_layout.setContentsMargins(12, 12, 12, 12)
        activity_layout.setSpacing(8)

        # Zone responsive avec scrollarea
        activity_scroll = QScrollArea()
        activity_scroll.setWidgetResizable(True)
        activity_scroll.setFrameShape(QFrame.Shape.NoFrame)
        activity_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        activity_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        activity_inner = QWidget()
        activity_inner.setStyleSheet("background: transparent;")
        self.activity_list_layout = QVBoxLayout(activity_inner)
        self.activity_list_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_list_layout.setSpacing(8)
        self.activity_list_layout.addStretch(1)

        activity_scroll.setWidget(activity_inner)
        activity_layout.addWidget(activity_scroll, 1)

        view_all_btn = SecondaryButton("Voir tout l'historique")
        view_all_btn.clicked.connect(lambda: self._navigate("edition"))
        activity_layout.addWidget(view_all_btn)

        activity_panel.add_tab("Activité Récente", activity_widget, icon_name="ph.clock-counter-clockwise", closable=True)
        activity_panel.set_active_tab(0)
        right_container.addWidget(activity_panel)

        splitter.addWidget(right_container)

        right_container.setSizes([220, 380])
        right_container.setCollapsible(0, True)
        right_container.setCollapsible(1, True)
        right_container.setStretchFactor(0, 1)
        right_container.setStretchFactor(1, 2)

        splitter.setSizes([900, 360])
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, True)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    def refresh_data(self):
        self.worker = StatsWorker()
        self.worker.stats_loaded.connect(self._on_stats_loaded)
        self.worker.feed_loaded.connect(self._on_feed_loaded)
        self.worker.start()

    def _on_file_selected(self, file_path: str):
        # We navigate to creation view and maybe pass the file path later
        self._navigate("creation")

    def _on_activity_card_clicked(self, note_id: int) -> None:
        self._navigate("edition", {"note_id": note_id})

    @Slot(dict)
    def _on_stats_loaded(self, stats: dict) -> None:
        try:
            cards_val = f"{stats['cards']:,}"
            docs_val = str(stats["notes"])

            self.stat_cards_forged.set_value(cards_val)
            self.stat_docs_analyzed.set_value(docs_val)
            # Keeps success rate and model as mockup defaults unless DB has complex tracking later
        except RuntimeError:
            pass

    @Slot(list)
    def _on_feed_loaded(self, feed: list) -> None:
        try:
            # Vider les éléments précédents sauf le stretch final
            while self.activity_list_layout.count() > 1:
                item = self.activity_list_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            for item in feed:
                note_id = item["note_id"]
                title = f"Note #{note_id} (v{item['version']})"
                time_desc = f"{item['created_at']} via {item['source']}"
                icon = "ph.sparkle" if item["source"] == "ai" else "ph.cards"
                color = DesignTokens.COLOR_BLUE if item["source"] == "ai" else DesignTokens.COLOR_GREEN

                act_widget = ActivityItem(note_id, title, time_desc, icon, color)
                act_widget.clicked.connect(self._on_activity_card_clicked)
                self.activity_list_layout.insertWidget(self.activity_list_layout.count() - 1, act_widget)
        except RuntimeError:
            pass

    def is_dirty(self) -> bool:
        return False

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit à chaud tous les composants du tableau de bord."""
        if hasattr(self, "hero_banner") and hasattr(self.hero_banner, "refresh_theme"):
            self.hero_banner.refresh_theme(profile)
        if hasattr(self, "btn_forge") and hasattr(self.btn_forge, "refresh_theme"):
            self.btn_forge.refresh_theme(profile)
        if hasattr(self, "btn_library") and hasattr(self.btn_library, "refresh_theme"):
            self.btn_library.refresh_theme(profile)
        if hasattr(self, "btn_consultant") and hasattr(self.btn_consultant, "refresh_theme"):
            self.btn_consultant.refresh_theme(profile)
        if hasattr(self, "drop_zone") and hasattr(self.drop_zone, "refresh_theme"):
            self.drop_zone.refresh_theme(profile)
        if hasattr(self, "stat_cards_forged") and hasattr(self.stat_cards_forged, "refresh_theme"):
            self.stat_cards_forged.refresh_theme(profile)
        if hasattr(self, "stat_success_rate") and hasattr(self.stat_success_rate, "refresh_theme"):
            self.stat_success_rate.refresh_theme(profile)
        if hasattr(self, "stat_docs_analyzed") and hasattr(self.stat_docs_analyzed, "refresh_theme"):
            self.stat_docs_analyzed.refresh_theme(profile)
        if hasattr(self, "stat_default_model") and hasattr(self.stat_default_model, "refresh_theme"):
            self.stat_default_model.refresh_theme(profile)
