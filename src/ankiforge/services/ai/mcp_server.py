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
