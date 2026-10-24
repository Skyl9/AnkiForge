# Architecture du Système de Thèmes : Persistance Bi-Axiale, Bibliothèque JSON et Format d'Échange

**Statut :** accepté (ADR consolidé unifiant les décisions thématiques sur la persistance, la bibliothèque et le format d'échange)

Afin d'offrir une personnalisation graphique complète, partageable et robuste sans introduire de complexité inutile dans la base de données, nous unifions les fondations du système de thèmes d'AnkiForge autour de trois piliers :
1. La séparation stricte de la persistance en deux axes indépendants (**Famille de Thème × Source du Mode**),
2. Une **bibliothèque globale de fichiers JSON** sur disque comme source unique de vérité partagée entre profils,
3. Un **format d'échange bivalent** au niveau de la Famille avec charge utile tolérante aux deltas de jetons.

---

## 1. Désencastrer les Deux Axes d'Apparence dans la Persistance

### Le Problème
Auparavant, la préférence d'apparence était persistée sous forme d'un identifiant de variante unique (`theme_id`, ex: `"nord-dark"`). Ce scalaire unique encastrait deux notions orthogonales : l'identité esthétique (la palette Nord, Dracula, etc.) et le régime visuel (Sombre, Clair, ou Suivi du système d'exploitation). Il était impossible d'exprimer « suivre le thème de l'OS » sans casser la résolution de la famille graphique choisie.

### Options Considérées
1. **Conserver `theme_id` + un drapeau booléen `follow_system`** : *Rejeté*. Laisse intact le défaut structurel où un identifiant scalaire porte deux concepts distincts.
2. **Stocker une sentinelle dans `theme_id` (ex. `"auto"`)** : *Rejeté*. Casse les contrats de `get_family_for_theme` qui attend un identifiant de thème ou de famille réel.
3. **Séparer les deux axes (`theme_family` et `appearance_mode_source`)** : *Retenu*. Aligne la persistance sur le modèle formel de `DESIGN.md` (Mode d'Apparence × Famille de Thème) et fait de « Suivre le système » une règle de dérivation dynamique.

### Décisions & Règles
- Deux clés sont persistées de manière autonome dans les préférences de chaque profil : `appearance/theme_family` (ex: `"catppuccin"`) et `appearance/mode_source` (`"dark"`, `"light"`, ou `"system"`).
- La Variante active est calculée dynamiquement au runtime en croisant ces deux informations.
- La lecture paresseuse avec normalisation au premier accès préserve la rétrocompatibilité avec les profils historiques enregistrés avec l'ancienne clé scalaire `theme_id`.
- Le choix explicite d'une Famille par l'utilisateur prime toujours sur la suggestion par défaut du layout actif.

---

## 2. Bibliothèque de Thèmes Partagée en Fichiers JSON

### Le Problème
Les thèmes personnalisés créés ou importés par l'utilisateur doivent pouvoir être versionnés, inspectés, copiés et partagés facilement sans alourdir le schéma relationnel SQLite ni imposer de migrations complexes à chaque ajout de jeton de style.

### Options Considérées
1. **Nouvelle table Peewee pour les thèmes** : *Rejeté*. La finalité première est le partage de thèmes entre utilisateurs et la sauvegarde de fichiers légers. Une table SQL imposerait des migrations sans gain fonctionnel.
2. **Table SQLite comme cache et fichiers JSON comme vérité** : *Rejeté*. Complexité injustifiée de synchronisation bidirectionnelle pour un volume de quelques kilo-octets.
3. **Fichiers JSON sur disque comme source unique de vérité** : *Retenu*.

### Décisions & Règles
- Les Familles et Variantes personnalisées résident dans un répertoire dédié sous le dossier de données de l'application (`~/.ankiforge/themes/`).
- La bibliothèque est **globale à l'installation et partagée entre tous les profils**. Un profil utilisateur ne détient pas de copie privée : il référence une Famille de la bibliothèque commune.
- Au démarrage, le registre en mémoire de `StyleEngine` est hydraté par balayage de ce répertoire.
- **Résolution de collision sans écrasement** : L'importation d'un thème dont le nom entre en collision avec un thème existant applique un renommage numérique automatique (`nom_2.json`) et réécrit l'identifiant interne dérivé du fichier pour interdire l'existence de deux vérités concurrentes.

---

## 3. Format d'Échange Bivalent et Charge Utile Tolérante

### Le Problème
Comment échanger des thèmes créés par la communauté sans forcer l'utilisateur à concevoir ou exporter deux fichiers séparés, tout en autorisant la surcharge partielle d'une palette sans écraser destructivellement les jetons par défaut ?

### Options Considérées
1. **Conteneur Famille avec charge utile exhaustive obligatoire** : *Rejeté*. Forcerait l'exportation de variantes que l'utilisateur n'a pas touchées et écraserait des jetons sains lors de l'import.
2. **Unité = une seule Variante isolée** : *Rejeté*. Casse l'expérience bi-axiale où un thème complet propose une ergonomie coordonnée en mode sombre et clair.
3. **Delta strict contre la base de la Famille** : *Rejeté*. Dépend trop fortement des versions amont du logiciel et devient fragile si les jetons d'origine évoluent.
4. **Conteneur de Famille avec charge utile tolérante** : *Retenu*.

### Décisions & Règles
- **Unité d'échange = Famille de Thème** : Tout fichier de thème exporté (`.json`) est un conteneur portant l'identité de la Famille et ses deux variantes (`dark` et `light`).
- **Charge utile tolérante (Partial Payloads)** : Chaque variante ne déclare que les jetons qu'elle redéfinit spécifiquement. L'importateur applique un delta non destructif : seuls les champs explicitement présents sont surchargés, les valeurs absentes conservent le repli standard du moteur.
- **Jetons dérivés exclus** : Les jetons purement calculés (`DesignTokens`, bordures ou fonds dérivés) ne sont jamais inclus dans le JSON sérialisé ; ils sont re-dérivés dynamiquement par `StyleEngine` à l'application.
- **Versionnage du schéma** : Le format JSON intègre un champ `schema_version: 1` pour assurer l'extensibilité future.
