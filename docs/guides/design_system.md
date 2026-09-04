# Design System & Thèmes 🎨

L'interface graphique d'AnkiForge respecte une architecture de design rigoureuse inspirée des standards des éditeurs de code professionnels. Toute l'identité visuelle est gouvernée par le document de référence `DESIGN.md`.

---

## 🎭 1. Les 12 Thèmes Embarqués

AnkiForge intègre 12 thèmes chromatiques méticuleusement calibrés pour respecter les contrastes d'accessibilité (WCAG AA/AAA) :

### Thèmes Sombres (Dark Modes)
- **Tokyo Night** (Thème par défaut) : Palette néon bleu profond et violette, reposante pour de longues sessions nocturnes.
- **Nord** : Atmosphère polaire aux teintes pastel douces et contrastées.
- **Dracula** : Palette iconique rose/violet à fort contraste.
- **Obsidian** : Noirs profonds et bordures épurées, rappelant le célèbre second cerveau.
- **Catppuccin Mocha** : Couleurs chaudes et pastel sur fond gris ardoise.
- **Gruvbox Dark** : Tons rétro chauds aux dominantes sépia et ambre.
- **Monokai Pro** : Teintes vives et précises, réputées pour la clarté typographique.
- **One Dark Pro** : L'élégance sobre issue de l'écosystème Atom / VS Code.

### Thèmes Clairs (Light Modes)
- **GitHub Light** : Interface clinique, blanche et lumineuse pour une lisibilité maximale en plein jour.
- **Catppuccin Latte** : Douceur pastel et contrastes maîtrisés sans éblouissement.
- **Solarized Light** : Palette éprouvée aux teintes crème et cyans équilibrés.
- **Paper** : Texture visuelle rappelant les fiches bristol et l'encre imprimée.

Le changement de thème s'effectue instantanément depuis la barre d'état ou le menu **Paramètres ➔ Apparence** sans redémarrer l'application.

---

## 🖥️ 2. Les 4 Agencements d'Interface (*Layouts*)

Pour s'adapter à la taille de votre moniteur et à votre tâche en cours, AnkiForge propose 4 agencements pré-configurés :

1. **Standard** : Configuration polyvalente avec panneau de navigation latéral, éditeur central et panneau d'inspection à droite.
2. **Compact** : Marges et espacements réduits, optimisé pour les écrans d'ordinateurs portables 13 pouces.
3. **Focus** : Masque automatiquement les barres d'outils et docks secondaires pour créer une bulle de concentration dédiée à la rédaction de cartes.
4. **Wide** : Tire parti des moniteurs ultra-larges (*Ultrawide*) et configurations multi-écrans en déployant les docks en colonnes parallèles.

---

## 🧩 3. Moteur de Styles Dynamique (`StyleEngine`)

L'application applique une règle stricte : **zéro couleur codée en dur dans le code source**.

Toutes les feuilles de style Qt (QSS) sont générées dynamiquement par `StyleEngine.generate_stylesheet()` à partir des tokens sémantiques :

```python
# Exemple de tokenisation sémantique
bg_surface = theme.bg_surface        # Arrière-plan des panneaux et cartes
accent_primary = theme.accent_primary # Boutons d'action et éléments actifs
text_primary = theme.text_primary     # Typographie principale
border_subtle = theme.border_subtle   # Séparateurs discrets
```

Cette architecture garantit que tout nouveau composant UI hérite immédiatement et parfaitement des 12 thèmes sans effort supplémentaire.
