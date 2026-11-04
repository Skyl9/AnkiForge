# ADR 0056 — Dimensionnement Adaptatif et Persistance du Volet Maître du Garde-Fou MCP

**Statut** : Accepté  
**Date** : 2026-11-04  
**Décideurs** : Tristan Rigaud-Humbert, Agent Antigravity  
**Contexte** : Cadrage `/grill-with-docs` sur le ticket `UI - Repositionnement en Largeur des Propositions en Attente du Garde-Fou`

---

## Contexte & Problématique

Le sous-onglet **Garde-Fou & Validation** (`MCPGardeFouWidget`, introduit par l'[ADR 0029](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0029-garde-fou-mcp-et-comparateur-semantique-de-cartes.md) et structuré par l'[ADR 0030](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/docs/adr/0030-disposition-et-sous-onglets-du-serveur-mcp.md)) utilise une disposition Maître-Détail horizontale articulée par un `QSplitter`.

Trois anomalies ergonomiques et techniques combinées entravaient l'utilisation sur différentes résolutions d'écran :

1. **Bornes rigides de dimensionnement** : `self.left_panel.setMinimumWidth(380)` et `self.left_panel.setMaximumWidth(520)` confinaient le volet des propositions dans une fourchette étroite de 140 pixels, empêchant tout élargissement sur moniteur large ou réduction sur écran compact.
2. **Défaut d'extensibilité et de retour à la ligne des cartes** : Les items de l'arbre (`HierarchicalPatchTreeWidget`) insérés via `setItemWidget` figeaient leur `sizeHint()` initial sans étirement élastique, tandis que `resizeColumnToContents(0)` forçait une largeur statique et que le titre (`lbl_title.setWordWrap(False)`) tronquait l'information textuelle.
3. **Absence de persistance de la géométrie du séparateur** : L'instance `QSplitter` n'était pas conservée comme attribut membre (`splitter` local dans `_setup_ui()`) et ne mémorisait pas son état via `QSettings`, provoquant des sauts ou des réinitialisations de position lors des cycles de vie ou des rechargements de propositions.

---

## Décisions & Architecture

### 1. Assouplissement des Contraintes de Largeur du Volet Maître
- `self.left_panel.setMinimumWidth(280)` : abaissement du plancher pour accommoder les affichages étroits ou multifenêtres.
- **Suppression intégrale de `setMaximumWidth`** : le volet maître peut s'étendre librement jusqu'à 50 % de la largeur totale de la fenêtre selon les besoins de l'utilisateur.
- Taille initiale par défaut calibrée à **360 px** lors de la première ouverture d'un profil.

### 2. Élastification de l'Arbre et Support du Multi-Lignes Fluide
- Dans `HierarchicalPatchTreeWidget` :
  - Activation de `self.header().setStretchLastSection(True)` pour que la colonne unique occupe systématiquement 100 % de l'espace alloué au viewport.
- Dans `PatchListItemWidget` et `BundleHeaderItemWidget` :
  - `lbl_title.setWordWrap(True)` pour permettre l'affichage intégral des intitulés de patchs longs ou complexes sans débordement horizontal.
- Dans `reload_pending_patches()` :
  - Suppression de l'appel statique `resizeColumnToContents(0)` qui rompait l'alignement responsive lors des redimensionnements.

### 3. Persistance de la Géométrie du Splitter via QSettings
- La référence au séparateur est persistée sur le composant : `self.splitter = splitter`.
- Clé de configuration dédiée : `mcp/garde_fou_splitter_state` (stockée via `QSettings`).
- Restauration déterministe lors de la construction UI, avec repli fluide :
  ```python
  state = settings.value("mcp/garde_fou_splitter_state")
  if state:
      self.splitter.restoreState(state)
  else:
      self.splitter.setSizes([360, max(500, self.width() - 360)])
  ```
- Sauvegarde réactive connectée au signal `self.splitter.splitterMoved`.
- Immunisation de la position du splitter lors des appels de `reload_pending_patches()` et des réceptions d'événements (`MCPPatchStagedEvent`, `MCPBundleStagedEvent`).

---

## Conséquences

- **Adaptabilité multi-écrans** : Confort visuel garanti des écrans portables compacts jusqu'aux moniteurs ultra-larges.
- **Préservation de la mémoire d'agencement** : L'utilisateur retrouve la disposition exacte de son poste de travail sans saut visuel au fil des allers-retours ou validations de propositions MCP.
- **Lisibilité renforcée** : Les titres descriptifs des propositions ne sont plus brutalement élidés lorsque le volet est redimensionné.
