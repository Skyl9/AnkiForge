# src/database/models.py
import datetime
import json
import os

from peewee import *

from ankiforge.utils.paths import get_app_data_dir

# 3. On définit le chemin final de la base de données
DB_PATH = get_app_data_dir() / 'ankiforge.db'
# Base de données SQLite connectée au bon endroit
db = SqliteDatabase(DB_PATH, pragmas={
    'journal_mode': 'wal',  # Permet la lecture et l'écriture simultanées !
    'cache_size': -1024 * 64,  # Alloue 64MB de RAM pour accélérer les requêtes
    'foreign_keys': 1, # Force le respect des clés étrangères (sécurité des suppressions en cascade)
    'synchronous': 1 # Équilibre parfait entre sécurité en cas de crash et vitesse d'écriture
})

class BaseModel(Model):
    class Meta:
        database = db


class DeckModel(BaseModel):
    """Représente un paquet Anki et sa hiérarchie (Subdecks)"""
    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (did)
    parent_deck = ForeignKeyField('self', null=True, backref='subdecks')
    name = CharField(unique=True)  # Ex: "Science::Physique"
    description = TextField(null=True)
    created_at = DateTimeField(default=datetime.datetime.now)


class NoteTypeModel(BaseModel):
    """Représente le TYPE de note (Basic, Cloze...)"""
    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (mid)
    name = CharField()
    fields_schema = TextField()  # JSON: Liste des noms des champs ["Front", "Back"]
    templates = TextField()  # JSON: Les formats HTML des différentes cartes
    css_style = TextField()  # Le CSS global du modèle


class NoteModel(BaseModel):
    """Le conteneur physique de la note. Il ne change jamais."""
    anki_id = BigIntegerField(unique=True, null=True)
    guid = CharField(unique=True)
    note_type = ForeignKeyField(NoteTypeModel, backref='notes')
    tags = TextField(null=True)
    status = CharField(default="new")

    @db.atomic()
    def add_version(self, new_content_dict: dict, source: str = "manual") -> 'NoteVersionModel':
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
            is_active=True
        )
        return new_version


class NoteVersionModel(BaseModel):
    """L'historique des contenus de la note (Le fameux système de version)."""
    note = ForeignKeyField(NoteModel, backref='versions', on_delete='CASCADE')
    version_number = IntegerField(default=1)
    content = TextField() # Le JSON contenant "Recto" et "Verso"
    created_at = DateTimeField(default=datetime.datetime.now)
    source = CharField(default="ai") # Peut être 'ai', 'manual', ou 'import'
    is_active = BooleanField(default=True) # Permet de savoir quelle version exporter

class CardModel(BaseModel):
    """La carte physique générée par la Note et rangée dans un Deck"""
    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (cid)
    note = ForeignKeyField(NoteModel, backref='cards')
    deck = ForeignKeyField(DeckModel, backref='cards')
    template_index = IntegerField(default=0)  # Index du template (Recto=0, Verso=1)


class PromptModel(BaseModel):
    """Stocke les templates Jinja2 personnalisés"""
    name = CharField(unique=True)
    content = TextField()
    description = TextField(null=True)
    is_active = BooleanField(default=True)


class AgentModel(BaseModel):
    """Définit un agent IA unique (ex: Créateur, Linteur, Contrôleur)."""
    name = CharField(unique=True)
    description = TextField(null=True)
    system_prompt = TextField()  # Stockera le contenu du prompt Jinja2

    class Meta:
        table_name = 'agents'


class PipelineModel(BaseModel):
    """Définit une chaîne d'exécution (ex: Génération Complète Ensimag)."""
    name = CharField(unique=True)
    description = TextField(null=True)

    class Meta:
        table_name = 'pipelines'


class PipelineStepModel(BaseModel):
    """Table de liaison : Associe un Agent à un Pipeline avec un ordre précis."""
    pipeline = ForeignKeyField(PipelineModel, backref='steps', on_delete='CASCADE')
    agent = ForeignKeyField(AgentModel, backref='pipeline_steps', on_delete='CASCADE')
    step_order = IntegerField()  # 1, 2, 3... l'ordre d'exécution

    class Meta:
        table_name = 'pipeline_steps'
        # On s'assure qu'il n'y a pas deux étapes "1" dans le même pipeline
        indexes = (
            (('pipeline', 'step_order'), True),
        )

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
    folder = ForeignKeyField(FolderModel, backref='documents', null=True, on_delete='CASCADE')

def init_db() -> None:
    db.connect(reuse_if_open=True)
    # Ajout des nouvelles tables à l'initialisation
    db.create_tables([
        DeckModel, NoteTypeModel, NoteModel, CardModel,NoteVersionModel,
        AgentModel, PipelineModel, PipelineStepModel,DocumentModel,FolderModel,PromptModel
    ])

def seed_initial_data() -> None:
    """
    Responsabilité UNIQUE : Peupler la base avec les données métier indispensables
    au premier lancement de l'application.
    """
    # Si des agents existent déjà, on ne fait rien
    if AgentModel.select().count() > 0:
        return


    # Agent 1 : Le Créateur
    extracteur = AgentModel.create(
        name="Extracteur de Connaissances",
        description="Extrait le contenu brut du texte...",
        system_prompt="Ton prompt ici..."
    )

    # Agent 2 : Le Contrôleur
    controleur = AgentModel.create(
        name="Contrôleur Technique JSON/LaTeX",
        description="Vérifie le formatage...",
        system_prompt="Ton prompt strict ici..."
    )

    # Pipeline par défaut
    pipeline_complet = PipelineModel.create(
        name="Génération Standard",
        description="Extraction suivie d'un contrôle rigoureux."
    )

    PipelineStepModel.create(pipeline=pipeline_complet, agent=extracteur, step_order=1)
    PipelineStepModel.create(pipeline=pipeline_complet, agent=controleur, step_order=2)