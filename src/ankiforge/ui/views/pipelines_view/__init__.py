"""
Package PipelinesView d'AnkiForge (Éditeur de Chaînes DAG et d'Actions Système).
Re-exporte l'ensemble des constantes, assistants, widgets et la vue principale pour 100% rétrocompatibilité.
"""

from ankiforge.ui.views.pipelines_view.constants import (
    PRESET_TEMPLATES,
    STEP_TYPES_META,
    apply_pill_style,
    audit_pipeline_dag,
)
from ankiforge.ui.views.pipelines_view.view import PipelinesView
from ankiforge.ui.views.pipelines_view.widgets import (
    DagFlowOverviewWidget,
    InlineInsertButton,
    PersonaIdentityCard,
    PersonaSelectorDialog,
    PipelineRunDialog,
    PromptPreviewDialog,
    StatusPillBadge,
    StepInspectorPanel,
    StepItemWidget,
    StepPickerCard,
    StepPickerDialog,
    StepTestDialog,
    SubTabButton,
    TagPillButton,
)

__all__ = [
    "PipelinesView",
    "STEP_TYPES_META",
    "PRESET_TEMPLATES",
    "audit_pipeline_dag",
    "apply_pill_style",
    "TagPillButton",
    "SubTabButton",
    "StatusPillBadge",
    "DagFlowOverviewWidget",
    "StepItemWidget",
    "InlineInsertButton",
    "StepPickerCard",
    "StepPickerDialog",
    "PersonaSelectorDialog",
    "PersonaIdentityCard",
    "PromptPreviewDialog",
    "StepInspectorPanel",
    "StepTestDialog",
    "PipelineRunDialog",
]
