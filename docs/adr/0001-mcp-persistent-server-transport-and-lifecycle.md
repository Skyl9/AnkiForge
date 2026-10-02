# Serveur MCP persistant externe pour agents CLI

Pour permettre à des agents autonomes externes (comme `agy`, Claude Code ou OpenCode) d'interagir avec AnkiForge en direct pendant que l'utilisateur travaille dans l'IDE ou en mode headless, nous exposons un serveur d'écoute local en arrière-plan via le protocole MCP en dual-stack : transport principal **Streamable HTTP** standard MCP 2.x (`http://127.0.0.1:8765/mcp`) et transport legacy **SSE** (`http://127.0.0.1:8765/sse`).

## Statut
Accepté

## Options considérées
1. **Sous-processus stdio dédié** : Rejeté car impossible à brancher sur une session graphique PySide6 déjà en cours d'exécution (stdio est monopolisé par le processus parent).
2. **Socket Unix locale (`~/.ankiforge/mcp.sock`)** : Rejeté pour des raisons de portabilité multi-OS (Windows exige des pipes nommés spécifiques).
3. **HTTP / SSE local avec jeton Bearer éphémère** : Retenu initialement car standardisé dans le SDK MCP 2.x (`mcp.server.mcpserver`), interopérable avec tous les agents CLI, et gérable en multi-clients simultanés.
4. **Migration Streamable HTTP avec dual-stack SSE legacy** : Retenu pour éliminer l'erreur `405 Method Not Allowed` des clients MCP modernes (qui s'attendent par défaut à `POST /mcp`), tout en maintenant la rétrocompatibilité totale avec les clients SSE historiques (`GET /sse` + `POST /messages/`).

## Conséquences
- L'application graphique Qt héberge un thread d'arrière-plan démarrant la boucle asynchrone `uvicorn` (FastMCP / MCPServer) montant les routes Streamable HTTP (`/mcp`) et SSE legacy (`/sse`, `/messages/`) sur le même port sans bloquer l'UI Qt.
- La sécurité est garantie par un jeton Bearer aléatoire stocké à chaque session dans `~/.ankiforge/mcp_auth_token` (droits `0600`) et documenté dans `~/.ankiforge/mcp_server.json` (publiant `url` pour Streamable HTTP et `sse_url` pour SSE).
- En mode graphique, le serveur utilise la base de données active de l'IDE. En mode CLI (`ankiforge --mcp-server`), un argument `--profile` permet de cibler un profil spécifique.
- Les mutations de données (`apply_patch`) s'exécutent sous transaction SQLite WAL atomique et émettent un signal Qt pour synchroniser l'affichage de l'IDE en temps réel.
