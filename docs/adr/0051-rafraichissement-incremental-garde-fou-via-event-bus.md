# ADR 0051 — Rafraîchissement Incrémental du Garde-Fou MCP via Event Bus Typé

**Statut** : Accepté
**Date** : 2026-10-27
**Décideurs** : Architecture AnkiForge
**Contexte** : Interview `grill-with-docs` — Cadrage UI Garde-Fou réactif

---

## Contexte

Le sous-onglet **Garde-Fou & Validation** (`MCPGardeFouWidget`) affiche les propositions de patchs chirurgicaux (Two-Phase Commit) émises par des agents MCP externes. Actuellement, à chaque arrivée d'un patch (`MCPPatchStagedEvent`), le widget effectue une **recharge complète** via `reload_pending_patches()` :

```python
# Code actuel — recharge complète
def reload_pending_patches(self) -> None:
    self.patch_tree.clear()  # ❌ Perte état expansion/sélection/scroll
    self.patch_tree.reset_selectable_items()
    # Re-query DB, rebuild all widgets...
```

**Problèmes identifiés :**
1. **Scintillement visuel** à chaque patch entrant
2. **Perte du contexte utilisateur** : items expandus, sélection courante, position scroll
3. **Coût CPU/DB** : re-query + rebuild widgets à chaque événement
4. **Architecture couplée** : passage obligé par `MCPServerDashboardWidget` (signal Qt intermédiaire)

---

## Décision

### 1. Abonnement Direct au Bus d'Événements
`MCPGardeFouWidget` s'abonne **directement** à `MCPPatchStagedEvent` dans son `__init__` :
```python
event_bus.subscribe(MCPPatchStagedEvent, self._on_mcp_patch_staged)
```
> **Raison** : Découplage total du Dashboard. Le Garde-Fou devient autonome, réutilisable ailleurs. Le Dashboard ne gère plus que le badge compteur et les toasts.

### 2. Rafraîchissement Incrémental (Pas de `clear()`)
À la réception d'un `MCPPatchStagedEvent` :
- **Patch standalone** → `addTopLevelItem()` avec widget custom
- **Patch d'un bundle** → `addChild()` sous le nœud bundle parent existant
- **Bundle complet** (`MCPBundleStagedEvent`) → Création du nœud parent bundle, puis insertion des étapes comme enfants

> **Raison** : `QTreeWidget` préserve nativement l'état (expansion, sélection, scroll) si on n'appelle pas `clear()`.

### 3. Snapshot d'État d'Arbre (Helper Dédié)
Deux utilitaires dans `MCPGardeFouWidget` (ou module partagé `ui/utils/tree_state.py`) :
```python
def _save_tree_state(self) -> dict:
    return {
        "expanded_ids": [item.data(0, Qt.ItemDataRole.UserRole) 
                         for item in self._iter_expanded_items()],
        "selected_id": self.patch_tree.currentItem().data(0, Qt.ItemDataRole.UserRole) 
                       if self.patch_tree.currentItem() else None,
        "scroll_pos": self.patch_tree.verticalScrollBar().value(),
    }

def _restore_tree_state(self, state: dict) -> None:
    # Restaure expansion, sélection, scroll
```

> **Raison** : Garantie de préservation du contexte même si une recharge complète ponctuelle devient nécessaire (ex: filtre, rechargement manuel).

### 4. Gestion des Bundles — Nœud Parent à la Réception de `MCPBundleStagedEvent`
```python
def _on_mcp_bundle_staged(self, event: MCPBundleStagedEvent) -> None:
    bundle_item = QTreeWidgetItem()
    bundle_item.setData(0, Qt.ItemDataRole.UserRole, f"bundle:{event.bundle_id}")
    bundle_widget = BundleHeaderItemWidget(...)  # existant
    self.patch_tree.addTopLevelItem(bundle_item)
    self.patch_tree.setItemWidget(bundle_item, 0, bundle_widget)
    # Les étapes arriveront via MCPPatchStagedEvent (is_step=True)
```

> **Raison** : UX atomique — l'utilisateur voit le bloc arriver complet, avec badge "X étapes".

