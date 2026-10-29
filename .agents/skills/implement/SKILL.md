---
name: implement
description: >-
  Implémente une tâche ou un ticket Obsidian en déroulant le cycle TDD, les vérifications statiques et la revue de code avant livraison.
  Use when the user asks to "implement", "implémenter", "coder le ticket", "développer", or starts building a feature or bugfix from a spec or Obsidian ticket.
  When NOT to use: Do not use for exploratory interview (use grill-with-docs) or ticket slicing (use to-tickets).
disable-model-invocation: true
---

# Implement — Implémentation Pilotée par les Tests et Suivi Obsidian

Prend en charge la réalisation d'une tâche, d'une spécification ou d'un ticket Obsidian (`ankiforge_obsidian/Tickets/<Type> - <Titre>.md`).

## 1. Démarrage et Cycle de Vie Obsidian

1. **Prise en charge du ticket** :
   - Lire la note du ticket ciblée dans `ankiforge_obsidian/Tickets/`.
   - **Vérification préalable de l'état réel** : exécuter `git status` et `git log --oneline -5` sur le dépôt principal pour déterminer si l'implémentation existe déjà (code et tests déjà présents). Si c'est le cas, ne pas réimplémenter — passer directement à la vérification canonique (`script/verify.py`) puis à la clôture du ticket.
   - Dans le tableau Kanban `ankiforge_obsidian/Avancement du projet.md`, déplacer la carte correspondante vers la colonne `## 🏃 En cours`.
   - **Règle anti-boucle** : appliquer la modification en une seule passe atomique (One-shot pass) sans relecture circulaire.
2. **Clarifier la couture (Seam)** :
   - Vérifier les critères d'acceptation et identifier le point d'entrée modulaire (modèle, service, ou widget Qt).

## 2. Développement Test-First (/tdd)

- Développer le comportement attendu tranche par tranche en pilotant **`/tdd`** :
  1. Écrire le test unitaire ou d'intégration rouge (`tests/...`).
  2. Implémenter le code minimal pour passer le test au vert.
  3. Refactoriser pour la lisibilité et la compacité.
