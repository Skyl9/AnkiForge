# ADR 0050 — Paramètre `recursive` unifié pour les requêtes de paquet MCP

## Statut
Accepté

## Contexte
Les outils MCP `get_cards_by_deck_or_tag` et `get_notes_by_model` exposent un paramètre booléen contrôlant l'inclusion des sous-paquets dans le filtre `deck_name`. Historiquement, ce paramètre s'appelait `include_subdecks` (défaut `True`). Le feedback d'architecture (FEEDBACK_DEV_AGENTIQUE.md § Axe 3) recommandait de le renommer `recursive` pour alignement avec les conventions d'API hiérarchiques standard (GitHub REST API, AWS SDK, Kubernetes API) où `recursive=true` est le terme canonique pour "descendre dans l'arbre".

## Décision
1. **Nom canonique** : `recursive` (booléen, défaut `True`) pour les deux outils MCP.
2. **Alias déprécié** : `include_subdecks` conservé comme alias dans le schéma JSON pour compatibilité ascendante, mais non documenté dans le catalogue d'outils.
3. **Comportement** : `recursive=true` → filtre `deck_name` étendu à `Nom::%` (sous-arborescence complète) ; `recursive=false` → égalité stricte `deck_name = 'Nom'`.
4. **Documentation** : Le glossaire `CONTEXT.md` définit les termes « Requête récursive de paquet » et « Paramètre `recursive` (MCP) » avec bannissement explicite de `include_subdecks`.

## Conséquences
- **Positives** : Cohérence terminologique avec l'écosystème API ; auto-documentation pour développeurs d'agents externes ; alignement avec le vocabulaire arbre du domaine (`::` comme séparateur d'arborescence).
- **Négatives** : Rupture mineure pour agents existants utilisant `include_subdecks` (atténuée par l'alias).
- **Migration** : Aucun changement de comportement (défaut `True` conservé) ; seul le nom de paramètre change dans le schéma exposé.

## Alternatives considérées
- Conserver `include_subdecks` : plus explicite pour non-techniciens, mais incohérent avec les standards d'API hiérarchiques et source de confusion avec le pattern Peewee `delete_instance(recursive=True)` qui signifie "cascade suppression".
- Dual-naming permanent : complexifie la maintenance et la documentation sans valeur ajoutée.

## Références
- FEEDBACK_DEV_AGENTIQUE.md § Axe 3 (ligne 155)
- CONTEXT.md : entrées « Requête récursive de paquet » et « Paramètre `recursive` (MCP) »
- `src/ankiforge/services/ai/mcp_server.py` : outils `get_cards_by_deck_or_tag`, `get_notes_by_model`
- `src/ankiforge/services/ai/mcp_tool_registry.py` : implémentation `MCPToolRegistry.get_cards_by_deck_or_tag`