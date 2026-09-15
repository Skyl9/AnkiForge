# Éditeur de Notes Natif & Mathématiques KaTeX ✍️

L'**Éditeur de Notes** d'AnkiForge (`ForgeNoteEditor`) a été pensé comme un IDE de précision pour la rédaction de cartes de haut niveau. Contrairement aux éditeurs basés sur des textareas web lourdes, il est développé en **100% natif Qt (PySide6)** pour garantir une réactivité immédiate sans latence.

---

## 📐 1. Moteur Mathématique KaTeX Live

AnkiForge intègre un pipeline de rendu mathématique ultra-rapide s'appuyant sur **KaTeX** :

### Syntaxes Prises en Charge
- **Formules En Ligne (*Inline*)** : Encadrées par `\( ... \)` ou `$ ... $` (ex: `\( f(x) = \frac{1}{1+x} \)`).
- **Formules Hors-Texte (*Display*)** : Encadrées par `\[ ... \]` ou `$$ ... $$` (ex: `\[ \int_0^1 x^2 \, dx = \frac{1}{3} \]`).
- **Balises Anki Historiques** : Support des balises `[latex]...[/latex]` héritées des anciens paquets Anki.
- **Clozes Mathématiques Hybrides** : Prise en charge transparente des textes à trous imbriqués dans les équations (ex: `\( {{c1::x^2}} + 1 = 0 \)`). Le moteur sépare intelligemment l'occlusion pour permettre à KaTeX de compiler la formule sans erreur de syntaxe.

### Autocomplétion des Macros LaTeX
Lorsque vous commencez à taper un antislash `\` dans un champ, une palette d'autocomplétion s'affiche pour vous proposer les symboles usuels :
- **Symboles grecs** : `\alpha`, `\beta`, `\gamma`, `\theta`, `\lambda`, `\omega`...
- **Opérateurs & Calculs** : `\frac{num}{den}`, `\sqrt{x}`, `\sum_{i=1}^n`, `\int_a^b`, `\lim_{x \to \infty}`...
- **Matrices & Ensembles** : `\begin{pmatrix}`, `\in`, `\subset`, `\mathbb{R}`, `\forall`, `\exists`...

Pressez ++tab++ ou ++enter++ pour insérer le snippet avec ses placeholders pré-remplis.

---

## 🧩 2. Gestionnaire de Textes à Trous (*Clozes*)

L'insertion de trous mnémotechniques s'effectue avec une fluidité maximale :
- **Raccourci Dédié** : Sélectionnez le mot ou la formule à masquer et appuyez sur ++ctrl+shift+c++ (ou ++cmd+shift+c++ sous macOS).
- **Incrémentation Automatique** : Si le champ contient déjà `{{c1::mot}}`, la prochaine sélection insérera automatiquement `{{c2::autre mot}}`.
- **Indice Fixe** : Pour masquer plusieurs éléments sous le même masque simultané, utilisez ++ctrl+alt+shift+c++.
- **Support des Indices (*Hints*)** : Ajoutez un indice affiché pendant la révision sous la forme `{{c1::réponse::indice}}`.

---

## 🚩 3. Drapeaux Anki (Flags 1 à 7)

AnkiForge prend en charge la palette complète des **7 drapeaux de couleur** officiels d'Anki pour classifier vos cartes à la volée :

| Drapeau | Couleur | Raccourci Clavier | Usage Conseillé |
| :---: | :--- | :---: | :--- |
| 🔴 **1** | Rouge | ++ctrl+1++ | Carte critique ou examen imminent |
| 🟠 **2** | Orange | ++ctrl+2++ | Révision prioritaire |
| 🟢 **3** | Vert | ++ctrl+3++ | Carte validée et maîtrisée |
| 🔵 **4** | Bleu | ++ctrl+4++ | Carte issue d'un document externe |
| 🟣 **5** | Rose | ++ctrl+5++ | Carte en attente de reformulation |
| 🩵 **6** | Turquoise | ++ctrl+6++ | Modèle mathématique / Démonstration |
| 🟪 **7** | Violet | ++ctrl+7++ | Carte mnémotechnique / Palais mental |
| ⚪ **0** | Aucun | ++ctrl+0++ | Retirer le drapeau actif |

Les drapeaux sont synchronisés lors des imports/exports `.apkg` et `.colpkg`.

---

## ⏳ 4. Time Machine & Historique de Versions

Toute modification apportée à une carte dans AnkiForge fait l'objet d'un instantané versionné via `NoteVersionModel` :
- **Boîte de Dialogue Time Machine** (`TimeMachineDialog`) : Explorez la chronologie complète des révisions d'une note.
- **Différence Visuelle (Diff)** : Visualisez précisément les ajouts en vert et les suppressions en rouge entre deux dates.
- **Restauration en 1 Clic** : Annulez une mauvaise manipulation de l'IA ou un mauvais prompt en restaurant un état antérieur en un seul clic.
