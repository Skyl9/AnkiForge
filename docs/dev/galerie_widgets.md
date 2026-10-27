# Galerie de Widgets (mode développeur) 🧩

La galerie de widgets est un **banc d'observation visuel** réservé au mode développeur. Elle
instancie chaque composant de l'interface avec des charges factices déterministes, sans
écriture en base, sans appel réseau et sans démarrer les workers de production.

Elle sert à trois choses :

- **inspecter** un composant isolément (thème, disposition, états vide/chargé/erreur) ;
- **vérifier** qu'une famille entière reste instanciable après une refonte ;
- **documenter** l'inventaire réel des widgets, dialogues, modèles et ViewModels du dépôt.

## 1. Ouvrir la galerie

```bash
uv run ankiforge --dev          # environnement isolé (~/.ankiforge-dev)
# ou
ANKIFORGE_ENV=development uv run ankiforge
```

Parcours : **Paramètres → onglet « Développeur » → bouton « Galerie de widgets »**.

L'onglet « Développeur » **n'existe pas hors mode développement** : il n'est créé que si
`is_development()` renvoie vrai, comportement verrouillé par le test
`test_settings_modal_exposes_developer_tab_only_in_dev_mode`.

La fenêtre propose une recherche plein texte, l'arbre des familles, un sélecteur de thème et
un sélecteur de disposition (les quatre layouts réels : `ide`, `macos`, `dashboard`,
`glassmorphism`). Ce dernier n'est actif que lorsque l'aperçu courant est la coquille de la
fenêtre principale, seule à savoir appliquer une disposition (`ShellPreviewWindow.set_layout`).

## 2. Familles couvertes

| Famille | Contenu | Mode d'aperçu |
| --- | --- | --- |
| `components` | Widgets autonomes de `ui/components` | Widget réel |
| `dialogs` | Boîtes de dialogue de `ui/dialogs` | Dialogue réel, ouvert en modal |
| `layouts` | Les quatre dispositions de `ui/layouts` | Layout réel + vues de substitution |
| `models` | Modèles Qt (`QAbstractItemModel`) et délégués | Tableau/liste lié, ou lignes peintes |
| `shell` | `MainWindow` (coquille) et `SettingsModal` | Coquille recomposée / dialogue réel |
| `viewmodels` | ViewModels `QObject` de `ui/viewmodels` | Inspecteur de signaux |

!!! info "Hors périmètre assumé"
    Les familles `views` et `widgets` ne sont pas encore branchées : elles font l'objet de
    tickets dédiés. La galerie n'instancie pas davantage la **vraie** `MainWindow`, qui
    démarre des timers réseau, un worker de métriques et le démon MCP.

## 3. Anatomie d'une entrée

Le registre est déclaratif (`src/ankiforge/ui/widget_gallery/registry.py`) :

```python
@dataclass
class GalleryEntry:
    family: str  # nom de la famille (dossier de l'arbre)
    name: str  # libellé affiché (traduit via tr())
    factory: Callable[[], QWidget]
    module: str = ""  # module d'origine, renseigné automatiquement
    modal: bool = False  # l'aperçu s'ouvre légitimement en modal
```

Une famille expose au minimum trois artefacts complémentaires :

1. `XXX_FACTORIES: dict[str, Callable[[], QWidget]]` — la **source unique** de la couverture ;
2. `xxx_labels() -> dict[str, str]` — les libellés français, écrits avec `tr()` pour rester
   extractibles par `lupdate` ;
3. `register()` — enregistre chaque factory via le décorateur `gallery_widget(...)`,
   de façon **idempotente** (un second appel ne duplique rien).

Certaines familles ajoutent un quatrième artefact uniquement lorsqu'elles en ont besoin :
`COMPONENT_CLASS_IDS` / `SHELL_CLASS_IDS` relient une clé de factory à la classe réellement
testée, ce qui autorise un aperçu contextuel (conteneur autour du composant, coquille
recomposée) sans perdre le lien de couverture.

## 4. Ajouter une entrée à une famille existante

Ajoutez la factory, son libellé, puis l'entrée dans le mapping — dans cet ordre :

```python
def _make_mon_modele() -> QWidget:
    model = MonModele()
    model.set_donnees(make_fake_xxx())
    return ItemModelPreview(model, tr("Mon modèle"))


MODEL_FACTORIES["MonModele"] = _make_mon_modele


def model_labels() -> dict[str, str]:
    return {
        # ...
        "MonModele": tr("Mon modèle"),
    }
```

Le test de couverture de la famille échouera tant que les trois points ne sont pas alignés :
il compare le mapping au **parcours réel des classes** du paquet concerné. C'est volontaire —
on ne peut pas « oublier » silencieusement un composant.

## 5. Ajouter une famille

Déposez un module dans `src/ankiforge/ui/widget_gallery/families/` :

- nom de fichier en `snake_case` (`^[a-z][a-z0-9_]*$`) : il devient le nom de la famille ;
- fonction `register()` obligatoire ; son absence est journalisée et la famille ignorée ;
- chargement automatique et **tolérant aux pannes** : une famille qui lève est journalisée
  sans empêcher l'ouverture de la galerie.

