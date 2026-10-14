# Autocomplétion hiérarchique et fil d'Ariane prévisionnel pour les paquets et sous-paquets

**Statut :** accepté

Afin de fluidifier la création et la structuration arborescente des paquets Anki tout en prévenant les créations accidentelles par faute de frappe, nous unifions les parcours de création sur un dialogue modal unique enrichi d'un **compléteur hiérarchique contextuel découplé** (`HierarchyCompleter`) et d'un **fil d'Ariane prévisionnel interactif**.

## Le problème

La création de paquets et sous-paquets dans Anki repose conventionnellement sur le séparateur double-deux-points `::` (ex: `Sciences::Physique::Thermodynamique`). Dans l'application existante :
1. **Disparité des parcours** : `DeckSelectWindow` et `EditionView` utilisent `CreateDeckDialog`, tandis que `CreationView._on_create_new_deck` recourt à une boîte de dialogue primitive `QInputDialog.getText()`, sans validation ni assistance.
2. **Absence d'assistance à la saisie** : L'utilisateur doit saisir manuellement et sans faute la chaîne complète des paquets parents. Une coquille dans le nom d'un parent (ex: `Science::Physique` au lieu de `Sciences::Physique`) crée silencieusement une branche orpheline parallèle.
3. **Opacité structurelle** : Rien n'indique en temps réel si les segments saisis correspondent à des paquets déjà présents en base ou à des créations de nouveaux conteneurs.

## Options considérées

1. **Formulaire scindé à deux champs (Sélecteur de parent + Champ de sous-paquet)** :
   Rejeté. Bien que ce motif évite la syntaxe `::`, il alourdit l'interface, complique la création en profondeur de plusieurs niveaux d'un coup (ex: créer directement `A::B::C`) et rompt avec l'usage standard d'Anki familier des utilisateurs.
2. **QCompleter plat standard (recherche textuelle globale brute)** :
   Rejeté. Un compléteur conventionnel traite les noms comme des chaînes plates, sans conscience des segments hiérarchiques. Il ne permet pas de filtrer contextuellement les sous-paquets directs dès que le séparateur `::` est saisi.
3. **Compléteur couplé à la base de données (`DeckHierarchyCompleter`)** :
   Rejeté. Coupler directement le composant UI à `DeckRepository` et Peewee empêche sa réutilisation pour d'autres arborescences (dossiers de documents, tags) et impose des mocks de base de données pour les tests unitaires.
4. **Couture unique unifiée avec `HierarchyCompleter` générique, insertion sans suffixe et fil d'Ariane interactif** :
   **Retenu**.

## Décisions et Règles d'Architecture

### 1. Unification stricte sur `CreateDeckDialog`
`QInputDialog.getText()` est banni pour la création de paquets dans `CreationView`. Tous les points d'entrée applicatifs convergent vers `CreateDeckDialog`, garantissant une expérience homogène et testable.

### 2. Composant générique `HierarchyCompleter`
Le composant vit dans `src/ankiforge/ui/components/` et hérite de `QCompleter` (ou pilote un popup de suggestions stylé selon `DESIGN.md`) :
- Il reçoit une collection de chemins complets (`list[str]`) et un séparateur (par défaut `SEPARATOR = "::"` de `hierarchy.py`).
- Il analyse le préfixe courant de la saisie :
  - **Au niveau racine** (aucun séparateur) : il suggère les paquets racines existants ainsi que les correspondances textuelles.
  - **Après un séparateur** (ex: `Sciences::`) : il restreint ses suggestions aux enfants directs sous ce préfixe (`Sciences::Biologie`, `Sciences::Physique`), tout en laissant le champ libre pour une nouvelle feuille.
- **Insertion sans suffixe forcé** : La sélection d'une suggestion insère le libellé exact (ex: `Sciences`), sans forcer l'ajout de `::`. L'utilisateur conserve ainsi la liberté de valider directement ce paquet ou de taper `::` pour continuer l'arborescence.

### 3. Fil d'Ariane prévisionnel interactif
Sous le champ de saisie, un composant réactif décompose les segments du chemin en temps réel :
- **Statut visuel explicite** : Chaque segment est affiché sous forme de badge stylé avec les jetons sémantiques, distinguant les conteneurs déjà existants en base (badge existant raccordé) du conteneur en cours de création (badge nouveau).
- **Navigation interactive par clic** : Cliquer sur un segment parent tronque immédiatement la saisie dans le champ texte au niveau de ce parent, permettant une exploration ou un changement de branche sans manipulation fastidieuse du curseur.

### 4. Idempotence bienveillante
Si le nom saisi correspond exactement à un paquet existant, le dialogue ne bloque pas l'utilisateur par une erreur. Il affiche une indication bienveillante (*« Ce paquet existe déjà (il sera sélectionné) »*) et permet la validation directe, retournant l'instance existante à l'appelant.

## Conséquences

- **Qualité et cohérence de l'arbre** : Réduction drastique des branches dupliquées par coquille typographique sur les parents.
- **Réutilisabilité** : Le composant `HierarchyCompleter` est immédiatement exploitable pour l'arborescence des dossiers documentaires et la hiérarchie des tags.
- **Testabilité** : La logique de complétion et de filtrage hiérarchique est testable par des tests unitaires purs et instantanés (< 2s, règle GEMINI), sans toucher à SQLite ni à Peewee.
- **Expérience utilisateur** : Fluidité maximale alliant la rapidité de la saisie clavier d'Anki et la clarté visuelle d'un IDE moderne.
