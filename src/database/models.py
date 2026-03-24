# src/database/models.py
import datetime
import os
import uuid

from peewee import *

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Base de données SQLite (fichier local)
DATA_DIR = os.path.join(BASE_DIR, 'data')
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
# 3. On définit le chemin final de la base de données
DB_PATH = os.path.join(DATA_DIR, 'ankiforge.db')

# Base de données SQLite connectée au bon endroit
db = SqliteDatabase(DB_PATH)


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

    def add_version(self, new_content_dict: dict, source: str = "manual") -> 'NoteVersionModel':
        """
        Crée une nouvelle version de la note (comme un git commit).
        Désactive l'ancienne version active.
        """
        import json

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


def init_db():
    db.connect()
    # Ajout des nouvelles tables à l'initialisation
    db.create_tables([
        DeckModel, NoteTypeModel, NoteModel, CardModel,NoteVersionModel,
        AgentModel, PipelineModel, PipelineStepModel  # <-- NOUVEAU
    ])
    if AgentModel.select().count() == 0:
        print("🌱 Création des Agents IA par défaut...")

        # Agent 1 : Le Créateur
        extracteur = AgentModel.create(
            name="Extracteur de Connaissances",
            description="Extrait le contenu brut du texte pour créer les flashcards de base.",
            system_prompt="""Tu es un expert en création de flashcards. 
    Extrait les informations clés du texte.
    CONTRAINTE ABSOLUE : Réponds UNIQUEMENT avec un objet JSON valide contenant la clé "notes".
    Clés exigées pour chaque note : ["{{ fields_str }}"]."""
        )

        # Agent 2 : Le Contrôleur Technique
        controleur = AgentModel.create(
            name="Contrôleur Technique JSON/LaTeX",
            description="Vérifie le formatage des données (JSON strict, balises LaTeX).",
            system_prompt="""Tu es un ingénieur qualité strict.
    Vérifie les flashcards fournies. 
    1. Vérifie que chaque objet possède EXACTEMENT ces clés : ["{{ fields_str }}"].
    2. Formate les mathématiques avec \\( et \\[.
    CONTRAINTE ABSOLUE : Réponds UNIQUEMENT avec le JSON final valide."""
        )

        # On crée un Pipeline par défaut
        pipeline_complet = PipelineModel.create(
            name="Génération Standard",
            description="Extraction suivie d'un contrôle technique rigoureux."
        )

        # On relie les agents au pipeline dans le bon ordre
        PipelineStepModel.create(pipeline=pipeline_complet, agent=extracteur, step_order=1)
        PipelineStepModel.create(pipeline=pipeline_complet, agent=controleur, step_order=2)
