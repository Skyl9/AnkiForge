---
name: critique-design-contradictoire
description: >-
  Jury contradictoire qui pousse une icône, un logo ou une page vitrine dans ses
  retranchements en instanciant des sous-agents experts multi-écoles, en confrontant
  aux références du marché (faux-amis visuels) et en traquant le LLM Vector Slop
  ainsi que les erreurs optiques de Gestalt.
  Use when the user asks to "critique design contradictoire", "pousser le design
  dans ses retranchements", "instancier des sous-agents designers", "critiquer
  l'icône", "critique-design-contradictoire", or wants an uncompromising multi-expert
  adversarial critique of a visual asset.
  When NOT to use: Do not use for code/database adversarial review (use
  doubt-driven-development) or static QSS token checks (use audit-design-ui).
---

# ⚖️ Critique Design Contradictoire — Le Jury Multi-Écoles Sans Complaisance

En tant que **Président du Jury d'Iconographie & Direction Artistique**, ton mandat est de **penser contre le design proposé** : le pousser dans ses retranchements, débusquer toute trace de génération mécanique ou d'ambiguïté sémantique, et prescrire des corrections géométriques millimétrées.

> **Référence détaillée :** Consulter `references/prompts_jury_et_grille_critique.md` pour les définitions complètes de sous-agents (`define_subagent` / `invoke_subagent`) et la checklist du *LLM Vector Slop*.

---

## 1. Règle Préalable : Inspection du Code ET du Rendu Physique

Il est formellement interdit de critiquer un fichier `.svg` uniquement en lisant son texte XML :
1. Générer un aperçu matriciel PNG multi-échelles (`1024`, `512`, `128`, `64`, `32`, `16 px`) sur **fond sombre ET sur fond blanc transparent**.
2. Inspecter l'image rendue avec `read_file` **et** lire les coordonnées exactes du fichier `.svg` (ainsi que la page d'accueil associée pour vérifier la cohérence globale).

---

## 2. Instanciation Parallèle du Jury de 3 Sous-Agents (`define_subagent` + `invoke_subagent`)

Définir le sous-agent `icon-design-critic` (en lecture seule) enrichi des connaissances de design documentées, puis lancer **3 experts contradictoires en parallèle** :

### Expert 1 — Rigueur Systémique, Grille & Survie à `16×16 px`
- Vérifie l'harmonie chromatique et structurelle avec le reste de l'écosystème (ex. page vitrine papier chaud `#f6f5f0`, encre `#0f1117`, accent Indigo `#3730a3`/`#4f46e5`).
- Calcule mathématiquement le **sous-échantillonnage à `16×16 px`** (sur une `viewBox` de `128`, `1 px = 8 unités SVG` : tout détail ou écart `< 5 unités` fusionne en une tache grise).
- Applique le test de la silhouette monochrome 1-bit et traque les pincements optiques dans l'espace négatif.

### Expert 2 — Anatomie OS, Optique de Bézier & Artisanat Indépendant
- Confronte l'icône au savoir-faire des artisans indépendants et studios de référence (marges de sécurité dans le *squircle* macOS : au moins `40 à 50 unités` sur `1024`, soit `5 à 6 unités` sur `128` entre tout coin interne et le liseré).
- Audite les courbes de Bézier : rejette les traits d'épaisseur uniforme (`stroke-width` constant façon « fil de fer / cintre ») au profit de vrais contours typographiques à pleins et déliés.
- Débusque les **bugs de calques** : ombre portée grise qui salit une forme blanche, fausse bordure (`stroke`) qui bave sur le fond, ou `stroke` de *squircle* qui crée un halo lavande semi-transparent sur fond blanc (au lieu d'un *inset rim*).

### Expert 3 — Métaphore Produit, Faux-Amis du Marché & Gestalt Cognitive
- **Tableau comparatif face aux icônes du marché** (*Raycast, Linear, Notion, Things 3, Quizlet, Duolingo, iA Writer*) :
  - Identifie les **faux-amis visuels** (ex. une carte verticale à bordure inférieure épaisse qui ressemble à un *écran d'iPhone/iPad*, ou une coche `✓` sur fond bleu qui évoque une application de *To-Do list / 2FA* plutôt qu'AnkiDraft).
- **Sémantique métier sans contresens** : vérifie qu'aucune couleur ne trahit le code mental de l'utilisateur (ex. bannir un bandeau rouge/corail qui signifie *« Échec / Again »* dans Anki).
- **Loi de Proximité de la Gestalt** :
  - Traque l'**effet « code-barres »** (> 3 lignes horizontales sur une carte).
  - Traque l'**effet « formulaire »** (espacement vertical strictement égal entre 3 barres, donnant l'impression de 3 champs isolés au lieu de *1 Titre + 1 Paragraphe de 2 lignes*).
  - Traque la **symétrie mécanique** (`Court / Long / Court` où la 1re et la 3e barre ont la même longueur).

---

## 3. Diagnostic Binaire : « Generative Raster Slop » vs « LLM Vector Slop »

Chaque rapport de critique doit séparer explicitement deux diagnostics :
1. **Generative Raster Slop (clichés d'imagerie IA)** : étoile magique à 4 branches, soupe de 4 dégradés concurrents, néons baveux, fausse 3D isométrique.
2. **LLM Vector Slop (code SVG écrit à l'aveugle par un LLM)** :
   - Collision de bordure (*out-of-bounds* mordant sur le liseré du *squircle*),
   - Tangente aveugle (la tranchée de découpe ampute l'arche gauche d'un `?`, le faisant ressembler à un `7` ou un `>`),
   - Dysharmonie des rayons de courbure (`rx` à `90°` secs dans un conteneur organique),
   - Répartition purement arithmétique sans centre de gravité optique.

---

## 4. Format de Restitution & Boucle de Convergence

Consolider les conclusions unanimes des 3 experts sous cette structure :

1. **Tableau comparatif face aux références** (`Variante | Références proches | Force | Écueil visuel ou technique`).
2. **Grille de notation optique (`/10`)** : *Storytelling & Métaphore*, *Palette & Contraste (clair/sombre)*, *Échelle & Respiration (padding)*, *Harmonie des formes (`rx`)*, *Loi de Proximité (Gestalt)*.
3. **Liste des corrections chirurgicales chiffrées** : toute dimension `< 8/10` ou tout marqueur de *Vector Slop* déclenche immédiatement la correction dans le générateur CSG (`conception-graphisme`) suivie d'une contre-vérification PNG.

---

## ⛔ Ne PAS utiliser ce skill si...

- L'objectif est de challenger une architecture logicielle, un schéma SQLite Peewee ou du code Python → utiliser `doubt-driven-development`.
- L'objectif est de vérifier statiquement l'absence de couleurs codées en dur dans les widgets Qt → utiliser `audit-design-ui`.
- L'objectif est de rechercher et fabriquer initialement l'icône ou la page vitrine → commencer par `conception-graphisme`.
