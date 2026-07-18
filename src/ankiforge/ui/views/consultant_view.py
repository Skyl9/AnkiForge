import json
import logging
from typing import Any

import markdown
import qtawesome as qta
from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtGui import QKeyEvent, QTextCursor, QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QPushButton,
)

from ankiforge.database.models import CardModel, DeckModel, DocumentModel, LLMConfigModel, NoteModel, NoteVersionModel
from ankiforge.services.workers.consultant_worker import ConsultantWorker
from ankiforge.ui.components.components import HeaderLabel, PrimaryButton, RoundedPanel, DBComboBox, EmptyStateWidget
from ankiforge.ui.theme import DesignTokens, apply_shadow

logger = logging.getLogger(__name__)


class MentionPopup(QListWidget):
    item_selected = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
                font-size: 13px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 6px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                color: #ffffff;
            }}
        """)
        self.itemClicked.connect(self._on_item_clicked)
        self.hide()
        self.current_mode = ""

    def populate(self, mode: str, query: str = ""):
        self.clear()
        self.current_mode = mode
        query = query.lower()

        if mode == "/":
            commands = [
                ("audit", self.tr("🔍 /audit : Analyze and find errors")),
                ("explain", self.tr("📖 /explain : Explain a concept")),
                ("mnemonics", self.tr("🧠 /mnemonics : Create mnemonics")),
                ("clear", self.tr("🧹 /clear : Clear current context")),
            ]
            for cmd_id, display in commands:
                if query in cmd_id or query in display.lower():
                    item = QListWidgetItem(display)
                    item.setData(Qt.ItemDataRole.UserRole, cmd_id)
                    self.addItem(item)

        elif mode == "@":
            for deck in DeckModel.select():
                if query in deck.name.lower():
                    item = QListWidgetItem(self.tr("📦 Deck : {0}").format(deck.name))
                    item.setData(Qt.ItemDataRole.UserRole, f"deck_{deck.id}")
                    self.addItem(item)
            for doc in DocumentModel.select():
                if query in doc.title.lower():
                    item = QListWidgetItem(self.tr("📄 Doc : {0}").format(doc.title))
                    item.setData(Qt.ItemDataRole.UserRole, f"doc_{doc.id}")
                    self.addItem(item)

        if self.count() > 0:
            self.setCurrentRow(0)

    def _on_item_clicked(self, item: QListWidgetItem):
        self.item_selected.emit(self.current_mode, item.data(Qt.ItemDataRole.UserRole))


class CommandTextEdit(QTextEdit):
    mention_inserted = Signal(str, str)
    send_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.popup = MentionPopup()
        self.popup.item_selected.connect(self._on_popup_selected)
        self.setPlaceholderText(self.tr("Type / for a command, or @ to load context (Doc, Deck)..."))

        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: none;
                font-size: {DesignTokens.FONT_SIZE_BASE}px;
            }}
        """)

        self.is_typing_mention = False
        self.mention_start_pos = 0
        self.current_mention_mode = ""

    def keyPressEvent(self, event: QKeyEvent):
        if self.popup.isVisible():
            if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.popup.currentRow()
                if event.key() == Qt.Key.Key_Down:
                    self.popup.setCurrentRow((row + 1) % self.popup.count())
                else:
                    self.popup.setCurrentRow((row - 1) % self.popup.count())
                return
            elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab):
                item = self.popup.currentItem()
                if item:
                    self.popup._on_item_clicked(item)
                return
            elif event.key() == Qt.Key.Key_Escape:
                self.hide_popup()
                return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.send_requested.emit()
            return

        super().keyPressEvent(event)

        cursor = self.textCursor()
        text_before_cursor = cursor.block().text()[: cursor.positionInBlock()]

        if text_before_cursor.endswith("@") and (len(text_before_cursor) == 1 or text_before_cursor[-2] == " "):
            self.start_mention("@", cursor.position())
        elif text_before_cursor.endswith("/") and (len(text_before_cursor) == 1 or text_before_cursor[-2] == " "):
            self.start_mention("/", cursor.position())
        elif self.is_typing_mention:
            if event.key() == Qt.Key.Key_Space or cursor.position() < self.mention_start_pos:
                self.hide_popup()
            else:
                query = self.toPlainText()[self.mention_start_pos : cursor.position()]
                self.popup.populate(self.current_mention_mode, query)
                if self.popup.count() == 0:
                    self.hide_popup()
                else:
                    self.update_popup_position()

    def start_mention(self, mode: str, pos: int):
        self.is_typing_mention = True
        self.current_mention_mode = mode
        self.mention_start_pos = pos
        self.popup.populate(mode, "")
        self.update_popup_position()
        self.popup.show()

    def update_popup_position(self):
        cursor_rect = self.cursorRect()
        global_pos = self.mapToGlobal(cursor_rect.bottomLeft())
        self.popup.move(global_pos + QPoint(0, 5))
        self.popup.resize(300, 150)

    def hide_popup(self):
        self.is_typing_mention = False
        self.popup.hide()

    @Slot(str, str)
    def _on_popup_selected(self, mode: str, data_id: str):
        self.hide_popup()
        cursor = self.textCursor()
        cursor.setPosition(self.mention_start_pos - 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.mention_inserted.emit(mode, data_id)


class ContextChip(QFrame):
    removed = Signal(str)

    def __init__(self, data_id: str, display_text: str, parent=None):
        super().__init__(parent)
        self.data_id = data_id

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_HOVER};
                border-radius: 12px;
                padding: 2px 8px;
            }}
            QLabel {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-weight: bold;
                font-size: 11px;
                background: transparent;
            }}
            QToolButton {{
                background: transparent;
                color: {DesignTokens.TEXT_MUTED};
                border: none;
                font-weight: bold;
                font-size: 14px;
                border-radius: 8px;
            }}
            QToolButton:hover {{
                color: {DesignTokens.COLOR_RED};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        lbl = QLabel(display_text)
        btn_close = QToolButton()
        btn_close.setText("×")
        btn_close.setFixedSize(16, 16)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self._on_remove)

        layout.addWidget(lbl)
        layout.addWidget(btn_close)

    def _on_remove(self):
        self.removed.emit(self.data_id)


class ChatMessageWidget(QWidget):
    """A bubble representing a message (User or AI)."""

    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.is_user = is_user
        self.raw_text = text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)

        # Avatar
        self.avatar = QLabel()
        self.avatar.setFixedSize(32, 32)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_user:
            self.avatar.setText("U")
            self.avatar.setStyleSheet(f"""
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {DesignTokens.ACCENT_PRIMARY}, stop:1 {DesignTokens.ACCENT_HOVER});
                    color: white;
                    border-radius: 16px;
                    font-weight: bold;
                }}
            """)
        else:
            icon = qta.icon("fa5s.robot", color=DesignTokens.ACCENT_PRIMARY)
            self.avatar.setPixmap(icon.pixmap(20, 20))
            self.avatar.setStyleSheet(f"""
                QLabel {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 16px;
                }}
            """)

        self.bubble = QFrame()
        bubble_layout = QVBoxLayout(self.bubble)
        bubble_layout.setContentsMargins(15, 12, 15, 12)

        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setFrameShape(QFrame.Shape.NoFrame)
        self.text_browser.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_browser.document().documentLayout().documentSizeChanged.connect(self._adjust_height)

        if is_user:
            self.text_browser.setPlainText(text)
            self.text_browser.setStyleSheet(f"""
                QTextBrowser {{
                    background: transparent;
                    color: #ffffff;
                    font-size: {DesignTokens.FONT_SIZE_BASE}px;
                }}
            """)
            self.bubble.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)

            # Layout logic: User message (Text on left, Avatar on right)
            layout.addStretch()
            layout.addWidget(self.bubble, stretch=1)

            avatar_layout = QVBoxLayout()
            avatar_layout.addWidget(self.avatar)
            avatar_layout.addStretch()
            layout.addLayout(avatar_layout)
        else:
            html = markdown.markdown(text, extensions=["extra", "codehilite", "tables"])
            self.text_browser.setHtml(html)
            self.text_browser.setStyleSheet(f"""
                QTextBrowser {{
                    background: transparent;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: {DesignTokens.FONT_SIZE_BASE}px;
                }}
            """)
            self.bubble.setStyleSheet(f"""
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            """)
            apply_shadow(self.bubble, blur=DesignTokens.SHADOW_SM_BLUR)

            # Layout logic: AI message (Avatar on left, Text on right)
            avatar_layout = QVBoxLayout()
            avatar_layout.addWidget(self.avatar)
            avatar_layout.addStretch()
            layout.addLayout(avatar_layout)

            layout.addWidget(self.bubble, stretch=1)
            layout.addStretch()

        bubble_layout.addWidget(self.text_browser)

        if not is_user:
            actions_layout = QHBoxLayout()
            actions_layout.setContentsMargins(0, 5, 0, 0)
            actions_layout.addStretch()

            btn_copy = QToolButton()
            btn_copy.setIcon(qta.icon("fa5s.copy", color=DesignTokens.TEXT_MUTED))
            btn_copy.setStyleSheet("border: none; background: transparent;")
            btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_copy.clicked.connect(self._copy_text)

            btn_regen = QToolButton()
            btn_regen.setIcon(qta.icon("fa5s.sync-alt", color=DesignTokens.TEXT_MUTED))
            btn_regen.setStyleSheet("border: none; background: transparent;")
            btn_regen.setCursor(Qt.CursorShape.PointingHandCursor)

            btn_up = QToolButton()
            btn_up.setIcon(qta.icon("fa5s.thumbs-up", color=DesignTokens.TEXT_MUTED))
            btn_up.setStyleSheet("border: none; background: transparent;")
            btn_up.setCursor(Qt.CursorShape.PointingHandCursor)

            btn_down = QToolButton()
            btn_down.setIcon(qta.icon("fa5s.thumbs-down", color=DesignTokens.TEXT_MUTED))
            btn_down.setStyleSheet("border: none; background: transparent;")
            btn_down.setCursor(Qt.CursorShape.PointingHandCursor)

            actions_layout.addWidget(btn_copy)
            actions_layout.addWidget(btn_regen)
            actions_layout.addWidget(btn_up)
            actions_layout.addWidget(btn_down)
            bubble_layout.addLayout(actions_layout)

    @Slot(object)
    def _adjust_height(self, _=None):
        doc_height = self.text_browser.document().size().height()
        self.text_browser.setMinimumHeight(int(doc_height) + 10)
        self.text_browser.setMaximumHeight(int(doc_height) + 10)

    @Slot()
    def _copy_text(self):
        cb = QGuiApplication.clipboard()
        cb.setText(self.raw_text)


