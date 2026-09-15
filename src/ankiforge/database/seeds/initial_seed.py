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

    if NoteTypeModel.select().where(NoteTypeModel.name == "Image Occlusion Enhanced").count() == 0:
        NoteTypeModel.create(
            name="Image Occlusion Enhanced",
            description="Masquage d'images (Image Occlusion). Découverte active sur schémas, diagrammes et planches anatomiques.",
            fields_schema=json.dumps(
                [
                    "id",
                    "Header",
                    "Image",
                    "Question Mask",
                    "Answer Mask",
                    "Original Mask",
                    "Footer",
                    "Remarks",
                    "Sources",
                    "Extra 1",
                    "Extra 2",
                ],
                ensure_ascii=False,
            ),
            templates=json.dumps(
                [
                    {
                        "name": "Image Occlusion",
                        "qfmt": (
                            "{{#Header}}<div style='font-weight: bold; margin-bottom: 8px;'>{{Header}}</div>{{/Header}}\n"
                            "<div id='image-wrapper'>\n"
                            "    {{Image}}\n"
                            "    {{Question Mask}}\n"
                            "</div>\n"
                            "{{#Footer}}<div style='margin-top: 8px; font-size: 0.9em; opacity: 0.8;'>{{Footer}}</div>{{/Footer}}"
                        ),
                        "afmt": (
                            "{{#Header}}<div style='font-weight: bold; margin-bottom: 8px;'>{{Header}}</div>{{/Header}}\n"
                            "<div id='image-wrapper'>\n"
                            "    {{Image}}\n"
                            "    {{Answer Mask}}\n"
                            "</div>\n"
                            "{{#Footer}}<div style='margin-top: 8px; font-size: 0.9em; opacity: 0.8;'>{{Footer}}</div>{{/Footer}}\n"
                            "{{#Remarks}}<hr id=answer><div style='text-align: left; margin-top: 8px;'>{{Remarks}}</div>{{/Remarks}}"
                        ),
                    }
                ],
                ensure_ascii=False,
            ),
            css_style=(
                ".card {\n"
                "  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;\n"
                "  font-size: 16px;\n"
                "  text-align: center;\n"
                "  color: palette(text);\n"
                "}\n"
                "#image-wrapper {\n"
                "  position: relative;\n"
                "  display: inline-block;\n"
                "  max-width: 100%;\n"
                "}\n"
                "#image-wrapper img {\n"
                "  max-width: 100%;\n"
                "  height: auto;\n"
                "}\n"
                "#image-wrapper img:first-child {\n"
                "  display: block;\n"
                "  position: static;\n"
                "}\n"
                "#image-wrapper img:not(:first-child) {\n"
                "  position: absolute;\n"
                "  top: 0;\n"
                "  left: 0;\n"
                "  width: 100%;\n"
                "  height: 100%;\n"
                "  pointer-events: none;\n"
                "}\n"
            ),
        )

    # Lecture des prompts depuis les fichiers .jinja2
    extracteur_prompt = (prompts_dir / "extracteur.jinja2").read_text(encoding="utf-8") if (prompts_dir / "extracteur.jinja2").exists() else ""
    controleur_prompt = (prompts_dir / "controleur.jinja2").read_text(encoding="utf-8") if (prompts_dir / "controleur.jinja2").exists() else ""
    cloze_prompt = (prompts_dir / "cloze.jinja2").read_text(encoding="utf-8") if (prompts_dir / "cloze.jinja2").exists() else ""

    # ==========================================
    # PERSONA 1 : L'ARCHIVISTE PÉDAGOGUE (Extracteur)
    # ==========================================
    extracteur, _ = PersonaModel.get_or_create(
        name="Archiviste Pédagogue",
        defaults={
            "description": "Extrait le cours en respectant l'atomicité, la dissimulation des hypothèses et le tout-LaTeX.",
            "system_prompt": extracteur_prompt,
        },
    )

    # ==========================================
    # PERSONA 2 : LE CONTRÔLEUR QUALITÉ (Linter)
    # ==========================================
    controleur, _ = PersonaModel.get_or_create(
        name="Linter & Contrôleur Qualité",
        defaults={
            "description": "Applique le mapping CSS, audite le LaTeX (ajoute &nbsp;), traque les sauts de ligne et valide le JSON.",
            "system_prompt": controleur_prompt,
        },
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
            "persona_type": "mcp",
            "allowed_tools": json.dumps(["*"]),
        },
    )

    # ==========================================
    # PERSONAS DÉDIÉS AU SERVEUR MCP
    # ==========================================
    from ankiforge.services.ai.tools_catalog import AGENT_PRESETS

    PersonaModel.get_or_create(
        name="Auditeur Wozniak",
        defaults={
            "description": "Auditeur expert basé sur les 20 règles de formulation de Piotr Wozniak (atomicité, clarté).",
            "system_prompt": (
                "Tu es l'Auditeur Qualité Wozniak d'AnkiForge. Ton rôle exclusif est d'analyser la clarté et la rétention des cartes "
                "au regard des 20 règles fondamentales de Piotr Wozniak. Tu traques le manque d'atomicité, les listes complexes "
                "et les interférences. Tu proposes des reformulations précises sous forme de Staged Diffs."
            ),
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["wozniak_auditor"]["tools"]),
        },
    )

    PersonaModel.get_or_create(
        name="Architecte Modèles & CSS",
        defaults={
            "description": "Spécialiste de la structure des types de cartes, gabarits HTML/KaTeX et personnalisation visuelle CSS.",
            "system_prompt": (
                "Tu es l'Architecte Modèles & CSS d'AnkiForge. Ton rôle est de concevoir, auditer et améliorer les types de notes, "
                "les schémas de champs, les templates Jinja2/KaTeX et les styles CSS. Tu t'assures de l'ergonomie visuelle sur mobile et desktop."
            ),
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["css_architect"]["tools"]),
        },
    )

    PersonaModel.get_or_create(
        name="Analyste SRS & Sangsues",
        defaults={
            "description": "Spécialiste de la dynamique d'apprentissage, analyse des taux d'oubli, cartes sangsues et prédictions FSRS.",
            "system_prompt": (
                "Tu es l'Analyste SRS d'AnkiForge. Ton rôle est d'examiner en profondeur les métriques d'apprentissage de la collection : "
                "distribution des intervalles, cartes provoquant des échecs répétés (sangsues), et charge de révision future."
            ),
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["srs_analyst"]["tools"]),
        },
    )

    PersonaModel.get_or_create(
        name="Chercheur RAG & Documents",
        defaults={
            "description": "Spécialiste de l'interrogation des sources documentaires importées, index sémantiques et analyse de couverture.",
            "system_prompt": (
                "Tu es le Chercheur RAG d'AnkiForge. Ton rôle est d'explorer les documents sources importés (PDF, web, transcriptions) "
                "et la documentation officielle pour vérifier que toutes les notions clés ont été convenablement transformées en flashcards."
            ),
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["rag_researcher"]["tools"]),
        },
    )

    PersonaModel.get_or_create(
        name="Administrateur BDD Peewee",
        defaults={
            "description": "Expert technique habilité à effectuer des diagnostics SQL directs et à exécuter des scripts Python.",
            "system_prompt": (
                "Tu es l'Administrateur BDD Peewee d'AnkiForge. Tu disposes des autorisations pour exécuter des requêtes SQL SELECT "
                "en lecture seule et lancer des outils d'ingénierie Python afin d'extraire des rapports statistiques avancés."
            ),
            "persona_type": "mcp",
            "allowed_tools": json.dumps(AGENT_PRESETS["database_admin"]["tools"]),
        },
    )
    # ==========================================
    # CRÉATION DES PIPELINES
    # ==========================================
    pipeline_complet, _ = PipelineModel.get_or_create(
        name="Excellence Math/Info (Archiviste + Linter)",
        defaults={
            "description": "Pipeline haute-fidélité pour les cours scientifiques. Extrait intelligemment puis formate le LaTeX, les balises CSS et le code.",
        },
    )
    if not PipelineStepModel.select().where((PipelineStepModel.pipeline == pipeline_complet) & (PipelineStepModel.step_order == 1)).exists():
        PipelineStepModel.create(pipeline=pipeline_complet, persona=extracteur, step_type="LLM_PROMPT", step_order=1)
    if not PipelineStepModel.select().where((PipelineStepModel.pipeline == pipeline_complet) & (PipelineStepModel.step_order == 2)).exists():
        PipelineStepModel.create(pipeline=pipeline_complet, persona=controleur, step_type="LLM_PROMPT", step_order=2)

    pipeline_rapide, _ = PipelineModel.get_or_create(
        name="Extraction Simple (Brouillon)",
        defaults={
            "description": "Utilise uniquement l'Archiviste. Rapide et économe, mais sans vérification du formatage HTML/LaTeX.",
        },
    )
    if not PipelineStepModel.select().where((PipelineStepModel.pipeline == pipeline_rapide) & (PipelineStepModel.step_order == 1)).exists():
        PipelineStepModel.create(pipeline=pipeline_rapide, persona=extracteur, step_type="LLM_PROMPT", step_order=1)

    # ==========================================
    # CRÉATION DES MOTEURS IA
    # ==========================================
    if LLMConfigModel.select().count() == 0:
        LLMConfigModel.create(
            display_name="Google Gemini 3.5 Flash Lite",
            provider="gemini",
            model_id="gemini-3.5-flash-lite",
            context_limit=1048576,
            max_tokens=65536,
            sort_order=0,
            prompt_pricing=0.0,
            completion_pricing=0.0,
            is_free=True,
            supports_vision=True,
            supports_thinking=False,
            supports_json=True,
            speed_rating="ultra-fast",
            quality_tier="economy",
            recommended_tasks='["flashcards", "batch", "vision"]',
            description="Le moteur par défaut ultra-rapide et gratuit d'AnkiForge.",
        )
        LLMConfigModel.create(
            display_name="GPT-4o (OpenAI)",
            provider="openai",
            model_id="gpt-4o",
            context_limit=128000,
            max_tokens=16384,
            sort_order=10,
            prompt_pricing=2.5,
            completion_pricing=10.0,
            supports_vision=True,
            supports_thinking=False,
            supports_json=True,
            speed_rating="fast",
            quality_tier="flagship",
            recommended_tasks='["flashcards", "audit", "vision"]',
            description="Référence polyvalente pour la formulation et l'audit Wozniak.",
        )
        LLMConfigModel.create(
            display_name="Claude 3.7 Sonnet (Anthropic)",
            provider="anthropic",
            model_id="claude-3-7-sonnet-20250219",
            context_limit=200000,
            max_tokens=64000,
            sort_order=15,
            prompt_pricing=3.0,
            completion_pricing=15.0,
            supports_vision=True,
            supports_thinking=True,
            supports_json=True,
            speed_rating="fast",
            quality_tier="flagship",
            recommended_tasks='["flashcards", "audit", "reasoning", "vision"]',
            description="Modèle hybride avec mode Extended Thinking et vision de pointe.",
        )
        LLMConfigModel.create(
            display_name="Mistral Local (Ollama)",
            provider="ollama",
            model_id="mistral",
            context_limit=32768,
            max_tokens=16384,
            sort_order=30,
            prompt_pricing=0.0,
            completion_pricing=0.0,
            is_free=True,
            supports_vision=False,
            supports_thinking=False,
            supports_json=True,
            speed_rating="fast",
            quality_tier="balanced",
            recommended_tasks='["flashcards", "batch"]',
            description="Modèle 100% local hébergé sur votre machine via Ollama.",
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
