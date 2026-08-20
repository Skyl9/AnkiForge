# ruff: noqa: E501
import datetime
import json
from pathlib import Path
from typing import Any

from peewee import (
    SQL,
    BigIntegerField,
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
)

from ankiforge.utils.paths import get_app_data_dir

# 3. On définit le chemin final de la base de données
DEFAULT_DB_PATH = get_app_data_dir() / "ankiforge.db"
DB_PATH = DEFAULT_DB_PATH

# Base de données SQLite (initialisation différée possible pour le multi-profils)
db = SqliteDatabase(
    None,
    timeout=30,
    pragmas={
        "journal_mode": "wal",  # Permet la lecture et l'écriture simultanées !
        "cache_size": -1024 * 64,  # Alloue 64MB de RAM pour accélérer les requêtes
        "foreign_keys": 1,  # Force le respect des clés étrangères (sécurité des suppressions en cascade)
        "synchronous": 1,  # Équilibre parfait entre sécurité en cas de crash et vitesse d'écriture
    },
)
db.init(DEFAULT_DB_PATH)


class BaseModel(Model):
    id: Any

    class Meta:
        database = db


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

    note_type_id: Any
    cards: Any

    anki_id = BigIntegerField(unique=True, null=True)
    guid = CharField(unique=True)
    note_type = ForeignKeyField(NoteTypeModel, backref="notes")
    tags = TextField(null=True)
    status = CharField(default="new")
    last_synced_at = DateTimeField(null=True)
    anki_content_hash = CharField(null=True)

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


class MediaModel(BaseModel):
    """Représente un fichier média physique géré par ankiforge_obsidian"""

    filename = CharField(unique=True)  # Nom unique généré (ex: sha256.png)
    original_name = CharField()  # Nom d'origine (ex: schema.png)
    checksum = CharField(unique=True)  # Hash SHA-256 pour la déduplication
    mime_type = CharField()  # Type MIME (image/png, audio/mp3)
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "mediamodel"


class NoteVersionMediaModel(BaseModel):
    """Table de liaison entre une version de note et ses médias associés"""

    note_version = ForeignKeyField(NoteVersionModel, backref="medias", on_delete="CASCADE")
    media = ForeignKeyField(MediaModel, backref="note_versions", on_delete="RESTRICT")

    class Meta:
        table_name = "noteversionmediamodel"


class CardModel(BaseModel):
    """La carte physique générée par la Note et rangée dans un Deck"""

    note_id: Any
    deck_id: Any

    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (cid)
    note = ForeignKeyField(NoteModel, backref="cards", on_delete="CASCADE")
    deck = ForeignKeyField(DeckModel, backref="cards", on_delete="CASCADE")
    template_index = IntegerField(default=0)  # Index du template (Recto=0, Verso=1)

    # --- Statistiques FSRS synchronisées depuis Anki ---
    ivl = IntegerField(default=0)
    reps = IntegerField(default=0)
    lapses = IntegerField(default=0)
    stability = FloatField(default=0.0)
    difficulty = FloatField(default=0.0)
    retrievability = FloatField(default=0.0)


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
    prompt_pricing = FloatField(default=0.0)
    completion_pricing = FloatField(default=0.0)
    is_free = BooleanField(default=False)

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
    task_type = CharField(default="1. Reformulation & Génération Wozniak")  # Type de tâche IA pour répartition
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "token_usage"


class PersonaFolderModel(BaseModel):
    """Dossier et sous-dossier de classification pour organiser les Personas et Agents IA."""

    name = CharField()
    parent = ForeignKeyField("self", backref="subfolders", null=True, on_delete="CASCADE")
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "persona_folders"

    def get_full_path(self) -> str:
        """Retourne le chemin complet du dossier (ex: 'Création / Mathématiques / Algèbre')."""
        parts = [str(self.name)]
        curr = self.parent
        visited = {self.id}
        while curr is not None and curr.id not in visited:
            parts.append(str(curr.name))
            visited.add(curr.id)
            curr = curr.parent
        return " / ".join(reversed(parts))


