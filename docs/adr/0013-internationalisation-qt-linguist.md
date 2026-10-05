# Internationalisation par Qt Linguist

L'interface d'AnkiForge est écrite en français, ce qui la rend inutilisable pour un utilisateur anglophone sans être pour autant impossible à traduire. Nous adoptons la mécanique **Qt Linguist** — la même que celle de KDE, VLC ou Qt Designer — plutôt qu'un moteur maison : `pylupdate5` extrait, `lrelease` compile en binaire, `QTranslator` résout à l'exécution. L'écosystème est éprouvé, les catalogues s'éditent dans un outil graphique, et PySide6 est déjà le moteur d'interface.

## Statut
Accepté

## Options considérées

1. **Dictionnaires Python maison (`_("texte")` + JSON)** : rejeté. Aucun outil visuel, aucun contrôle de cohérence des marqueurs, aucune gestion des pluriels ni des concaténations. C'est ce que faisait le projet avant, et cela n'a jamais produit de catalogue complet.
2. **Traduction automatique (LLM ou API) des catalogues** : rejeté. Une traduction automatique non relue est une faute silencieuse : elle produit une interface qui a l'air correcte et ne l'est pas. La traduction humaine fait l'objet d'un ticket distinct (`Doc - Traduction Humaine des Catalogues i8n vers l Anglais`). L'infrastructure rend ce travail faisable ; elle ne le fait pas à sa place.
3. **`gettext` GNU** : rejeté. Qt ne le consomme pas nativement ; il faudrait un pont, donc une couche propriétaire.
4. **Qt Linguist** : retenu. Natif PySide6, outils de référence, format `.ts`/`.qm` documenté, et surtout un **format de marqueur de position** (`%1`, `%2`, `%n`) que le traducteur peut déplacer librement dans la phrase cible.

## Conséquences

### Langue source = français, repli = français

`SOURCE_LANGUAGE = "fr"`. Un catalogue identique à la langue source est inutile à l'exécution : Qt restitue déjà le texte écrit dans le code. `install_translator()` **ne lève jamais** — un catalogue absent, illisible ou vide se traduit par une interface qui reste en français, jamais par un échec au démarrage. Une application qui refuse de démarrer faute de traduction est une application cassée ; une application qui démarre dans la langue de son code ne l'est pas.

### Un seul module d'amorçage

`src/ankiforge/utils/i18n.py` est **l'unique couture** de traduction au runtime : résolution du dossier, installation du `QTranslator`, exposition de `tr()`. Aucun autre module n'instancie de `QTranslator`, aucun n'essaie de deviner un chemin de catalogue.

### Un seul emplacement de ressources