### 5. Thread-Safety — Marshalling vers Thread Principal Qt
L'`event_bus` est thread-safe mais publie depuis n'importe quel thread. Le slot doit être décoré :
```python
@Slot(MCPPatchStagedEvent)
def _on_mcp_patch_staged(self, event: MCPPatchStagedEvent) -> None:
    # Tout code Qt ici s'exécute sur le thread principal
```
L'`AppEventBus.publish()` utilise déjà `QMetaObject.invokeMethod` pour le marshalling (vérifier `event_bus.py` — sinon, ajouter un wrapper `@Slot` + `QTimer.singleShot(0, ...)`).

---

## Alternatives Rejetées

| Alternative | Raison du rejet |
|-------------|-----------------|
| Recharge complète optimisée (debounce + restauration) | Ne résout pas le scintillement ni le coût DB ; complexité de restauration équivalente |
| Double abonnement (Dashboard + Garde-Fou) | Risque de double traitement, responsabilité floue, coupling résiduel |
| Modèle personnalisé `QAbstractItemModel` | Sur-ingénierie pour le besoin actuel ; `QTreeWidget` + widgets custom suffit |
| Signal Qt `_patch_staged_received` seul | Maintient le coupling au Dashboard ; pas de découplage réel |

---

## Conséquences

### Positives
- ✅ **Zéro scintillement** : insertion ciblée, pas de `clear()`/`rebuild`
- ✅ **Contexte préservé** : expansion, sélection, scroll restaurés
- ✅ **Découplage** : Garde-Fou autonome, testable indépendamment
- ✅ **Performance** : O(1) insertion vs O(N) recharge complète
- ✅ **Bundles visibles** : nœud parent créé au commit, étapes attachées dynamiquement

### Négatives / Risques
- ⚠️ **Complexité d'insertion** : il faut retrouver le parent bundle pour les étapes (`is_step=True`)
- ⚠️ **Déduplication** : l'ancien `_last_notified_patch_id` du Dashboard doit être migré dans le Garde-Fou
- ⚠️ **Événements hors ordre** : si `MCPPatchStagedEvent` arrive avant `MCPBundleStagedEvent` (rare), l'étape est ajoutée en standalone puis déplacée — gérer gracieusement

### Migration
1. Ajouter `event_bus.subscribe(MCPPatchStagedEvent, ...)` + `event_bus.subscribe(MCPBundleStagedEvent, ...)` dans `MCPGardeFouWidget.__init__`
2. Implémenter `_on_mcp_patch_staged` (insertion incrémentale) et `_on_mcp_bundle_staged` (création nœud parent)
3. Ajouter `_save_tree_state` / `_restore_tree_state`
4. Supprimer l'appel à `reload_pending_patches()` depuis `MCPServerDashboardWidget.on_patch_staged`
5. Conserver `reload_pending_patches()` pour : rechargement manuel, ouverture de session, changement de filtre
6. Dashboard : ne garder que `queue_updated` (badge) + `show_toast` (notification)

---

## Références

- `src/ankiforge/utils/event_bus.py` — `MCPPatchStagedEvent`, `MCPBundleStagedEvent`, `event_bus`
- `src/ankiforge/ui/views/consultant_view/widgets/mcp_garde_fou_widget.py` — `MCPGardeFouWidget`, `HierarchicalPatchTreeWidget`
- `src/ankiforge/ui/views/consultant_view/widgets/mcp_dashboard_widget.py` — `MCPServerDashboardWidget`
- `src/ankiforge/services/ai/staged_patch_registry.py` — `_notify_staged_patch`, `_notify_mcp_bundle_staged`

---

## Suivi

- [ ] Implémenter `_on_mcp_patch_staged` (incrémental)
- [ ] Implémenter `_on_mcp_bundle_staged` (nœud parent)
- [ ] Ajouter helpers `_save_tree_state` / `_restore_tree_state`
- [ ] Migrer déduplication `_last_notified_patch_id` dans Garde-Fou
- [ ] Nettoyer `MCPServerDashboardWidget` (supprimer rechargement complet)
- [ ] Tests : arrivée patch standalone, patch dans bundle, bundle complet, recharge manuelle