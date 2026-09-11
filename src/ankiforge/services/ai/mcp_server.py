import logging

from mcp.server.mcpserver import MCPServer

from ankiforge.database.models import LLMConfigModel, db
from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry
from ankiforge.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)

# Initialisation du serveur MCP AnkiForge
mcp = MCPServer("AnkiForge")


@mcp.tool()
def audit_deck_wozniak(deck_name: str) -> str:
    """Effectue un audit de qualité Wozniak complet sur un paquet (20 règles de formulation, atomicité, redondance)."""
    return ConsultantToolRegistry.audit_deck_wozniak(deck_name)


@mcp.tool()
def audit_card_wozniak(note_id: int) -> str:
    """Analyse chirurgicale d'une carte spécifique au regard des 20 règles de Piotr Wozniak."""
    return ConsultantToolRegistry.audit_card_wozniak(note_id)


@mcp.tool()
def find_duplicate_cards(deck_name: str = "", threshold: float = 0.75) -> str:
    """Détecte les cartes doublons ou formulées de manière quasi-identique dans un paquet via distance Levenshtein."""
    return ConsultantToolRegistry.find_duplicate_cards(deck_name, threshold)


@mcp.tool()
def propose_card_refactor(note_id: int, new_fields_json: str, explanation: str = "") -> str:
    """Propose une modification de carte avec Diff pour validation humaine (Garde-Fou)."""
    return ConsultantToolRegistry.propose_card_refactor(note_id, new_fields_json, explanation)


@mcp.tool()
def propose_card_split(note_id: int, new_cards_json: str, explanation: str = "") -> str:
    """Propose de scinder une carte dense en N cartes atomiques avec Diff comparatif pour validation humaine."""
    return ConsultantToolRegistry.propose_card_split(note_id, new_cards_json, explanation)


@mcp.tool()
def propose_css_tune(note_type_name: str, css_snippet: str, selector: str = "") -> str:
    """Propose un ajustement CSS pour un modèle de carte avec aperçu live avant enregistrement."""
    return ConsultantToolRegistry.propose_css_tune(note_type_name, css_snippet, selector)


@mcp.tool()
def get_collection_panorama_360() -> str:
    """Fournit une vision panoramique 360° de la collection (paquets, cartes, sangsues, santé globale)."""
    return ConsultantToolRegistry.get_collection_panorama_360()


@mcp.tool()
def inspect_deck_deep_scan(deck_name: str) -> str:
    """Effectue une analyse approfondie d'un paquet spécifique (distribution des intervalles, top cartes sangsues)."""
    return ConsultantToolRegistry.inspect_deck_deep_scan(deck_name)


@mcp.tool()
def get_note_full_profile_360(note_id: int) -> str:
    """Génère le profil complet 360° d'une note (cartes, historique Time Machine, stats SRS, tags)."""
    return ConsultantToolRegistry.get_note_full_profile_360(note_id)


@mcp.tool()
def query_peewee(sql_query: str) -> str:
    """Exécute une requête SQL en lecture seule sur la base de données SQLite."""
    return ConsultantToolRegistry.query_peewee(sql_query)


@mcp.tool()
def get_deck_stats(deck_name: str) -> str:
    """Récupère les statistiques détaillées d'un paquet Anki (nombre total de cartes, révisions et difficultés)."""
    return ConsultantToolRegistry.get_deck_stats(deck_name)


@mcp.tool()
def get_cards_by_deck_or_tag(deck_name: str = "", tag: str = "", limit: int = 20) -> str:
    """Récupère une liste de cartes filtrée par nom de paquet ou par tag."""
    return ConsultantToolRegistry.get_cards_by_deck_or_tag(deck_name, tag, limit)


@mcp.tool()
def find_cards_by_content(query: str, deck_name: str = "", limit: int = 8) -> str:
    """Recherche des cartes par mot-clé dans leur question/réponse pour retrouver facilement leur note_id."""
    return ConsultantToolRegistry.find_cards_by_content(query, deck_name, limit)


@mcp.tool()
def list_note_types() -> str:
    """Liste tous les modèles de cartes (Note Types) disponibles dans la collection."""
    return ConsultantToolRegistry.list_note_types()


@mcp.tool()
def get_note_type_details(note_type_name: str) -> str:
    """Consulte les détails complets d'un modèle de carte (champs requis, templates HTML Recto/Verso, CSS)."""
    return ConsultantToolRegistry.get_note_type_details(note_type_name)


