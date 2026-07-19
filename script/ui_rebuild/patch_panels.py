with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/panels.py", "r") as f:
    content = f.read()

# Replace the imports
content = content.replace(
    "from ankiforge.ui.components.buttons import IconButton", "from ankiforge.ui.components.buttons import IconButton\nfrom ankiforge.ui.components.tabs import ScrollableTabBarWidget"
)

# Replace IdePanel __init__ and add_tab and methods
old_init = """        # Tabs container (ide-tabs-list) — scrollable horizontally
        self._tabs_container = QWidget()
        self._tabs_container.setStyleSheet("border: none; background: transparent;")
        self._tabs_layout = QHBoxLayout(self._tabs_container)
        self._tabs_layout.setContentsMargins(0, 0, 0, 0)
        self._tabs_layout.setSpacing(0)
        self._tabs_layout.addStretch()
        self.header_layout.addWidget(self._tabs_container, stretch=1)

        # Extra widgets zone (e.g. view toggles)
        self._extra_widgets_zone = QWidget()
        self._extra_widgets_zone.setStyleSheet("border: none; background: transparent;")
        self._extra_layout = QHBoxLayout(self._extra_widgets_zone)
        self._extra_layout.setContentsMargins(0, 0, 0, 0)
        self._extra_layout.setSpacing(4)
        self._extra_widgets_zone.setVisible(False)
        self.header_layout.addWidget(self._extra_widgets_zone)

        # Detach button
        if detachable:
            self.detach_btn = IconButton("ph.arrow-up-right", "Détacher", 24)
            self.detach_btn.clicked.connect(self.detach_requested.emit)
            self.header_layout.addWidget(self.detach_btn)

        self.layout_v.addWidget(self.header)

        # --- Content (ide-panel-content) ---
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("border: none; background: transparent;")
        self.layout_v.addWidget(self.content_stack)

        # Tab state
        self._tab_buttons: list[QPushButton] = []
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._btn_group.idClicked.connect(self._on_tab_clicked)

        # If a plain title was given (no tabs added), show it as a static label
        self._static_title_label: QLabel | None = None
        if title:
            self._static_title_label = QLabel(title)
            self._static_title_label.setStyleSheet(
                f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; "
                f"border: none; padding-left: 16px;"
            )
            self._tabs_layout.insertWidget(0, self._static_title_label)"""

new_init = """        # If a plain title was given (no tabs added), show it as a static label
        self._static_title_label: QLabel | None = None
        if title:
            self._static_title_label = QLabel(title)
            self._static_title_label.setStyleSheet(
                f"font-weight: bold; color: {DesignTokens.TEXT_PRIMARY}; "
                f"border: none; padding-left: 16px;"
            )
            self.header_layout.addWidget(self._static_title_label)

        # Tabs container (ide-tabs-list) — scrollable horizontally
        self.tabs_bar = ScrollableTabBarWidget()
        self.tabs_bar.tab_changed.connect(self._on_tab_clicked)
        self.tabs_bar.tab_reordered.connect(self._on_tab_reordered)
        self.header_layout.addWidget(self.tabs_bar, stretch=1)

        # Extra widgets zone (e.g. view toggles)
        self._extra_widgets_zone = QWidget()
        self._extra_widgets_zone.setStyleSheet("border: none; background: transparent;")
        self._extra_layout = QHBoxLayout(self._extra_widgets_zone)
        self._extra_layout.setContentsMargins(0, 0, 0, 0)
        self._extra_layout.setSpacing(4)
        self._extra_widgets_zone.setVisible(False)
        self.header_layout.addWidget(self._extra_widgets_zone)

        # Detach button
        if detachable:
            self.detach_btn = IconButton("ph.arrow-up-right", "Détacher", 24)
            self.detach_btn.clicked.connect(self.detach_requested.emit)
            self.header_layout.addWidget(self.detach_btn)

        self.layout_v.addWidget(self.header)

        # --- Content (ide-panel-content) ---
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet("border: none; background: transparent;")
        self.layout_v.addWidget(self.content_stack)"""

content = content.replace(old_init, new_init)

