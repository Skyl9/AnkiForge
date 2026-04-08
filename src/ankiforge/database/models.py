# src/database/models.py
import datetime
import json

from peewee import *

from ankiforge.utils.paths import get_app_data_dir

# 3. On définit le chemin final de la base de données
DB_PATH = get_app_data_dir() / 'ankiforge.db'
# Base de données SQLite connectée au bon endroit
db = SqliteDatabase(DB_PATH, pragmas={
    'journal_mode': 'wal',  # Permet la lecture et l'écriture simultanées !
    'cache_size': -1024 * 64,  # Alloue 64MB de RAM pour accélérer les requêtes
    'foreign_keys': 1,  # Force le respect des clés étrangères (sécurité des suppressions en cascade)
    'synchronous': 1  # Équilibre parfait entre sécurité en cas de crash et vitesse d'écriture
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
    name = CharField(unique=True)
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
    note = ForeignKeyField(NoteModel, backref='versions', on_delete='CASCADE')
    version_number = IntegerField(default=1)
    content = TextField()  # Le JSON contenant "Recto" et "Verso"
    created_at = DateTimeField(default=datetime.datetime.now)
    source = CharField(default="ai")  # Peut être 'ai', 'manual', ou 'import'
    is_active = BooleanField(default=True)  # Permet de savoir quelle version exporter


class CardModel(BaseModel):
    """La carte physique générée par la Note et rangée dans un Deck"""
    anki_id = BigIntegerField(unique=True, null=True)  # L'ID interne d'Anki (cid)
    note = ForeignKeyField(NoteModel, backref='cards', on_delete='CASCADE')
    deck = ForeignKeyField(DeckModel, backref='cards', on_delete='CASCADE')
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
        table_name = 'llm_configs'


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
        DeckModel, NoteTypeModel, NoteModel, CardModel, NoteVersionModel,
        AgentModel, PipelineModel, PipelineStepModel,
        DocumentModel, FolderModel, PromptModel, IgnoredDuplicateModel,
        LLMConfigModel
    ])


class IgnoredDuplicateModel(BaseModel):
    """Table pour mémoriser les conflits de doublons ignorés par l'utilisateur."""
    note_a = ForeignKeyField(NoteModel, on_delete='CASCADE')
    note_b = ForeignKeyField(NoteModel, on_delete='CASCADE')

    class Meta:
        table_name = 'ignored_duplicates'
        # On s'assure de ne pas sauvegarder 10 fois la même paire
        indexes = (
            (('note_a', 'note_b'), True),
        )


