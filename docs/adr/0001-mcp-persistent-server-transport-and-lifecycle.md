# Serveur MCP persistant externe pour agents CLI

Pour permettre à des agents autonomes externes (comme `agy`, Claude Code ou OpenCode) d'interagir avec AnkiForge en direct pendant que l'utilisateur travaille dans l'IDE ou en mode headless, nous exposons un serveur d'écoute local en arrière-plan via le protocole MCP sur transport HTTP/SSE (`http://127.0.0.1:8765/sse`).

## Statut
Accepté

## Options considérées
1. **Sous-processus stdio dédié** : Rejeté car impossible à brancher sur une session graphique PySide6 déjà en cours d'exécution (stdio est monopolisé par le processus parent).
2. **Socket Unix locale (`~/.ankiforge/mcp.sock`)** : Rejeté pour des raisons de portabilité multi-OS (Windows exige des pipes nommés spécifiques).
3. **HTTP / SSE local avec jeton Bearer éphémère** : Retenu car standardisé dans le SDK MCP 2.x (`mcp.server.mcpserver`), interopérable avec tous les agents CLI, et gérable en multi-clients simultanés.

## Conséquences
- L'application graphique Qt héberge un thread d'arrière-plan démarrant la boucle asynchrone `uvicorn` (FastMCP / MCPServer) sans bloquer l'UI Qt.
- La sécurité est garantie par un jeton Bearer aléatoire stocké à chaque session dans `~/.ankiforge/mcp_auth_token` (droits `0600`) et documenté dans `~/.ankiforge/mcp_server.json`.
- En mode graphique, le serveur utilise la base de données active de l'IDE. En mode CLI (`ankiforge --mcp-server`), un argument `--profile` permet de cibler un profil spécifique.
- Les mutations de données (`apply_patch`) s'exécutent sous transaction SQLite WAL atomique et émettent un signal Qt pour synchroniser l'affichage de l'IDE en temps réel.
