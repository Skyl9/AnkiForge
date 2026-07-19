content = open("src/ankiforge/ui/views/consultant_view.py").read()

new_widget_code = """
class ChatMessageWidget(QWidget):
    \"\"\"A bubble representing a message (User or AI).\"\"\"
    
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
            self.avatar.setStyleSheet(f\"\"\"
                QLabel {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {DesignTokens.ACCENT_PRIMARY}, stop:1 {DesignTokens.ACCENT_HOVER});
                    color: white;
                    border-radius: 16px;
                    font-weight: bold;
                }}
            \"\"\")
        else:
            icon = qta.icon("fa5s.robot", color=DesignTokens.ACCENT_PRIMARY)
            self.avatar.setPixmap(icon.pixmap(20, 20))
            self.avatar.setStyleSheet(f\"\"\"
                QLabel {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: 16px;
                }}
            \"\"\")

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
            self.text_browser.setStyleSheet(f\"\"\"
                QTextBrowser {{
                    background: transparent;
                    color: #ffffff;
                    font-size: {DesignTokens.FONT_SIZE_BASE}px;
                }}
            \"\"\")
            self.bubble.setStyleSheet(f\"\"\"
                QFrame {{
                    background-color: {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            \"\"\")
            
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
            self.text_browser.setStyleSheet(f\"\"\"
                QTextBrowser {{
                    background: transparent;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: {DesignTokens.FONT_SIZE_BASE}px;
                }}
            \"\"\")
            self.bubble.setStyleSheet(f\"\"\"
                QFrame {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_MD}px;
                }}
            \"\"\")
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
"""

start_str = "class ChatMessageWidget(QWidget):"
end_str = "class ConsultantTab(QWidget):"

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_widget_code + "\n\n" + content[end_idx:]
    open("src/ankiforge/ui/views/consultant_view.py", "w").write(new_content)
    print("Patched!")
else:
    print("Could not find start/end bounds")
