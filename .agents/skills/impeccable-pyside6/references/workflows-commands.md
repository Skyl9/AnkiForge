# Workflows & Commandes Chirurgicales Impeccable pour PySide6

Ce guide détaille l'exécution méthodique des passes de finition inspirées du framework Impeccable. Chaque commande constitue une opération de haute précision applicable à un composant, un dialogue ou une vue PySide6 complète.

---

## Vue d'Ensemble des 8 Passes Chirurgicales

La chaîne idéale de refonte complète d'une interface suit cet ordre séquentiel strict :
**`/first-eyes`** ➔ **`/clarify`** ➔ **`/distill`** ➔ **`/arrange`** ➔ **`/typeset`** ➔ **`/harden`** ➔ **`/polish`**

| Commande | Intention Clé | Question d'Évaluation |
| :--- | :--- | :--- |
| `/first-eyes` | **Regard Extérieur & Onboarding** | *Que comprend et ressent un novice découvrant cet écran pour la toute première fois ?* |
| `/clarify` | **UX Writing & Anti-Jargon** | *Ce texte parle-t-il la langue de l'utilisateur ou la tuyauterie du code backend ?* |
| `/distill` | **Élimination du bruit visuel** | *Quel élément graphique n'apporte aucune information fonctionnelle ?* |
| `/arrange` | **Alignement & Grille spatiale (4px)** | *Les marges et espacements suivent-ils un rythme mathématique strict ?* |
| `/typeset` | **Hiérarchie & Rythme typographique** | *Le texte guide-t-il l'œil instantanément vers l'essentiel ?* |
| `/harden` | **Robustesse & Responsive desktop** | *Le layout survit-il au redimensionnement extrême (1280×800 et 820×560) ?* |
| `/polish` | **Affordance & Micro-interactions** | *L'interface réagit-elle au survol, au clic et au focus avec fluidité ?* |
| `/quieter` ou `/bolder` | **Pondération & Contraste d'attention** | *L'intensité visuelle est-elle équilibrée ou surcharge-t-elle l'esprit ?* |

---

## 1. Passe `/first-eyes` : Simulation "Nouvel Utilisateur" & Onboarding

### Objectif
Sortir du prisme de développeur pour auditer l'écran avec la naïveté totale d'un utilisateur "Jour 1" qui vient d'installer AnkiForge.

### Protocole d'Exécution
1. Appliquer le test des 3 secondes à froid (Où suis-je ? Que puis-je faire ? Par quoi commencer ?).
2. Simuler l'état "Base vierge" (0 document, 0 carte, 0 deck) et auditer l'`EmptyStateWidget`.
3. Détecter l'effet "cockpit d'avion" : identifier les paramètres experts à replier ou masquer.
4. Auditer les boutons désactivés (`setEnabled(False)`) et exiger un tooltip explicatif.

### Format de Restitution Obligatoire : "Journal de bord des 60 premières secondes"
Lorsque l'utilisateur sollicite `/first-eyes` ou demande un avis extérieur sur une vue, l'agent **DOIT impérativement démarrer sa réponse** par un récit incarné à la première personne :

> **Journal de bord (Première immersion) :**
> *"J'ouvre cet écran pour la première fois. Mon regard est immédiatement attiré par [élément], mais je ne sais pas si c'est cliquable. Je lis le terme '[jargon]', qui ne m'évoque rien du tout. J'hésite à cliquer sur le bouton principal car j'ai peur de [peur/incompréhension]. Le tableau est complètement vide et je ne vois pas par quelle action débuter mon travail..."*

Ce récit est immédiatement suivi par le tableau des frictions cognitives :
`Friction Constatée | Cause UI/Conceptuelle | Impact Psychologique | Correctif Immédiat PySide6`

Consulter la méthode détaillée dans `references/first-time-user-walkthrough.md`.

---

## 2. Passe `/clarify` : UX Writing & Éradication du Jargon

### Objectif
Traduire la tuyauterie interne du code en une microcopy bienveillante, fluide et axée sur l'action et le bénéfice pour l'utilisateur.

