import logging
import asyncio
from mcp.server.mcpserver import MCPServer
from ankiforge.database.models import db, LLMConfigModel
from ankiforge.services.ai.rag_service import RAGService

logger = logging.getLogger(__name__)

# Initialisation du serveur MCP AnkiForge (équivalent FastMCP en v2)
mcp = MCPServer("AnkiForge")


@mcp.tool()
def query_peewee(sql_query: str) -> str:
    """
    Exécute une requête SQL en lecture seule sur la base de données SQLite de l'utilisateur.
    Utile pour l'agent (Persona) s'il doit interroger le nombre de cartes ou le statut d'un deck.
    """
    sql_query = sql_query.strip()

    # Sécurité basique : Lecture seule (Rejet des commandes destructrices)
    forbidden_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE"]
    if any(keyword in sql_query.upper() for keyword in forbidden_keywords):
        return "Erreur : Seules les requêtes SELECT (lecture seule) sont autorisées par sécurité."

    try:
        cursor = db.execute_sql(sql_query)
        results = cursor.fetchall()

        # Formater les résultats pour l'IA
        if not results:
            return "Aucun résultat trouvé."

        columns = [description[0] for description in cursor.description]
        formatted = f"Colonnes : {', '.join(columns)}\n"
        for row in results[:50]:  # Limiter à 50 résultats pour ne pas exploser le contexte
            formatted += f"- {row}\n"

        if len(results) > 50:
            formatted += f"... (tronqué, {len(results) - 50} résultats supplémentaires masqués)\n"

        return formatted
    except Exception as e:
        logger.warning("Tool query_peewee échoué avec la requête : %s. Erreur : %s", sql_query, e)
        return f"Erreur SQL : {str(e)}"


@mcp.tool()
def get_deck_stats(deck_name: str) -> str:
    """
    Récupère les statistiques détaillées d'un paquet Anki (nombre total de cartes, révisions et difficultés).
    """
    from peewee import fn
    from ankiforge.database.models import DeckModel, CardModel

    try:
        deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
        if not deck:
            return f"Erreur : Le paquet '{deck_name}' n'existe pas."

        total_cards = CardModel.select().where(CardModel.deck == deck).count()
        avg_reps = CardModel.select(fn.AVG(CardModel.reps)).where(CardModel.deck == deck).scalar() or 0.0
        total_lapses = CardModel.select(fn.SUM(CardModel.lapses)).where(CardModel.deck == deck).scalar() or 0

        return (
            f"Statistiques du Paquet '{deck.name}' :\n"
            f"- Nombre total de cartes : {total_cards}\n"
            f"- Nombre moyen de révisions : {float(avg_reps):.1f}\n"
            f"- Nombre total d'oublis (lapses) : {total_lapses}\n"
        )
    except Exception as e:
        logger.error("Erreur get_deck_stats : %s", e)
        return f"Erreur lors de la récupération des statistiques : {e}"


@mcp.tool()
def get_cards_by_deck_or_tag(deck_name: str = "", tag: str = "", limit: int = 20) -> str:
    """
    Récupère une liste de cartes filtrée par nom de paquet ou par tag.
    """
    import json
    from ankiforge.database.models import DeckModel, CardModel, NoteModel, NoteVersionModel

    try:
        query = NoteModel.select().join(CardModel).distinct()
        if deck_name:
            deck = DeckModel.get_or_none(DeckModel.name == deck_name.strip())
            if deck:
                query = query.where(CardModel.deck == deck)
        if tag:
            query = query.where(NoteModel.tags.contains(tag.strip()))

        notes = list(query.limit(min(limit, 50)))
        if not notes:
            return "Aucune carte trouvée avec ces critères."

        result_cards = []
        for n in notes:
            active_version = NoteVersionModel.get_or_none(note=n, is_active=True)
            content = {}
            if active_version and active_version.content:
                try:
                    content = json.loads(active_version.content)
                except Exception:
                    content = {"raw": active_version.content}
            result_cards.append(
                {
                    "note_id": n.id,
                    "tags": n.tags,
                    "fields": content,
                }
            )

        return json.dumps(result_cards, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erreur get_cards_by_deck_or_tag : %s", e)
        return f"Erreur lors de la recherche des cartes : {e}"


@mcp.tool()
def update_card_model_css(note_type_name: str, css_rule: str) -> str:
    """
    Met à jour les styles CSS d'un modèle de carte (NoteTypeModel) dans la base de données.
    """
    from ankiforge.database.models import NoteTypeModel

    try:
        nt = NoteTypeModel.get_or_none(NoteTypeModel.name == note_type_name.strip())
        if not nt:
            return f"Erreur : Le modèle de carte '{note_type_name}' n'existe pas."

        with db.atomic():
            nt.css_style = (nt.css_style or "") + f"\n\n/* Ajouté par le Consultant IA */\n{css_rule}"
            nt.save()

        return f"Succès : Le style CSS du modèle '{nt.name}' a été enrichi avec succès !"
    except Exception as e:
        logger.error("Erreur update_card_model_css : %s", e)
        return f"Erreur lors de la mise à jour CSS : {e}"


@mcp.tool()
def search_document(query: str, document_id: int) -> str:
    """
    Recherche une information précise dans un document spécifique via FAISS.
    """
    logger.info("Recherche dans le document %d avec la requête : %s", document_id, query)

    llm_config = LLMConfigModel.select().first()
    if not llm_config:
        return "Erreur : Aucun moteur IA configuré. Impossible d'effectuer la recherche vectorielle."

    try:
        rag = RAGService(llm_config)
        results = rag.search(str(document_id), query, top_k=3)

        snippets = []
        for r in results:
            if isinstance(r, dict):
                loc = r.get("heading_path") or (f"Page {r.get('page_number')}" if r.get("page_number") else "Extrait")
                snippets.append(f"[{loc}] : {r.get('content', '')}")
            else:
                snippets.append(str(r))
        formatted = "Extraits trouvés :\n" + "\n---\n".join(snippets)
        return formatted
    except Exception as e:
        logger.error("Erreur lors de la recherche RAG : %s", e)
        return f"Erreur lors de la recherche : {e}"


@mcp.resource("ankiforge://database/schema")
def get_db_schema() -> str:
    """
    Expose le schéma de la base de données AnkiForge sous forme de ressource MCP.
    """
    try:
        cursor = db.execute_sql("SELECT sql FROM sqlite_master WHERE type='table';")
        schemas = [row[0] for row in cursor.fetchall() if row[0]]
        return "\n\n".join(schemas)
    except Exception as e:
        return f"Erreur lors de la récupération du schéma : {e}"


def start_mcp_server_stdio():
    """Démarre le serveur MCP en mode standard I/O."""
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    start_mcp_server_stdio()
