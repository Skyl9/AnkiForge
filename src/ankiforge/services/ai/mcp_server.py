import logging
import asyncio
from mcp.server.mcpserver import MCPServer
from ankiforge.database.models import db

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
        logger.warning(f"Tool query_peewee échoué avec la requête : {sql_query}. Erreur : {e}")
        return f"Erreur SQL : {str(e)}"


@mcp.tool()
def search_document(query: str, document_id: int) -> str:
    """
    (Bouchon) Recherche une information précise dans un document spécifique via FAISS ou recherche textuelle.
    """
    logger.info(f"Recherche dans le document {document_id} avec la requête : {query}")
    return f"Résultats simulés pour la recherche '{query}' dans le document {document_id}. (RAG non initialisé)."


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
