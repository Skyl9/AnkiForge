# ruff: noqa: E501
import datetime
import logging

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    TextField,
)

from ankiforge.database.base import BaseModel
from ankiforge.database.models.ai import PersonaModel

logger = logging.getLogger(__name__)


class PipelineModel(BaseModel):
    """Définit une chaîne d'exécution (ex: Génération Complète Ensimag)."""

    name = CharField(unique=True)
    description = TextField(null=True)

    class Meta:
        table_name = "pipelines"


class PipelineStepModel(BaseModel):
    """Table de liaison : Associe une Persona ou une Action à un Pipeline avec un ordre précis."""

    pipeline = ForeignKeyField(PipelineModel, backref="steps", on_delete="CASCADE")
    persona = ForeignKeyField(PersonaModel, backref="pipeline_steps", null=True, on_delete="CASCADE")
    step_order = IntegerField()  # 1, 2, 3... l'ordre d'exécution
    step_type = CharField(default="LLM_PROMPT")  # LLM_PROMPT, RAG_RETRIEVAL, MAP_REDUCE, HUMAN_VALIDATION, PYTHON_TOOL
    on_success_step = ForeignKeyField("self", null=True, backref="success_successors", on_delete="SET NULL")
    on_failure_step = ForeignKeyField("self", null=True, backref="failure_successors", on_delete="SET NULL")
    failure_behavior = CharField(default="stop")  # 'stop', 'continue', 'goto_failure_step'
    config_data = TextField(default="{}", null=True)  # Paramètres avancés JSON (prompt, top_k, variables, LLM dédié, etc.)

    class Meta:
        table_name = "pipeline_steps"
        indexes = ((("pipeline", "step_order"), True),)


class PythonToolModel(BaseModel):
    """Stocke les scripts et outils Python déterministes exécutables dans les étapes DAG."""

    name = CharField(unique=True)  # ex: clean_html_latex
    display_name = CharField()  # ex: Nettoyeur HTML & Formules LaTeX
    description = TextField(null=True)
    code = TextField()  # Script Python exécutable (def run(state): ...)
    is_builtin = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "python_tools"
