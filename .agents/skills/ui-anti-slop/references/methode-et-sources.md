# Méthode UI anti-slop — Références et critères

## Principe de décision

L'originalité est un moyen, pas un score esthétique. Une proposition est
retenue si elle rend une action métier plus lisible, réduit une erreur ou
augmente la confiance dans la provenance et l'état du traitement. Une
proposition purement décorative est écartée, même si elle est visuellement
distinctive.

La bonne unité de travail est la **direction**, pas le widget. Une direction
fixe une philosophie, une hiérarchie et un détail signature ; les composants
ne sont que ses moyens d'expression. Cette distinction évite de demander à
l'agent de « rendre joli » un écran sans tâche ni critère vérifiable.

### Grille rapide

| Critère | Question |
|---|---|
| Ancrage produit | Est-ce impossible à copier dans un dashboard générique ? |
| Utilité | Quelle décision ou action devient plus facile ? |
| Lisibilité | La hiérarchie reste-t-elle évidente sans couleur ni animation ? |
| Réversibilité | Peut-on tester la direction sans migration ni refonte ? |
| Cohérence | Les tokens, composants, i18n et layouts existants sont-ils réutilisés ? |
| Accessibilité | Contraste, clavier, focus et cible restent-ils vérifiables ? |

## Revue en cinq dimensions

Noter de 1 à 10 et justifier chaque note par un fait :

| Dimension | 1–3 | 4–6 | 7–10 |
|---|---|---|---|
| Philosophie | assemblage de tendances | cohérent mais générique | vision lisible et tenue |
| Hiérarchie | tout concourt | priorité partielle | lecture immédiate |
| Finition | défauts visibles | professionnel irrégulier | détails intentionnels |
| Fonction | friction ou action cachée | utilisable avec détours | tâche directe et états complets |
| Originalité | template reconnaissable | quelques traits | ancrage métier mémorable |

Le seuil est **7 dans chaque dimension**, sans note inférieure à 5. Ce seuil
est un outil de discussion, pas une preuve de qualité utilisateur : le critère
de réussite de la tâche et les retours observables priment toujours.

## Anti-patterns à traquer

- empiler cartes, pills, dégradés, halos ou glassmorphism sans hiérarchie ;
- remplacer une information par une couleur, une icône seule ou une animation ;
- multiplier les variantes de composants pour simuler la nouveauté ;
- créer une hero section alors que la tâche est une édition ou une validation ;
- proposer une visualisation sans source, unité, état vide ou état d'erreur ;
- traiter un défaut d'alignement par une marge locale au lieu de corriger le layout.

Ces motifs sont des signaux d'investigation, pas des violations automatiques :
un composant peut les employer lorsqu'ils servent une relation ou un état
documenté.

Le dépôt `Wholiver/swiftui-design-skill` est une référence utile pour sa
séparation entre principes, directions, anti-patterns et revue notée. Ses
règles mobiles ne sont pas transposées telles quelles : AnkiForge reste une
application desktop Qt et ses tokens, layouts, icônes Phosphor et conventions
d'accessibilité font foi.

## Protocole d'audit visuel

1. Capturer la vue dans les layouts et thèmes touchés.
2. Examiner dans cet ordre : action principale, alignement des bords,
   hiérarchie typographique, densité, états, débordements, focus.
3. Reproduire le défaut dans un test ou un scénario minimal.
4. Corriger à la source partagée avant d'ajouter une exception locale.
5. Rejouer les états et comparer le comportement, pas seulement la capture.
6. Noter les cinq dimensions, consigner les scores et ne garder que les
   changements dont le critère de réussite est démontré.

## Conseils de designers à appliquer avec discernement

- **Commencer par le contenu réel** : afficher immédiatement la tâche et ses
  données plutôt qu'une accroche décorative ou un écran « bienvenue ».
- **Faire gagner chaque élément** : si sa suppression ne dégrade ni la décision,
  ni la navigation, ni la confiance, il ne mérite probablement pas sa place.
- **Créer une signature par relation** : provenance, couverture et délimitation
  sont des matières visuelles propres à AnkiForge ; elles valent mieux qu'un
  style de carte ou un dégradé à la mode.
- **Préférer les hypothèses réversibles** : une maquette honnête et un
  placeholder explicite valent mieux qu'un asset inventé qui verrouille une
  mauvaise direction.
- **Écrire l'interface comme un produit** : les libellés décrivent l'action,
  les erreurs indiquent la cause et la récupération, et les titres structurent
  le contenu au lieu de meubler l'espace.

## Sources primaires consultées

- W3C, **WCAG 2.2** : principes Perceivable, Operable, Understandable,
  Robust et critères testables : https://www.w3.org/TR/WCAG22/
- W3C, **Focus Appearance (2.4.13)** : indicateur de focus d'au moins 2 px
  et contraste 3:1 (niveau AAA) :
  https://www.w3.org/WAI/WCAG22/Understanding/focus-appearance.html
- W3C, **Target Size Minimum (2.5.8)** : cible de 24×24 px ou espacement
  équivalent (niveau AA) :
  https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html
- Qt 6, **Accessibility for QWidget-based applications** : arbre
  d'accessibilité, rôles, relations, états et textes exposés :
  https://doc.qt.io/qt-6/accessible-qwidget.html
- Nielsen Norman Group, **10 Usability Heuristics** : visibilité de l'état,
  contrôle, prévention des erreurs, reconnaissance, sobriété et cohérence :
  https://www.nngroup.com/articles/ten-usability-heuristics/
- Laws of UX, **collection de principes d'interaction** : charge cognitive,
  Fitts, Hick, proximité, similarité, common region et Von Restorff :
  https://lawsofux.com/
- IBM Accessibility, **Content design** : titres structurés, alternatives
  textuelles fonctionnelles et labels persistants proches des champs :
  https://www.ibm.com/able/toolkit/design/content/
- Wholiver, **swiftui-design-skill** (GitHub, MIT) : exemple public de skill
  anti-slop avec directions, règles concrètes et revue en cinq dimensions :
  https://github.com/Wholiver/swiftui-design-skill

Les sources définissent des contraintes d'utilisabilité et d'accessibilité ;
elles ne prescrivent pas une esthétique. Les directions visuelles doivent donc
être dérivées du domaine AnkiForge puis filtrées par ces contraintes.
