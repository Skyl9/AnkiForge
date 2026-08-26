"""
Composant réutilisable encapsulant la prévisualisation d'une carte Anki.
Multi-appareils : Bureau (100% largeur), Tablette (768px) et Mobile (375px).
Seule la largeur du conteneur varie selon le mode sélectionné.
"""

import json
from typing import Any, Optional

from PySide6.QtCore import QUrl, Slot, Qt, QCoreApplication, QTimer
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea, QSizePolicy

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.theme import DesignTokens, is_dark_mode
from ankiforge.ui.components.inputs import StyledComboBox
from ankiforge.ui.components.buttons import IconButton, SecondaryButton
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.ui.widgets.cloze_manager import sync_preview_card_selector, get_preview_template
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.utils.anki_renderer import render_anki_card, AnkiFields
from ankiforge.utils.paths import get_media_dir


class CardPreviewWidget(QWidget):
    """
    Composant réutilisable encapsulant la prévisualisation d'une carte Anki.
    Support multi-appareils (Bureau 🖥️ 100%, Tablette 📱 768px, Mobile 📱 375px).
    La seule différence entre les modes est la largeur du navigateur.
    """

    def __init__(self, parent: Optional[QWidget] = None, show_header: bool = True) -> None:
        super().__init__(parent)
        self.current_fields: dict[str, str] = {}
        self.current_templates: list[dict[str, Any]] = []
        self.current_css: str = ""
        self._device_mode: str = "desktop"
        self.is_recto: bool = True
        self._is_preview_dark: bool = is_dark_mode()

        self._setup_ui(show_header)
        self._connect_signals()

    def _setup_ui(self, show_header: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # --- En-tête de contrôles (Barre de contrôles unifiée sur 1 seule ligne) ---
        self.controls_container = QWidget()
        self.controls_layout = QHBoxLayout(self.controls_container)
        self.controls_layout.setContentsMargins(6, 4, 6, 4)
        self.controls_layout.setSpacing(6)

        if show_header:
            lbl_preview = QLabel("APERÇU")
            lbl_preview.setStyleSheet(f"font-weight: bold; color: {DesignTokens.TEXT_MUTED}; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; border: none;")
            self.controls_layout.addWidget(lbl_preview)

        # Sélecteur de carte (Carte n°1, Carte n°2)
        self.card_selector = StyledComboBox()
        self.card_selector.setMinimumWidth(100)
        self.card_selector.setFixedHeight(26)
        self.card_selector.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 0 8px;
                font-size: 11px;
            }}
            QComboBox:focus {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.controls_layout.addWidget(self.card_selector)

        self.controls_layout.addStretch()

        # Boutons de bascule multi-appareils (Bureau / Tablette / Mobile)
        self.device_container = QWidget()
        device_layout = QHBoxLayout(self.device_container)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(2)

        self.btn_desktop = IconButton("monitor", tooltip="Mode Bureau (100% largeur)", size=22)
        self.btn_desktop.setStyleSheet(f"background-color: {DesignTokens.BG_HOVER}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px;")
        self.btn_desktop.clicked.connect(lambda: self.set_device_mode("desktop"))

        self.btn_tablet = IconButton("device-tablet", tooltip="Mode Tablette (768px)", size=22)
        self.btn_tablet.clicked.connect(lambda: self.set_device_mode("tablet"))

        self.btn_mobile = IconButton("device-mobile", tooltip="Mode Mobile (375px)", size=22)
        self.btn_mobile.clicked.connect(lambda: self.set_device_mode("mobile"))

        device_layout.addWidget(self.btn_desktop)
        device_layout.addWidget(self.btn_tablet)
        device_layout.addWidget(self.btn_mobile)
        self.controls_layout.addWidget(self.device_container)

        self.btn_theme_toggle = IconButton("sun" if self._is_preview_dark else "moon", tooltip="Basculer le thème", size=22)
        self.btn_theme_toggle.clicked.connect(self._toggle_theme)
        self.controls_layout.addWidget(self.btn_theme_toggle)

        # Bouton pour basculer Recto/Verso
        self.btn_toggle_side = SecondaryButton("Voir Verso")
        self.btn_toggle_side.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_toggle_side.setFixedHeight(26)
        self.btn_toggle_side.setStyleSheet("""
            QPushButton {
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        self.btn_toggle_side.clicked.connect(self._on_toggle_side)
        self.controls_layout.addWidget(self.btn_toggle_side)

        layout.addWidget(self.controls_container)

        # --- Zone de Prévisualisation Premium Flashcard ---
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.card_wrapper = QWidget()
        self.card_wrapper_layout = QVBoxLayout(self.card_wrapper)
        self.card_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.card_wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Cadre Flashcard (Sans bordure pour prendre tout l'espace)
        self.flashcard_frame = QFrame()
        self.flashcard_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.flashcard_frame.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                border-radius: 0px;
            }
        """)

        frame_layout = QVBoxLayout(self.flashcard_frame)
        frame_layout.setContentsMargins(8, 8, 8, 8)

        # SafeWebEngineView pour le rendu MathJax + HTML/CSS
        self.web_view = SafeWebEngineView()
        self.web_view.setMinimumHeight(240)
        frame_layout.addWidget(self.web_view)

        self.card_wrapper_layout.addWidget(self.flashcard_frame)
        self.scroll_area.setWidget(self.card_wrapper)

        layout.addWidget(self.scroll_area, 1)

    def _connect_signals(self) -> None:
        self.card_selector.currentIndexChanged.connect(self._on_card_selected)

    @Slot(int)
    def _on_card_selected(self, index: int) -> None:
        self._render()

    @Slot()
    def _toggle_theme(self) -> None:
        self._is_preview_dark = not self._is_preview_dark
        icon_name = "sun" if self._is_preview_dark else "moon"
        self.btn_theme_toggle.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
        self._render()

    @Slot()
    def _on_toggle_side(self) -> None:
        self.is_recto = not self.is_recto
        if self.is_recto:
            self.btn_toggle_side.setText("Voir Verso")
            self.btn_toggle_side.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        else:
            self.btn_toggle_side.setText("Masquer Verso")
            self.btn_toggle_side.setIcon(load_phosphor_icon("ph.eye-slash", color=DesignTokens.TEXT_PRIMARY))
        self._render()

    def set_device_mode(self, mode: str) -> None:
        """Ajuste uniquement la largeur du conteneur selon l'appareil choisi."""
        self._device_mode = mode

        inactive_style = "background-color: transparent; border-radius: 4px;"
        active_style = f"background-color: {DesignTokens.BG_HOVER}; border: 1px solid {DesignTokens.ACCENT_PRIMARY}; border-radius: 4px;"

        self.btn_desktop.setStyleSheet(inactive_style)
        self.btn_tablet.setStyleSheet(inactive_style)
        self.btn_mobile.setStyleSheet(inactive_style)

        if mode == "tablet":
            self.card_wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.flashcard_frame.setFixedWidth(768)
            self.btn_tablet.setStyleSheet(active_style)
        elif mode == "mobile":
            self.card_wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.flashcard_frame.setFixedWidth(375)
            self.btn_mobile.setStyleSheet(active_style)
        else:  # desktop mode (PC)
            self.card_wrapper_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            self.flashcard_frame.setMinimumWidth(0)
            self.flashcard_frame.setMaximumWidth(16777215)
            self.btn_desktop.setStyleSheet(active_style)

        # Force QScrollArea & WebEngine layout pass instantly without requiring window resize
        self.card_wrapper.adjustSize()
        self.scroll_area.setWidget(self.card_wrapper)
        self.flashcard_frame.updateGeometry()
        self.web_view.updateGeometry()

        frame_size = self.flashcard_frame.size()
        QCoreApplication.sendEvent(self.flashcard_frame, QResizeEvent(frame_size, frame_size))
        web_size = self.web_view.size()
        QCoreApplication.sendEvent(self.web_view, QResizeEvent(web_size, web_size))

        self._render()
        QTimer.singleShot(10, self._render)

    def set_empty_state(self, message: str = "Sélectionnez une carte pour la prévisualiser.") -> None:
        """Affiche un message par défaut quand aucune carte n'est chargée."""
        text_color = DesignTokens.TEXT_MUTED
        placeholder = f"""
        <html>
        <body style='background: transparent; margin: 0; display: flex; height: 100vh; align-items: center; justify-content: center;'>
            <div style='color: {text_color}; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; text-align: center; font-size: 13px; font-weight: 500;'>
                {message}
            </div>
        </body>
        </html>
        """
        self.web_view.setHtmlSafe(placeholder)

    def update_preview(
        self,
        note_type: NoteTypeModel | None,
        fields_dict: dict[str, str],
        override_templates: list | None = None,
        override_css: str | None = None,
    ) -> None:
        """Met à jour les données et rafraîchit l'aperçu HTML."""
        if not note_type and not override_templates:
            self.set_empty_state()
            return

        self.current_fields = fields_dict

        if override_templates is not None:
            self.current_templates = override_templates
        else:
            self.current_templates = json.loads(note_type.templates) if note_type and note_type.templates else []

        if override_css is not None:
            self.current_css = override_css
        else:
            self.current_css = getattr(note_type, "css_style", "") or ""

        self.card_selector.blockSignals(True)
        sync_preview_card_selector(
            selector=self.card_selector,
            templates=self.current_templates,
            current_fields=self.current_fields,
        )
        self.card_selector.blockSignals(False)

        self._render()

    @Slot()
    def _render(self) -> None:
        """Génère le HTML final sans modification externe de style."""
        if not self.current_templates:
            return

        from ankiforge.ui.widgets.cloze_manager import is_template_cloze

        is_cloze = is_template_cloze(self.current_templates)
        selected_tmpl_idx = max(0, self.card_selector.currentIndex())

        tmpl, card_idx = get_preview_template(
            templates=self.current_templates,
            is_cloze=is_cloze,
            selected_index=selected_tmpl_idx,
        )

        is_recto = self.is_recto
        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")

        cur_fields = AnkiFields(self.current_fields.copy())

        final_html = render_anki_card(
            raw_html=raw_html,
            css=self.current_css,
            fields_dict=cur_fields,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", ""),
            is_dark_mode=self._is_preview_dark,
            template_index=card_idx,
        )

        media_dir = get_media_dir()
        media_dir.mkdir(exist_ok=True)
        base_url = QUrl.fromLocalFile(str(media_dir) + "/")

        self.web_view.setHtmlSafe(final_html, base_url)

    def refresh_theme(self, profile: Any) -> None:
        """Rafraîchit le mode sombre/clair et les icônes de contrôle du composant."""
        self._is_preview_dark = getattr(profile, "is_dark", True)
        if hasattr(self, "btn_desktop") and hasattr(self.btn_desktop, "refresh_theme"):
            self.btn_desktop.refresh_theme(profile)
        if hasattr(self, "btn_tablet") and hasattr(self.btn_tablet, "refresh_theme"):
            self.btn_tablet.refresh_theme(profile)
        if hasattr(self, "btn_mobile") and hasattr(self.btn_mobile, "refresh_theme"):
            self.btn_mobile.refresh_theme(profile)
        if hasattr(self, "btn_theme_toggle"):
            self.btn_theme_toggle.setIcon(load_phosphor_icon("sun" if self._is_preview_dark else "moon", color=profile.text_secondary))
        self._render()

    def clear_memory(self) -> None:
        """Nettoie la RAM du moteur web."""
        self.web_view.cleanup()

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "web_view"):
            self.web_view.cleanup()
        super().closeEvent(event)