old_methods = """    def add_tab(self, title: str, widget: QWidget, icon_name: str = "") -> int:
        \"\"\"Ajoute un onglet avec titre, contenu et icône optionnelle.

        Si c'est le premier onglet ajouté et qu'un titre statique existait,
        ce titre est masqué au profit des boutons d'onglets.
        \"\"\"
        # Hide static title when tabs are used
        if self._static_title_label is not None and len(self._tab_buttons) == 0:
            self._static_title_label.setVisible(False)

        idx = len(self._tab_buttons)

        btn = QPushButton()
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedHeight(36)

        # Set icon if provided
        if icon_name:
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))
        btn.setText(f" {title}" if icon_name else title)

        btn.setStyleSheet(f\"\"\"
            QPushButton {{
                background-color: transparent;
                color: {DesignTokens.TEXT_SECONDARY};
                border: none;
                border-top: 2px solid transparent;
                padding: 0 12px;
                font-family: "{DesignTokens.FONT_MAIN}";
                font-size: {DesignTokens.FONT_SIZE_BASE}px;
            }}
            QPushButton:hover {{
                color: {DesignTokens.TEXT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            QPushButton:checked {{
                color: {DesignTokens.TEXT_PRIMARY};
                border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                background-color: transparent;
            }}
        \"\"\")

        self._btn_group.addButton(btn, idx)
        self._tab_buttons.append(btn)
        # Insert before the stretch
        self._tabs_layout.insertWidget(self._tabs_layout.count() - 1, btn)

        self.content_stack.addWidget(widget)

        # Activate the first tab automatically
        if idx == 0:
            btn.setChecked(True)

        return idx

    def set_active_tab(self, index: int) -> None:
        \"\"\"Active un onglet par son index.\"\"\"
        if 0 <= index < len(self._tab_buttons):
            self._tab_buttons[index].setChecked(True)
            self.content_stack.setCurrentIndex(index)

    def add_header_widget(self, widget: QWidget) -> None:
        \"\"\"Ajoute un widget supplémentaire dans le header (après les tabs, avant le detach).\"\"\"
        self._extra_widgets_zone.setVisible(True)
        self._extra_layout.addWidget(widget)

    def add_header_separator(self) -> None:
        \"\"\"Ajoute un séparateur vertical dans la zone extra du header.\"\"\"
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; border: none; background: {DesignTokens.BORDER_COLOR}; max-width: 1px;")
        self._extra_widgets_zone.setVisible(True)
        self._extra_layout.addWidget(sep)

    def _on_tab_clicked(self, idx: int) -> None:
        self.content_stack.setCurrentIndex(idx)
        # Update icons for active/inactive state
        for i, btn in enumerate(self._tab_buttons):
            if i == idx:
                btn.setIcon(load_phosphor_icon(
                    btn.property("icon_name") or "",
                    color=DesignTokens.TEXT_PRIMARY
                ) if btn.property("icon_name") else QIcon())
            else:
                btn.setIcon(load_phosphor_icon(
                    btn.property("icon_name") or "",
                    color=DesignTokens.TEXT_SECONDARY
                ) if btn.property("icon_name") else QIcon())
        self.tab_changed.emit(idx)"""

new_methods = """    def add_tab(self, title: str, widget: QWidget, icon_name: str = "") -> int:
        \"\"\"Ajoute un onglet avec titre, contenu et icône optionnelle.

        Si c'est le premier onglet ajouté et qu'un titre statique existait,
        ce titre est masqué au profit des boutons d'onglets.
        \"\"\"
        # Hide static title when tabs are used
        if self._static_title_label is not None and len(self.tabs_bar.tabs) == 0:
            self._static_title_label.setVisible(False)

        idx = self.tabs_bar.add_tab(title, icon_name)
        self.content_stack.addWidget(widget)

        return idx

    def set_active_tab(self, index: int) -> None:
        \"\"\"Active un onglet par son index.\"\"\"
        self.tabs_bar.set_active_tab(index)

    def add_header_widget(self, widget: QWidget) -> None:
        \"\"\"Ajoute un widget supplémentaire dans le header (après les tabs, avant le detach).\"\"\"
        self._extra_widgets_zone.setVisible(True)
        self._extra_layout.addWidget(widget)

    def add_header_separator(self) -> None:
        \"\"\"Ajoute un séparateur vertical dans la zone extra du header.\"\"\"
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(20)
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; border: none; background: {DesignTokens.BORDER_COLOR}; max-width: 1px;")
        self._extra_widgets_zone.setVisible(True)
        self._extra_layout.addWidget(sep)

    def _on_tab_clicked(self, idx: int) -> None:
        self.content_stack.setCurrentIndex(idx)
        # Update icons for active/inactive state
        for i, btn in enumerate(self.tabs_bar.tabs):
            if i == idx:
                btn.setIcon(load_phosphor_icon(
                    btn.property("icon_name") or "",
                    color=DesignTokens.TEXT_PRIMARY
                ) if btn.property("icon_name") else QIcon())
            else:
                btn.setIcon(load_phosphor_icon(
                    btn.property("icon_name") or "",
                    color=DesignTokens.TEXT_SECONDARY
                ) if btn.property("icon_name") else QIcon())
        self.tab_changed.emit(idx)

    def _on_tab_reordered(self, from_idx: int, to_idx: int) -> None:
        # Reorder stacked widget
        widget = self.content_stack.widget(from_idx)
        self.content_stack.removeWidget(widget)
        self.content_stack.insertWidget(to_idx, widget)
        # Update current index to follow the active tab
        for i, btn in enumerate(self.tabs_bar.tabs):
            if btn.isChecked():
                self.content_stack.setCurrentIndex(i)
                break"""

content = content.replace(old_methods, new_methods)

with open("/Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/ui/components/panels.py", "w") as f:
    f.write(content)
