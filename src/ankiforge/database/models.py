# ruff: noqa: E501
import datetime
import json

from pathlib import Path
from peewee import (
    SqliteDatabase,
    Model,
    IntegerField,
    BigIntegerField,
    ForeignKeyField,
    CharField,
    TextField,
    DateTimeField,
    BooleanField,
    FloatField,
    SQL,
)

from ankiforge.utils.paths import get_app_data_dir

# 3. On définit le chemin final de la base de données
DB_PATH = get_app_data_dir() / "ankiforge.db"
# Base de données SQLite connectée au bon endroit
db = SqliteDatabase(
    DB_PATH,
    pragmas={
        "journal_mode": "wal",  # Permet la lecture et l'écriture simultanées !
        "cache_size": -1024 * 64,  # Alloue 64MB de RAM pour accélérer les requêtes
        "foreign_keys": 1,  # Force le respect des clés étrangères (sécurité des suppressions en cascade)
        "synchronous": 1,  # Équilibre parfait entre sécurité en cas de crash et vitesse d'écriture
    },
)


class BaseModel(Model):
    class Meta:
        database = db


class SchemaVersionModel(BaseModel):
    """Stocke la version actuelle de la structure de la base de données."""

    version = IntegerField(default=1)

    class Meta:
        table_name = "schema_version"


class DeckModel(BaseModel):
    """Représente un paquet Anki et sa hiérarchie (Subdecks)"""

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (did)
    parent_deck = ForeignKeyField("self", null=True, backref="subdecks")
    name = CharField(unique=True)  # Ex: "Science::Physique"
    description = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)


class NoteTypeModel(BaseModel):
    """Représente le TYPE de note (Basic, Cloze...)"""

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (mid)
    name = CharField(unique=True)
    fields_schema = TextField()  # JSON: Liste des noms des champs ["Front", "Back"]
    templates = TextField()  # JSON: Les formats HTML des différentes cartes
    css_style = TextField()  # Le CSS global du modèle


class NoteModel(BaseModel):
    """Le conteneur physique de la note. Il ne change jamais."""

    anki_id = BigIntegerField(unique=True, null=True)
    guid = CharField(unique=True)
    note_type = ForeignKeyField(NoteTypeModel, backref="notes")
    tags = TextField(null=True)
    status = CharField(default="new")

    @db.atomic()
    def add_version(self, new_content_dict: dict, source: str = "manual") -> "NoteVersionModel":
        """
        Crée une nouvelle version de la note (comme un git commit).
        Désactive l'ancienne version active.
        """

        # 1. Trouver la version actuellement active
        current_active = NoteVersionModel.get_or_none(note=self, is_active=True)
        new_version_num = 1

        if current_active:
            new_version_num = current_active.version_number + 1
            current_active.is_active = False
            current_active.save()

        # 2. Créer la nouvelle version
        new_version = NoteVersionModel.create(
            note=self,
            version_number=new_version_num,
            content=json.dumps(new_content_dict, ensure_ascii=False),
            source=source,
            is_active=True,
        )
        return new_version

    @classmethod
    def purge_old_versions(cls, keep_last: int = 15) -> int:
        """
        Nettoie la base de données en ne conservant que les N dernières versions
        pour chaque note. Retourne le nombre de versions supprimées.
        """
        deleted_count = 0

        with db.atomic():
            for note in cls.select():
                # On récupère les versions de la plus récente à la plus ancienne
                versions = list(note.versions.order_by(NoteVersionModel.version_number.desc()))

                # S'il y a plus de versions que la limite autorisée
                if len(versions) > keep_last:
                    versions_to_delete = versions[keep_last:]
                    ids_to_delete = [v.id for v in versions_to_delete]

                    # On supprime en bloc pour optimiser les performances SQLite
                    NoteVersionModel.delete().where(NoteVersionModel.id.in_(ids_to_delete)).execute()
                    deleted_count += len(ids_to_delete)

        return deleted_count


class NoteVersionModel(BaseModel):
    """L'historique des contenus de la note (Le fameux système de version)."""

    note = ForeignKeyField(NoteModel, backref="versions", on_delete="CASCADE")
    version_number = IntegerField(default=1)
    content = TextField()  # Le JSON contenant "Recto" et "Verso"
    created_at = DateTimeField(default=datetime.datetime.now)
    source = CharField(default="ai")  # Peut être 'ai', 'manual', ou 'import'
    is_active = BooleanField(default=True)  # Permet de savoir quelle version exporter


class CardModel(BaseModel):
    """La carte physique générée par la Note et rangée dans un Deck"""

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (cid)
    note = ForeignKeyField(NoteModel, backref="cards", on_delete="CASCADE")
    deck = ForeignKeyField(DeckModel, backref="cards", on_delete="CASCADE")
    template_index = IntegerField(default=0)  # Index du template (Recto=0, Verso=1)


