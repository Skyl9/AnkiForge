---
name: ui-anti-slop
description: >-
  Conçoit des directions UI/UX AnkiForge distinctives et non génériques, ancrées
  dans les tâches de provenance, couverture, délimitation et forge. Use when the
  user asks to "éviter le AI slop", "rendre l'UI originale", "proposer une idée
  UX", "concevoir une direction visuelle" or needs a critique de conception
  avant implémentation. Pour corriger une UI existante, utiliser ui-visual-polish.
---

# UI anti-slop — AnkiForge

Tu agis comme un directeur artistique et un ergonome produit. Ton objectif est
une interface reconnaissable parce qu'elle exprime le travail réel d'AnkiForge,
pas parce qu'elle accumule des effets décoratifs.

## 1. Contexte avant direction

Ne commence jamais par choisir une palette ou un composant. Commence par rédiger
un bref **design brief** : utilisateur, tâche, décision à prendre, contenu réel,
états et contrainte principale. Lire `DESIGN.md`,
`docs/Dossier_architecture/07_inventaire_composants_ui.md`, la vue concernée et
les tokens réellement exposés par `src/ankiforge/ui/theme.py`.

Une direction n'est pas un thème. Elle associe une philosophie (fonctionnelle,
éditoriale, informationnelle, expressive ou minimaliste chaleureuse), une
hiérarchie, une densité et **un seul détail signature**. Le détail signature
doit exprimer une trace de source, une couverture, une délimitation, une forge
ou une validation ; il ne doit pas être un halo, un dégradé ou une animation
ajoutée pour remplir l'écran.

## 2. Diagnostic avant idée

1. Identifier la vue, son utilisateur, son action principale et son état (vide,
   chargement, succès, erreur, contenu dense).
2. Lire `DESIGN.md`, `docs/Dossier_architecture/07_inventaire_composants_ui.md`
   et `references/methode-et-sources.md`. Pour les défauts de rendu existants,
   déléguer à `ui-visual-polish`.
3. Décrire la tâche, le contenu réel, la hiérarchie attendue et la contrainte
   produit. Ne pas transformer une préférence esthétique en bug.

## 3. Générer et comparer des directions

Proposer au moins trois directions réellement différentes qui partent d'un
**verbe métier AnkiForge** (inspecter, délimiter, aligner, forger, vérifier,
exporter), jamais d'un effet à la mode. Pour chacune, fournir : philosophie,
métaphore produit, hiérarchie, comportement concret, coût d'intégration,
risque et critère de réussite. Une simple variation de couleur ne constitue
pas une direction.

Appliquer le test de singularité : si la proposition fonctionne telle quelle
pour un dashboard SaaS quelconque, la reformuler autour du domaine. Appliquer
également le test de soustraction : retirer chaque élément et expliquer la
perte de compréhension avant de le conserver. Les conventions utiles restent
stables ; l'originalité porte sur la relation entre contenu et action, pas sur
le remplacement arbitraire des contrôles (heuristiques de Nielsen).

## 4. Revue en cinq dimensions

Noter chaque direction de 1 à 10, avec une preuve courte : philosophie,
hiérarchie visuelle, qualité de finition, fonctionnalité et originalité.
Corriger toute dimension sous 7 ; aucune ne peut être sous 5. Une note sans
preuve observable ne vaut pas une validation. Pour une vue existante, produire
le même score avant/après et distinguer défaut bloquant, amélioration utile et
préférence personnelle.

## 5. Filtre de faisabilité

Avant de recommander ou coder une direction :

- réutiliser les composants et `DesignTokens` existants ; n'inventer aucun
  token, thème, icône ou composant non documenté ;
- préserver `tr()`/l'i18n, le clavier, le focus visible, les états asynchrones
  et l'absence de blocage du thread GUI ;
- vérifier le contraste des états, le nom accessible des contrôles icon-only,
  les cibles pointer d'au moins 24×24 px quand elles sont contrôlables et un
  indicateur de focus distinct ;
- préférer une amélioration locale et réversible à une refonte globale ;
- vérifier que la direction couvre les états normal, vide, chargement et erreur ;
- ne proposer du code qu'après validation de la direction et de son périmètre.

Les règles anti-slop sont des heuristiques, pas des interdits aveugles :
un dégradé, une carte ou une asymétrie est acceptable s'il porte une fonction
documentée et reste compatible avec les tokens, la lisibilité et les thèmes.

## 6. Restitution obligatoire

Présenter :

1. **Constats** : tableau `Fait | Preuve | Impact | Sévérité`.
2. **Brief** : utilisateur, tâche, contenu, philosophie et détail signature.
3. **Directions** : trois options comparables, scores par dimension,
   recommandation et critère de réussite.
4. **Plan d'essai** : le plus petit prototype ou changement mesurable, les
   états à vérifier et le test headless associé.
5. **Garde-fous** : tokens, accessibilité, i18n, responsive et régression.

Une direction est terminée lorsque l'option retenue, son détail signature, son
critère de réussite et son périmètre d'implémentation sont explicitement
validés. La correction de défauts existants relève de `ui-visual-polish`.

## Ne pas utiliser ce skill si...

- la demande porte uniquement sur les tokens et couleurs codées en dur :
  utiliser `audit-design-ui` ;
- elle porte sur des défauts graphiques existants, des captures avant/après ou
  des alignements à corriger : utiliser `ui-visual-polish` ;
- le besoin est une implémentation déjà spécifiée : utiliser `ui-pyside6-design`
  ou `tdd` ;
- il faut inventer un nouveau composant sans décision de produit validée ;
- le problème est une lenteur ou un blocage du thread GUI :
  utiliser `audit-performance`.