### Protocole d'Exécution
1. **Épurer les termes développeurs** : Remplacer systématiquement *MCP, init_workspace, NoteType, Chunk, Vector Store, Peewee* par leurs équivalents humains.
2. **Recomposer les messages d'erreur** : Appliquer la formule en 3 temps : *(1) Ce qui s'est passé + (2) Cause probable sans stacktrace + (3) Action de déblocage*.
3. **Sécuriser les actions critiques** : Ajouter une mention rassurante avant génération ou export (innocuité des fichiers d'origine, gratuité du modèle local).

Consulter le lexique complet dans `references/first-time-user-walkthrough.md`.

---

## 3. Passe `/distill` : Épuration et Clarté Radicale

### Objectif
Supprimer les ornements superflus, les bordures étouffantes, les fonds hétérogènes et les lignes de séparation redondantes pour laisser respirer le contenu.

### Protocole d'Exécution
1. **Éradiquer les `QGroupBox`** : Remplacer les cadres gravés par de simples espacements ou des conteneurs sans bordure.
2. **Nettoyer les séparateurs (`QFrame.HLine`)** : Remplacer les barres horizontales parasites par des espacements rythmés (`setSpacing(16)`).
3. **Unifier les fonds** : S'assurer que le contenu repose sur `BG_PANEL` ou `BG_MAIN`, sans sous-boîtes contrastées inutiles.
4. **Débruiter les icônes** : Supprimer les icônes purement décoratives qui n'aident pas à l'action.

---

## 4. Passe `/arrange` : Rythme Spatial et Alignements Optiques

### Objectif
Harmoniser toutes les dimensions selon la grille de 4px d'AnkiForge (`4, 8, 12, 16, 24px`) et aligner optiquement les composants.

### Protocole d'Exécution
1. **Marges de Conteneur** :
   - Panneaux et dialogues majeurs : `setContentsMargins(16, 16, 16, 16)`.
   - Cartes et sous-panneaux internes : `setContentsMargins(12, 12, 12, 12)`.
   - Barres d'outils et en-têtes : `setContentsMargins(16, 8, 16, 8)`.
2. **Espacements entre Contrôles (`setSpacing`)** :
   - Entre éléments étroitement liés (icône + libellé, champ + aide) : `4px` ou `6px`.
   - Entre champs d'un même groupe : `8px`.
   - Entre groupes de formulaires : `16px`.
   - Entre sections majeures : `24px`.
3. **Alignement des Lignes de Base** :
   - Vérifier que les boutons, inputs et labels sur une même ligne horizontale partagent un alignement vertical centré (`Qt.AlignmentFlag.AlignVCenter`).
4. **Spacers Élastiques (`addStretch`)** :
   - Placer judicieusement `layout.addStretch()` en bas de formulaire pour maintenir les contrôles groupés en haut plutôt que dilués verticalement.

---

## 5. Passe `/typeset` : Hiérarchie Typographique Studio

### Objectif
Imposer une typographie lisible, hiérarchisée et élégante, guidant l'attention de l'utilisateur avec précision.

### Protocole d'Exécution
1. **Titres Majeurs (14-16px, Semibold 600)** : `COLOR_TEXT_PRIMARY`, marge inférieure nette.
2. **Sous-titres & Sections (11-12px, Bold 600, Uppercase)** : `letter-spacing: 0.5px`, couleur `COLOR_TEXT_MUTED`.
3. **Corps & Formulaires (12-13px, Regular 400)** : `COLOR_TEXT_PRIMARY` ou `SECONDARY`, lisibilité optimale sur `FONT_MAIN`.
4. **Aides & Métadonnées (10-11px, Muted)** : `COLOR_TEXT_MUTED`, placé sous les champs sans encombrer.
5. **Code & Données Précises (11-12px, Monospace)** : Utiliser systématiquement `FONT_CODE` (JetBrains Mono / monospace).

---

## 6. Passe `/harden` : Résilience et Responsive Desktop

### Objectif
Garantir que le widget ne casse jamais, ne tronque pas de texte et s'adapte sans faille aux dimensions d'écran critiques.

### Protocole d'Exécution
1. **Épreuve du 1280×800** : La fenêtre principale doit fonctionner sans défilement horizontal.
2. **Épreuve du 820×560** : Tout dialogue modal doit rester parfaitement manipulable et lisible à cette taille.
3. **Word Wrap Systématique** : Appliquer `setWordWrap(True)` sur tous les `QLabel` textuels.
4. **Taille Minimum Saine** : Pas de `setMinimumWidth` arbitraire > 400px.
5. **Résilience aux Traductions (`ADR 0013`)** : Prévoir 20 à 30 % de longueur supplémentaire pour les textes traduits (allemand/anglais) sans tronquer les boutons.

---

## 7. Passe `/polish` : Affordance et Micro-Détails

### Objectif
Donner à l'interface le toucher soigné d'un produit professionnel : curseurs, ombres d'élévation, transitions et retours visuels.

### Protocole d'Exécution
1. **Curseurs Interactifs** : Assigner `Qt.CursorShape.PointingHandCursor` sur tous les boutons, liens, onglets et cartes cliquables.
2. **Attribut de Survol** : Activer `setAttribute(Qt.WidgetAttribute.WA_Hover, True)` sur les contrôles personnalisés.
3. **Élévation et Ombres Douces** : Appliquer `apply_shadow(widget, blur=12, offset_y=2, color=...)` sur les cartes flottantes.
4. **Normalisation des Icônes** : Vérifier que toutes les icônes proviennent de `load_phosphor_icon` et adoptent des teintes sémantiques cohérentes.

---

## 8. Commandes d'Ajustement : `/quieter` & `/bolder`

### `/quieter` (Atténuer la Charge Cognitive)
À utiliser lorsqu'une vue est visuellement agressive ou encombrée :
- Remplacer un bouton plein (`PrimaryButton`) secondaire par un bouton ghost ou contour (`SecondaryButton`).
- Passer la couleur d'un texte de `PRIMARY` à `SECONDARY` ou `MUTED`.
- Réduire l'épaisseur d'une bordure ou la rendre plus transparente.
- Réduire le corps de police d'une note d'aide d'1px.

### `/bolder` (Affirmer le Point Focal)
À utiliser lorsqu'une action essentielle se perd dans l'interface :
- Valoriser l'action principale unique avec `PrimaryButton` et son glow signature.
- Ajouter un badge d'état contrasté (`StatusBadge`).
- Accentuer la taille ou la graisse du libellé clé.
- Structurer un résumé métrique via une `StatCard` percutante.
