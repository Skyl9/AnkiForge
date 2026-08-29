import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QSplitter,
    QScrollArea,
    QGridLayout,
    QSizePolicy,
    QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont

from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.components import IdePanel, SecondaryButton, PrimaryButton
from ankiforge.services.audit.metrics_service import MetricsService
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DashboardWorker(QThread):
    """Worker asynchrone pour charger les métriques du cockpit sans bloquer l'UI."""

    data_loaded = Signal(dict)

    def run(self):
        try:
            data = MetricsService.get_full_dashboard_data()
            self.data_loaded.emit(data)
        except Exception:
            logger.exception("Erreur lors du calcul des métriques du tableau de bord")


# Alias rétrocompatible
StatsWorker = DashboardWorker


class DashboardHeroBanner(QFrame):
    """Bandeau d'accueil centré, épuré et agrandi (120px)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(122)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        # Icône carrée arrondie centrée
        self.icon_wrapper = QFrame()
        self.icon_wrapper.setFixedSize(42, 42)
        self.icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-radius: {DesignTokens.RADIUS_MD}px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        icon_layout = QVBoxLayout(self.icon_wrapper)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(load_phosphor_icon("ph.stack", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        icon_layout.addWidget(self.icon_label)
        layout.addWidget(self.icon_wrapper, 0, Qt.AlignmentFlag.AlignCenter)

        # Titre centré agrandi
        self.title = QLabel('Bienvenue dans <span style="color: %s;">AnkiForge</span>' % DesignTokens.ACCENT_PRIMARY)
        self.title.setFont(QFont(DesignTokens.FONT_MAIN, 20, QFont.Weight.Bold))
        self.title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        # Sous-titre centré
        self.subtitle = QLabel("Le générateur de cartes intelligent et votre assistant d'apprentissage personnel.")
        self.subtitle.setFont(QFont(DesignTokens.FONT_MAIN, 12))
        self.subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        apply_shadow(self, blur=14, offset_y=3, color="rgba(0, 0, 0, 0.14)")

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            DashboardHeroBanner {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style()
        self.icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {profile.bg_active};
                border-radius: {profile.radius_md}px;
                border: 1px solid {profile.border_color};
            }}
        """)
        self.icon_label.setPixmap(load_phosphor_icon("ph.stack", color=profile.accent_primary).pixmap(24, 24))
        self.title.setText('Bienvenue dans <span style="color: %s;">AnkiForge</span>' % profile.accent_primary)
        self.title.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class DashboardActionButton(QFrame):
    """Bouton d'action rapide aux proportions soignées et hauteur fixe respectable (84px)."""

    clicked = Signal()

    def __init__(self, title, subtitle, icon_name, color, bg_color, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(84)
        self.icon_name = icon_name
        self.color = color
        self.bg_color = bg_color
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.icon_wrapper = QFrame()
        self.icon_wrapper.setFixedSize(42, 42)
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
        self.icon_label.setPixmap(icon.pixmap(22, 22))
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        icon_layout.addWidget(self.icon_label)

        layout.addWidget(self.icon_wrapper)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addStretch(1)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title_label.setWordWrap(True)
        text_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.subtitle_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; border: none; background: transparent;")
        self.subtitle_label.setWordWrap(True)
        text_layout.addWidget(self.subtitle_label)
        text_layout.addStretch(1)

        layout.addLayout(text_layout, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            DashboardActionButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            DashboardActionButton:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style()
        self.icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {profile.bg_active};
                border-radius: {profile.radius_sm}px;
                border: none;
            }}
        """)
        self.icon_label.setPixmap(load_phosphor_icon(self.icon_name, color=self.color).pixmap(22, 22))
        self.title_label.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle_label.setStyleSheet(f"color: {profile.text_muted}; font-size: 10px; border: none; background: transparent;")


class DiagnosticCardWidget(QFrame):
    """Carte individuelle d'alerte et diagnostic proactif dans le tableau de bord."""

    action_clicked = Signal(str, object)

    def __init__(self, data: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.data = data
        self.severity = data.get("severity", "info")
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Icône d'alerte
        color = DesignTokens.COLOR_BLUE
        if self.severity == "warning":
            color = DesignTokens.COLOR_YELLOW
        elif self.severity == "danger":
            color = DesignTokens.COLOR_RED

        self.icon_label = QLabel()
        icon_name = data.get("icon", "ph.warning-circle")
        self.icon_label.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(22, 22))
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_label)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumWidth(0)

        # Textes (Titre + Message)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.title_lbl = QLabel(data.get("title", "Alerte"))
        self.title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title_lbl.setWordWrap(True)
        self.title_lbl.setMinimumWidth(0)
        self.title_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(self.title_lbl)

        self.msg_lbl = QLabel(data.get("message", ""))
        self.msg_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        self.msg_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setMinimumWidth(0)
        self.msg_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(self.msg_lbl)

        layout.addLayout(text_layout, 1)

        # Bouton d'action proactif 1-clic
        action_label = data.get("action_label", "Voir")
        if self.severity == "warning":
            self.action_btn = PrimaryButton(action_label)
        else:
            self.action_btn = SecondaryButton(action_label)
        self.action_btn.setFixedHeight(30)
        self.action_btn.clicked.connect(self._on_action)
        layout.addWidget(self.action_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _apply_style(self) -> None:
        border_color = DesignTokens.BORDER_COLOR
        left_accent = DesignTokens.COLOR_BLUE
        if self.severity == "warning":
            border_color = DesignTokens.COLOR_YELLOW
            left_accent = DesignTokens.COLOR_YELLOW
        elif self.severity == "danger":
            border_color = DesignTokens.COLOR_RED
            left_accent = DesignTokens.COLOR_RED

        self.setStyleSheet(f"""
            DiagnosticCardWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {border_color};
                border-left: 3px solid {left_accent};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            DiagnosticCardWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

    def _on_action(self) -> None:
        target_view = self.data.get("target_view", "dashboard")
        target_tab = self.data.get("target_tab")
        payload = {"tab": target_tab} if target_tab else None
        self.action_clicked.emit(target_view, payload)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style()
        self.title_lbl.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.msg_lbl.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class ProactiveDiagnosticsWidget(QFrame):
    """Panneau de supervision regroupant les diagnostics et actions proactives."""

    action_clicked = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(8)

        # En-tête
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.header_icon = QLabel()
        self.header_icon.setPixmap(load_phosphor_icon("ph.shield-check", color=DesignTokens.TEXT_PRIMARY).pixmap(16, 16))
        self.header_title = QLabel("Diagnostics & Actions Proactives")
        self.header_title.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        self.header_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        header.addWidget(self.header_icon)
        header.addWidget(self.header_title)
        header.addStretch()
        self.main_layout.addLayout(header)

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.main_layout.addWidget(self.cards_container)

        # État vierge / parfait
        self.empty_card = QFrame()
        self.empty_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {DesignTokens.COLOR_GREEN};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)
        empty_layout = QHBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(16, 12, 16, 12)
        empty_layout.setSpacing(10)
        empty_icon = QLabel()
        empty_icon.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(20, 20))
        empty_layout.addWidget(empty_icon)
        self.empty_text = QLabel("✨ Toutes vos cartes et documents sont conformes et à jour !")
        self.empty_text.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        self.empty_text.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        empty_layout.addWidget(self.empty_text)
        empty_layout.addStretch()

        self.cards_layout.addWidget(self.empty_card)

    def set_diagnostics(self, diagnostics: List[Dict[str, Any]]) -> None:
        """Met à jour les cartes de diagnostics affichées."""
        while self.cards_layout.count() > 0:
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not diagnostics:
            self.cards_layout.addWidget(self.empty_card)
            self.empty_card.show()
        else:
            for diag in diagnostics:
                card = DiagnosticCardWidget(diag, self.cards_container)
                card.action_clicked.connect(self.action_clicked.emit)
                self.cards_layout.addWidget(card)

    def refresh_theme(self, profile: Any) -> None:
        self.header_title.setStyleSheet(f"color: {profile.text_primary};")
        self.empty_text.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class ActivityItem(QFrame):
    """Élément d'activité récente affichant une macro-action ou une note."""

    clicked = Signal(int)

    def __init__(self, note_id: Optional[int], title: str, subtitle: str, icon_name: str, bg_color: str, parent=None):
        super().__init__(parent)
        self.note_id = note_id or 0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumWidth(0)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        icon_wrapper = QFrame()
        icon_wrapper.setFixedSize(34, 34)
        icon_wrapper.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border-radius: 17px;
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
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.title_label = QLabel(title)
        self.title_label.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.subtitle_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMinimumWidth(0)
        self.subtitle_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        text_layout.addWidget(self.subtitle_label)

        layout.addLayout(text_layout, 1)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            ActivityItem {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            ActivityItem:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.note_id)
        super().mouseReleaseEvent(event)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style()
        self.title_label.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle_label.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class DashboardDropZone(QFrame):
    """Zone de glisser-déposer immersive et agrandie prenant la hauteur disponible."""

    file_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(175)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        self.icon_label = QLabel()
        icon = load_phosphor_icon("ph.upload-simple", color=DesignTokens.ACCENT_PRIMARY)
        self.icon_label.setPixmap(icon.pixmap(40, 40))
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        layout.addWidget(self.icon_label)

        self.title = QLabel("Glissez un PDF, Document ou Paquet Anki ici")
        self.title.setFont(QFont(DesignTokens.FONT_MAIN, 14, QFont.Weight.Bold))
        self.title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)

        self.subtitle = QLabel("L'analyse sémantique, l'importation ou la génération démarreront automatiquement.")
        self.subtitle.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        self.subtitle.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.subtitle)

        self.btn = SecondaryButton("Parcourir les fichiers")
        self.btn.setFixedHeight(34)
        self.btn.setMinimumWidth(180)
        self.btn.clicked.connect(self._browse_files)
        layout.addWidget(self.btn, 0, Qt.AlignmentFlag.AlignCenter)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            DashboardDropZone {{
                background-color: {DesignTokens.BG_PANEL};
                border: 2px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            DashboardDropZone:hover {{
                border: 2px dashed {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style()
        self.icon_label.setPixmap(load_phosphor_icon("ph.upload-simple", color=profile.accent_primary).pixmap(36, 36))
        self.title.setStyleSheet(f"color: {profile.text_primary}; border: none; background: transparent;")
        self.subtitle.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")
        if hasattr(self, "btn") and hasattr(self.btn, "refresh_theme"):
            self.btn.refresh_theme(profile)

    def _browse_files(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner un fichier",
            "",
            "Fichiers supportés (*.pdf *.txt *.md *.apkg *.colpkg);;Documents (*.pdf *.txt *.md);;Paquets Anki (*.apkg *.colpkg);;Tous les fichiers (*.*)",
        )
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
    """Tuile KPI anti-troncation avec word-wrap et typographie adaptative."""

    def __init__(self, value, label, value_color=None, parent=None):
        super().__init__(parent)
        self.value_color = value_color
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(3)
        layout.setContentsMargins(10, 10, 10, 10)

        self.val_label = QLabel(value)
        self.val_label.setFont(QFont(DesignTokens.FONT_MAIN, 18, QFont.Weight.Bold))
        color = value_color if value_color else DesignTokens.TEXT_PRIMARY
        self.val_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        self.val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.val_label)

        self.lbl_label = QLabel(label.upper())
        self.lbl_label.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
        self.lbl_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_label.setWordWrap(True)
        layout.addWidget(self.lbl_label)

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            StatItem {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
        """)

    def set_value(self, value: Any, value_color: Optional[str] = None):
        self.val_label.setText(str(value))
        if value_color:
            self.value_color = value_color
            self.val_label.setStyleSheet(f"color: {value_color}; border: none; background: transparent;")

    def refresh_theme(self, profile: Any) -> None:
        self._apply_style()
        color = self.value_color if self.value_color else profile.text_primary
        self.val_label.setStyleSheet(f"color: {color}; border: none; background: transparent;")
        self.lbl_label.setStyleSheet(f"color: {profile.text_muted}; border: none; background: transparent;")


class DashboardView(QWidget):
    request_navigation = Signal(str, object)
    dashboard_data_updated = Signal(dict)

    def __init__(self, ai_manager: Any = None, profile_name: str = "default", parent: QWidget | None = None):
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self._import_dialog: Optional[QWidget] = None
        self._export_dialog: Optional[QWidget] = None
        self.worker: Optional[DashboardWorker] = None
        self.setup_ui()

    def _navigate(self, view_id: str, data: Optional[dict] = None) -> None:
        self.request_navigation.emit(view_id, data)

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # ----------------------------------------------------
        # COLONNE GAUCHE (Forge & Supervision Proactive - 65%)
        # ----------------------------------------------------
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
        content_layout.setContentsMargins(18, 16, 18, 16)
        content_layout.setSpacing(14)

        # 1. Hero Banner centré agrandi (sans profil)
        self.hero_banner = DashboardHeroBanner()
        content_layout.addWidget(self.hero_banner)

        # 2. Actions Rapides élargies (82px)
        actions_header = QHBoxLayout()
        self.actions_icon = QLabel()
        self.actions_icon.setPixmap(load_phosphor_icon("ph.lightning", color=DesignTokens.TEXT_PRIMARY).pixmap(14, 14))
        self.actions_title = QLabel("Actions Rapides")
        self.actions_title.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        self.actions_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        actions_header.addWidget(self.actions_icon)
        actions_header.addWidget(self.actions_title)
        actions_header.addStretch()
        content_layout.addLayout(actions_header)

        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.btn_forge = DashboardActionButton("Forger des cartes", "Depuis un document", "ph.hammer", DesignTokens.COLOR_BLUE, DesignTokens.BG_ACTIVE)
        self.btn_forge.clicked.connect(lambda: self._navigate("creation"))
        self.btn_import = DashboardActionButton("Importer .apkg", "Paquet ou collection", "ph.download-simple", DesignTokens.COLOR_YELLOW, DesignTokens.BG_ACTIVE)
        self.btn_import.clicked.connect(self._open_import_dialog)
        self.btn_export = DashboardActionButton("Exporter .apkg", "Vers Anki Desktop", "ph.upload-simple", DesignTokens.ACCENT_PRIMARY, DesignTokens.BG_ACTIVE)
        self.btn_export.clicked.connect(self._open_export_dialog)
        self.btn_library = DashboardActionButton("Bibliothèque", "Explorer paquets", "ph.books", DesignTokens.COLOR_GREEN, DesignTokens.BG_ACTIVE)
        self.btn_library.clicked.connect(lambda: self._navigate("documents"))

        actions_layout.addWidget(self.btn_forge)
        actions_layout.addWidget(self.btn_import)
        actions_layout.addWidget(self.btn_export)
        actions_layout.addWidget(self.btn_library)
        content_layout.addLayout(actions_layout)

        # 3. Zone de Drop généreuse prenant la hauteur disponible
        self.drop_zone = DashboardDropZone()
        self.drop_zone.file_selected.connect(self._on_file_selected)
        content_layout.addWidget(self.drop_zone, 1)

        # 4. Diagnostics & Actions Proactives (directement sous la dropzone)
        self.diagnostics_widget = ProactiveDiagnosticsWidget()
        self.diagnostics_widget.action_clicked.connect(self._navigate)
        content_layout.addWidget(self.diagnostics_widget)

        scroll_area.setWidget(content_widget)
        left_panel.add_tab("Accueil", scroll_area, icon_name="ph.house", closable=True)
        left_panel.set_active_tab(0)

        left_layout.addWidget(left_panel)
        splitter.addWidget(left_container)

        # ----------------------------------------------------
        # COLONNE DROITE (Cockpit Métriques & Macro-Activités - 35%)
        # ----------------------------------------------------
        right_container = QSplitter(Qt.Orientation.Vertical)
        right_container.setMinimumWidth(340)

        # Panneau 1 : Supervision & Santé (4 KPIs)
        stats_panel = IdePanel(detachable=True)
        stats_widget = QWidget()
        stats_main_layout = QVBoxLayout(stats_widget)
        stats_main_layout.setContentsMargins(12, 12, 12, 12)
        stats_main_layout.setSpacing(8)

        stats_grid = QGridLayout()
        stats_grid.setContentsMargins(0, 0, 0, 0)
        stats_grid.setSpacing(8)

        self.stat_wozniak = StatItem("100%", "Santé Wozniak", DesignTokens.COLOR_GREEN)
        self.stat_coverage = StatItem("100%", "Couverture RAG", DesignTokens.COLOR_BLUE)
        self.stat_cost = StatItem("$ 0.00", "Dépenses IA", DesignTokens.ACCENT_PRIMARY)
        self.stat_duplicates = StatItem("0", "Doublons", DesignTokens.COLOR_GREEN)

        stats_grid.addWidget(self.stat_wozniak, 0, 0)
        stats_grid.addWidget(self.stat_coverage, 0, 1)
        stats_grid.addWidget(self.stat_cost, 1, 0)
        stats_grid.addWidget(self.stat_duplicates, 1, 1)
        stats_main_layout.addLayout(stats_grid)

        stats_panel.add_tab("Supervision && Santé", stats_widget, icon_name="ph.chart-line-up", closable=True)
        stats_panel.set_active_tab(0)
        right_container.addWidget(stats_panel)

        # Panneau 2 : Activité Récente (Grandes actions / Macro-Activités)
        activity_panel = IdePanel(detachable=True)
        activity_widget = QWidget()
        activity_widget.setMinimumWidth(0)
        activity_layout = QVBoxLayout(activity_widget)
        activity_layout.setContentsMargins(10, 10, 10, 10)
        activity_layout.setSpacing(6)

        activity_scroll = QScrollArea()
        activity_scroll.setMinimumWidth(0)
        activity_scroll.setWidgetResizable(True)
        activity_scroll.setFrameShape(QFrame.Shape.NoFrame)
        activity_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        activity_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        activity_inner = QWidget()
        activity_inner.setMinimumWidth(0)
        activity_inner.setStyleSheet("background: transparent;")
        self.activity_list_layout = QVBoxLayout(activity_inner)
        self.activity_list_layout.setContentsMargins(0, 0, 0, 0)
        self.activity_list_layout.setSpacing(6)
        self.activity_list_layout.addStretch(1)

        activity_scroll.setWidget(activity_inner)
        activity_layout.addWidget(activity_scroll, 1)

        view_all_btn = SecondaryButton("Voir tout l'historique")
        view_all_btn.setFixedHeight(28)
        view_all_btn.clicked.connect(lambda: self._navigate("edition"))
        activity_layout.addWidget(view_all_btn)

        activity_panel.add_tab("Activité Récente", activity_widget, icon_name="ph.clock-counter-clockwise", closable=True)
        activity_panel.set_active_tab(0)
        right_container.addWidget(activity_panel)

        splitter.addWidget(right_container)

        right_container.setSizes([160, 400])
        right_container.setCollapsible(0, False)
        right_container.setCollapsible(1, False)

        splitter.setSizes([850, 370])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)

    def refresh_data(self):
        """Lance l'actualisation asynchrone des données du tableau de bord."""
        logger.debug("Actualisation asynchrone des métriques du tableau de bord…")
        self.worker = DashboardWorker()
        self.worker.data_loaded.connect(self._on_data_loaded)
        self.worker.start()

    def _on_data_loaded(self, data: dict):
        """Réception et affichage des métriques, alertes et grandes actions."""
        kpis = data.get("kpis", {})

        # 1. Mise à jour des KPIs
        wozniak = kpis.get("wozniak", {})
        score = wozniak.get("score", 100)
        score_color = DesignTokens.COLOR_GREEN
        if score < 70:
            score_color = DesignTokens.COLOR_RED
        elif score < 90:
            score_color = DesignTokens.COLOR_YELLOW
        self.stat_wozniak.set_value(f"{score}%", score_color)

        coverage = kpis.get("coverage", {})
        cov_val = coverage.get("coverage", 100)
        self.stat_coverage.set_value(f"{cov_val}%", DesignTokens.COLOR_BLUE)

        telemetry = kpis.get("telemetry", {})
        cost = telemetry.get("total_cost_usd", 0.0)
        self.stat_cost.set_value(f"$ {cost:.2f}", DesignTokens.ACCENT_PRIMARY)

        dup_count = kpis.get("duplicates_count", 0)
        dup_color = DesignTokens.COLOR_GREEN if dup_count == 0 else DesignTokens.COLOR_YELLOW
        self.stat_duplicates.set_value(str(dup_count), dup_color)

        # 2. Diagnostics & Alertes Proactives
        diagnostics = data.get("diagnostics", [])
        self.diagnostics_widget.set_diagnostics(diagnostics)

        # 3. Flux des Grandes Actions (Macro-Activités)
        macro_items = data.get("macro_activities")
        if macro_items is None:
            # Repli sur recent_feed si macro_activities non disponible
            feed_items = data.get("recent_feed", [])
            macro_items = [
                {
                    "title": f"Note #{f['note_id']} v{f['version']}",
                    "subtitle": f"{f.get('source', 'manual')} • {f['created_at']}",
                    "icon": "ph.sparkle" if f.get("source") in ["ai_generator", "dag_pipeline"] else "ph.pencil-simple",
                    "bg_color": "rgba(99, 102, 241, 0.15)" if f.get("source") in ["ai_generator", "dag_pipeline"] else "rgba(59, 130, 246, 0.15)",
                    "sample_note_id": f["note_id"],
                }
                for f in feed_items
            ]

        while self.activity_list_layout.count() > 1:
            item = self.activity_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for m in macro_items:
            act_item = ActivityItem(
                note_id=m.get("sample_note_id"),
                title=m.get("title", "Action"),
                subtitle=m.get("subtitle", ""),
                icon_name=m.get("icon", "ph.sparkle"),
                bg_color=m.get("bg_color", "rgba(99, 102, 241, 0.15)"),
            )
            nid = m.get("sample_note_id")
            if nid:
                act_item.clicked.connect(lambda n=nid: self._navigate("edition", {"note_id": n}))
            self.activity_list_layout.insertWidget(self.activity_list_layout.count() - 1, act_item)

        # Émettre l'événement pour TopBar et MainWindow
        self.dashboard_data_updated.emit(data)

    def _on_file_selected(self, file_path: str) -> None:
        p = Path(file_path)
        if p.suffix.lower() in [".apkg", ".colpkg", ".txt"]:
            self._open_import_dialog(initial_path=file_path)
        else:
            self._navigate("creation", {"prompt": f"Source chargée: {file_path}", "title": p.stem})

    def _open_import_dialog(self, initial_path: Optional[str] = None) -> None:
        from ankiforge.ui.dialogs.import_dialog import ImportDialog

        if not self._import_dialog:
            self._import_dialog = ImportDialog(parent=self)
            self._import_dialog.import_finished.connect(lambda _: self.refresh_data())

        if isinstance(self._import_dialog, ImportDialog):
            if initial_path:
                self._import_dialog.set_initial_file(initial_path)
            self._import_dialog.show()
            self._import_dialog.raise_()
            self._import_dialog.activateWindow()

    def _open_export_dialog(self) -> None:
        from ankiforge.ui.dialogs.export_dialog import ExportDialog

        if not self._export_dialog:
            self._export_dialog = ExportDialog(parent=self)

        if isinstance(self._export_dialog, ExportDialog):
            self._export_dialog.show()
            self._export_dialog.raise_()
            self._export_dialog.activateWindow()

    def refresh_theme(self, profile: Any) -> None:
        """Adapte les composants de la vue lors du switch de thème."""
        if hasattr(self, "actions_icon"):
            self.actions_icon.setPixmap(load_phosphor_icon("ph.lightning", color=profile.text_primary).pixmap(14, 14))
        if hasattr(self, "actions_title"):
            self.actions_title.setStyleSheet(f"color: {profile.text_primary};")
        if hasattr(self, "hero_banner"):
            self.hero_banner.refresh_theme(profile)
        if hasattr(self, "btn_forge"):
            self.btn_forge.refresh_theme(profile)
        if hasattr(self, "btn_import"):
            self.btn_import.refresh_theme(profile)
        if hasattr(self, "btn_export"):
            self.btn_export.refresh_theme(profile)
        if hasattr(self, "btn_library"):
            self.btn_library.refresh_theme(profile)
        if hasattr(self, "drop_zone"):
            self.drop_zone.refresh_theme(profile)
        if hasattr(self, "diagnostics_widget"):
            self.diagnostics_widget.refresh_theme(profile)
        if hasattr(self, "stat_wozniak"):
            self.stat_wozniak.refresh_theme(profile)
        if hasattr(self, "stat_coverage"):
            self.stat_coverage.refresh_theme(profile)
        if hasattr(self, "stat_cost"):
            self.stat_cost.refresh_theme(profile)
        if hasattr(self, "stat_duplicates"):
            self.stat_duplicates.refresh_theme(profile)
        if hasattr(self, "activity_list_layout"):
            for i in range(self.activity_list_layout.count()):
                item = self.activity_list_layout.itemAt(i)
                if item and item.widget() and hasattr(item.widget(), "refresh_theme"):
                    item.widget().refresh_theme(profile)