class PersonaModel(BaseModel):
    """Définit un agent IA unique (ex: Créateur, Linteur, Contrôleur) augmenté de capacités."""

    name = CharField(unique=True)
    description = TextField(null=True)
    system_prompt = TextField()  # Stockera le contenu du prompt Jinja2
    output_format = CharField(default="json")
    persona_type = CharField(default="pipeline")  # 'pipeline', 'mcp', 'universal'
    folder = ForeignKeyField(PersonaFolderModel, backref="personas", null=True, on_delete="SET NULL")
    allowed_tools = TextField(default="[]")  # JSON: ["query_peewee", "rag_retrieval"]
    llm_config = ForeignKeyField(LLMConfigModel, null=True, on_delete="SET NULL")
    created_at = DateTimeField(constraints=[SQL("DEFAULT CURRENT_TIMESTAMP")])

    class Meta:
        table_name = "personas"


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
        # On s'assure qu'il n'y a pas deux étapes "1" dans le même pipeline
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


class FolderModel(BaseModel):
    """Stocke les dossiers de la bibliothèque."""

    name = CharField(unique=True)


class DocumentModel(BaseModel):
    """Stocke les cours après extraction par Marker et leur lien vers la BDD Vectorielle."""

    title = CharField(unique=True)
    content = TextField()
    chroma_collection_name = CharField(null=True)  # Nom de la collection ChromaDB pour le RAG
    created_at = DateTimeField(default=datetime.datetime.now)
    # 🆕 Clé étrangère vers le dossier. null=True permet d'avoir des docs "non rangés".
    # on_delete='CASCADE' supprime les documents si on supprime le dossier.
    folder = ForeignKeyField(FolderModel, backref="documents", null=True, on_delete="CASCADE")
    # Média original importé (ex: PDF source avant passage dans Marker)
    original_media = ForeignKeyField(MediaModel, backref="parsed_documents", null=True, on_delete="SET NULL")
    # Type de fichier d'origine (pdf, md, png, youtube, web)
    file_type = CharField(default="md")
    # Pour les documents issus du Web ou YouTube
    source_url = CharField(null=True)


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


class LinterRuleModel(BaseModel):
    """
    Définit une règle d'audit personnalisable par l'utilisateur.
    Ces règles seront injectées dynamiquement dans le prompt du Linter.
    """

    name = CharField(unique=True)  # Ex: "Principe d'Atomicité Minimale"
    category = CharField(default="cat-atomicite")  # Ex: "cat-atomicite", "cat-katex", "cat-cloze", "cat-interference", "custom"
    category_label = CharField(default="Atomicité & Restructuration")  # Label affiché dans les KPIs
    description = TextField(null=True)  # Ex: "Une carte ne doit traiter que d'un seul concept."
    is_active = BooleanField(default=True)  # Permet d'activer/désactiver à la volée
    color = CharField(default="#f87171")  # Couleur hexadécimale du badge/catégorie
    icon_name = CharField(default="squares-four")  # Nom d'icône Phosphor

    # L'instruction système stricte passée à l'IA
    prompt_injection = TextField()

    # Few-Shot Prompting (Exemples Avant/Après pour guider l'IA)
    example_bad = TextField(null=True)  # JSON d'une mauvaise carte
    example_good = TextField(null=True)  # JSON de la carte corrigée

    class Meta:
        table_name = "linter_rules"


class AuditRecordModel(BaseModel):
    """
    Stocke le résultat de l'audit IA pour une version SPÉCIFIQUE d'une note.
    Permet le 'Soft Analysis' (ne pas ré-auditer ce qui l'a déjà été).
    """

    note = ForeignKeyField(NoteModel, backref="audits", on_delete="CASCADE")
    note_version = ForeignKeyField(NoteVersionModel, backref="audit_record", on_delete="CASCADE")

    is_compliant = BooleanField(default=True)
    rule_broken = CharField(null=True)  # Nom de la règle brisée (ex: "Atomicité")
    reason = TextField(null=True)  # Explication textuelle de Qwen
    suggestion = TextField(null=True)  # JSON de la suggestion de l'IA (Front/Back)

    analyzed_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "audit_records"
        # On s'assure qu'une version de note n'a qu'un seul record d'audit actif
        indexes = ((("note", "note_version"), True),)


def init_db() -> None:
    db.connect(reuse_if_open=True)
    # La création des tables est désormais entièrement déléguée à peewee-migrate.