class ConsultantTab(QWidget):
    """
    AI Consultant Studio view.
    2-Column Layout with Chat Panel and Context Panel.
    """

    def __init__(self, ai_manager: Any) -> None:
        super().__init__()
        self.ai_manager = ai_manager
        self.active_context: list[str] = []
        self.chat_thread: ConsultantWorker | None = None

        self._setup_ui()
        self._connect_signals()

        self.refresh_context_chips()

    def refresh_data(self) -> None:
        """Called when the view is displayed to refresh contents."""
        self._populate_llms()

    def _setup_ui(self) -> None:
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(15)

        self._build_header()

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.main_layout.addWidget(self.splitter, stretch=1)

        self._build_chat_panel()
        self._build_context_panel()

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 0)

    def _build_header(self) -> None:
        header_layout = QHBoxLayout()
        header_layout.addWidget(HeaderLabel(self.tr("🧠 AI Consultant Studio")))
        header_layout.addStretch()

        self.llm_selector = DBComboBox(LLMConfigModel, display_field="display_name", sort_field="display_name")
        self.llm_selector.setMinimumHeight(32)
        self.llm_selector.setMinimumWidth(150)
        header_layout.addWidget(self.llm_selector)

        self.main_layout.addLayout(header_layout)

    def _build_chat_panel(self) -> None:
        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(0, 0, 10, 0)

        # 1. Messages Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.messages_widget = QWidget()
        self.messages_widget.setStyleSheet("background: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.empty_state = EmptyStateWidget(
            icon_name="fa5s.robot", title=self.tr("Votre Consultant Personnel"), description=self.tr("Sélectionnez un document à analyser (tapez @), ou posez directement une question.")
        )
        self.messages_layout.addWidget(self.empty_state)

        self.scroll_area.setWidget(self.messages_widget)
        chat_layout.addWidget(self.scroll_area, stretch=1)

        # 2. Quick Prompts
        quick_prompts_layout = QHBoxLayout()
        prompts = [
            ("🔍", self.tr("Audit Decks"), "/audit"),
            ("📖", self.tr("Explain"), "/explain"),
            ("🧠", self.tr("Mnemonics"), "/mnemonics"),
        ]
        for icon, text, cmd in prompts:
            btn = QPushButton(f"{icon} {text}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_HOVER};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 12px;
                    padding: 4px 10px;
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    color: #fff;
                }}
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, c=cmd: self.chat_input.insertPlainText(c + " "))  # type: ignore[has-type]
            quick_prompts_layout.addWidget(btn)
        quick_prompts_layout.addStretch()
        chat_layout.addLayout(quick_prompts_layout)

        # 3. Chat Input
        input_panel = RoundedPanel()
        input_panel.setStyleSheet(f"""
            RoundedPanel {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        apply_shadow(input_panel, blur=DesignTokens.SHADOW_SM_BLUR)
        input_layout = QHBoxLayout(input_panel)
        input_layout.setContentsMargins(10, 10, 10, 10)

        self.chat_input = CommandTextEdit()
        self.chat_input.setMinimumHeight(60)
        self.chat_input.setMaximumHeight(120)

        self.btn_send = PrimaryButton(qta.icon("fa5s.paper-plane", color="white"), "")
        self.btn_send.setFixedSize(40, 40)
        self.btn_send.setStyleSheet(f"""
            PrimaryButton {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-radius: 20px;
            }}
            PrimaryButton:hover {{
                background-color: {DesignTokens.ACCENT_HOVER};
            }}
        """)

        input_layout.addWidget(self.chat_input, stretch=1)
        input_layout.addWidget(self.btn_send, alignment=Qt.AlignmentFlag.AlignBottom)

        chat_layout.addWidget(input_panel)

        self.lbl_chat_status = QLabel("")
        self.lbl_chat_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        chat_layout.addWidget(self.lbl_chat_status)

        self.splitter.addWidget(chat_container)

    def _build_context_panel(self) -> None:
        context_container = QWidget()
        context_container.setMinimumWidth(300)
        context_container.setMaximumWidth(350)
        context_layout = QVBoxLayout(context_container)
        context_layout.setContentsMargins(10, 0, 0, 0)

        # Sources attachées
        lbl_ctx = QLabel(self.tr("🔗 Attached Sources"))
        lbl_ctx.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold;")
        context_layout.addWidget(lbl_ctx)

        self.context_chips_panel = RoundedPanel()
        self.context_chips_layout = QVBoxLayout(self.context_chips_panel)
        self.context_chips_layout.setSpacing(5)
        self.context_chips_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        context_layout.addWidget(self.context_chips_panel)

        # System Prompt
        lbl_sys = QLabel(self.tr("⚙️ System Prompt"))
        lbl_sys.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; margin-top: 15px;")
        context_layout.addWidget(lbl_sys)

        self.system_prompt_input = QTextEdit()
        self.system_prompt_input.setPlaceholderText(self.tr("You are an expert tutor..."))
        self.system_prompt_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
            }}
        """)
        context_layout.addWidget(self.system_prompt_input, stretch=1)

        # Agent Memory
        lbl_mem = QLabel(self.tr("🧠 Agent Memory"))
        lbl_mem.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: bold; margin-top: 15px;")
        context_layout.addWidget(lbl_mem)

        self.memory_list = QListWidget()
        self.memory_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
            }}
        """)
        context_layout.addWidget(self.memory_list, stretch=1)

        self.splitter.addWidget(context_container)

    def _connect_signals(self) -> None:
        self.chat_input.mention_inserted.connect(self.on_mention_inserted)
        self.chat_input.send_requested.connect(self.send_message)
        self.btn_send.clicked.connect(self.send_message)

    def _populate_llms(self) -> None:
        self.llm_selector.refresh_data()

    @Slot(str, str)
    def on_mention_inserted(self, mode: str, data_id: str) -> None:
        if mode == "/":
            if data_id == "clear":
                self.clear_context()
                self._add_system_message(self.tr("🧹 Context has been cleared."))
            else:
                self.chat_input.insertPlainText(f"/{data_id} ")

        elif mode == "@":
            if data_id not in self.active_context:
                self.active_context.append(data_id)
                self.refresh_context_chips()
            self.chat_input.setFocus()

    @Slot(str)
    def remove_context_item(self, data_id: str) -> None:
        if data_id in self.active_context:
            self.active_context.remove(data_id)
            self.refresh_context_chips()

    def clear_context(self) -> None:
        self.active_context.clear()
        self.refresh_context_chips()

    def refresh_context_chips(self) -> None:
        while self.context_chips_layout.count():
            child = self.context_chips_layout.takeAt(0)
            if child:
                widget = child.widget()
                if widget:
                    widget.deleteLater()

        if not self.active_context:
            lbl = QLabel(self.tr("No context attached"))
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-style: italic; font-size: 11px;")
            self.context_chips_layout.addWidget(lbl)
            return

        for ctx_id in self.active_context:
            display_text = self.tr("Unknown")
            if ctx_id.startswith("deck_"):
                d_id = int(ctx_id.split("_")[1])
                deck = DeckModel.get_or_none(DeckModel.id == d_id)
                display_text = self.tr("📦 {0}").format(deck.name) if deck else self.tr("Unknown deck")
            elif ctx_id.startswith("doc_"):
                d_id = int(ctx_id.split("_")[1])
                doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                display_text = self.tr("📄 {0}").format(doc.title) if doc else self.tr("Unknown doc")

            chip = ContextChip(ctx_id, display_text)
            chip.removed.connect(self.remove_context_item)
            self.context_chips_layout.addWidget(chip)

    def _add_system_message(self, text: str) -> None:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-style: italic; font-size: 12px; margin: 5px 0;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.messages_layout.addWidget(lbl)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        # Force layout update then scroll
        QApplication.processEvents()
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    @Slot()
    def send_message(self) -> None:
        instruction = self.chat_input.toPlainText().strip()
        if not instruction:
            return

        self.empty_state.hide()

        # Add User Message
        msg_widget = ChatMessageWidget(instruction, is_user=True)
        self.messages_layout.addWidget(msg_widget)

        self.chat_input.clear()
        self.btn_send.setEnabled(False)
        self.lbl_chat_status.setText(self.tr("📦 Data collection..."))
        self._scroll_to_bottom()

        context_data = self._build_context_data()

        llm_id = self.llm_selector.currentData()
        llm_config = LLMConfigModel.get_or_none(LLMConfigModel.id == llm_id)
        if not llm_config:
            self._add_system_message(self.tr("⚠️ No AI engine selected."))
            self.btn_send.setEnabled(True)
            self.lbl_chat_status.setText("")
            return

        active_provider = self.ai_manager.create_provider_from_config(llm_config)

        # In case we need system prompt override:
        _custom_system_prompt = self.system_prompt_input.toPlainText().strip()

        self.chat_thread = ConsultantWorker(active_provider, context_data, instruction)
        # Note: If ConsultantWorker doesn't accept a custom system prompt, we might not pass it here,
        # but for future-proofing, if it's updated, it would be used.

        self.chat_thread.progress.connect(self.on_chat_progress)
        self.chat_thread.finished_signal.connect(self.on_chat_success)
        self.chat_thread.error_signal.connect(self.on_chat_error)
        self.chat_thread.start()

    @Slot(str)
    def on_chat_progress(self, msg: str) -> None:
        self.lbl_chat_status.setText(self.tr("⏳ {0}").format(msg))

    def _build_context_data(self) -> dict:
        data: dict[str, list] = {"documents": [], "paquets": []}

        for ctx_id in self.active_context:
            if ctx_id.startswith("doc_"):
                d_id = int(ctx_id.split("_")[1])
                doc = DocumentModel.get_or_none(DocumentModel.id == d_id)
                if doc:
                    data["documents"].append({"titre": doc.title, "contenu": doc.content})

            elif ctx_id.startswith("deck_"):
                d_id = int(ctx_id.split("_")[1])
                deck = DeckModel.get_or_none(DeckModel.id == d_id)
                if deck:
                    notes = []
                    query = NoteModel.select().join(CardModel).where(CardModel.deck == deck).distinct().limit(100)
                    for note in query:
                        v = NoteVersionModel.get_or_none(note=note, is_active=True)
                        if v:
                            notes.append(json.loads(v.content))
                    data["paquets"].append({"nom": deck.name, "notes": notes, "modele": []})
        return data

    @Slot(str)
    def on_chat_success(self, response_text: str) -> None:
        self.lbl_chat_status.setText("")

        # Adding some dummy memory to illustrate the Memory Panel
        memory_item = QListWidgetItem("Memory: Discussed " + self.active_context[0] if self.active_context else "General Discussion")
        self.memory_list.addItem(memory_item)

        # Add AI Message
        msg_widget = ChatMessageWidget(response_text, is_user=False)
        self.messages_layout.addWidget(msg_widget)

        self.btn_send.setEnabled(True)
        self._scroll_to_bottom()

    @Slot(str)
    def on_chat_error(self, error_msg: str) -> None:
        self.lbl_chat_status.setText(self.tr("❌ Error"))
        self._add_system_message(f"AI Error: {error_msg}")
        self.btn_send.setEnabled(True)
        self._scroll_to_bottom()
