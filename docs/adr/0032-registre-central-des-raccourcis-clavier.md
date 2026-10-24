# Registre central des raccourcis clavier, gestion des portées et neutralisation des dialogues

**Statut :** accepté (ADR consolidé intégrant la sécurisation et la neutralisation de dialogue de l'ex-ADR 0031)

Afin d'éliminer les séquences câblées en double et les gestes annoncés sans action, nous instaurons un **registre central déclaratif des raccourcis** (`src/ankiforge/ui/shortcuts/`) comme unique source de vérité de tout binding, de tout libellé affiché et de la documentation : quatre portées hiérarchiques (`Dialogue > Widget > Vue > Application`), activation des bindings par vue affichée, règle « la saisie de texte prime toujours », surcharges utilisateur persistées dans `SettingsService`, refus strict des conflits intra-portée et liste noire de séquences réservées.

---

## Le Problème

1. **Aucune source de vérité** : environ quarante séquences sont posées en `QShortcut` dispersés dans les vues, les dialogues et la fenêtre principale, sans inventaire commun. Ajouter un raccourci suppose de deviner ce qui est déjà pris, et à quelle portée.
2. **Annonces orphelines** : la palette de commandes, les infobulles et certaines barres d'état affichent des séquences sans câblage (`⌘K`, `Ctrl+,`, `Ctrl+1..5`, `Ctrl+Entrée` du Studio, `Ctrl+S` de plusieurs vues, `Ctrl+N`, `Ctrl+Alt+L`, `Ctrl+Shift+I`). L'utilisateur apprend des gestes morts.
3. **Collision silencieuse** : `Ctrl+Shift+E` porte à la fois l'export `.apkg` annoncé et l'édition groupée de la vue Édition ; l'un des deux devient inaccessible sans que rien ne le signale.
4. **Libellés figés** : `command_palette.py` code ses séquences en dur, en désaccord avec le câblage réel ; `editor_toolbar_widget.register_action` stocke une chaîne de raccourci pour l'affichage seulement.
5. **Fenêtre unique, vues multiples** : les vues sont des pages d'un même `QStackedWidget`. Un `QShortcut` posé dans une page non affichée peut rester actif, ce qui interdit la réutilisation des séquences entre vues sans activation par vue affichée.
6. **Aucune personnalisation** : les habitudes clavier des utilisateurs d'Anki (ou d'ailleurs) ne peuvent pas être reportées.

## Options Considérées

1. **Statu quo documenté** : produire un inventaire markdown des séquences existantes sans toucher au câblage. *Rejeté* : un document ne contraint rien ; la dérive reprend dès la première vue ajoutée.
2. **Une table Peewee `shortcuts`** : persister les bindings dans la base du profil. *Rejeté* : les raccourcis sont une préférence d'interface, pas une donnée métier ; `SettingsService` assure déjà la persistance et l'isolation par profil.
3. **Tout en `QAction` Qt avec `QShortcut` hybrides** : s'appuyer sur le système d'actions natif. *Rejeté* : ne répond ni à la source de vérité documentaire, ni à la portée hiérarchique, ni à la génération des libellés et de la page de référence.
4. **Registre Python déclaratif + manager de liaison + surcharges en `SettingsService`** : *Retenu*.

## Décisions et Règles d'Architecture

### 1. Registre déclaratif unique
`src/ankiforge/ui/shortcuts/` porte `ShortcutId` (`StrEnum`), `ShortcutDefinition` (dataclass gelée : identifiant, catégorie, portée, séquence par défaut, libellé), `ShortcutScope` et le catalogue exhaustif. Les libellés sont **résolus paresseusement** (`tr()` à l'appel), conformément à l'ADR 0013 — jamais au chargement de module. Typage `mypy` strict, zéro `print()`.

### 2. Portées hiérarchiques et résolution
Quatre portées : **Dialogue > Widget > Vue > Application**. À l'événement, la portée la plus spécifique active gagne. Les **touches nues** ne sont admises qu'en portée Widget, sur une liste ou une table focalisée.

### 3. Règle du texte prioritaire
Toute saisie de texte focalisée absorbe les touches nues et les séquences d'édition avant toute résolution de raccourci : taper « e » dans un champ n'édite jamais une carte.

### 4. Activation par vue affichée
Le manager active les bindings de la vue courante et désactive ceux des pages masquées ainsi que ceux masqués par un dialogue modal. Ce double mécanisme (portées + activation) autorise la réutilisation d'une même séquence par plusieurs vues sans collision, et interdit tout déclenchement depuis un écran non visible.

### 5. Routeurs d'action primaire
`Ctrl+S` (enregistrer) et `Ctrl+Entrée` (action primaire) sont des définitions **uniques** de portée Application qui délèguent à la vue active. Tout `QShortcut` local doublonnant est supprimé ; `EditorToolbarWidget.register_action` cesse de porter un libellé de raccourci et lit le catalogue.

### 6. Surcharges, conflits et séquences réservées
Les personnalisations (identifiant → séquence) sont persistées dans `SettingsService`, sans table Peewee et sans écriture lorsque la valeur égale le défaut. Un conflit **intra-portée** est refusé avec explication. Une liste noire de séquences réservées (`Ctrl+C`/`X`/`V`/`Z`/`Y`/`A` dans les champs, `Ctrl+W`, `Ctrl+Q`) n'est pas remappable.

### 7. Affichage et documentation générés
Toute infobulle, toute entrée de palette et la page de référence clavier sont **générées** depuis le catalogue. Une annonce sans binding est câblée ou supprimée.

### 8. Garde-fou de dérive
`script/check_shortcuts_drift.py --check|--fix` régénère et valide la page de référence ; une étape `shortcuts-drift` est ajoutée à la porte canonique `script/verify.py`, sur le patron exact de `instructions-drift`.

### 9. Neutralisation des dialogues modaux et persistance explicite (ex-ADR 0031)

Afin d'éliminer toute perte de données et toute fermeture impromptue lors de la configuration ou de la capture de raccourcis, les règles d'ergonomie et de neutralisation de `QDialog` sont généralisées :
- **Neutralisation d'`autoDefault`** : Désactivation explicite d'`autoDefault` sur tous les boutons secondaires, icônes et boutons d'annulation des dialogues (`setAutoDefault(False)`).
- **Interception de la touche Entrée** : Surcharge de `keyPressEvent(event)` pour intercepter `Qt.Key.Key_Return` et `Qt.Key.Key_Enter` au niveau racine, interdisant la fermeture aveugle via `QDialog.accept()`.
- **Validation en place avec toast** : Dans les champs de saisie simple (`QLineEdit`, ex: libellés de drapeaux Anki ou filtres), l'appui sur `Entrée` (`returnPressed`) déclenche l'enregistrement global sans fermer la modale, avec confirmation visuelle immédiate par toast non bloquant.
- **Navigation par tabulation (`Tab` / `Shift+Tab`)** : L'ordre séquentiel de focalisation est strictement respecté pour permettre la complétion rapide de grilles de champs avant validation finale.
- **Raccourci universel `Ctrl+S` / `Cmd+S` en portée Dialogue** : Tout dialogue de configuration expose un `QShortcut` mappé sur la clé standard d'enregistrement pour offrir une parité clavier totale avec le bouton principal de pied de page.
- **Repli canonique des libellés vides** : Un champ de configuration vidé par l'utilisateur réapplique immédiatement le repli textuel par défaut (`DesignTokens.FLAG_NAMES[idx]`), garantissant l'absence de valeurs nulles orphelines.
