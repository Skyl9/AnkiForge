from PySide6.QtWidgets import QLabel

from .badges import Badge, StatusBadge, TagButton
from .buttons import ActionButton, DangerButton, IconButton, PremiumActionCard, PrimaryButton, SecondaryButton
from .code_editor import (
    CodeEditorWithGutter,
    CSSFormatter,
    CSSLinter,
    CSSSyntaxHighlighter,
    HTMLFormatter,
    HTMLLinter,
    HTMLSyntaxHighlighter,
    LintIssue,
    NativeCodeEditor,
    extract_colors_from_text,
)
from .deck_select_window import DeckSelectWindow
from .document_select_window import DocumentSelectWindow
from .flow_layout import FlowLayout, FlowWidget
from .inputs import DBComboBox, GlowLineEdit, OptionToggleRow, StyledComboBox, StyledLineEdit, StyledTextEdit, ToggleSwitch
from .lists import ActivityItem, ContextItem, DocTreeItem, StyledListItem, VirtualListView
from .misc import StyledToolbar, UserAvatar
from .panels import EmptyStateWidget, GlassPanel, IdePanel, MetricCard, StatCard
from .sidebar import ClickableLabel, Sidebar, SidebarItem
from .tables import CicdTable, StyledTableWidget, VirtualTableView
from .tabs import IdeTabBar, PillTabBar, SettingsTabBar
from .title_bar import GlobalTitleBar
from .topbar import TopBar

HeaderLabel = QLabel
RoundedPanel = GlassPanel

__all__ = [
    "PrimaryButton",
    "SecondaryButton",
    "DangerButton",
    "IconButton",
    "ActionButton",
    "RoundedPanel",
    "HeaderLabel",
    "EmptyStateWidget",
    "PremiumActionCard",
    "IdePanel",
    "GlassPanel",
    "MetricCard",
    "StatCard",
    "IdeTabBar",
    "PillTabBar",
    "SettingsTabBar",
    "StyledLineEdit",
    "StyledTextEdit",
    "GlowLineEdit",
    "ToggleSwitch",
    "OptionToggleRow",
    "StyledComboBox",
    "DBComboBox",
    "StyledListItem",
    "ActivityItem",
    "DocTreeItem",
    "ContextItem",
    "VirtualListView",
    "Badge",
    "StatusBadge",
    "TagButton",
    "StyledTableWidget",
    "CicdTable",
    "VirtualTableView",
    "UserAvatar",
    "StyledToolbar",
    "Sidebar",
    "SidebarItem",
    "ClickableLabel",
    "TopBar",
    "GlobalTitleBar",
    "FlowLayout",
    "FlowWidget",
    "CodeEditorWithGutter",
    "NativeCodeEditor",
    "HTMLLinter",
    "CSSLinter",
    "LintIssue",
    "HTMLSyntaxHighlighter",
    "CSSSyntaxHighlighter",
    "CSSFormatter",
    "HTMLFormatter",
    "extract_colors_from_text",
    "DeckSelectWindow",
    "DocumentSelectWindow",
]
