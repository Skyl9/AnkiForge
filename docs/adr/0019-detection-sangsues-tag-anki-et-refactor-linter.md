# Détection des cartes sangsues par tag Anki et refactoring atomique via le Linter Wozniak

**Statut :** Accepté

Afin de permettre le diagnostic et la remédiation cognitive des cartes en échec répété de révision (« sangsues » ou *leeches*) tout en respectant le principe de « Forge pure » d'AnkiForge (IDE de création et d'audit, sans révision en direct), nous rejetons la gestion d'un statut de suspension locale non transitif vers Anki au profit d'un alignement sur le tag officiel `leech` posé par Anki, couplé à un mode de détection préventif et un pont modal vers le Linter Wozniak appliquant la validation en deux phases (*Two-Phase Commit* / `propose_card_split`).

## Options considérées

1. **Option A — Statut de sangsue interne indépendant avec boutons de suspension locale** : Rejeté.
   - **Non-transitivité vers Anki** : Modifier `CardModel.is_suspended` dans AnkiForge ne met pas à jour la file d'attente active des révisions Anki sans synchronisation descendante lourde. Proposer une suspension locale créerait une fausse promesse chez l'utilisateur qui continuerait de voir la carte apparaître dans Anki.
   - **Rôle d'AnkiForge** : L'application n'est pas un réviseur de flashcards ; son apport à forte valeur ajoutée est la restructuration du contenu textuel défaillant selon les 20 règles de Piotr Wozniak.

2. **Option B — Détection strictement restreinte au tag `leech` d'Anki** : Partiellement retenu.
   - Conforme à la mécanique officielle d'Anki (qui ajoute le tag `leech` à la note lorsque le seuil d'échecs du paquet est franchi lors d'une révision).
   - Toutefois, un utilisateur peut vouloir identifier préventivement des cartes fragiles avant même qu'Anki ne déclenche son seuil (par exemple 4 échecs sous FSRS alors qu'Anki est réglé sur 8).

3. **Option C — Détection duale dans l'onglet SRS & pont modal vers le Linter Wozniak** : **Retenu**.
   - **Emplacement analytique (Q1 & Q7)** : Intégration d'un panneau pleine largeur « Diagnostic des Cartes Sangsues » dans l'onglet « Jetons & SRS » (`AITokensSrsTab`), sous la grille 2 colonnes de rétention FSRS.
   - **Requête de détection (Q2 & Q6)** : Filtrage prioritaire sur le tag `leech` de la note (`NoteModel.tags`), complété d'une bascule de filtre optionnelle pour inclure les cartes à rechutes fréquentes non encore tagguées (`CardModel.lapses >= 4`).
   - **Granularité physique (Q3 & Q9)** : Chaque rangée du tableau représente la carte physique exacte (`CardModel`) avec son `template_index`/face (car une seule face d'une note réversible ou un seul masquage de cloze peut échouer), son paquet, son intervalle `ivl`, sa stabilité FSRS, sa difficulté, son nombre d'oublis `lapses` et l'extrait textuel de la note. Tri par défaut par `lapses` décroissant puis `stability` croissante.
   - **Parcours d'audit sans rupture de contexte (Q4 & Q8)** : Le bouton « Scinder (Wozniak) » ouvre un dialogue modal d'inspection affichant la carte actuelle et ses métriques. L'utilisateur déclenche explicitement la génération de scission IA pour maîtriser ses coûts de jetons.
   - **Validation en deux phases (Two-Phase Commit)** : La scission s'appuie sur `propose_card_split`, produisant un `StagedPatch` prévisualisable. L'application du patch (`apply_patch`) crée les sous-cartes atomiques conformes (Règle 4 d'atomicité et Règle 5 de clarté univoque) dans le même paquet et archive la note parente sangsue (`status = "archived"`).

## Conséquences

- **Respect de la philosophie de Forge** : AnkiForge se concentre sur sa valeur clé (remédiation cognitive et découpage atomique assisté par IA) plutôt que de dupliquer la mécanique de gestion de file d'Anki.
- **Continuité de l'expérience utilisateur** : L'utilisateur identifie les faiblesses mémorielles dans son tableau de bord SRS et opère la chirurgie de découpage immédiatement sans rechargement ni bascule d'onglet.
- **Traçabilité et non-régression** : La note sangsue originale est archivée avec ses versions antérieures préservées, et les sous-cartes générées héritent de la provenance documentaire et des tags du paquet.
