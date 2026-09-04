from __future__ import annotations

import datetime
import json
import logging
import re
import uuid
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
from ankiforge.ui.views.consultant_view.widgets.inline_diff_card_widget import InlineDiffCardWidget
from ankiforge.ui.views.consultant_view.widgets.thought_step_widget import ThoughtStepWidget
from ankiforge.ui.views.consultant_view.widgets.tool_call_widget import ToolCallWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class ChatMessageWidget(QWidget):
    """Bulle de message conversationnel interactive avec support du streaming en temps réel et diffs inline."""

    diff_applied = Signal(str)
    diff_rejected = Signal(str)
    diff_reverted = Signal(str)
    diff_inspect_requested = Signal(dict)
    open_editor_requested = Signal(int)

    def __init__(
        self,
        sender: str,
        text: str = "",
        is_user: bool = False,
        thoughts: list[tuple[int, str]] | None = None,
        tool_calls: list[tuple[str, str, str, bool]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_user = is_user
        self.raw_text = text
        self.is_streaming = not is_user and not text

        self._thought_widgets: dict[int, ThoughtStepWidget] = {}
        self._tool_widgets: list[ToolCallWidget] = []

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

        self.content_wrapper = QWidget()
        self.content_layout = QVBoxLayout(self.content_wrapper)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(6)

        now_str = datetime.datetime.now().strftime("%H:%M")
        sender_html = f"<span style='font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;'>{sender}</span>"
        time_html = f"<span style='color: {DesignTokens.TEXT_MUTED}; font-size: 11px; margin-left: 6px;'>{now_str}</span>"
        self.header_lbl = QLabel(f"{sender_html} {time_html}")
        self.header_lbl.setStyleSheet("border: none; background: transparent;")
        self.content_layout.addWidget(self.header_lbl)

        # Conteneur pour pensées et outils injectés en direct
        self.steps_wrapper = QWidget()
        self.steps_wrapper_layout = QVBoxLayout(self.steps_wrapper)
        self.steps_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_wrapper_layout.setSpacing(4)

        self.accordion_toggle_btn = QPushButton("🧠 Réflexion & Outils ReAct")
        self.accordion_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.accordion_toggle_btn.setIcon(load_phosphor_icon("ph.caret-down", color=DesignTokens.TEXT_MUTED))
        self.accordion_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 500;
                color: {DesignTokens.TEXT_MUTED};
                text-align: left;
            }}
            QPushButton:hover {{
                color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
        """)
        self.accordion_toggle_btn.clicked.connect(self._toggle_steps_visibility)
        self.steps_wrapper_layout.addWidget(self.accordion_toggle_btn)

        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(6)
        self.steps_wrapper_layout.addWidget(self.steps_container)

        self.content_layout.addWidget(self.steps_wrapper)

        if thoughts:
            for item in thoughts:
                try:
                    step_num = int(item[0])
                    th_txt = str(item[1])
                    self.add_or_update_thought(step_num, th_txt, is_running=False)
                except Exception:
                    pass

        if tool_calls:
            for item in tool_calls:
                try:
                    t_name = str(item[0])
                    t_args = str(item[1]) if len(item) > 1 else "{}"
                    t_res = str(item[2]) if len(item) > 2 else ""
                    t_err = bool(item[3]) if len(item) > 3 else False
                    tc_widget = ToolCallWidget(t_name, t_args, t_res, is_error=t_err, is_running=False)
                    self._tool_widgets.append(tc_widget)
                    self.steps_layout.addWidget(tc_widget)
                except Exception:
                    pass

        has_steps = bool(self._thought_widgets or self._tool_widgets)
        self.steps_wrapper.setVisible(has_steps or self.is_streaming)
        if has_steps and not self.is_streaming:
            self._update_accordion_label()
            # Replié par défaut pour la lisibilité
            self.steps_container.setVisible(False)
            self.accordion_toggle_btn.setIcon(load_phosphor_icon("ph.caret-right", color=DesignTokens.TEXT_MUTED))

        self.body_card = QFrame()
        body_layout = QVBoxLayout(self.body_card)
        body_layout.setContentsMargins(14, 12, 14, 12)

        self.msg_body = QLabel()
        self.msg_body.setWordWrap(True)
        self.msg_body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        if is_user:
            self.msg_body.setText(text)
            self.msg_body.setTextFormat(Qt.TextFormat.PlainText)
            self.body_card.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_ACTIVE};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            self.msg_body.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; font-size: 13px; line-height: 1.5;")
        else:
            html = render_markdown_message(text) if text else "<i>En attente de réponse...</i>"
            self.msg_body.setText(html)
            self.msg_body.setTextFormat(Qt.TextFormat.RichText)
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
        self.content_layout.addWidget(self.body_card)

        # Conteneur des actions interactives post-réponse
        self.actions_container = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_container)
        self.actions_layout.setContentsMargins(0, 4, 0, 0)
        self.actions_layout.setSpacing(6)
        self.content_layout.addWidget(self.actions_container)

        if not is_user and text:
            self._render_action_buttons()

        if not is_user:
            layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)
            layout.addWidget(self.content_wrapper, 1)
        else:
            layout.addWidget(self.content_wrapper, 1)
            layout.addWidget(self.avatar_lbl, alignment=Qt.AlignmentFlag.AlignTop)

    def append_text_chunk(self, chunk: str) -> None:
        """Ajoute un fragment de texte en direct (Streaming token-by-token)."""
        self.raw_text += chunk
        html = render_markdown_message(self.raw_text)
        self.msg_body.setText(html)

    def add_or_update_thought(self, step: int, thought_text: str, is_running: bool = False) -> None:
        """Ajoute ou met à jour un bloc de réflexion en direct."""
        if step in self._thought_widgets:
            self._thought_widgets[step].update_text(thought_text, is_running=is_running)
        else:
            w = ThoughtStepWidget(step, thought_text, is_running=is_running)
            self._thought_widgets[step] = w
            self.steps_layout.addWidget(w)

    def add_tool_start(self, tool_name: str, args_str: str) -> ToolCallWidget:
        """Insère une carte d'outil en cours d'exécution avec spinner."""
        tc_widget = ToolCallWidget(tool_name, args_str, "", is_error=False, is_running=True)
        self._tool_widgets.append(tc_widget)
        self.steps_layout.addWidget(tc_widget)
        return tc_widget

    def update_tool_result(self, tool_name: str, result_str: str, is_error: bool = False) -> None:
        """Met à jour la dernière carte d'outil correspondant au nom."""
        for tc in reversed(self._tool_widgets):
            if tc.tool_name == tool_name and tc.is_running:
                tc.update_result(result_str, is_error=is_error)
                return

        # Si non trouvé, on en crée un achevé
        tc_widget = ToolCallWidget(tool_name, "{}", result_str, is_error=is_error, is_running=False)
        self._tool_widgets.append(tc_widget)
        self.steps_layout.addWidget(tc_widget)

    def mark_as_finished(self, text: str = "") -> None:
        """Finalise le message de l'assistant et ajoute les boutons d'actions."""
        self.is_streaming = False
        if text:
            self.raw_text = text
            html = render_markdown_message(self.raw_text)
            self.msg_body.setText(html)

        # Passer toutes les pensées en état achevé
        for th in self._thought_widgets.values():
            th.update_text(th.lbl_content.text(), is_running=False)

        has_steps = bool(self._thought_widgets or self._tool_widgets)
        self.steps_wrapper.setVisible(has_steps)
        if has_steps:
            self._update_accordion_label()

        self._render_action_buttons()

    def _toggle_steps_visibility(self) -> None:
        """Bascule l'état déplié/replié des étapes de raisonnement et outils."""
        should_hide = not self.steps_container.isHidden()
        self.steps_container.setHidden(should_hide)
        icon_name = "ph.caret-right" if should_hide else "ph.caret-down"
        self.accordion_toggle_btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_MUTED))

    def _update_accordion_label(self) -> None:
        """Met à jour le texte du bouton accordéon avec le nombre d'étapes."""
        n_th = len(self._thought_widgets)
        n_tc = len(self._tool_widgets)
        parts = []
        if n_th > 0:
            parts.append(f"{n_th} étape{'s' if n_th > 1 else ''} de réflexion")
        if n_tc > 0:
            parts.append(f"{n_tc} outil{'s' if n_tc > 1 else ''} exécuté{'s' if n_tc > 1 else ''}")
        summary = " • ".join(parts) if parts else "Détails de l'exécution"
        self.accordion_toggle_btn.setText(f"🧠 {summary}")

    def add_inline_diff(self, patch_data: dict[str, Any]) -> InlineDiffCardWidget:
        """Ajoute une carte de diff interactive avec Garde-Fou directement dans la bulle de chat."""
        diff_card = InlineDiffCardWidget(patch_data, parent=self)
        diff_card.applied.connect(self.diff_applied.emit)
        diff_card.rejected.connect(self.diff_rejected.emit)
        diff_card.reverted.connect(self.diff_reverted.emit)
        diff_card.inspect_requested.connect(self.diff_inspect_requested.emit)
        diff_card.open_editor_requested.connect(self.open_editor_requested.emit)
        self.content_layout.addWidget(diff_card)
        return diff_card

    def mark_as_cancelled(self) -> None:
        """Affiche un indicateur élégant d'interruption par l'utilisateur."""
        self.is_streaming = False
        banner = QLabel("⏹ <i>Génération interrompue par l'utilisateur.</i>")
        banner.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px; padding: 4px 8px; background: rgba(234, 179, 8, 0.1); border-radius: 4px;")
        self.content_layout.addWidget(banner)
        self._render_action_buttons()

    def _render_action_buttons(self) -> None:
        """Génère les boutons d'actions contextuels."""
        while self.actions_layout.count() > 0:
            item = self.actions_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not self.is_user:
            css_match = re.search(r"```(?:css)?\s*(\.[\s\S]+?)\s*```", self.raw_text)
            if css_match:
                css_code = css_match.group(1)
                btn_apply_css = SecondaryButton("Appliquer le Style CSS")
                btn_apply_css.setIcon(load_phosphor_icon("ph.palette", color=DesignTokens.TEXT_PRIMARY))
                btn_apply_css.clicked.connect(lambda _, c=css_code: self._apply_generated_css(c))
                self.actions_layout.addWidget(btn_apply_css)

            if '"Front":' in self.raw_text or '"front":' in self.raw_text:
                btn_import_cards = SecondaryButton("Importer dans la Forge")
                btn_import_cards.setIcon(load_phosphor_icon("ph.arrow-down", color=DesignTokens.TEXT_PRIMARY))
                btn_import_cards.clicked.connect(lambda: self._import_generated_cards(self.raw_text))
                self.actions_layout.addWidget(btn_import_cards)

            btn_copy = IconButton("ph.copy", tooltip="Copier le texte", size=18)
            btn_copy.clicked.connect(lambda: self._copy_text(self.raw_text))

            self.actions_layout.addStretch()
            self.actions_layout.addWidget(btn_copy)

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
