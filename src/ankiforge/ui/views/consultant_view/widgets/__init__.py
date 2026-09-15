"""Widgets spécialisés pour le module Consultant IA."""

from ankiforge.ui.views.consultant_view.widgets.chat_input import ConsultantChatInput
from ankiforge.ui.views.consultant_view.widgets.chat_message_widget import ChatMessageWidget
from ankiforge.ui.views.consultant_view.widgets.context_hub_widget import ContextHubWidget
from ankiforge.ui.views.consultant_view.widgets.inline_diff_card_widget import InlineDiffCardWidget
from ankiforge.ui.views.consultant_view.widgets.mention_completer import MentionCompleter
from ankiforge.ui.views.consultant_view.widgets.session_sidebar import ConsultantSessionSidebar
from ankiforge.ui.views.consultant_view.widgets.thought_step_widget import ThoughtStepWidget
from ankiforge.ui.views.consultant_view.widgets.tool_call_widget import ToolCallWidget
from ankiforge.ui.views.consultant_view.widgets.workspace_inspector_widget import WorkspaceInspectorWidget

__all__ = [
    "ChatMessageWidget",
    "ConsultantChatInput",
    "ConsultantSessionSidebar",
    "ContextHubWidget",
    "InlineDiffCardWidget",
    "MentionCompleter",
    "ThoughtStepWidget",
    "ToolCallWidget",
    "WorkspaceInspectorWidget",
]