@mcp.tool()
def propose_note_type_refactor(
    note_type_name: str,
    new_fields_schema_json: str = "",
    new_css: str = "",
    new_templates_json: str = "",
    new_description: str = "",
    explanation: str = "",
) -> str:
    """Propose une modification structurelle d'un modèle de carte avec Garde-Fou."""
    return ConsultantToolRegistry.propose_note_type_refactor(note_type_name, new_fields_schema_json, new_css, new_templates_json, new_description, explanation)


@mcp.tool()
def search_document(query: str, document_id: int) -> str:
    """Recherche une information précise dans un document spécifique via FAISS."""
    logger.info("Recherche dans le document %d avec la requête : %s", document_id, query)

    llm_config = LLMConfigModel.select().first()
    if not llm_config:
        return "Erreur : Aucun moteur IA configuré. Impossible d'effectuer la recherche vectorielle."

    try:
        rag = RAGService(llm_config)
        results = rag.search(str(document_id), query, top_k=3)

        snippets = []
        for r in results:
            content = getattr(r, "page_content", getattr(r, "text", str(r)))
            snippets.append(content)

        if not snippets:
            return "Aucun passage pertinent trouvé dans ce document pour cette requête."

        return "Passages pertinents extraits :\n\n" + "\n---\n".join(snippets)

    except Exception as e:
        logger.error("Erreur lors de la recherche RAG dans le serveur MCP : %s", e)
        return f"Erreur lors de la recherche vectorielle : {e}"


# =====================================================================
# OUTILS DE DOCUMENTATION & BASE DE CONNAISSANCES INTERNE (ZENSICAL)
# =====================================================================


@mcp.tool()
def search_app_documentation(query: str, category: str = "", limit: int = 5) -> str:
    """Recherche des explications, guides et références d'architecture dans la documentation officielle d'AnkiForge via SQLite FTS5 BM25."""
    return ConsultantToolRegistry.search_app_documentation(query, category, limit)


@mcp.tool()
def read_app_doc_page(doc_path: str, section_anchor: str = "") -> str:
    """Consulte le contenu intégral ou une section d'une page de documentation officielle d'AnkiForge (ex: 'features/consultant_mcp.md')."""
    return ConsultantToolRegistry.read_app_doc_page(doc_path, section_anchor)


@mcp.tool()
def list_app_doc_topics(category: str = "") -> str:
    """Consulte le sommaire exhaustif de la documentation officielle d'AnkiForge classé par thématiques."""
    return ConsultantToolRegistry.list_app_doc_topics(category)


@mcp.tool()
def get_feature_quick_help(feature_name: str) -> str:
    """Obtient une synthèse immédiate d'une fonctionnalité clé (Ollama, KaTeX, DAG, RAG, Wozniak, Nuitka, Smart Merge, MCP)."""
    return ConsultantToolRegistry.get_feature_quick_help(feature_name)


# =====================================================================
# RESSOURCES MCP (EXPLORATION DIRECTE DE LA DOCUMENTATION)
# =====================================================================


@mcp.resource("docs://topics")
def get_docs_topics_resource() -> str:
    """Retourne la liste hiérarchique complète des chapitres et pages de la documentation officielle."""
    return ConsultantToolRegistry.list_app_doc_topics()


@mcp.resource("docs://page/{doc_path}")
def get_doc_page_resource(doc_path: str) -> str:
    """Fournit le contenu brut Markdown d'une page de documentation officielle."""
    return ConsultantToolRegistry.read_app_doc_page(doc_path)


# =====================================================================
# PROMPTS MCP (MODÈLES DE GUIDAGE IA)
# =====================================================================


@mcp.prompt("explain_ankiforge_feature")
def prompt_explain_feature(feature_name: str) -> str:
    """Prompt guidé pour expliquer pas à pas une fonctionnalité d'AnkiForge avec extraits officiels."""
    doc_summary = ConsultantToolRegistry.get_feature_quick_help(feature_name)
    return (
        f"Tu es un expert d'AnkiForge. Explique la fonctionnalité '{feature_name}' en t'appuyant sur la documentation officielle ci-dessous :\n\n"
        f"{doc_summary}\n\n"
        "Donne des exemples concrets d'utilisation et les bonnes pratiques recommandées."
    )


