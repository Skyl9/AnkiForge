# ruff: noqa: E501
import json
import logging
from pathlib import Path

from ankiforge.database.models.ai import LLMConfigModel, PersonaModel
from ankiforge.database.models.cards import NoteTypeModel
from ankiforge.database.models.pipelines import PipelineModel, PipelineStepModel
from ankiforge.database.seeds.linter_rules_seed import seed_default_linter_rules

logger = logging.getLogger(__name__)


def seed_initial_data() -> None:
    """
    Peuple la base avec les données métier initiales (Modèles, Prompts, Personas, Pipelines).
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
        defaults={
            "description": "Vérifie qu'une carte ne dit pas le contraire de son cours source (Anti-Hallucination).",
            "system_prompt": juge_prompt,
        },
    )

    if PersonaModel.select().where(PersonaModel.name == "Archiviste Pédagogue").count() > 0:
        return

    # Chemin vers les ressources de prompts (dossier src/ressources/prompts ou src/ankiforge/ressources/prompts)
    prompts_dir = Path(__file__).parent.parent.parent / "ressources" / "prompts"
    if not prompts_dir.exists():
        prompts_dir = Path(__file__).parent.parent.parent.parent / "ressources" / "prompts"

    if NoteTypeModel.select().where(NoteTypeModel.name == "Basique").count() == 0:
        NoteTypeModel.create(
            name="Basique",
            description="Questions directes, définitions conceptuelles, relations de cause à effet simples. Format Q/R standard.",
            fields_schema=json.dumps(["Front", "Back"], ensure_ascii=False),
            templates=json.dumps(
                [
                    {
                        "name": "Carte 1",
                        "qfmt": "{{Front}}",
                        "afmt": "{{FrontSide}}<hr id=answer>{{Back}}",
                    }
                ],
                ensure_ascii=False,
            ),
            css_style=".card { font-family: arial; font-size: 20px; text-align: center; color: palette(text); }",
        )

    if NoteTypeModel.select().where(NoteTypeModel.name == "Texte à trous (Cloze)").count() == 0:
        NoteTypeModel.create(
            name="Texte à trous (Cloze)",
            description="Phrases denses, citations, listes ordonnées et dates clés. Utilise la syntaxe {{c1::mot}} pour masquer l'information clé dans le champ Texte.",
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
    extracteur_prompt = (prompts_dir / "extracteur.jinja2").read_text(encoding="utf-8") if (prompts_dir / "extracteur.jinja2").exists() else ""
    controleur_prompt = (prompts_dir / "controleur.jinja2").read_text(encoding="utf-8") if (prompts_dir / "controleur.jinja2").exists() else ""
    cloze_prompt = (prompts_dir / "cloze.jinja2").read_text(encoding="utf-8") if (prompts_dir / "cloze.jinja2").exists() else ""

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
        defaults={
            "description": "Assistant polyvalent pour gérer l'application, suggérer des tags et optimiser la structure de la collection.",
            "system_prompt": generaliste_prompt,
        },
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
        defaults={
            "description": "Auditeur expert basé sur les 20 règles de formulation de Piotr Wozniak.",
            "system_prompt": wozniak_prompt,
        },
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
        logger.warning("Erreur seed_builtin_tools: %s", e)
