"""
Vue AI Consultant — Modernisée, Conforme au Design System, Boucle ReAct & Outils MCP.

- Moteur Autonome ReAct (Thought ➔ Action ➔ Observation ➔ Response) multi-étapes.
- Blocs Visuels Interactifs :
  * ThoughtStepWidget : Cartouche repliable affichant le raisonnement de l'agent.
  * ToolCallWidget : Carte d'appel d'outil affichant les arguments d'entrée et les données observées.
  * ChatMessageWidget : Bulles de discussion avec détection automatique de CSS, JSON et actions 1-clic.
- Barre de Suggestions Rapides (Quick Action Pills) :
  * 📊 Diagnostic Sangsues & Rétention.
  * 🔍 Détection de Doublons Sémantiques.
  * 🎨 Stylisation CSS de Modèles de Cartes.
  * ⚡ Audit de Formulation Minimale.
  * 🛠️ Exécution & Création d'Outils Python Déterministes.
- Panneau de Contexte Actif :
  * Sélecteur de Persona Consultant (portée 'mcp' ou 'universal').
  * Attachement dynamique de Paquets (@) et Documents.
  * Compteurs de mémoire et de tokens en direct.
"""

import datetime
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

import markdown
from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentModel,
    LLMConfigModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    PersonaModel,
    db,
)
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, StyledMenu, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


def render_markdown_message(text: str) -> str:
    """Convertit du texte Markdown en HTML avec typographie et styles élégants."""
    html_content = markdown.markdown(text, extensions=["tables", "fenced_code", "nl2br", "sane_lists"])
    styled_html = f"""
    <div style="font-family: {DesignTokens.FONT_MAIN}; font-size: 13px; line-height: 1.5; color: {DesignTokens.TEXT_PRIMARY};">
        <style>
            h1, h2, h3, h4, h5, h6 {{
                color: {DesignTokens.TEXT_PRIMARY};
                margin-top: 8px;
                margin-bottom: 4px;
                font-weight: bold;
            }}
            h3 {{ font-size: 13px; color: {DesignTokens.ACCENT_PRIMARY}; }}
            h4 {{ font-size: 12px; color: {DesignTokens.COLOR_YELLOW}; }}
            p {{ margin: 3px 0; color: {DesignTokens.TEXT_PRIMARY}; }}
            ul, ol {{ margin: 3px 0; padding-left: 16px; color: {DesignTokens.TEXT_PRIMARY}; }}
            li {{ margin-bottom: 2px; }}
            strong {{ color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; }}
            em {{ color: {DesignTokens.TEXT_SECONDARY}; font-style: italic; }}
            code {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.COLOR_BLUE};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                padding: 1px 4px;
                border-radius: 3px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
            }}
            pre {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 8px 10px;
                margin: 6px 0;
            }}
            pre code {{
                background-color: transparent;
                border: none;
                padding: 0;
                color: #38bdf8;
            }}
        </style>
        {html_content}
    </div>
    """
    return styled_html


# =====================================================================
# COMPOSANT : ÉTAPE DE RÉFLEXION REACT (THOUGHTSTEPWIDGET)
# =====================================================================