class SettingModel(BaseModel):
    """
    Stocke les paramètres et préférences utilisateur du profil en base de données SQLite.
    Fournit des méthodes utilitaires avec sérialisation/désérialisation JSON automatique.
    """

    key = CharField(unique=True, index=True)
    value = TextField()
    category = CharField(default="general", index=True)
    updated_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "settings"

    @classmethod
    def get_value(cls, key: str, default: Any = None) -> Any:
        """Récupère la valeur d'un paramètre avec conversion JSON si applicable."""
        try:
            record = cls.get_or_none(cls.key == key)
            if record is None:
                return default
            try:
                return json.loads(record.value)
            except (json.JSONDecodeError, TypeError):
                return record.value
        except Exception:
            return default

    @classmethod
    @db.atomic()
    def set_value(cls, key: str, value: Any, category: str = "general") -> "SettingModel":
        """Enregistre ou met à jour un paramètre en BDD."""
        if isinstance(value, str):
            value_str = value
        else:
            value_str = json.dumps(value, ensure_ascii=False)

        record = cls.get_or_none(cls.key == key)
        if record:
            record.value = value_str
            record.category = category
            record.updated_at = datetime.datetime.now()
            record.save()
            return record
        else:
            return cls.create(
                key=key,
                value=value_str,
                category=category,
                updated_at=datetime.datetime.now(),
            )

    @classmethod
    def get_category(cls, category: str) -> dict[str, Any]:
        """Récupère tous les paramètres d'une catégorie donnée sous forme de dictionnaire."""
        results: dict[str, Any] = {}
        try:
            for record in cls.select().where(cls.category == category):
                try:
                    results[record.key] = json.loads(record.value)
                except (json.JSONDecodeError, TypeError):
                    results[record.key] = record.value
        except Exception:
            pass  # nosec B110
        return results

    @classmethod
    @db.atomic()
    def set_many(cls, settings_dict: dict[str, Any], category: str = "general") -> None:
        """Enregistre un lot de paramètres dans une transaction atomique."""
        for k, v in settings_dict.items():
            cls.set_value(k, v, category=category)


class IgnoredDuplicateModel(BaseModel):
    """Table pour mémoriser les conflits de doublons ignorés par l'utilisateur."""

    note_a = ForeignKeyField(NoteModel, on_delete="CASCADE")
    note_b = ForeignKeyField(NoteModel, on_delete="CASCADE")

    class Meta:
        table_name = "ignored_duplicates"
        # On s'assure de ne pas sauvegarder 10 fois la même paire
        indexes = ((("note_a", "note_b"), True),)


class AICacheModel(BaseModel):
    """Stocke le cache des appels de complétion d'IA pour économiser les coûts et le réseau"""

    prompt_hash = CharField(index=True)
    system_prompt_hash = CharField()
    model_id = CharField()
    temperature = FloatField()
    response_content = TextField()
    created_at = DateTimeField(default=datetime.datetime.now)

    class Meta:
        table_name = "ai_cache"
        indexes = ((("prompt_hash", "system_prompt_hash", "model_id", "temperature"), True),)


class DocumentChunkModel(BaseModel):
    """
    Un morceau de texte (paragraphe, sous-section ou page) issu d'un DocumentModel.
    Permet le suivi fin de la couverture de cours et l'indexation RAG.
    """

    document = ForeignKeyField(DocumentModel, backref="chunks", on_delete="CASCADE")
    chunk_index = IntegerField()  # Pour garder l'ordre du texte (0, 1, 2...)
    content = TextField()
    content_hash = CharField(index=True)  # Hash MD5 du texte brut
    page_number = IntegerField(null=True)
    heading_path = CharField(null=True)
    is_profiled = BooleanField(default=False, null=True)

    class Meta:
        table_name = "document_chunks"


class NoteChunkLinkModel(BaseModel):
    """
    Liaison de traçabilité entre une Note Anki (NoteModel) et son fragment source (DocumentChunkModel).
    Permet le calcul de complétion de cours et l'audit anti-hallucination.
    """

    note = ForeignKeyField(NoteModel, backref="chunk_links", on_delete="CASCADE")
    chunk = ForeignKeyField(DocumentChunkModel, backref="note_links", on_delete="CASCADE")
    is_hallucinating = BooleanField(default=False)

    class Meta:
        table_name = "note_chunk_links"
        indexes = ((("note", "chunk"), True),)


