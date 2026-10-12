# Régime d'écriture MCP : création directe de paquets vs création staged de notes et contrôle d'hallucination

Afin d'outiller les agents externes pour la saisie et l'organisation sans risquer d'altérer ou de polluer la collection par des générations défaillantes, nous établissons un arbitrage asymétrique : les conteneurs organisationnels (paquets) sont créés directement et de manière idempotente, tandis que les unités de contenu (notes et cartes) sont obligatoirement assujetties à la validation en deux phases (*Two-Phase Commit* / `StagedPatch`), avec un contrôle strict interdisant l'assignation à des paquets inexistants.

## Statut
Accepté

## Options considérées
1. **Écriture directe inconditionnelle pour les notes et les paquets** : Rejeté pour les notes. Bien qu'une création de note soit une opération additive, une boucle d'agent autonome défaillante pourrait injecter des dizaines de cartes erronées ou mal formatées sans prévisualisation ni contrôle utilisateur, en violation directe d'ADR 0002.
2. **Two-Phase Commit obligatoire pour les paquets (`deck_create`)** : Rejeté car contre-productif. La création d'un paquet hiérarchique est une opération purement structurelle, idempotente et sans destruction, qui n'altère aucune carte existante. Imposer un `StagedPatch` pour un simple dossier alourdirait inutilement la file d'attente humaine.
3. **Création implicite et automatique des paquets cibles lors de la création d'une note** : Rejeté pour prévenir les hallucinations. Si un agent externe fait une faute de frappe ou invente un nom de paquet fantôme (ex: `"Médecine::Anatomie::Cœur"` avec une graphie erronée), une création automatique polluerait l'arborescence des paquets. Le rejet strict force l'agent à interroger les paquets existants ou à créer délibérément le paquet via `create_deck`.
4. **Régime asymétrique avec contrôle strict d'hallucination de paquet** : Retenu.
   - `create_deck(deck_name, description="")` écrit directement en base de manière synchrone et idempotente via `DeckRepository.get_or_create_deck_hierarchical`.
   - `list_decks(filter="")` permet à l'agent de découvrir les paquets existants.
   - `create_note(...)` et `create_notes_batch(...)` rejettent immédiatement tout appel ciblant un paquet inexistant (avec suggestion des paquets existants les plus proches).
   - Les notes valides génèrent un `StagedPatch` persistant (`note_create` ou `batch_note_create`) prévisualisable dans le `WorkspaceInspectorWidget` et validable en un clic par l'humain ou via l'outil `apply_patch(patch_id)` par un agent autorisé.

## Conséquences
- **Sécurité et intégrité** : Aucune carte physique n'entre en base sans être passée par le filtre d'un `StagedPatch`. L'arborescence des paquets est protégée contre les créations accidentelles par hallucination.
- **Performance et découvrabilité** : L'outil léger `list_decks` évite aux agents de charger l'intégralité du panorama de collection pour simplement vérifier un nom de paquet.
- **Ergonomie du lot (Batch)** : `create_notes_batch` encapsule l'ensemble d'une génération dans un patch groupé atomique (tout-ou-rien), évitant à l'utilisateur de valider individuellement des dizaines de fiches issues d'une même séance de travail.
- **Expérience IHM enrichie** : Le `WorkspaceInspectorWidget` bénéficie d'un rendu visuel dédié pour les patchs de création (badges de type de note et de paquet, tableau des champs saisis, avertissements de doublons sur le champ clé et aperçu dynamique des cartes générées).