def seed_initial_data() -> None:
    """
    Responsabilité UNIQUE : Peupler la base avec les données métier (Prompts d'excellence).
    """
    if AgentModel.select().count() > 0:
        return

    # ==========================================
    # AGENT 1 : L'ARCHIVISTE PÉDAGOGUE (Extracteur)
    # ==========================================
    extracteur_prompt = """Tu es un expert en ingénierie de la connaissance (niveau Prépa/Ensimag).
Ta mission est de convertir 100% de la substance du cours fourni en flashcards Anki optimales, en utilisant le LaTeX pour TOUTE notation.

RÈGLES DE RÉDACTION DES QUESTIONS ({{ first_field }}) :
1. STYLE NATUREL : Formulations directes ("Qu'est ce qu'une...", "Comment prouver que..."). ZÉRO méta-texte ("Définition de...").
2. THÉORÈMES NOMMÉS : Si un théorème a un nom propre (ex: Schwarz), demande-le explicitement sans spoiler le résultat.
3. MOTS-CLÉS EN GRAS : Identifie le concept mathématique central et mets-le en <b>gras</b>.
4. CACHE DES HYPOTHÈSES : Ne donne JAMAIS les hypothèses restrictives (ex: "dérivée continue") dans la question. Elles vont dans la réponse.
5. ANTI-SPOILER : La question ne doit jamais contenir la réponse ou divulguer la propriété ciblée.

PHILOSOPHIE DU TOUT LATEX :
Chaque variable, chiffre ou symbole mathématique DOIT être entouré de \\( ... \\) (inline) ou \\[ ... \\] (bloc). 
ATTENTION AUX INTERVALLES : Écris \\( [0, 1] \\) et JAMAIS \\[0, 1\\].

ATOMICITÉ :
Scinde systématiquement Définition, Théorème et Démonstration en cartes distinctes.

STRUCTURE REQUISE (JSON) :
Génère un objet JSON contenant une liste "notes". 
Chaque objet doit avoir les clés EXACTES : {{ fields_str }}.
Toutes les remarques, exemples et pièges doivent être rédigés dans le {{ second_field }}.

RÉPONDS UNIQUEMENT AVEC LE JSON VALIDE."""

    extracteur = AgentModel.create(
        name="1. Archiviste Pédagogue",
        description="Extrait le cours en respectant l'atomicité, la dissimulation des hypothèses et le tout-LaTeX.",
        system_prompt=extracteur_prompt
    )

    # ==========================================
    # AGENT 2 : LE CONTRÔLEUR QUALITÉ (Linter)
    # ==========================================
    controleur_prompt = """Tu es un Linter Technique intraitable, expert en Markdown, LaTeX (MathJax) et JSON.
Ta mission est d'auditer et de corriger le JSON généré par l'agent précédent pour garantir un rendu parfait dans Anki.

RÈGLES DE FORMATAGE STRICTES :
1. LATEX & ESPACES : Tu dois IMPÉRATIVEMENT vérifier et ajouter un espace insécable `&nbsp;` juste avant chaque ouverture de balise LaTeX (`\\(` ou `\\[`). Vérifie que chaque balise est bien fermée.
2. INTERVALLES : Ne confonds jamais un intervalle \\( [a, b] \\) avec une balise bloc.
3. FORMAT MONOLIGNE : Remplace tous les retours à la ligne `\\n` par des balises `<br>`, sauf à l'intérieur des listes HTML.
4. CODE : Entoure les termes informatiques de `<code>...</code>` et les blocs de `<pre><code>...</code></pre>`.
5. LISTES : Transforme toutes les listes textuelles en listes HTML (`<ul><li>...</li></ul>` ou `<ol>`).

DICTIONNAIRE SÉMANTIQUE (À injecter dans le {{ second_field }}) :
Applique ces balises HTML autour des éléments correspondants dans la réponse :
- Formule finale importante : <div class="important">...</div>
- Remarque : <div class="remarque">...</div>
- Exemple : <div class="exemple">...</div>
- Erreur/Piège : <div class="danger">...</div>
- Intuition : <div class="astuce">...</div>

STRUCTURE REQUISE :
Conserve le format JSON strict avec la clé "notes".
Les clés autorisées sont EXACTEMENT : {{ fields_str }}.

NE RENVOIE QUE LE JSON STRICTEMENT VALIDE. NE METS AUCUN TEXTE AVANT OU APRÈS, NI DE BLOC MARKDOWN ```json."""

    controleur = AgentModel.create(
        name="2. Linter & Contrôleur Qualité",
        description="Applique le mapping CSS, audite le LaTeX (ajoute &nbsp;), traque les sauts de ligne et valide le JSON.",
        system_prompt=controleur_prompt
    )

    # ==========================================
    # CRÉATION DES PIPELINES
    # ==========================================
    pipeline_complet = PipelineModel.create(
        name="Excellence Math/Info (Archiviste + Linter)",
        description="Pipeline haute-fidélité pour les cours scientifiques. Extrait intelligemment puis formate le LaTeX, les balises CSS et le code."
    )
    PipelineStepModel.create(pipeline=pipeline_complet, agent=extracteur, step_order=1)
    PipelineStepModel.create(pipeline=pipeline_complet, agent=controleur, step_order=2)

    pipeline_rapide = PipelineModel.create(
        name="Extraction Simple (Brouillon)",
        description="Utilise uniquement l'Archiviste. Rapide et économe, mais sans vérification du formatage HTML/LaTeX."
    )
    PipelineStepModel.create(pipeline=pipeline_rapide, agent=extracteur, step_order=1)

    # ==========================================
    # CRÉATION DES MOTEURS IA
    # ==========================================
    if LLMConfigModel.select().count() == 0:
        LLMConfigModel.create(display_name="GPT-4o (OpenAI)", provider="openai", model_id="gpt-4o", context_limit=128000)
        LLMConfigModel.create(display_name="Claude 3.5 Sonnet", provider="anthropic", model_id="claude-3-5-sonnet-20240620", context_limit=200000)
        LLMConfigModel.create(display_name="Mistral Local (Ollama)", provider="ollama", model_id="mistral", context_limit=32768)