def seed_initial_data() -> None:
    """
    Peuple la base avec les données métier (Modèles, Prompts, Pipelines).
    Utilise get_or_create pour être idempotent et permettre les mises à jour sans purger la BDD.
    """
    juge_prompt = (
        "Tu es l'Agent Juge d'AnkiForge, un fact-checker impitoyable contre les hallucinations.\n"
        "Je vais te fournir le contenu d'une carte d'apprentissage (Anki) et le fragment de cours (Chunk) dont elle est issue.\n"
        "Ta mission est de vérifier que la carte ne contredit pas le cours et n'invente aucune information.\n\n"
        "Format de réponse JSON strict :\n"
        "{\n"
        '  "is_hallucinating": false,\n'
        '  "reason": "La carte reprend exactement la définition du cours sans rien ajouter."\n'
        "}"
    )
    PersonaModel.get_or_create(
        name="Juge Fact-Checker",
        defaults={"description": "Vérifie qu'une carte ne dit pas le contraire de son cours source (Anti-Hallucination).", "system_prompt": juge_prompt},
    )

    if PersonaModel.select().where(PersonaModel.name == "Archiviste Pédagogue").count() > 0:
        return

    # Chemin vers les ressources de prompts (dossier src/ressources/prompts ou src/ankiforge/ressources/prompts)
    prompts_dir = Path(__file__).parent.parent / "ressources" / "prompts"
    if not prompts_dir.exists():
        prompts_dir = Path(__file__).parent.parent.parent / "ressources" / "prompts"

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
    # PERSONA 1 : L'ARCHIVISTE PÉDAGOGUE (Extracteur)
    # ==========================================
    extracteur = PersonaModel.create(
        name="Archiviste Pédagogue",
        description="Extrait le cours en respectant l'atomicité, la dissimulation des hypothèses et le tout-LaTeX.",
        system_prompt=extracteur_prompt,
    )

    # ==========================================
    # PERSONA 2 : LE CONTRÔLEUR QUALITÉ (Linter)
    # ==========================================
    controleur = PersonaModel.create(
        name="Linter & Contrôleur Qualité",
        description="Applique le mapping CSS, audite le LaTeX (ajoute &nbsp;), traque les sauts de ligne et valide le JSON.",
        system_prompt=controleur_prompt,
    )

    cloze_agent, _ = PersonaModel.get_or_create(
        name="Générateur Auto-Cloze",
        defaults={
            "description": "Crée des phrases à trous (c1, c2) optimisées pour la mémorisation d'informations denses.",
            "system_prompt": cloze_prompt,
        },
    )

    # ==========================================
    # PERSONA 4 : L'ASSISTANT GÉNÉRALISTE
    # ==========================================
    generaliste_prompt = (
        "Tu es l'Assistant Généraliste AnkiForge. \n"
        "Ton rôle est d'accompagner l'utilisateur dans la gestion globale de sa base de connaissances.\n"
        "Tu es capable d'analyser le contenu, proposer des modifications sur la structure des paquets, "
        "suggérer des tags pertinents, ou détecter des doublons.\n"
        "Si tu as besoin d'informations (comme la liste des paquets ou des agents), n'hésite pas à utiliser tes outils SQL pour inspecter la base de données.\n"
        "Sois toujours clair, proactif, et pédagogue dans tes réponses."
    )
    PersonaModel.get_or_create(
        name="Consultant Généraliste",
        defaults={"description": "Assistant polyvalent pour gérer l'application, suggérer des tags et optimiser la structure de la collection.", "system_prompt": generaliste_prompt},
    )

    # ==========================================
    # PERSONA 5 : L'AUDITEUR WOZNIAK
    # ==========================================
    wozniak_prompt = (
        "You are an expert Anki flashcard auditor following Piotr Wozniak's '20 rules of formulating knowledge'.\n"
        "Your goal is to review the provided flashcards and point out major violations of the rules (e.g., lack of atomicity, complex lists, redundancy, poorly formulated questions, lack of context).\n\n"
        "For each note, output whether it passes or fails, the rule broken, and a suggested improvement. \n"
        "Return a JSON array of objects.\n\n"
        "JSON Structure:\n"
        "[\n"
        "  {\n"
        '    "note_id": 123,\n'
        '    "pass": false,\n'
        '    "rule_broken": "Atomicity",\n'
        '    "reason": "The card asks for 3 different concepts at once.",\n'
        '    "suggestion": {"Front": "Question 1?", "Back": "Answer 1"} \n'
        "  }\n"
        "]\n"
        "Always wrap your response in standard JSON. Only provide suggestions if it fails."
    )
    PersonaModel.get_or_create(
        name="Auditeur Wozniak",
        defaults={"description": "Auditeur expert basé sur les 20 règles de formulation de Piotr Wozniak.", "system_prompt": wozniak_prompt},
    )
    # ==========================================
    # CRÉATION DES PIPELINES
    # ==========================================
    pipeline_complet = PipelineModel.create(
        name="Excellence Math/Info (Archiviste + Linter)",
        description="Pipeline haute-fidélité pour les cours scientifiques. Extrait intelligemment puis formate le LaTeX, les balises CSS et le code.",
    )
    PipelineStepModel.create(pipeline=pipeline_complet, persona=extracteur, step_type="LLM_PROMPT", step_order=1)
    PipelineStepModel.create(pipeline=pipeline_complet, persona=controleur, step_type="LLM_PROMPT", step_order=2)

    pipeline_rapide = PipelineModel.create(
        name="Extraction Simple (Brouillon)",
        description="Utilise uniquement l'Archiviste. Rapide et économe, mais sans vérification du formatage HTML/LaTeX.",
    )
    PipelineStepModel.create(pipeline=pipeline_rapide, persona=extracteur, step_type="LLM_PROMPT", step_order=1)

    # ==========================================
    # CRÉATION DES MOTEURS IA
    # ==========================================
    if LLMConfigModel.select().count() == 0:
        LLMConfigModel.create(
            display_name="GPT-4o (OpenAI)",
            provider="openai",
            model_id="gpt-4o",
            context_limit=128000,
            prompt_pricing=5.0,
            completion_pricing=15.0,
        )
        LLMConfigModel.create(
            display_name="Claude 3.5 Sonnet",
            provider="anthropic",
            model_id="claude-3-5-sonnet-20240620",
            context_limit=200000,
            prompt_pricing=3.0,
            completion_pricing=15.0,
        )
        LLMConfigModel.create(
            display_name="Mistral Local (Ollama)",
            provider="ollama",
            model_id="mistral",
            context_limit=32768,
            prompt_pricing=0.0,
            completion_pricing=0.0,
        )

    # ==========================================
    # INITIALISATION DES RÈGLES WOZNIAK DU LINTER
    # ==========================================
    seed_default_linter_rules()

    # ==========================================
    # INITIALISATION DES OUTILS PYTHON NATIFS
    # ==========================================
    try:
        from ankiforge.services.tools.tool_service import ToolService

        ToolService.seed_builtin_tools()
    except Exception as e:
        import logging as logger

        logger.getLogger(__name__).warning("Erreur seed_builtin_tools: %s", e)