class PromptModel(BaseModel):
    """Stocke les templates Jinja2 personnalisés"""

    name = CharField(unique=True)
    content = TextField()
    description = TextField(null=True)
    is_active = BooleanField(default=True)


class LLMConfigModel(BaseModel):
    """Stocke les configurations physiques des modèles d'IA (Le 'Moteur')."""

    display_name = CharField(unique=True)
    provider = CharField()
    model_id = CharField()
    context_limit = IntegerField(default=8192)
    temperature = FloatField(default=0.7)
    api_key = CharField(null=True)

    class Meta:
        table_name = "llm_configs"


class TokenUsageModel(BaseModel):
    """Stocke l'historique de consommation pour calculer les coûts API."""

    provider = CharField()  # ex: "openai", "gemini", "ollama"
    model_id = CharField()  # ex: "gpt-4o", "gemini-2.0-flash"
    prompt_tokens = IntegerField(default=0)
    completion_tokens = IntegerField(default=0)
    total_tokens = IntegerField(default=0)
    estimated_cost_usd = FloatField(default=0.0)  # On le calculera grossièrement
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "token_usage"


class AgentModel(BaseModel):
    """Définit un agent IA unique (ex: Créateur, Linteur, Contrôleur)."""

    name = CharField(unique=True)
    description = TextField(null=True)
    system_prompt = TextField()  # Stockera le contenu du prompt Jinja2
    output_format = CharField(default="json")
    created_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])

    class Meta:
        table_name = "agents"


class PipelineModel(BaseModel):
    """Définit une chaîne d'exécution (ex: Génération Complète Ensimag)."""

    name = CharField(unique=True)
    description = TextField(null=True)

    class Meta:
        table_name = "pipelines"


class PipelineStepModel(BaseModel):
    """Table de liaison : Associe un Agent à un Pipeline avec un ordre précis."""

    pipeline = ForeignKeyField(PipelineModel, backref="steps", on_delete="CASCADE")
    agent = ForeignKeyField(AgentModel, backref="pipeline_steps", on_delete="CASCADE")
    step_order = IntegerField()  # 1, 2, 3... l'ordre d'exécution

    class Meta:
        table_name = "pipeline_steps"
        # On s'assure qu'il n'y a pas deux étapes "1" dans le même pipeline
        indexes = ((("pipeline", "step_order"), True),)


class FolderModel(BaseModel):
    """Stocke les dossiers de la bibliothèque."""

    name = CharField(unique=True)


class DocumentModel(BaseModel):
    """Stocke les cours après extraction par Marker."""

    title = CharField(unique=True)
    content = TextField()
    created_at = DateTimeField(default=datetime.datetime.now)
    # 🆕 Clé étrangère vers le dossier. null=True permet d'avoir des docs "non rangés".
    # on_delete='CASCADE' supprime les documents si on supprime le dossier.
    folder = ForeignKeyField(FolderModel, backref="documents", null=True, on_delete="CASCADE")


class JobModel(BaseModel):
    """
    Table de suivi des tâches de fond (Parsing PDF, Batch IA long, etc.)
    Permet la reprise après crash.
    """

    # Type de tâche : 'parse_pdf', 'batch_ai', 'audit'
    job_type = CharField()
    # Chemin du fichier source ou ID du document cible
    target = CharField()
    # Statuts : 'pending', 'processing', 'completed', 'failed', 'cancelled'
    status = CharField(default="pending")
    # Progression de 0 à 100
    progress = IntegerField(default=0)
    # Stockage JSON des paramètres spécifiques (ex: pipeline_id, model_id)
    params = TextField(null=True)
    # Log d'erreur en cas d'échec
    error_log = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)
    updated_at = DateTimeField(default=datetime.datetime.now)

    def save(self, *args, **kwargs):
        self.updated_at = datetime.datetime.now()
        return super().save(*args, **kwargs)


def init_db() -> None:
    db.connect(reuse_if_open=True)
    # Ajout des nouvelles tables à l'initialisation
    db.create_tables(
        [
            DeckModel,
            NoteTypeModel,
            NoteModel,
            CardModel,
            NoteVersionModel,
            AgentModel,
            PipelineModel,
            PipelineStepModel,
            DocumentModel,
            FolderModel,
            PromptModel,
            IgnoredDuplicateModel,
            LLMConfigModel,
            TokenUsageModel,
            SchemaVersionModel,
            JobModel,
        ]
    )


