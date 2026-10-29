# ADR 0053 : Outils MCP de contexte OCR album et enregistrement pour agent externe

**Statut :** accepté

## 1. Contexte

L'agent externe (Claude Code, agy, Cursor) doit pouvoir transcrire lui-même les planches d'un album via son propre moteur VLM, sans que le serveur MCP d'AnkiForge n'orchestre l'OCR côté application. Aucun outil MCP n'exposait auparavant le contexte des planches d'album ni n'offrait de point d'entrée dédié à l'enregistrement d'un texte transcrit par un agent externe (seul `correct_plate_ocr`, piloté par l'UI locale, existait).

## 2. Décision

Le registre MCP expose deux nouveaux outils :

### `get_album_ocr_context(document_id, page_ids=None, confirm_vision=False)`

Expose le contexte OCR par planche d'un album (identifiant de planche, numéro, rotation, média, statut, présence d'un texte OCR, besoin de transcription).

- `document_id` est requis ; le document doit impérativement être de type `album`, sinon l'outil est rejeté.
- `page_ids` est facultatif et filtre sur une liste d'identifiants de planches ; son absence retourne toutes les planches de l'album.
- **Garde-fou Vision** : l'outil est rejeté si `confirm_vision` est faux. L'agent externe doit déclarer explicitement disposer d'une capacité VLM/Vision avant d'accéder au contexte de transcription.
- La réponse est toujours JSON et contient `status`, `document_id`, `title`, `total_plates` et la liste `plates`.

### `set_album_page_ocr(page_id, corrected_text, agent_external=False)`

Enregistre le texte transcrit d'une planche et émet une mutation MCP tracée (`plate_ocr_update`, domaine `docs`) via `_notify_mcp_mutation`, réutilisant la convention déjà établie par `correct_plate_ocr`.

- `page_id` et `corrected_text` sont requis.
- `agent_external` indique si l'enregistrement provient d'un agent externe (défaut : false).
- Le texte précédent et le nouveau texte sont consignés dans la charge utile de la mutation.

Les deux outils passent par `MCPToolRegistry` et leurs schémas sont déclarés dans `DEFAULT_CONSULTANT_TOOLS`, avec des wrappers `@mcp.tool()` dans `mcp_server.py`.

## 3. Raisons

La séparation entre le contexte de lecture (à disposition de l'agent externe pour qu'il choisisse son moteur VLM) et l'enregistrement (mutation tracée) respecte le périmètre d'autorité distribuée : l'agent externe raisonne sur son propre modèle, et AnkiForge conserve la traçabilité de la couche textuelle résultante sans altérer le fichier image sous-jacent. Le garde-fou `confirm_vision` évite qu'un agent sans capacité Vision ne soumette une transcription imaginaire.

## 4. Conséquences

- Deux nouveaux outils MCP ajoutés au catalogue (passage de 79 à 81 outils).
- Les schémas sont déclarés dans `DEFAULT_CONSULTANT_TOOLS` et introspectables par les agents externes.
- La mutation `plate_ocr_update` alimente le bus d'événements central (`MCPDataMutatedEvent`, domaine `docs`) et le Garde-Fou MCP.
- Aucun appel réseau IA n'est initié par le serveur : l'agent externe reste responsable de sa propre transcription.