class ThoughtStepWidget(QFrame):
    """Cartouche repliable affichant la pensée / le raisonnement ReAct d'une étape."""

    def __init__(self, step: int, thought_text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {DesignTokens.BG_ACTIVE};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # En-tête cliquable pour replier/déplier
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.brain", color=DesignTokens.ACCENT_PRIMARY).pixmap(14, 14))
        header_row.addWidget(icon_lbl)

        lbl_title = QLabel(f"Raisonnement ReAct — Étape {step}")
        lbl_title.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-size: 11px;")
        header_row.addWidget(lbl_title, 1)

        self.btn_toggle = QPushButton("Détails ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.btn_toggle.clicked.connect(self._toggle_content)
        header_row.addWidget(self.btn_toggle)
        layout.addLayout(header_row)

        self.icon_lbl = icon_lbl
        self.lbl_title = lbl_title
        self.lbl_content = QLabel(thought_text)
        self.lbl_content.setWordWrap(True)
        self.lbl_content.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;")
        self.lbl_content.hide()
        layout.addWidget(self.lbl_content)

    def _toggle_content(self) -> None:
        if self.lbl_content.isHidden():
            self.lbl_content.show()
            self.btn_toggle.setText("Masquer ▴")
        else:
            self.lbl_content.hide()
            self.btn_toggle.setText("Détails ▾")

    def refresh_theme(self, profile: Any) -> None:
        self.setStyleSheet(f"""
            ThoughtStepWidget {{
                background-color: {profile.bg_active};
                border: 1px solid {profile.border_color};
                border-radius: 8px;
            }}
            ThoughtStepWidget QLabel {{
                background: transparent;
            }}
        """)
        self.icon_lbl.setPixmap(load_phosphor_icon("ph.brain", color=profile.accent_primary).pixmap(14, 14))
        self.lbl_title.setStyleSheet(f"color: {profile.accent_primary}; font-weight: bold; font-size: 11px;")
        self.lbl_content.setStyleSheet(f"color: {profile.text_secondary}; font-size: 11px; line-height: 1.4;")


# =====================================================================
# COMPOSANT : APPEL D'OUTIL INTERACTIF (TOOLCALLWIDGET)
# =====================================================================


class ToolCallWidget(QFrame):
    """Affiche l'exécution d'un outil MCP / Python avec payload et observation."""

    def __init__(self, tool_name: str, args_json: str, result_str: str, is_error: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tool_name = tool_name
        self.is_error = is_error
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        border_color = "rgba(239, 68, 68, 0.4)" if is_error else "rgba(16, 185, 129, 0.35)"
        bg_color = "rgba(239, 68, 68, 0.08)" if is_error else "rgba(16, 185, 129, 0.08)"

        self.setStyleSheet(f"""
            ToolCallWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            ToolCallWidget QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # En-tête
        header = QHBoxLayout()
        header.setSpacing(8)

        self.icon_lbl = QLabel()
        icon_name = "ph.database" if "peewee" in tool_name or "sql" in tool_name else ("ph.palette" if "css" in tool_name else "ph.wrench")
        icon_color = "#f87171" if is_error else "#34d399"
        self.icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(14, 14))
        header.addWidget(self.icon_lbl)

        self.lbl_tool = QLabel(f"Outil invoqué : <b>{tool_name}</b>")
        self.lbl_tool.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px;")
        header.addWidget(self.lbl_tool, 1)

        badge_status = Badge("Échec" if is_error else "Succès", variant="status")
        apply_pill_style(badge_status, "#ef4444" if is_error else "#10b981")
        header.addWidget(badge_status)

        self.btn_toggle = QPushButton("Voir données ▾")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet("QPushButton { background: transparent; border: none; color: #94a3b8; font-size: 10px; font-weight: bold; }")
        self.btn_toggle.clicked.connect(self._toggle_details)
        header.addWidget(self.btn_toggle)

        layout.addLayout(header)

        # Zone détaillée repliable (Arguments + Observation)
        self.details_box = QWidget()
        details_layout = QVBoxLayout(self.details_box)
        details_layout.setContentsMargins(0, 4, 0, 0)
        details_layout.setSpacing(4)

        lbl_args = QLabel(f"<b>Entrée (JSON) :</b> <code>{args_json}</code>")
        lbl_args.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: monospace;")
        lbl_args.setWordWrap(True)
        details_layout.addWidget(lbl_args)

        edit_result = QPlainTextEdit()
        edit_result.setReadOnly(True)
        edit_result.setPlainText(result_str)
        edit_result.setMaximumHeight(90)
        edit_result.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_MAIN};
                color: #38bdf8;
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 6px;
            }}
        """)
        details_layout.addWidget(edit_result)

        self.details_box.hide()
        layout.addWidget(self.details_box)

    def _toggle_details(self) -> None:
        if self.details_box.isHidden():
            self.details_box.show()
            self.btn_toggle.setText("Masquer ▴")
        else:
            self.details_box.hide()
            self.btn_toggle.setText("Voir données ▾")

    def refresh_theme(self, profile: Any) -> None:
        border_color = "rgba(239, 68, 68, 0.4)" if self.is_error else "rgba(16, 185, 129, 0.35)"
        bg_color = "rgba(239, 68, 68, 0.08)" if self.is_error else "rgba(16, 185, 129, 0.08)"
        self.setStyleSheet(f"""
            ToolCallWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
            ToolCallWidget QLabel {{
                background: transparent;
            }}
        """)
        self.lbl_tool.setStyleSheet(f"color: {profile.text_primary}; font-size: 11px;")


# =====================================================================
# COMPOSANT : BULLE DE MESSAGE CHAT (CHATMESSAGEWIDGET)
# =====================================================================


class ChatMessageWidget(QWidget):
    """Bulle de message conversationnel (Utilisateur ou Assistant IA)."""

    def __init__(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        thoughts: Optional[List[tuple[int, str]]] = None,
        tool_calls: Optional[List[tuple[str, str, str, bool]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.is_user = is_user
        self.raw_text = text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # Avatar
        self.avatar_lbl = QLabel()
        self.avatar_lbl.setFixedSize(34, 34)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if is_user:
            self.avatar_lbl.setText("Vous")
            self.avatar_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    color: white;
                    font-weight: 700;
                    font-size: 11px;
                    border-radius: 17px;
                }}
            """)
            layout.addStretch()
        else:
            self.avatar_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color="white").pixmap(18, 18))
            self.avatar_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 17px;
                }}
            """)

        # Bulle de contenu
        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        # Header (Auteur + Heure)
        now_str = datetime.datetime.now().strftime("%H:%M")
        sender_html = f"<span style='font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;'>{sender}</span>"
        time_html = f"<span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin-left: 6px;'>{now_str}</span>"
        self.header_lbl = QLabel(f"{sender_html} {time_html}")
        self.header_lbl.setStyleSheet("border: none; background: transparent;")
        content_layout.addWidget(self.header_lbl)

        # 1. Éléments ReAct (Pensées et Outils)
        if thoughts:
            for step_num, th_txt in thoughts:
                th_widget = ThoughtStepWidget(step_num, th_txt)
                content_layout.addWidget(th_widget)

        if tool_calls:
            for t_name, t_args, t_res, t_err in tool_calls:
                tc_widget = ToolCallWidget(t_name, t_args, t_res, is_error=t_err)
                content_layout.addWidget(tc_widget)

        # 2. Corps du message
        self.body_card = QFrame()
        body_layout = QVBoxLayout(self.body_card)
        body_layout.setContentsMargins(14, 12, 14, 12)

        self.msg_body = QLabel()
        self.msg_body.setWordWrap(True)
        self.msg_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # Rendu HTML/Markdown propre
        if is_user:
            self.msg_body.setText(text)
            self.msg_body.setTextFormat(Qt.TextFormat.PlainText)
        else:
            html = render_markdown_message(text)
            self.msg_body.setText(html)
            self.msg_body.setTextFormat(Qt.TextFormat.RichText)

        if is_user:
            self.body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            self.msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-size: 13px; line-height: 1.5;")
        else:
            self.body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            self.msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-size: 13px; line-height: 1.5;")
            apply_shadow(self.body_card, blur=10, offset_y=2)

        body_layout.addWidget(self.msg_body)
        content_layout.addWidget(self.body_card)

        # 3. Actions contextuelles sous la réponse IA
        if not is_user:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 4, 0, 0)
            actions_layout.setSpacing(6)

            # Détection de code CSS pour application 1-clic
            css_match = re.search(r"```(?:css)?\s*(\.[\s\S]+?)\s*```", text)
            if css_match:
                css_code = css_match.group(1)
                btn_apply_css = SecondaryButton("Appliquer le Style CSS")
                btn_apply_css.setIcon(load_phosphor_icon("ph.palette", color=DesignTokens.TEXT_PRIMARY))
                btn_apply_css.clicked.connect(lambda _, c=css_code: self._apply_generated_css(c))
                actions_layout.addWidget(btn_apply_css)

            # Détection de cartes JSON pour import 1-clic
            if '"Front":' in text or '"front":' in text:
                btn_import_cards = SecondaryButton("Importer ces cartes dans la Forge")
                btn_import_cards.setIcon(load_phosphor_icon("ph.arrow-down", color=DesignTokens.TEXT_PRIMARY))
                btn_import_cards.clicked.connect(lambda: self._import_generated_cards(text))
                actions_layout.addWidget(btn_import_cards)

            btn_copy = IconButton("ph.copy", tooltip="Copier le texte", size=18)
            btn_copy.clicked.connect(lambda: self._copy_text(text))

            actions_layout.addStretch()
            actions_layout.addWidget(btn_copy)
            content_layout.addLayout(actions_layout)

        if not is_user:
            layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)
            layout.addWidget(content_wrapper, 1)
        else:
            layout.addWidget(content_wrapper, 1)
            layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)

    def _copy_text(self, txt: str) -> None:
        cb = QApplication.clipboard()
        if cb:
            cb.setText(txt)
        show_toast(self, "Réponse copiée dans le presse-papiers !")

    def _apply_generated_css(self, css_rule: str) -> None:
        nt = NoteTypeModel.select().first()
        if nt:
            with db.atomic():
                nt.css_style = (nt.css_style or "") + f"\n\n/* Ajouté par le Consultant IA */\n{css_rule}"
                nt.save()
            show_toast(self, f"Style CSS appliqué avec succès au modèle '{nt.name}' !")
        else:
            show_toast(self, "Aucun modèle de note disponible.", is_error=True)

    def _import_generated_cards(self, text: str) -> None:
        try:
            match = re.search(r"(\[[\s\S]+?\])", text)
            if match:
                cards = json.loads(match.group(1))
                if isinstance(cards, list):
                    deck, _ = DeckModel.get_or_create(name="Défaut")
                    nt = NoteTypeModel.select().first()
                    with db.atomic():
                        for c in cards:
                            if isinstance(c, dict):
                                note = NoteModel.create(guid=uuid.uuid4().hex, note_type=nt, tags="consultant_import")
                                note.add_version(c, source="ai_consultant")
                                CardModel.create(note=note, deck=deck, template_index=0)
                    show_toast(self, f"{len(cards)} cartes importées avec succès dans la Forge !")
                    return
            show_toast(self, "Aucun format de cartes valide détecté.", is_error=True)
        except Exception as e:
            show_toast(self, f"Erreur lors de l'import : {e}", is_error=True)

    def refresh_theme(self, profile: Any) -> None:
        if hasattr(self, "avatar_lbl"):
            if self.is_user:
                self.avatar_lbl.setStyleSheet(f"""
                    QLabel {{
                        background-color: {profile.accent_primary};
                        color: white;
                        font-weight: 700;
                        font-size: 11px;
                        border-radius: 17px;
                    }}
                """)
            else:
                self.avatar_lbl.setStyleSheet(f"""
                    QLabel {{
                        background-color: {profile.accent_primary};
                        border-radius: 17px;
                    }}
                """)
        if hasattr(self, "header_lbl"):
            sender_name = "Vous" if self.is_user else "AnkiForge AI"
            now_str = datetime.datetime.now().strftime("%H:%M")
            sender_html = f"<span style='font-weight: bold; color: {profile.text_primary}; font-size: 12px;'>{sender_name}</span>"
            time_html = f"<span style='color: {profile.text_muted}; font-size: 11px; margin-left: 6px;'>{now_str}</span>"
            self.header_lbl.setText(f"{sender_html} {time_html}")

        if hasattr(self, "body_card") and hasattr(self, "msg_body"):
            if self.is_user:
                self.body_card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {profile.bg_active};
                        border: 1px solid {profile.accent_primary};
                        border-radius: {profile.radius_md}px;
                    }}
                """)
                self.msg_body.setStyleSheet(f"color: {profile.text_primary}; border: none; font-size: 13px; line-height: 1.5;")
            else:
                self.body_card.setStyleSheet(f"""
                    QFrame {{
                        background-color: {profile.bg_panel};
                        border: 1px solid {profile.border_color};
                        border-radius: {profile.radius_md}px;
                    }}
                """)
                self.msg_body.setStyleSheet(f"color: {profile.text_primary}; border: none; font-size: 13px; line-height: 1.5;")


# =====================================================================
# VUE PRINCIPALE : CONSULTANTVIEW (AI CONSULTANT STUDIO)
# =====================================================================


class ConsultantView(QWidget):
    """
    AI Consultant Studio — Moteur ReAct, Intégration Outils Peewee/MCP et Visualisation Riche.
    """

    def __init__(self, ai_manager: Optional[Any] = None, profile_name: str = "default", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.profile_name = profile_name
        self.worker: Optional[ConsultantWorker] = None
        self.used_tokens_count = 0
        self.modified_cards_count = 0
        self.active_context: List[str] = []

        # Tampons pour les étapes ReAct en cours d'exécution
        self._current_thoughts: List[tuple[int, str]] = []
        self._current_tool_calls: List[tuple[str, str, str, bool]] = []

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()
        self._insert_welcome_message()

    def refresh_theme(self, profile: Any) -> None:
        """Adapte le studio Consultant IA lors d'un switch de thème."""
        if hasattr(self, "chat_panel") and hasattr(self.chat_panel, "refresh_theme"):
            self.chat_panel.refresh_theme(profile)
        if hasattr(self, "side_panel") and hasattr(self.side_panel, "refresh_theme"):
            self.side_panel.refresh_theme(profile)
        if hasattr(self, "lbl_chat_status"):
            self.lbl_chat_status.setStyleSheet(f"color: {profile.color_purple}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        if hasattr(self, "chat_messages_layout"):
            for i in range(self.chat_messages_layout.count()):
                item = self.chat_messages_layout.itemAt(i)
                if item and item.widget() and hasattr(item.widget(), "refresh_theme"):
                    item.widget().refresh_theme(profile)
        if hasattr(self, "btn_send") and hasattr(self.btn_send, "refresh_theme"):
            self.btn_send.refresh_theme(profile)

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # ── 1. Panneau Principal de Chat ──────────────────────────────────────
        self.chat_panel = IdePanel(detachable=True)

        # Header Selector : Moteur LLM & Persona
        self.model_selector = StyledComboBox()
        self.model_selector.setMinimumWidth(180)
        self.chat_panel.add_header_widget(self.model_selector)
        self.chat_panel.add_header_separator()

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(0)

        # Statut live pour la progression ReAct
        self.lbl_chat_status = QLabel("")
        self.lbl_chat_status.setStyleSheet(f"color: {DesignTokens.COLOR_PURPLE}; font-size: 11px; padding: 4px 16px; font-weight: bold;")
        chat_layout.addWidget(self.lbl_chat_status)

        # Zone d'affichage des messages
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.chat_scroll.setStyleSheet("background: transparent;")

        self.chat_scroll_widget = QWidget()
        self.chat_messages_layout = QVBoxLayout(self.chat_scroll_widget)
        self.chat_messages_layout.setContentsMargins(16, 16, 16, 16)
        self.chat_messages_layout.setSpacing(14)
        self.chat_messages_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_scroll_widget)
        chat_layout.addWidget(self.chat_scroll, 1)

        # Zone de saisie utilisateur
        input_area = QWidget()
        input_area_layout = QVBoxLayout(input_area)
        input_area_layout.setContentsMargins(16, 6, 16, 14)
        input_area_layout.setSpacing(8)

        # Suggestions Rapides (Quick Prompts Pills)
        quick_prompts_layout = QHBoxLayout()
        quick_prompts_layout.setContentsMargins(0, 0, 0, 0)
        quick_prompts_layout.setSpacing(6)

        prompts = [
            ("ph.chart-bar", "Rétention SRS", "Rétention SRS"),
            ("ph.magnifying-glass", "Cartes sangsues", "Cartes sangsues"),
            ("ph.palette", "Style CSS", "Style CSS"),
            ("ph.sparkle", "Audit Wozniak", "Audit Wozniak"),
            ("ph.wrench", "Outils MCP", "Outils MCP"),
        ]
        for icon, label, key in prompts:
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setIcon(load_phosphor_icon(icon, color=DesignTokens.ACCENT_PRIMARY))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 9999px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 500;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: #a5b4fc;
                }}
            """)
            btn.clicked.connect(lambda _, k=key: self._on_quick_prompt_clicked(k))
            quick_prompts_layout.addWidget(btn)

        quick_prompts_layout.addStretch()
        input_area_layout.addLayout(quick_prompts_layout)

        # Boîte de Chat Box
        self.chat_box_frame = QFrame()
        self.chat_box_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_LG}px;
            }}
            QFrame:focus-within {{
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        apply_shadow(self.chat_box_frame, blur=14, offset_y=2)

        box_layout = QVBoxLayout(self.chat_box_frame)
        box_layout.setContentsMargins(14, 10, 14, 10)
        box_layout.setSpacing(6)

        # Mentions actives de contexte
        self.mentions_layout = QHBoxLayout()
        self.mentions_layout.setContentsMargins(0, 0, 0, 0)
        self.mentions_layout.setSpacing(6)
        box_layout.addLayout(self.mentions_layout)

        # Textedit de saisie
        self.chat_input = StyledTextEdit()
        self.chat_input.setFixedHeight(48)
        self.chat_input.setPlaceholderText("Posez une question, demandez un diagnostic de vos paquets ou tapez '@' pour attacher...")
        self.chat_input.setStyleSheet("border: none; background: transparent; font-size: 13px;")
        box_layout.addWidget(self.chat_input)

        # Toolbar inférieure
        box_footer = QHBoxLayout()
        box_footer.setContentsMargins(0, 0, 0, 0)

        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(4)
        self.btn_attach = IconButton("ph.paperclip", tooltip="Attacher un Paquet ou Document (@)", size=22)
        self.btn_attach.clicked.connect(self._on_add_context)

        self.btn_mention = IconButton("ph.at", tooltip="Attacher un Paquet/Doc (@)", size=22)
        self.btn_mention.clicked.connect(self._on_add_context)

        tools_layout.addWidget(self.btn_attach)
        tools_layout.addWidget(self.btn_mention)
        box_footer.addLayout(tools_layout)
        box_footer.addStretch()

        self.tokens_badge = QLabel("0 tokens")
        self.tokens_badge.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; margin-right: 10px;")
        box_footer.addWidget(self.tokens_badge)

        self.btn_send = PrimaryButton("")
        self.btn_send.setIcon(load_phosphor_icon("ph.arrow-up", color="white"))
        self.btn_send.setFixedSize(34, 34)
        self.btn_send.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 17px;
                border: none;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """)
        self.btn_send.clicked.connect(self._on_send_clicked)
        box_footer.addWidget(self.btn_send)

        box_layout.addLayout(box_footer)
        input_area_layout.addWidget(self.chat_box_frame)

        disclaimer_lbl = QLabel("Le Consultant IA interroge directement votre base de données locale AnkiForge de manière sécurisée.")
        disclaimer_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        disclaimer_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        input_area_layout.addWidget(disclaimer_lbl)

        chat_layout.addWidget(input_area)

        self.chat_panel.add_tab("Chat Consultant", chat_container, "ph.chat-centered-text", closable=False)
        self.splitter.addWidget(self.chat_panel)

        # ── 2. Panneau de Contexte Actif ──────────────────────────────────────
        self.context_panel = IdePanel(detachable=True)
        self.context_panel.setMinimumWidth(280)

        context_container = QWidget()
        context_layout = QVBoxLayout(context_container)
        context_layout.setContentsMargins(12, 12, 12, 12)
        context_layout.setSpacing(14)

        # Section 1 : Persona / Rôle Consultant
        lbl_agent_title = QLabel("PERSONA & RÔLE DU CONSULTANT")
        lbl_agent_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_agent_title)

        self.persona_combo = StyledComboBox()
        self.persona_combo.currentIndexChanged.connect(self._on_agent_changed)
        context_layout.addWidget(self.persona_combo)

        self.sys_prompt_card = QFrame()
        self.sys_prompt_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        sys_layout = QVBoxLayout(self.sys_prompt_card)
        sys_layout.setContentsMargins(4, 4, 4, 4)

        self.sys_prompt_lbl = QLabel('"Expert en analyse de rétention Anki et création de modèles de cartes."')
        self.sys_prompt_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; line-height: 1.4;")
        self.sys_prompt_lbl.setWordWrap(True)
        sys_layout.addWidget(self.sys_prompt_lbl)
        context_layout.addWidget(self.sys_prompt_card)

        # Section 2 : Sources Attachées
        lbl_sources_title = QLabel("PAQUETS & DOCUMENTS ATTACHÉS")
        lbl_sources_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_sources_title)

        self.sources_list = QListWidget()
        self.sources_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                background: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 4px;
                padding: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.sources_list.setFixedHeight(110)
        context_layout.addWidget(self.sources_list)

        self.btn_add_context = SecondaryButton("Ajouter un contexte (@)")
        self.btn_add_context.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
        self.btn_add_context.setStyleSheet(f"border-style: dashed; border-color: {DesignTokens.BORDER_COLOR}; padding: 6px;")
        self.btn_add_context.clicked.connect(self._on_add_context)
        context_layout.addWidget(self.btn_add_context)

        context_layout.addStretch()

        # Section 3 : Mémoire & Tokens
        lbl_mem_title = QLabel("MÉMOIRE DE LA SESSION")
        lbl_mem_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        context_layout.addWidget(lbl_mem_title)

        mem_box = QFrame()
        mem_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        mem_layout = QVBoxLayout(mem_box)
        mem_layout.setContentsMargins(6, 6, 6, 6)
        mem_layout.setSpacing(6)

        row_tokens = QHBoxLayout()
        lbl_tok_title = QLabel("Tokens Estimés")
        lbl_tok_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_tokens_usage = QLabel("0")
        self.lbl_tokens_usage.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_CODE}; font-size: 11px; font-weight: bold;")
        row_tokens.addWidget(lbl_tok_title)
        row_tokens.addStretch()
        row_tokens.addWidget(self.lbl_tokens_usage)

        row_cards = QHBoxLayout()
        lbl_card_title = QLabel("Cartes dans le Contexte")
        lbl_card_title.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_cards_modified = QLabel("0")
        self.lbl_cards_modified.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE}; font-size: 11px; font-weight: bold;")
        row_cards.addWidget(lbl_card_title)
        row_cards.addStretch()
        row_cards.addWidget(self.lbl_cards_modified)

        mem_layout.addLayout(row_tokens)
        mem_layout.addLayout(row_cards)
        context_layout.addWidget(mem_box)

        self.btn_clear_memory = SecondaryButton("Vider la mémoire")
        self.btn_clear_memory.setIcon(load_phosphor_icon("ph.broom", color=DesignTokens.TEXT_PRIMARY))
        self.btn_clear_memory.clicked.connect(self._on_clear_memory)
        context_layout.addWidget(self.btn_clear_memory)

        # Encapsulation dans une QScrollArea transparente
        context_scroll = QScrollArea()
        context_scroll.setWidgetResizable(True)
        context_scroll.setFrameShape(QFrame.Shape.NoFrame)
        context_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        context_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar { width: 0px; }")
        context_scroll.setWidget(context_container)

        self.context_panel.add_tab("Contexte Actif", context_scroll, "ph.bounding-box", closable=False)
        self.splitter.addWidget(self.context_panel)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setSizes([750, 280])

    def _connect_signals(self) -> None:
        self.chat_input.textChanged.connect(self._on_input_text_changed)

    def refresh_data(self) -> None:
        """Rafraîchit les modèles, decks, documents et agents depuis Peewee."""
        try:
            # 1. LLM Engines
            self.model_selector.blockSignals(True)
            self.model_selector.clear()
            engines = list(LLMConfigModel.select())
            for eg in engines:
                display_name = getattr(eg, "display_name", getattr(eg, "provider", str(eg)))
                self.model_selector.addItem(f"⚡ {display_name}", userData=eg)
            self.model_selector.blockSignals(False)

            # 2. Personas (filtrés STRICTEMENT pour les types MCP et universels, exclusion des pipelines purs)
            self.persona_combo.blockSignals(True)
            self.persona_combo.clear()
            agents = list(PersonaModel.select().where(PersonaModel.persona_type.in_(["mcp", "universal"])).order_by(PersonaModel.name.asc()))
            if not agents:
                ag_default = PersonaModel.create(
                    name="Consultant Analytique",
                    description="Expert en diagnostic de collection, statistiques SRS et génération de styles.",
                    system_prompt="Tu es un Consultant IA expert en analyse de rétention Anki, diagnostic SRS et optimisation de modèles de cartes.",
                    persona_type="mcp",
                    output_format="text",
                )
                agents = [ag_default]

            for ag in agents:
                p_type = getattr(ag, "persona_type", "mcp")
                type_prefix = "🤝 " if p_type == "mcp" else "🌐 "
                self.persona_combo.addItem(f"{type_prefix}{ag.name}", userData=ag)

            self.persona_combo.blockSignals(False)
            self._on_agent_changed()

            self.refresh_context_list()

        except Exception as e:
            logger.warning("Erreur refresh_data consultant_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_agent_changed(self) -> None:
        agent: Optional[PersonaModel] = self.persona_combo.currentData()
        if agent and hasattr(agent, "system_prompt") and agent.system_prompt:
            prompt_str = str(agent.system_prompt)
            prompt_snippet = prompt_str[:140] + "..." if len(prompt_str) > 140 else prompt_str
            self.sys_prompt_lbl.setText(f'"{prompt_snippet}"')

    def refresh_context_list(self) -> None:
        """Met à jour l'affichage des éléments de contexte attachés."""
        self.sources_list.clear()

        # Update mentions badges dans la chat box
        while self.mentions_layout.count() > 0:
            layout_item = self.mentions_layout.takeAt(0)
            if layout_item:
                w = layout_item.widget()
                if w:
                    w.deleteLater()

        if not self.active_context:
            empty_item = QListWidgetItem("Aucun contexte attaché (cliquez sur +)")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.sources_list.addItem(empty_item)
            self.lbl_cards_modified.setText("0")
            return

        total_cards_in_context = 0

        for ctx_id in self.active_context:
            display_text = "Inconnu"
            if ctx_id.startswith("deck_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    deck = DeckModel.get_or_none(DeckModel.id == d_id)
                    if deck:
                        card_count = CardModel.select().where(CardModel.deck == deck).count()
                        total_cards_in_context += card_count
                        display_text = f"🎴 Deck: {deck.name} ({card_count} cartes)"
                        badge = Badge(f"🎴 {deck.name}", variant="status")
                        apply_pill_style(badge, DesignTokens.COLOR_GREEN)
                        self.mentions_layout.addWidget(badge)
                except Exception:
                    display_text = "Deck inconnu"
            elif ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        display_text = f"📄 Doc: {doc.title}"
                        badge = Badge(f"📄 {doc.title}", variant="status")
                        apply_pill_style(badge, DesignTokens.COLOR_BLUE)
                        self.mentions_layout.addWidget(badge)
                except Exception:
                    display_text = "Doc inconnu"

            self.sources_list.addItem(display_text)

        self.mentions_layout.addStretch()
        self.lbl_cards_modified.setText(str(total_cards_in_context))

    def _insert_welcome_message(self) -> None:
        """Insère le message d'accueil initial de l'assistant IA."""
        msg_ai = (
            "Bonjour ! Je suis votre <b>Consultant IA AnkiForge</b> raccordé à vos outils ReAct & MCP.<br><br>"
            "Je peux inspecter en direct vos métriques SRS (cartes sangsues, taux d'oubli), analyser la structure de vos cours, "
            "optimiser les modèles de cartes ou exécuter des scripts Python déterministes.<br><br>"
            "💡 <i>Cliquez sur les suggestions rapides ci-dessous ou attachez vos paquets via le bouton <b>+</b> ou <b>@</b>.</i>"
        )
        w = ChatMessageWidget("AnkiForge AI", msg_ai, is_user=False)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, w)

    @Slot()
    def _on_input_text_changed(self) -> None:
        text = self.chat_input.toPlainText()
        tokens = int(len(text.split()) * 1.3)
        self.tokens_badge.setText(f"{tokens} tokens")

    @Slot(str)
    def _on_quick_prompt_clicked(self, key: str) -> None:
        prompt_presets = {
            "Rétention SRS": "Analyse en détail la rétention SRS et la stabilité FSRS-4.5 de mes paquets.",
            "Cartes sangsues": "Détecte les cartes sangsues (lapses élevés) et propose des reformulations atomiques.",
            "Style CSS": "Génère un style CSS moderne pour mon modèle de carte actuel.",
            "Audit Wozniak": "Effectue un audit de formulation minimale basé sur les 20 règles de Piotr Wozniak.",
            "Outils MCP": "Quels outils Python et requêtes Peewee sont disponibles pour le consultant ?",
        }
        if key in prompt_presets:
            resolved_text = prompt_presets[key]
        else:
            clean_text = key
            for prefix in ["📊 ", "🔍 ", "🎨 ", "⚡ ", "🛠️ "]:
                clean_text = clean_text.replace(prefix, "")
            resolved_text = clean_text
        self.chat_input.setPlainText(resolved_text)
        self.chat_input.setFocus()

    @Slot()
    def _on_add_context(self) -> None:
        """Affiche un menu permettant d'attacher un Deck ou un Document au contexte IA."""
        menu = StyledMenu(self)

        menu_decks = menu.addMenu("🎴 Attacher un Paquet (Deck)")
        decks = list(DeckModel.select())
        if decks:
            for d in decks:
                action = QAction(d.name, self)
                action.triggered.connect(lambda _, deck_id=d.id: self._attach_context(f"deck_{deck_id}"))
                menu_decks.addAction(action)
        else:
            no_deck = QAction("Aucun paquet disponible", self)
            no_deck.setEnabled(False)
            menu_decks.addAction(no_deck)

        menu_docs = menu.addMenu("📄 Attacher un Document")
        docs = list(DocumentModel.select())
        if docs:
            for doc in docs:
                action = QAction(doc.title, self)
                action.triggered.connect(lambda _, doc_id=doc.id: self._attach_context(f"doc_{doc_id}"))
                menu_docs.addAction(action)
        else:
            no_doc = QAction("Aucun document disponible", self)
            no_doc.setEnabled(False)
            menu_docs.addAction(no_doc)

        menu.exec(self.btn_add_context.mapToGlobal(self.btn_add_context.rect().bottomLeft()))

    def _attach_context(self, ctx_id: str) -> None:
        if ctx_id not in self.active_context:
            self.active_context.append(ctx_id)
            self.refresh_context_list()
            show_toast(self, "Contexte attaché avec succès !")

    @Slot()
    def _on_clear_memory(self) -> None:
        self.active_context.clear()
        self.refresh_context_list()
        self.used_tokens_count = 0
        self.lbl_tokens_usage.setText("0")
        show_toast(self, "Contexte et mémoire réinitialisés avec succès.")

    def _build_context_data(self) -> Dict[str, List[Dict[str, Any]]]:
        """Extrait le contexte réel depuis la base Peewee."""
        data: Dict[str, List[Dict[str, Any]]] = {"documents": [], "paquets": []}

        for ctx_id in self.active_context:
            if ctx_id.startswith("doc_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                    if doc:
                        data["documents"].append({"titre": doc.title, "contenu": getattr(doc, "content", "")})
                except Exception:
                    pass  # nosec B110

            elif ctx_id.startswith("deck_"):
                try:
                    d_id = int(ctx_id.split("_")[1])
                    deck = DeckModel.get_or_none(DeckModel.id == d_id)
                    if deck:
                        notes_data = []
                        query = NoteModel.select().join(CardModel).where(CardModel.deck == deck).distinct().limit(100)
                        for note in query:
                            v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                            if v and v.content:
                                try:
                                    notes_data.append(json.loads(v.content))
                                except Exception:
                                    notes_data.append({"content": v.content})
                        data["paquets"].append({"nom": deck.name, "notes": notes_data})
                except Exception:
                    pass  # nosec B110

        return data

    @Slot()
    def _on_send_clicked(self) -> None:
        user_text = self.chat_input.toPlainText().strip()
        if not user_text:
            return

        # 1. Ajouter le message utilisateur dans le fil
        user_msg = ChatMessageWidget("Vous", user_text, is_user=True)
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, user_msg)
        self.chat_input.clear()

        # Scroll automatique
        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        # 2. Préparation du contexte et du worker
        context_data = self._build_context_data()
        selected_engine = self.model_selector.currentData()
        selected_persona = self.persona_combo.currentData()

        self.btn_send.setEnabled(False)
        self.lbl_chat_status.setText("⏳ Analyse ReAct et exécution d'outils en cours...")

        self._current_thoughts.clear()
        self._current_tool_calls.clear()

        ai_provider = None
        if self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config") and selected_engine:
            try:
                ai_provider = self.ai_manager.create_provider_from_config(selected_engine)
            except Exception as e:
                logger.warning("Impossible de créer le provider : %s", e)

        self.worker = ConsultantWorker(
            llm_config=selected_engine,
            persona=selected_persona,
            context_data=context_data,
            instruction=user_text,
            ai_provider=ai_provider,
        )
        self.worker.thought_emitted.connect(self._on_thought_received)
        self.worker.tool_call_emitted.connect(self._on_tool_call_received)
        self.worker.progress.connect(self._on_ai_progress)
        self.worker.finished_signal.connect(self._on_ai_response)
        self.worker.error_signal.connect(self._on_ai_error)
        self.worker.start()

    @Slot(int, str)
    def _on_thought_received(self, step: int, thought: str) -> None:
        self._current_thoughts.append((step, thought))

    @Slot(str, str, str, bool)
    def _on_tool_call_received(self, tool_name: str, args_str: str, result_str: str, is_error: bool) -> None:
        self._current_tool_calls.append((tool_name, args_str, result_str, is_error))

    @Slot(str)
    def _on_ai_progress(self, msg: str) -> None:
        self.lbl_chat_status.setText(f"⏳ {msg}")

    @Slot(str)
    def _on_ai_response(self, response: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("")

        ai_msg = ChatMessageWidget(
            sender="AnkiForge AI",
            text=response,
            is_user=False,
            thoughts=list(self._current_thoughts),
            tool_calls=list(self._current_tool_calls),
        )
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, ai_msg)

        QApplication.processEvents()
        self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum())

        self.used_tokens_count += int(len(response.split()) * 1.3) + 120
        self.lbl_tokens_usage.setText(f"{self.used_tokens_count:,}")

    @Slot(str)
    def _on_ai_error(self, error: str) -> None:
        self.btn_send.setEnabled(True)
        self.lbl_chat_status.setText("")
        err_msg = ChatMessageWidget(
            sender="AnkiForge AI",
            text=f"⚠️ <b>Erreur Consultant IA :</b> {error}",
            is_user=False,
            thoughts=list(self._current_thoughts),
            tool_calls=list(self._current_tool_calls),
        )
        self.chat_messages_layout.insertWidget(self.chat_messages_layout.count() - 1, err_msg)


ConsultantTab = ConsultantView