class IgnoredDuplicateModel(BaseModel):
    """Table pour mémoriser les conflits de doublons ignorés par l'utilisateur."""

    note_a = ForeignKeyField(NoteModel, on_delete="CASCADE")
    note_b = ForeignKeyField(NoteModel, on_delete="CASCADE")

    class Meta:
        table_name = "ignored_duplicates"
        # On s'assure de ne pas sauvegarder 10 fois la même paire
        indexes = ((("note_a", "note_b"), True),)


def seed_initial_data() -> None:
    """
    Peuple la base avec les données métier (Modèles, Prompts, Pipelines).
    Utilise get_or_create pour être idempotent et permettre les mises à jour sans purger la BDD.
    """
    if AgentModel.select().count() > 0:
        return

    # Chemin vers les ressources de prompts (dossier src/ankiforge/ressources/prompts)
    prompts_dir = Path(__file__).parent.parent / "ressources" / "prompts"

    if NoteTypeModel.select().where(NoteTypeModel.name == "Texte à trous (Cloze)").count() == 0:
        NoteTypeModel.create(
            name="Texte à trous (Cloze)",
            fields_schema=json.dumps(["Texte", "Remarques extra"], ensure_ascii=False),
            templates=json.dumps(
                [
                    {
                        "name": "Texte à trous",
                        "qfmt": "{{cloze:Texte}}",
                        "afmt": "{{cloze:Texte}}<br><br><hr id=answer><br>{{Remarques extra}}",
                    }
                ],
                ensure_ascii=False,
            ),
            css_style=".card { font-family: arial; font-size: 20px; text-align: center; color: palette(text); }\n.cloze { font-weight: bold; color: #2196f3; }",
        )

    # Lecture des prompts depuis les fichiers .jinja2
    extracteur_prompt = (prompts_dir / "extracteur.jinja2").read_text(encoding="utf-8")
    controleur_prompt = (prompts_dir / "controleur.jinja2").read_text(encoding="utf-8")
    cloze_prompt = (prompts_dir / "cloze.jinja2").read_text(encoding="utf-8")

    # ==========================================
    # AGENT 1 : L'ARCHIVISTE PÉDAGOGUE (Extracteur)
    # ==========================================
    extracteur = AgentModel.create(
        name="Archiviste Pédagogue",
        description="Extrait le cours en respectant l'atomicité, la dissimulation des hypothèses et le tout-LaTeX.",
        system_prompt=extracteur_prompt,
    )

    # ==========================================
    # AGENT 2 : LE CONTRÔLEUR QUALITÉ (Linter)
    # ==========================================
    controleur = AgentModel.create(
        name="Linter & Contrôleur Qualité",
        description="Applique le mapping CSS, audite le LaTeX (ajoute &nbsp;), traque les sauts de ligne et valide le JSON.",
        system_prompt=controleur_prompt,
    )

    # ==========================================
    # AGENT 3 : LE GÉNÉRATEUR AUTO-CLOZE
    # ==========================================
    cloze_agent, _ = AgentModel.get_or_create(
        name="Générateur Auto-Cloze",
        defaults={
            "description": "Crée des phrases à trous (c1, c2) optimisées pour la mémorisation d'informations denses.",
            "system_prompt": cloze_prompt,
        },
    )

    # ==========================================
    # CRÉATION DES PIPELINES
    # ==========================================
    pipeline_complet = PipelineModel.create(
        name="Excellence Math/Info (Archiviste + Linter)",
        description="Pipeline haute-fidélité pour les cours scientifiques. Extrait intelligemment puis formate le LaTeX, les balises CSS et le code.",
    )
    PipelineStepModel.create(pipeline=pipeline_complet, agent=extracteur, step_order=1)
    PipelineStepModel.create(pipeline=pipeline_complet, agent=controleur, step_order=2)

    pipeline_rapide = PipelineModel.create(
        name="Extraction Simple (Brouillon)",
        description="Utilise uniquement l'Archiviste. Rapide et économe, mais sans vérification du formatage HTML/LaTeX.",
    )
    PipelineStepModel.create(pipeline=pipeline_rapide, agent=extracteur, step_order=1)

    # ==========================================
    # CRÉATION DES MOTEURS IA
    # ==========================================
    if LLMConfigModel.select().count() == 0:
        LLMConfigModel.create(display_name="GPT-4o (OpenAI)", provider="openai", model_id="gpt-4o", context_limit=128000)
        LLMConfigModel.create(
            display_name="Claude 3.5 Sonnet",
            provider="anthropic",
            model_id="claude-3-5-sonnet-20240620",
            context_limit=200000,
        )
        LLMConfigModel.create(display_name="Mistral Local (Ollama)", provider="ollama", model_id="mistral", context_limit=32768)