Les catalogues vivent dans `src/ankiforge/resources/translations/` et sont résolus par `utils.paths.get_resource_path`, jamais par `Path(__file__)` — qui échoue dans tout bundle. Le dépôt porte historiquement **deux racines de ressources** (`src/ressources` pour les icônes et prompts, `src/ankiforge/resources` pour KaTeX et l'i18n) ; c'est leur divergence qui a cassé `database/seeds/initial_seed.py`. Elles sont désormais copiées **indépendamment** dans le bundle : une racine manquante ne prive plus l'application de l'autre.

### Trois états de catalogue, deux coutures de build

Le `.ts` est **versionné** (source de vérité, relisible en diff), le `.qm` est un **artefact** produit par `script/extract_translations.py`. Aucun n'est compilé à l'exécution.

Conséquence directe : le `.qm` est ignoré par Git, donc aussi par hatchling, qui respecte les fichiers d'exclusion du VCS. Sans déclaration explicite, le wheel partirait avec les `.ts` — utiles à l'extraction, inutiles à l'exécution — et **sans aucune traduction**. Le pilote compile les `.qm` avant Nuitka, puis `copy_app_resources_to_bundle()` recopie toute la racine `src/ankiforge/resources` dans le bundle (vers `Contents/Resources` pour macOS) ; Nuitka ne reçoit pas de glob de traduction, car sa destination serait résolue sous `Contents/MacOS` et entrerait en conflit avec l'exécutable. Le wheel conserve sa déclaration `artifacts` dans `pyproject.toml`. `tests/test_i18n_packaging.py` vérifie ces coutures.

### Deux formes d'écriture, et une seule interdiction

- littéral → `self.tr("Enregistrer")` dans une sous-classe de `QObject`, `tr("Enregistrer")` ailleurs ;
- littéral interpolé → `tr("Enregistré : %1/%2", faits, total)`.

**`tr(f"…")` est interdit.** Une f-chaîne est évaluée *avant* l'appel : le catalogue ne contiendrait qu'une suite de messages uniques, tous introuvables à l'exécution, et le traducteur gaspillerait son temps sur des entrées mortes. C'est le piège principal du mécanisme, d'autant plus qu'il ne produit aucune erreur.

Ces deux formes sont les **seules** que `pylupdate` extraie : il reconnaît `self.tr()` et `tr()`, et rien d'autre. Un helper d'interpolation nommé autrement serait invisible au catalogue, silencieusement.

### `self.tr()` ne sait pas substituer

`QObject.tr(sourceText, disambiguation=None, n=-1)` : le second argument positionnel de `self.tr()` est la **désambiguïsation**, pas une valeur. `self.tr("Total : %1", n)` ne lève donc aucune erreur — Qt cherche un message contextualisé par la chaîne représentée par `n`, ne le trouve pas, et renvoie silencieusement le texte source, marqueur `%1` inclus. L'interface affiche alors littéralement « Total : %1 ».

La règle est donc asymétrique et mérite d'être écrite deux fois : `self.tr()` pour un littéral seul, `tr()` dès qu'il y a une valeur. C'est aussi pour cela que `addItem`/`insertItem` ne traduit que leur **premier** littéral positionnel : les suivants sont des `userData`, donc des identifiants.

### Traduire trop tôt : le piège de l'import

Un `tr()` évalué au chargement du module est figé **avant** l'installation du traducteur. Or `__main__.py` importe `MainWindow` en tête de module, alors que `install_translator()` n'est appelé qu'après la création de `QApplication`. Un registre de navigation déclaré en constante de classe aurait donc gardé ses libellés français dans une interface anglaise, sans la moindre erreur.

`MainWindow.view_registry()` est une **méthode** pour cette raison : elle reconstruit la table à chaque appel, donc après l'installation. Toute donnée d'interface évaluée au chargement d'un module doit suivre cette règle — voir `tests/utils/test_i18n.py`.

### Les widgets maison sont des puits d'affichage

`QLabel`, `QPushButton` ou `setToolTip` ne sont qu'une partie des points d'entrée de texte : le projet perpète `Badge`, `DangerButton`, `SubTabButton`, `StorageMetricCard`… Une liste de noms figée serait fausse au premier widget nouveau, donc l'audit **déduit** le contrat des signatures : un `__init__` dont le premier paramètre s'appelle `text`, `label` ou `title` fait de la classe un puits d'affichage.

Une exception subsiste, et elle est mécanique : un littéral sans aucun mot en minuscules (`"0"`, `"LLM"`, `"OFF"`, `"(0)"`), contenant un marqueur de modèle Anki (`"{{FrontSide}}"`) ou un fragment HTML (`'<hr id="answer">'`) est une **donnée**, pas une phrase. Le mettre au catalogue produirait des entrées que le traducteur ne peut qu'abandonner ; et, pour une valeur qui sert aussi d'identité, une traduction cassant silencieusement la comparaison.

### Substitution après traduction

`QString::arg()` n'est pas disponible : PySide6 expose `QCoreApplication.translate()` comme un `str` Python. `tr(text, *values)` implémente donc la substitution lui-même, sur le texte **traduit** — condition pour qu'une traduction puisse réordonner la phrase (« `%1 files processed` »). `%n` prend la plus petite position libre, `%1`..`%99` sont positionnels, `%%` est un pourcentage littéral, un marqueur orphelin reste visible plutôt que de disparaître.

### Clés et valeurs : la distinction qui compte

Les tables `statut → libellé` (fichiers batch, indicateurs de création, aperçu de carte) gardent leurs **clés en littéral** — ce sont des identifiants persistés, comparés aux valeurs stockées — et traduisent **seulement les valeurs affichées**. Filtrer, c'est comparer ; comparer, c'est ne pas traduire.

### Ce qui reste à faire

La langue cible du premier cycle est `en` uniquement. Le catalogue anglais est extrait et versionné, **vide** : il attend le travail du ticket frère. L'audit de non-régression (`tests/utils/test_i18n_audit.py`) garantit qu'aucun libellé ne reste hors catalogue, qu'aucune f-chaîne ne passe par `tr()`, qu'aucune interpolation n'est mal formée, qu'aucun `tr()` ne s'exécute avant l'installation du traducteur, et qu'aucun catalogue n'est rempli automatiquement.