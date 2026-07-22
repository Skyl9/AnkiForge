from typing import Any
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
        self.setStyleSheet("""
            DashboardHeroBanner {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 rgba(99, 102, 241, 0.12), stop:1 rgba(139, 92, 246, 0.04));
                border: 1px solid rgba(139, 92, 246, 0.2);
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(12)

        icon_label = QLabel()
        icon = load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY)
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel('Bienvenue dans <span style="color: %s;">AnkiForge</span>' % DesignTokens.ACCENT_PRIMARY)
        font = QFont(DesignTokens.FONT_MAIN, 24, QFont.Weight.Bold)
        title.setFont(font)
        title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Le générateur de cartes intelligent et votre assistant d'apprentissage personnel.")
        subtitle.setFont(QFont(DesignTokens.FONT_MAIN, 13))
        subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        apply_shadow(self, blur=20, offset_y=4, color="rgba(0, 0, 0, 0.2)")


class DashboardActionButton(QFrame):
    clicked = Signal()

    def __init__(self, title, subtitle, icon_name, color, bg_color, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            DashboardActionButton {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            DashboardActionButton:hover {{
                background-color: #2d313a;
                border: 1px solid #6366f1;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        icon_wrapper = QFrame()
        icon_wrapper.setFixedSize(48, 48)
        icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_wrapper)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label = QLabel()
        icon = load_phosphor_icon(icon_name, color=color)
        icon_label.setPixmap(icon.pixmap(24, 24))
        icon_layout.addWidget(icon_label)

        layout.addWidget(icon_wrapper)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setFont(QFont(DesignTokens.FONT_MAIN, 14, QFont.Weight.Bold))
        title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        text_layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setFont(QFont(DesignTokens.FONT_MAIN, 12))
        subtitle_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; border: none; background: transparent;")
        text_layout.addWidget(subtitle_label)

        layout.addLayout(text_layout)
        layout.addStretch()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ActivityItem(QFrame):
    def __init__(self, title, subtitle, icon_name, bg_color, parent=None):
        super().__init__(parent)
        self.setStyleSheet("border: none; background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)

        icon_wrapper = QFrame()
        icon_wrapper.setFixedSize(32, 32)
        icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 16px;
            }}
        """)
        icon_layout = QVBoxLayout(icon_wrapper)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_label = QLabel()
        icon = load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY)
        icon_label.setPixmap(icon.pixmap(16, 16))
        icon_layout.addWidget(icon_label)

        layout.addWidget(icon_wrapper)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Medium))
        title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        text_layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        subtitle_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED};")
        text_layout.addWidget(subtitle_label)

        layout.addLayout(text_layout)
        layout.addStretch()


class DashboardDropZone(QFrame):
    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"""
            DashboardDropZone {{
                background-color: {DesignTokens.BG_MAIN};
                border: 2px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            DashboardDropZone:hover {{
                border: 2px dashed {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        icon_label = QLabel()
        icon = load_phosphor_icon("ph.upload-simple", color=DesignTokens.ACCENT_PRIMARY)
        icon_label.setPixmap(icon.pixmap(40, 40))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(icon_label)

        title = QLabel("Glissez un PDF ou Document ici")
        title.setFont(QFont(DesignTokens.FONT_MAIN, 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("L'analyse sémantique et la génération démarreront automatiquement.")
        subtitle.setFont(QFont(DesignTokens.FONT_MAIN, 13))
        subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        self.btn = SecondaryButton("Parcourir les fichiers")
        self.btn.clicked.connect(self._browse_files)
        layout.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignCenter)

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
        self.setStyleSheet(f"""
            StatItem {{
                background-color: #1e2128;
                border: 1px solid #2d313a;
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

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

        lbl_label = QLabel(label.upper())
        lbl_label.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        lbl_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_label)

    def set_value(self, value):
        self.val_label.setText(str(value))


class DashboardView(QWidget):
    request_navigation = Signal(str)

    def __init__(self, ai_manager: Any = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.setup_ui()

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

        content_layout.addWidget(DashboardHeroBanner())

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

        btn1 = DashboardActionButton("Forger des cartes", "Depuis un document", "ph.hammer", DesignTokens.COLOR_BLUE, "rgba(59, 130, 246, 0.1)")
        btn1.clicked.connect(lambda: self.request_navigation.emit("creation"))
        btn2 = DashboardActionButton("Bibliothèque", "Naviguer les paquets", "ph.books", DesignTokens.COLOR_GREEN, "rgba(16, 185, 129, 0.1)")
        btn2.clicked.connect(lambda: self.request_navigation.emit("documents"))
        btn3 = DashboardActionButton("Consulter l'IA", "Configurer les agents", "ph.robot", DesignTokens.COLOR_PURPLE, "rgba(139, 92, 246, 0.1)")
        btn3.clicked.connect(lambda: self.request_navigation.emit("consultant"))

        actions_layout.addWidget(btn1)
        actions_layout.addWidget(btn2)
        actions_layout.addWidget(btn3)
        content_layout.addLayout(actions_layout)

        drop_zone = DashboardDropZone()
        drop_zone.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        drop_zone.file_selected.connect(self._on_file_selected)
        content_layout.addWidget(drop_zone, 1)

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
        self.stat_default_model = StatItem("3.5", "Modèle par défaut", DesignTokens.COLOR_PURPLE)

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
        activity_layout.setContentsMargins(16, 16, 16, 16)
        activity_layout.setSpacing(8)

        self.activity_list_layout = QVBoxLayout()
        self.activity_list_layout.setSpacing(8)
        activity_layout.addLayout(self.activity_list_layout)

        activity_layout.addStretch()

        view_all_btn = SecondaryButton("Voir tout l'historique")
        activity_layout.addWidget(view_all_btn)

        activity_panel.add_tab("Activité Récente", activity_widget, icon_name="ph.clock-counter-clockwise", closable=True)
        activity_panel.set_active_tab(0)
        right_container.addWidget(activity_panel)

        splitter.addWidget(right_container)

        right_container.setSizes([180, 300])
        right_container.setCollapsible(0, True)
        right_container.setCollapsible(1, True)
        right_container.setStretchFactor(0, 1)
        right_container.setStretchFactor(1, 1)

        splitter.setSizes([800, 320])
        splitter.setCollapsible(0, True)
        splitter.setCollapsible(1, True)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

    def refresh_data(self):
        self.worker = StatsWorker()
        self.worker.stats_loaded.connect(self._on_stats_loaded)
        self.worker.feed_loaded.connect(self._on_feed_loaded)
        self.worker.start()

    def _on_file_selected(self, file_path: str):
        # We navigate to creation view and maybe pass the file path later
        self.request_navigation.emit("creation")

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
            # Clear previous items
            while self.activity_list_layout.count():
                item = self.activity_list_layout.takeAt(0)
                if item:
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()

            for item in feed:
                title = f"Note #{item['note_id']} (v{item['version']})"
                time_desc = f"{item['created_at']} via {item['source']}"
                icon = "ph.sparkle" if item["source"] == "ai" else "ph.cards"
                color = DesignTokens.COLOR_BLUE if item["source"] == "ai" else DesignTokens.COLOR_GREEN
                self.activity_list_layout.addWidget(ActivityItem(title, time_desc, icon, color))
        except RuntimeError:
            pass

    def is_dirty(self) -> bool:
        return False
