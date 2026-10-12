# Bandeau d'activité global hors des layouts et couture unique de réindexation

**Statut :** accepté

La transparence de l'avancement d'une réindexation RAG s'obtient en la rapportant à une **passe de réindexation** unique, alimentée par la **seule** couture `reindex_service.reindex_document`, et affichée par un **bandeau d'activité global hébergé au niveau de la fenêtre** — donc hors des quatre dispositions d'interface enfichables — plutôt que par une bannière ancrée dans la surface documentaire ou par un overlay flottant.

## Le défaut

`MigrationReindexWorker` émet déjà `progress(int doc_index, int total, str titre)` (`migration_reindex_worker.py:24`), mais aucun consommateur ne l'écoute : `__main__.py:317-326` ne branche que `finished_processing` sur un `logger.info`. La réindexation migratoire peut porter sur l'intégralité des documents d'un profil au premier lancement après changement de stratégie de découpage, et se déroule **sans aucun témoin** : rien n'indique quel document est traité, ni combien restent, ni combien de fragments ont été vectorisés.

Trois chemins déclenchent pourtant des réindexations, et **deux d'entre eux ne partagent pas la même couture** : la migration au démarrage et le bouton « Ré-indexer FAISS » passent par `reindex_service.reindex_document`, tandis que la rév vectorisation de la délimitation (`delimitation_dialog.py:4082-4085`) appelle `RAGService().create_index()` directement. Instrumenter un seul chemin, ou ancrer l'indicateur dans une vue, laisserait mécaniquement des passes muettes et invisibles selon l'écran où l'utilisateur se trouve.

## Options considérées

1. **Bannière discrète ancrée dans `DocumentsView`** (patron `batch_progress_container`) : rejeté. La réindexation migratoire démarre au lancement, souvent tandis que l'utilisateur est sur un autre écran ; la bannière serait invisible exactement là où le besoin de rassurance est le plus fort.
2. **Barre de statut persistante en bas de chaque layout** : rejeté. Il n'existe aujourd'hui aucune zone de pied de page partagée (`QStatusBar` est stylée dans `style_engine/engine.py:868` mais jamais instanciée), et dupliquer le composant dans les quatre dispositions multiplierait les points de dérive.
3. **Overlay / popup flottante** : rejeté. Non persistant et intrusif, il ne tient pas la promesse « sans avoir l'impression que l'application est figée » sur une passe longue.
4. **Bandeau d'activité global hébergé dans `MainWindow`, hors des layouts, alimenté par une couture unique de réindexation** : **retenu**.

## Conséquences

- **Un seul hôte, layout-agnostique.** Le bandeau vit dans `MainWindow`, au-dessus/en-dessous du widget central posé par `setCentralWidget(new_layout)` (`main_window.py:521`). Il reste donc visible à travers les quatre dispositions et survit à un changement de layout à chaud.
- **Une seule couture alimentaire.** Tous les déclencheurs — migration au démarrage, bouton « Ré-indexer FAISS », rév vectorisation de la délimitation — doivent publier sur la même voie et, si possible, converger vers `reindex_document`. Le chemin de délimitation qui contourne la couture est à raccorder. Il converge vers la variante **non destructive** `revectorize_document` (même module), car ses fragments viennent d'être mis à jour différentiellement par `sync_extracted_chunks` : un `reindex_document`, qui supprime puis recrée les fragments, emporterait en cascade les liens de couverture (`NoteChunkLinkModel.chunk` est en `on_delete="CASCADE"`).
- **Deux niveaux de granularité.** Le niveau **macro** (document courant, index sur total, pourcentage global) est toujours fiable car porté par le worker ; le niveau **micro** (fragments traités) est opportuniste car porté par `progress_cb`, et ne doit jamais retarder ni bloquer l'affichage du macro.
- **Annulation coopérative entre documents.** Une passe est annulable, mais l'interruption n'intervient qu'entre deux documents — jamais au milieu d'un document, pour ne pas laisser un document à moitié indexé.
- **Récapitulatif de fin.** Un toast de clôture récapitule documents et fragments réindexés ainsi que les erreurs ; cela impose d'enrichir `finished_processing` au-delà du couple `(processed, errors)` actuel.
- **Voie d'alimentation : service singleton Qt, pas le bus.** Un `QObject` singleton de thread principal (`started/progress/finished`) reçoit la progression des déclencheurs et alimente l'hôte. La progression est haute fréquence et typée (`int, int, str`) ; l'`AppEventBus` reste réservé aux faits de domaine grossiers (`DocumentIndexedEvent`, `CoverageSyncedEvent`).
- **Une seule passe active à la fois.** Un déclenchement qui survient pendant qu'une passe tourne est refusé franchement, par un toast discret (« Une réindexation est déjà en cours (N/M) »). Deux barres concurrentes seraient plus trompeuses qu'informatives, et SQLite impose déjà la sérialisation.
- **Le bandeau est masqué au repos.** Aucun mobilier permanent : l'indicateur n'existe que pendant une passe. Le pourcentage global reflète les **documents** traités, jamais un mélange avec les fragments ; la sous-progression du document courant est affichée à part, sous le libellé `Réindexation X/N : <titre>`.
- **Ensemble, ces choix délimitent le périmètre du suivi, pas sa mécanique fine.** Les détails de rendu (marges, ordre exact au-dessus/en-dessous du widget central) relèvent de l'implémentation.