- **Règles d'ingénierie AnkiForge obligatoires** :
  - Typage strict 100% (`mypy`).
  - Aucun `print()`, utiliser exclusivement le logging asynchrone (`logging.getLogger(__name__)`).
  - Tests UI Qt 100% headless (`pytest-qt`, `QT_QPA_PLATFORM=offscreen`).
  - Attente impérative des threads : tout test pilotant un widget démarrant un worker en tâche de fond (`QThread`, worker d'arrière-plan) doit obligatoirement attendre sa fin (`if widget.worker and widget.worker.isRunning(): widget.worker.wait()` ou `qtbot.waitUntil(widget.worker.isFinished)`) pour immuniser le teardown de `mock_db` contre tout verrou SQLite concurrent.
  - Mocks LLM obligatoires (zéro appel API payant en test).
  - Design Tokens réels : ne jamais présumer de tokens stylistiques non définis (`BG_SECONDARY`, `BORDER_HOVER` n'existent pas) ; se référer exclusivement à `src/ankiforge/ui/theme.py`.
  - Internationalisation paramétrée : `self.tr()` ne réalisant pas de substitution `%1`, tout message paramétré emploie la fonction globale `tr("Message : %1", val)` de `ankiforge.utils.i18n`.
  - Nouveaux modèles Peewee : ajouter impérativement toute nouvelle classe `*Model` dans la liste `models` de la fixture `mock_db` dans `tests/conftest.py` pour éviter l'erreur `no such table`. Recharger via `Model.get_by_id()` (jamais `refresh_from_db`).
  - Nouveaux outils FastMCP : enregistrer tout `@mcp.tool()` dans `TOOL_DOMAIN_MAP` et `TOOL_SAFEGUARDS_MAP` de `mcp_tool_catalog_widget.py`, assurer la parité de dispatch dans `ConsultantEngine` (`DEFAULT_CONSULTANT_TOOLS` et `_execute_tool_call()` dans `consultant_engine.py`), et actualiser de manière exhaustive l'ensemble des assertions de décompte dans les tests (recherche grep systématique `grep -rn "== <ancien_compte>" tests/` pour inclure les tests d'introspection et d'intégration du widget).
  - Internationalisation sans concaténation (`T-26`) : ne jamais assembler des fragments `tr("...") + tr("...")`. Rédiger des phrases entières complètes par branche (`tr("Cartes ciblées : %1 carte(s) dans le paquet '%2'.", n, p)` vs `tr("Cartes ciblées : %1 carte(s).", n)`).
  - Mutations de paquets hiérarchiques (`T-27`) : lors d'une suppression avec réassignation de cartes, interdire le déplacement vers un sous-paquet descendant (`target.name.startswith(f"{source.name}::")`), réassigner l'arborescence complète (paquet + descendants) et englober déplacement et suppression dans un unique `with db.atomic():`.
  - Tests asynchrones : encapsuler toujours dans `def test_...(): asyncio.run(_run())` synchrone (zéro `@pytest.mark.asyncio`).
  - Icônes Phosphor réelles : ne jamais présumer du nom d'une icône vectorielle ; vérifier impérativement son existence dans le manifeste `src/ressources/icons_manifest.txt` avant tout appel à `load_phosphor_icon("ph.<nom>")`.
  - Remplacements univoques sous `edit_file` : inclure systématiquement un contexte englobant suffisant (classe parente, méthode précédente) pour garantir un remplacement ciblé unique (`Made 1 replacement`).
  - Pré-validation syntaxique après `edit_file` : après toute modification d'un fichier Python contenant des blocs de contrôle de flux imbriqués (`try`/`except`/`finally`, `if`/`else`, boucles), exécuter impérativement `uv run python -c "import <module>"` ou `python -m py_compile <fichier>` pour détecter immédiatement une `SyntaxError` avant toute exécution de tests ou de `script/verify.py`.
  - Surcharges de méthodes Qt : ne jamais surcharger une méthode native de widget Qt (`QTreeWidget`, `QTableWidget`, etc.) en altérant son arité ou ses types de paramètres pour préserver le sous-typage Liskov sous `mypy strict` (`[override]`).
  - Contrats de retour d'API et dictionnaires : ne jamais présumer des clés de retour d'une méthode de service ou d'un registre (`apply_bundle_all()`, `to_dict()`) ; toujours inspecter la définition de la fonction ou du modèle avant d'écrire une assertion de test ou d'extraire une valeur.
  - Invocations FastMCP en test : `mcp.call_tool()` retourne une instance typée `CallToolResult` et non une liste ; utiliser obligatoirement le helper d'extraction `def _extract_text(res: Any) -> str: return str(res.content[0].text) if hasattr(res, "content") and res.content else str(res)` pour extraire le texte sans jamais tenter d'indexer `res[0]` ou d'appeler `len(res)`.
  - Édition chirurgicale Markdown : sur les fichiers Markdown vivants (`Avancement du projet.md`), limiter la chaîne `Target` aux seules lignes strictes de l'élément à déplacer sans englober les sauts de lignes inter-sections variables (`\n\n\n`), ou recourir à un remplacement par script pour prévenir les rejets de correspondance exacte.
  - Collision de variables locales sous Mypy Strict (`T-28`) : dans les grands répartiteurs et blocs de dispatch (`ConsultantEngine._execute_tool_call()`, etc.), employer impérativement des variables locales qualifiées et contextuelles (`plate_target_id`, `card_id_int`, `patch_id_str`) au lieu d'identifiants courts partagés (`p_id`, `data`, `res`) pour prévenir toute erreur de type incompatible `[assignment]` sous Mypy.
  - Typage strict des fixtures pytest (`T-29`) : annoter systématiquement `tmp_path: Path` (`from pathlib import Path`) et ne jamais utiliser le builtin `any` comme annotation de type.
  - Zéro émoji dans les valeurs métier persistées ou indexées (`T-30`) : bannir tout émoji des fonctions de nettoyage (`strip_html_for_sort`, `compute_sort_field`) alimentant les colonnes de base SQLite (`sort_field`, FTS5) ou les clauses de tri SQL (`ORDER BY sort_field`).
  - Rollback de migration complet avec double suppression d'index (`T-31`) : dans tout `rollback()` Peewee-migrate, détruire systématiquement les deux variantes de nom d'index (`idx_<table_name>_<column_name>` et `<table_name>_<column_name>`), et valider l'aller-retour complet (`migrate` + `rollback`) dans le test de la migration.
  - Initialisation de table virtuelle en test (`T-33`) : dans tout test PySide6 impliquant une vue tabulaire à modèle paginé virtuel (`EditionView`, etc.), appeler impérativement `view.refresh_data()` avant de simuler des clics de souris, des ouvertures de menus contextuels ou des résolutions géométriques de cellules (`visualRect()`), les données n'étant pas peuplées de manière synchrone dans `__init__`.
  - Validation matérielle des icônes de ticket (`T-34`) : ne jamais implémenter aveuglément un nom d'icône suggéré dans un ticket sans vérifier au préalable son existence dans `src/ressources/icons_manifest.txt` (ex: `funnel` retenu à la place de `sort-ascending` inexistant). En cas d'écart, adopter l'icône canonique la plus proche et rectifier le critère d'acceptation du ticket.
  - Caractères réservés dans les titres de tickets (`T-35`) : ne jamais inclure de barre oblique (`/`), d'anti-slash (`\`) ou de deux-points (`:`) dans le nom d'un fichier de ticket sous `ankiforge_obsidian/Tickets/` afin de prévenir la création accidentelle de sous-dossiers Unix parasites.
  - Faux positifs de fuite sur requêtes SQL Peewee (`T-36`) : dans tout test d'audit de fuite de données vérifiant l'absence d'une sentinelle secrète dans les logs (`caplog`), filtrer impérativement sur les enregistrements du logger applicatif concerné (`[r for r in caplog.records if r.name.startswith("ankiforge.<service>")]`) pour éviter la capture des requêtes SQL brutes émises par Peewee au niveau `DEBUG`.
  - Adaptation des libellés d'interface et anti-crop (`T-37`) : tout libellé d'onglet, bouton ou libellé d'interface susceptible d'être tronqué sur la largeur doit être raccourci pour tenir dans son conteneur, et le nom complet doit être porté par un `toolTip` et/ou un `accessibleName` en français. Ne jamais laisser un libellé texte se faire couper visuellement sans repli accessible.
  - Cohérence des propriétés publiques exposées après changement de type (`T-38`) : lorsqu'un attribut ou composant change de classe (ex: `QTabBar` → `SegmentedTabBar`), inspecter impérativement toutes les propriétés et méthodes du projet qui l'exposent (`@property`, signatures, appels externes) et mettre à jour leurs annotations de typage pour préserver la cohérence sous `mypy strict`, puis exécuter `script/verify.py` pour confirmer.
  - Zéro couleur en dur dans les contrats de données de service (`T-39`) : toute valeur de couleur portée par les données retournées par un service (ex: `badge_color`, `color` de catégorie, `bg`) doit utiliser les jetons `DesignTokens` de `src/ankiforge/ui/theme.py` ; aucun littéral hexadécimal (`#RRGGBB`) ni `rgba(...)` en dur ne doit traverser un contrat de données. Vérifier par grep systématique `grep -rn '#[0-9a-fA-F]\{3,8\}\|rgba(' src/ankiforge/services/` avant la porte canonique.
  - Source unique de vérité pour les constantes de contrat (`T-40`) : toute constante métier partagée (pénalités de score, seuils, seuils de similarité, couleurs de statut) doit être définie en un seul endroit et réutilisée par tous les consommateurs (service + UI + MCP). Interdiction de dupliquer une constante de contrat (ex: `_CATEGORY_PENALTY` dans `linter.py` et `wozniak_tab.py`) ; importer la définition unique ou exposer une fonction de calcul partagée. Revue systématique des assertions de test pour éliminer les tautologies (`or True`, `and True`, `== x or True`) avant la porte canonique.

## 3. Clôture, Vérification Canonique & Revue

1. **Pré-nettoyage Linter, Formatage & i18n (`ADR 0013`) — Ordre séquentiel strict (`T-32`)** :
   - **Étape 1a (Formatage prioritaire)** : Exécuter la passe rapide de formatage et de nettoyage des imports pour stabiliser la géométrie et les sauts de lignes du code source :
     ```bash
     uv run ruff check --fix . && uv run ruff format .
     ```
   - **Étape 1b (Extraction post-formatage)** : Si des chaînes utilisateur ont été ajoutées, modifiées ou retirées avec `tr()` dans l'UI :
     ```bash
     uv run python script/extract_translations.py
     ```
     > [!IMPORTANT]
     > L'extraction doit impérativement s'exécuter **après** `ruff format`. Si `ruff format` intervient après l'extraction, il décale les numéros de ligne des chaînes sources et rend immédiatement obsolètes les balises `<location line="N"/>` des fichiers `.ts` versionnés (`ankiforge_fr.ts`, `ankiforge_en.ts`), provoquant l'échec de `test_committed_catalog_matches_a_fresh_extraction`.
2. **Porte de vérification canonique** :
   ```bash
   uv run python script/verify.py
   ```
   Exécute la chaîne complète (ruff check/format, mypy strict, bandit, tests rapides).
3. **Revue de code à deux axes (Obligatoire)** :
   - Déclencher systématiquement **`/code-review`** (deux sous-agents parallèles : Standards & Spécification) pour confronter le diff aux exigences avant toute clôture.
   > [!IMPORTANT]
   > ⛔ **Garde-fou bloquant** : Il est formellement INTERDIT de clore le ticket, de modifier son statut en `✅ Terminé`, de toucher au Kanban ou de formuler une proposition de commit avant d'avoir formellement restitué le rapport de code-review à deux axes à l'utilisateur.
   - **Boucle de remédiation immédiate** : si la revue de code formule des constats ou demandes d'ajustements (standards, typage, design system, i18n) :
     1. Appliquer les corrections requises dans le code ou les tests.
     2. Si des chaînes traduisibles ont été modifiées, ré-exécuter `uv run python script/extract_translations.py`.
     3. Re-valider l'intégralité de la chaîne via `uv run python script/verify.py`.
     4. Ne passer à l'étape 4 qu'une fois la porte canonique 100% au vert post-remédiation.
4. **Mise à jour du statut Obsidian & Archivage Physique (Post-Revue)** :
   - Mettre à jour l'en-tête du ticket : `**Statut :** ✅ Terminé` et cocher les critères d'acceptation.
   - **Déplacement physique obligatoire** : déplacer la note du ticket de `ankiforge_obsidian/Tickets/ticket-actif/` vers `ankiforge_obsidian/Tickets/Archives/` (ainsi que les spécifications associées). La racine `Tickets/` ne doit jamais comporter de fichier à plat.
   - Déplacer la carte dans `ankiforge_obsidian/Avancement du projet.md` vers `## ✅ Terminé (done)` en ajustant le lien vers `[[Tickets/Archives/<Nom>|<Titre>]]`.
   - Vérifier l'absence de fichiers fantômes résiduels de 0 octet à la racine de `Tickets/`.
   - Si la colonne `Terminé` dépasse 15 items, archiver les plus anciens dans `Archives - Tickets Terminés.md`.
   - **Sous-Dépôt Git Autonome** : `ankiforge_obsidian/` dispose de son propre dépôt Git ignoré par la racine. Ne jamais l'inclure dans un `git add` du projet principal ; proposer un commit dédié via `git -C ankiforge_obsidian`.
   - **Arrêt immédiat** (One-shot pass).

## When NOT to use this skill

- Ne pas utiliser pour cadrer une idée non formalisée → utiliser `/grill-with-docs`.
- Ne pas utiliser pour découper une spécification en plusieurs tickets → utiliser `/to-tickets`.
- Ne pas utiliser pour qualifier des retours bruts → utiliser `/triage`.