```python
# src/ankiforge/ui/widget_gallery/families/charts.py
def register() -> None:
    for key, factory in CHART_FACTORIES.items():
        gallery_widget(family="charts", name=chart_labels()[key])(factory)
```

Ajoutez ensuite la famille à `EXPECTED_FAMILIES` dans `tests/ui/test_widget_gallery.py`, et un
test de couverture par introspection sur le modèle des familles existantes.

## 6. Aperçus non visuels

Les ViewModels, modèles Qt et délégués ne sont pas des widgets. Trois conteneurs génériques
(`src/ankiforge/ui/widget_gallery/previews.py`) les rendent observables :

- `ObjectPreview` — identité, liste des signaux et journal borné des émissions ; appelle
  `dispose()` à la fermeture pour libérer les abonnements au bus d'événements ;
- `ItemModelPreview` — tableau ou liste réellement lié au modèle, avec compteur
  `lignes × colonnes` ;
- `DelegatePreview` — un délégué appliqué à quelques lignes porteuses des rôles attendus ;
- `ShellPreviewWindow` — coquille de `MainWindow` recomposée avec les **vrais** layouts et le
  **vrai** registre `MainWindow.view_registry()`, chaque vue étant remplacée par un
  substitut textuel.

### Règles d'or d'un aperçu

- **Zéro écriture en base** et **zéro appel réseau** : uniquement les factories de
  `ankiforge/dev/fake_data.py`.
- **Aucun worker persistant** : si une construction en démarre un, l'aperçu doit attendre sa
  fin (les tests vérifient `worker.wait(...)`).
- **Pas d'effet de bord de production** : ne jamais instancier `MainWindow`, un démon MCP ou
  un gestionnaire de profil réel.
- **Déterminisme** : mêmes données à chaque ouverture, aucun aléatoire non maîtrisé.

Les données factices vivent dans `ankiforge/dev/fake_data.py` (charges statiques),
`ankiforge/dev/fake_services.py` (dépôts en mémoire, `FakeLLMProvider`) et
`ankiforge/dev/fake_qt_models.py` (`FakeNoteTableModel`). Ce dernier substitue la conversion
par lot du tableau de notes pour afficher des lignes nominales sans requête Peewee ; il est
isolé de `fake_services.py` pour ne pas faire dépendre les faux services de la couche UI.

Les ViewModels sont, eux, instanciés avec leurs **dépendances réelles** (dépôts, services)
mais **sans déclencher de chargement** : l'aperçu se contente de rendre leurs signaux et
états observables, sans peupler la base ni lancer de requête.

## 7. Entrées modales

`SettingsModal` et les dialogues s'ouvrent en modal : leur entrée porte `modal=True`.

```python
gallery_widget(family="shell", name=shell_labels()["SettingsModal"], modal=True)(_make_settings_modal)
```

Une entrée modale reste **affichée dans le volet d'aperçu** comme les autres ; le bouton
« Ouvrir en modal » de la barre d'outils s'active alors et appelle `exec()` sur une nouvelle
instance. Les entrées non modales affichent le même volet, mais le bouton reste désactivé.

## 8. Tests headless

```bash
uv run pytest tests/ui/test_widget_gallery.py -q            # ~309 tests, sans affichage
uv run pytest tests/ui/test_widget_gallery.py -m ui -q      # identique : la marque ui couvre tout le fichier
```

La suite couvre :

- un **smoke test paramétré** sur *toutes* les entrées découvertes à la collecte : chacune doit
  produire un `QWidget` sans crash, sans worker pendant, puis se fermer proprement ;
- la **couverture par introspection** de chaque famille : toute classe concrète déclarée dans
  le paquet source doit être enregistrée (les exclusions sont explicites et commentées) ;
- le **registre de la coquille** : `ShellPreviewWindow.navigation_ids()` doit égaler
  `MainWindow.view_registry()` ;
- le **câblage de la barre d'outils** : bouton modal piloté par `entry.modal`, sélecteur de
  disposition limité à la coquille, libération de l'aperçu courant à la fermeture ;
- la présence/absence de l'onglet « Développeur » selon `is_development()`.

Les libellés passant par `tr()`, tout nouveau texte doit être extrait des sources avant le
commit :

```bash
uv run python script/extract_translations.py
```

Tout se passe en `QT_QPA_PLATFORM=offscreen` : aucun snapshot d'image en assertion.

## 9. Capturer un aperçu

Pour une validation visuelle, capturez la vue en offscreen (voir la compétence
`ui-screenshot`) plutôt que d'ouvrir l'application :

```python
from PySide6.QtWidgets import QApplication

from ankiforge.ui.widget_gallery.families import load_families
from ankiforge.ui.widget_gallery.registry import WidgetGalleryRegistry

app = QApplication.instance() or QApplication([])
load_families()
entry_name = "Modèle de fragments RAG"  # libellé affiché dans l'arbre
entry = next(item for item in WidgetGalleryRegistry.list(family="models") if item.name == entry_name)

widget = entry.factory()
widget.resize(1200, 760)
widget.show()
app.processEvents()
widget.grab().save("apercu.png")
```

Les captures servent à **inspecter** un rendu, jamais à servir d'assertion automatisée.
