import datetime
import json
import logging
import re
import uuid
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.ui.components import (
    IconButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.views.consultant_view.constants import render_markdown_message
from ankiforge.ui.views.consultant_view.widgets.thought_step_widget import ThoughtStepWidget
from ankiforge.ui.views.consultant_view.widgets.tool_call_widget import ToolCallWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ChatMessageWidget(QWidget):
    """Bulle de message conversationnel (Utilisateur ou Assistant IA)."""

    def __init__(
        self,
        sender: str,
        text: str,
        is_user: bool = False,
        thoughts: list[tuple[int, str]] | None = None,
        tool_calls: list[tuple[str, str, str, bool]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_user = is_user
        self.raw_text = text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

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

        content_wrapper = QWidget()
        content_layout = QVBoxLayout(content_wrapper)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)

        now_str = datetime.datetime.now().strftime("%H:%M")
        sender_html = f"<span style='font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;'>{sender}</span>"
        time_html = f"<span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin-left: 6px;'>{now_str}</span>"
        self.header_lbl = QLabel(f"{sender_html} {time_html}")
        self.header_lbl.setStyleSheet("border: none; background: transparent;")
        content_layout.addWidget(self.header_lbl)

        if thoughts:
            for step_num, th_txt in thoughts:
                th_widget = ThoughtStepWidget(step_num, th_txt)
                content_layout.addWidget(th_widget)

        if tool_calls:
            for t_name, t_args, t_res, t_err in tool_calls:
                tc_widget = ToolCallWidget(t_name, t_args, t_res, is_error=t_err)
                content_layout.addWidget(tc_widget)

        self.body_card = QFrame()
        body_layout = QVBoxLayout(self.body_card)
        body_layout.setContentsMargins(14, 12, 14, 12)

        self.msg_body = QLabel()
        self.msg_body.setWordWrap(True)
        self.msg_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

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

        if not is_user:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 4, 0, 0)
            actions_layout.setSpacing(6)

            css_match = re.search(r"```(?:css)?\s*(\.[\s\S]+?)\s*```", text)
            if css_match:
                css_code = css_match.group(1)
                btn_apply_css = SecondaryButton("Appliquer le Style CSS")
                btn_apply_css.setIcon(load_phosphor_icon("ph.palette", color=DesignTokens.TEXT_PRIMARY))
                btn_apply_css.clicked.connect(lambda _, c=css_code: self._apply_generated_css(c))
                actions_layout.addWidget(btn_apply_css)

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
        try:
            model = NoteTypeModel.select().first()
            if model:
                model.css_style = (model.css_style or "") + "\n\n" + css_rule
                model.save()
                show_toast(self, f"Style CSS injecté avec succès dans le modèle '{model.name}' !")
        except Exception as e:
            logger.error("Échec de l'application CSS : %s", e)
            show_toast(self, f"Erreur application CSS: {e}", is_error=True)

    def _import_generated_cards(self, txt: str) -> None:
        try:
            json_match = re.search(r"(\[[\s\S]+\])", txt)
            if not json_match:
                show_toast(self, "Format JSON introuvable dans la réponse.", is_error=True)
                return

            cards_list = json.loads(json_match.group(1))
            deck, _ = DeckModel.get_or_create(name="Consultant_Imports")
            model = NoteTypeModel.select().first()
            if not model:
                model = NoteTypeModel.create(name="Basic", fields_schema='["Front", "Back"]', templates="[]", css_style="")

            with db.atomic():
                for c_data in cards_list:
                    note = NoteModel.create(guid=str(uuid.uuid4())[:10], note_type=model, tags=json.dumps(["AI_Consultant"]), status="pending")
                    NoteVersionModel.create(note=note, version_number=1, content=json.dumps(c_data), source="consultant", is_active=True)
                    CardModel.create(note=note, deck=deck, template_index=0)

            show_toast(self, f"{len(cards_list)} cartes importées dans le paquet 'Consultant_Imports' !")
        except Exception as e:
            logger.error("Erreur import cartes JSON : %s", e)
            show_toast(self, f"Erreur import cartes: {e}", is_error=True)

    def refresh_theme(self, profile: Any) -> None:
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
            self.body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_active};
                    border: 1px solid {profile.accent_primary};
                    border-radius: {profile.radius_md}px;
                }}
            """)
        else:
            self.avatar_lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: {profile.accent_primary};
                    border-radius: 17px;
                }}
            """)
            self.body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {profile.bg_panel};
                    border: 1px solid {profile.border_color};
                    border-radius: {profile.radius_md}px;
                }}
            """)
        self.msg_body.setStyleSheet(f"color: {profile.text_primary}; border: none; font-size: 13px; line-height: 1.5;")
        for child in self.findChildren((ThoughtStepWidget, ToolCallWidget)):
            if hasattr(child, "refresh_theme"):
                child.refresh_theme(profile)
