import datetime
from typing import Any

from peewee import BooleanField, CharField, DateTimeField, FloatField, IntegerField, TextField

from ankiforge.database.base import BaseModel


class BatchRunModel(BaseModel):
    """Persiste une exécution par lots : agrégats de fin de batch pour historique et reprise."""

    total_tasks = IntegerField(default=0)
    success_count = IntegerField(default=0)
    error_count = IntegerField(default=0)
    total_cards = IntegerField(default=0)
    started_at = DateTimeField(default=datetime.datetime.now)
    finished_at = DateTimeField(null=True)
    meta_data = TextField(default="{}")  # JSON libre (profil, versions, choix utilisateur…)

    class Meta:
        table_name = "batch_runs"
        indexes = ((("started_at",), False),)


class BatchTaskModel(BaseModel):
    """Persiste l'état d'une tâche de la file par lots (perdure au redémarrage).

    Contient tout ce qu'il faut pour reconstruire un BatchTaskSnapshot ou une
    entrée de queue : doc_id, deck/model/pipeline/llm cibles, paramètres de
    génération, portée (JSON), statut, tentative et cartes en attente de revue.
    """

    task_id = CharField(index=True)  # identifiant stable (hash scope+config ou uuid)
    doc_id = IntegerField(null=True)
    doc_title = CharField(default="")
    deck_id = IntegerField(null=True)
    deck_name = CharField(default="Général")
    model_id = IntegerField(null=True)
    model_name = CharField(default="Basic")
    pipeline_id = IntegerField(null=True)
    pipeline_name = CharField(default="Standard")
    llm_id = IntegerField(null=True)

    selection_mode = CharField(default="sections")
    scope_json = TextField(default="{}")  # scope_title, range_str, blocks[…]
    config_json = TextField(default="{}")  # llm_config + note_type_fields/templates + flags

    status = CharField(default="queued", index=True)
    attempt = IntegerField(default=0)
    cards_json = TextField(default="[]")  # cartes générées (pending/review)
    error = TextField(null=True)

    auto_validation = BooleanField(default=False)
    use_vision = BooleanField(default=False)
    temperature = FloatField(default=0.7)
    max_tokens = IntegerField(default=16384)
    strict_source_grounding = BooleanField(default=True)

    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    @classmethod
    def touch(cls, pk: Any) -> None:
        cls.update(updated_at=datetime.datetime.now()).where(cls.id == pk).execute()

    class Meta:
        table_name = "batch_tasks"
        indexes = ((("status",), False), (("created_at",), False))