@mcp.prompt("audit_architecture_compliance")
def prompt_audit_architecture(target_code_or_rule: str) -> str:
    """Prompt guidé pour vérifier la conformité d'un code ou d'une conception avec les 9 dossiers d'architecture AnkiForge."""
    arch_doc = ConsultantToolRegistry.read_app_doc_page("Dossier_architecture/02_architecture_technique.md")
    return (
        "Tu es l'architecte en chef d'AnkiForge. Vérifie que le code ou la proposition suivante respecte les principes architecturaux "
        f"décrits dans la documentation :\n\n{arch_doc[:2500]}...\n\n"
        f"Élément à auditer :\n{target_code_or_rule}"
    )


# =====================================================================
# GESTION DES AGENTS DÉDIÉS AU SERVEUR MCP
# =====================================================================


@mcp.tool()
def list_mcp_agents(scope: str = "mcp") -> str:
    """Liste tous les agents dédiés enregistrés (Auditeur Wozniak, Architecte CSS, Analyste SRS...) avec leurs outils."""
    return ConsultantToolRegistry.list_mcp_agents(scope)


@mcp.tool()
def get_mcp_agent_details(agent_name: str) -> str:
    """Consulte la configuration détaillée d'un agent dédié (prompt système Jinja2, modèle assigné, liste des outils)."""
    return ConsultantToolRegistry.get_mcp_agent_details(agent_name)


@mcp.tool()
def invoke_mcp_agent(agent_name: str, message: str, conversation_history_json: str = "[]") -> str:
    """Délègue une tâche ou une question à un agent dédié spécifique selon ses autorisations d'outils et son prompt."""
    return ConsultantToolRegistry.invoke_mcp_agent(agent_name, message, conversation_history_json)


@mcp.tool()
def create_or_update_mcp_agent(
    name: str,
    description: str,
    system_prompt: str,
    allowed_tools_json: str = "[]",
    persona_type: str = "mcp",
) -> str:
    """Crée ou met à jour la configuration d'un agent dédié dans la collection."""
    from ankiforge.database.models import PersonaModel

    try:
        agent, created = PersonaModel.get_or_create(
            name=name.strip(),
            defaults={
                "description": description.strip(),
                "system_prompt": system_prompt.strip(),
                "allowed_tools": allowed_tools_json.strip() or "[]",
                "persona_type": persona_type.strip(),
            },
        )
        if not created:
            agent.description = description.strip()
            agent.system_prompt = system_prompt.strip()
            agent.allowed_tools = allowed_tools_json.strip() or "[]"
            agent.persona_type = persona_type.strip()
            agent.save()
            action_str = "mis à jour"
        else:
            action_str = "créé"

        return f"Succès : L'agent dédié '{agent.name}' a été {action_str} avec succès (portée: {agent.persona_type})."
    except Exception as e:
        logger.error("Erreur create_or_update_mcp_agent : %s", e)
        return f"Erreur lors de l'enregistrement de l'agent : {e}"


@mcp.resource("agents://list")
def get_agents_list_resource() -> str:
    """Retourne la liste hiérarchique de tous les agents dédiés au format texte/JSON."""
    return ConsultantToolRegistry.list_mcp_agents(scope="all")


@mcp.resource("agents://{agent_name}")
def get_agent_profile_resource(agent_name: str) -> str:
    """Fournit le profil et la consigne système d'un agent dédié spécifique."""
    return ConsultantToolRegistry.get_mcp_agent_details(agent_name)


@mcp.prompt("run_with_agent")
def prompt_run_with_agent(agent_name: str, task: str) -> str:
    """Prompt guidé pour exécuter une tâche en adoptant la posture et les outils d'un agent dédié."""
    agent_info = ConsultantToolRegistry.get_mcp_agent_details(agent_name)
    return (
        f"Tu incarnes l'agent spécialisé '{agent_name}'. Voici ton profil et tes consignes strictes :\n\n"
        f"{agent_info}\n\n"
        f"### Mission à accomplir :\n{task}\n\n"
        "Respecte strictement tes compétences et ton périmètre d'action."
    )


def run_server() -> None:
    """Démarre le serveur FastMCP en mode asynchrone sécurisé."""
    logger.info("Démarrage du serveur MCP AnkiForge...")
    if db.is_closed():
        db.connect()

    try:
        mcp.run()
    except KeyboardInterrupt:
        logger.info("Arrêt du serveur MCP AnkiForge.")
    finally:
        if not db.is_closed():
            db.close()


if __name__ == "__main__":
    run_server()