def seed_default_linter_rules() -> None:
    """Peuple les règles d'audit Wozniak personnalisables par défaut si la table est vide."""
    if LinterRuleModel.select().count() > 0:
        return

    default_rules = [
        {
            "name": "Principe d'Atomicité Minimale",
            "category": "cat-atomicite",
            "category_label": "Atomicité & Restructuration",
            "description": "Une carte ne doit traiter que d'un seul concept ou fait univoque. Si le recto ou le verso contient une liste à puces ou plus de 2 faits distincts, scinder en sous-cartes atomiques.",
            "is_active": True,
            "color": "#f87171",
            "icon_name": "squares-four",
            "prompt_injection": "Vérifie l'atomicité de la carte. Si elle contient une énumération, une liste de plus de 2 éléments, ou pose plusieurs questions à la fois, signale l'erreur 'Principe d'Atomicité Minimale' et propose une scission concise.",
            "example_bad": json.dumps(
                {
                    "Recto": "Expliquer l'allocateur C++20, Valgrind, new vs malloc et delete vs free.",
                    "Verso": "L'allocateur gère le heap, Valgrind détecte les fuites, new alloue avec constructeur, delete détruit.",
                },
                ensure_ascii=False,
            ),
            "example_good": json.dumps(
                {
                    "Recto": "Quel est le rôle de l'allocateur C++20 ?",
                    "Verso": "Gérer l'allocation dynamique de mémoire sur le heap.",
                    "Champ Annexe Extra": "Valgrind et new/delete sont traités dans des cartes dédiées.",
                },
                ensure_ascii=False,
            ),
        },
        {
            "name": "Formatage KaTeX & Clarté Mathématique",
            "category": "cat-katex",
            "category_label": "Formules & Clarté KaTeX",
            "description": "Toute formule mathématique ou chimique doit être rigoureusement formatée en LaTeX entourée de $$...$$ ou $...$.",
            "is_active": True,
            "color": "#c084fc",
            "icon_name": "function",
            "prompt_injection": "Vérifie les notations scientifiques. Si une équation est en texte brut (ex: 'P(A|B) = P(B|A)*P(A)/P(B)') ou si le LaTeX est mal formé, signale 'Formatage KaTeX' et fournis la formule KaTeX exacte.",
            "example_bad": json.dumps({"Recto": "Quelle est la formule du Théorème de Bayes ?", "Verso": "P(A|B) = P(B|A)*P(A)/P(B)"}, ensure_ascii=False),
            "example_good": json.dumps(
                {
                    "Recto": "Quelle est la formule du Théorème de Bayes ?",
                    "Verso": "$$P(A \\mid B) = \\frac{P(B \\mid A) \\cdot P(A)}{P(B)}$$",
                    "Champ Annexe Extra": "P(A|B) = probabilité a posteriori.",
                },
                ensure_ascii=False,
            ),
        },
        {
            "name": "Questions Univoques & Suppression Cloze Surchargé",
            "category": "cat-cloze",
            "category_label": "Questions Univoques Q/R",
            "description": "Les textes à trous ne doivent pas masquer une phrase entière ni créer d'ambiguïté. Remplacer les clozes complexes par des questions directes.",
            "is_active": True,
            "color": "#f59e0b",
            "icon_name": "question",
            "prompt_injection": "Vérifie si la carte utilise un cloze (texte à trous) trop vaste ou ambigu. Si oui, signale 'Questions Univoques' et propose une conversion en question/réponse directe et sans équivoque.",
            "example_bad": json.dumps(
                {"Texte": "Les 5 principes SOLID sont {{c1::Single Responsibility}}, {{c2::Open-Closed}}, {{c3::Liskov}}, {{c4::Interface Segregation}} et {{c5::Dependency Inversion}}."},
                ensure_ascii=False,
            ),
            "example_good": json.dumps(
                {
                    "Recto": "Quel principe SOLID stipule qu'une classe ne doit avoir qu'une seule raison de changer ?",
                    "Verso": "Le principe de responsabilité unique (Single Responsibility Principle - SRP).",
                    "Champ Annexe Extra": "SOLID = SRP, OCP, LSP, ISP, DIP.",
                },
                ensure_ascii=False,
            ),
        },
        {
            "name": "Désambiguïsation & Non-Interférence",
            "category": "cat-interference",
            "category_label": "Désambiguïsation & Contexte",
            "description": "Une question ne doit pas être vague ou prêter à confusion entre deux domaines ou concepts proches. Préciser le contexte minimal.",
            "is_active": True,
            "color": "#3b82f6",
            "icon_name": "circles-three",
            "prompt_injection": "Vérifie que la question n'est pas trop courte ou ambiguë hors contexte. Si deux réponses différentes sont possibles selon la discipline, signale 'Désambiguïsation' et ajoute le préfixe de contexte [Discipline].",
            "example_bad": json.dumps({"Recto": "Quelle est la vitesse limite ?", "Verso": "La vitesse de la lumière c."}, ensure_ascii=False),
            "example_good": json.dumps(
                {
                    "Recto": "[Relativité Restreinte] Quelle est la vitesse limite absolue dans le vide ?",
                    "Verso": "$$c \\approx 3 \\times 10^8 \\text{ m/s}$$",
                    "Champ Annexe Extra": "Invariance de la vitesse de la lumière.",
                },
                ensure_ascii=False,
            ),
        },
    ]

    with LinterRuleModel._meta.database.atomic():
        for r in default_rules:
            LinterRuleModel.create(**r)
