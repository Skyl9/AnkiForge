# Checklist Canonique de Revue de Code — AnkiForge

Cette checklist constitue la référence opérationnelle pour l'**Axe 1 — Standards** de la compétence `code-review`.

---

## 1. Typage Statique Strict & Python 3.12+ (Règle 2)
- [ ] 100 % des fonctions, méthodes et attributs publics de `src/ankiforge/` sont intégralement typés (`disallow_untyped_defs = true`).
- [ ] Syntaxe moderne Python 3.12+ : unions `X | Y` (bannissement d'`Optional` et `Union`), types natifs `list[T]`, `dict[K, V]`, `tuple[T, ...]` (bannissement des imports `List`, `Dict`, `Tuple` depuis `typing`).
- [ ] Aucun `disable_error_code` global ajouté dans `pyproject.toml`.
- [ ] Utilisation adéquate des types stubs du projet (`types-peewee`, `types-requests`, `types-markdown`).

## 2. Logging Asynchrone & Règle T20 (Règle 3)
- [ ] **Zéro `print()`** dans `src/ankiforge/` (application stricte de Ruff `T20`).
- [ ] Instanciation canonique : `logger = logging.getLogger(__name__)`.
- [ ] Niveau de log sémantique approprié : `DEBUG` pour le traçage verbeux, `INFO` pour les jalons métier, `WARNING` pour les replis tolérés, `ERROR` pour les défaillances capturées, `CRITICAL` pour les blocages majeurs.
- [ ] Zéro secret interpolé en clair : clés d'API (`sk-*`, `AIza*`), tokens Bearer et identifiants doivent être anonymisés ou filtrés via `SecretRedactionFilter`.

## 3. Tests Headless Qt, Isolation & Mocks (Règles 4 & 5)
- [ ] Tests compatibles exécution headless : `QT_QPA_PLATFORM=offscreen`, `QTWEBENGINE_DISABLE_SANDBOX=1`, `ANKIFORGE_MOCK_WEBENGINE=1`.
- [ ] Zéro snapshot visuel en assertion de test : tester la logique métier, les signaux, les slots et l'état des widgets via `pytest-qt` (`qtbot`).
- [ ] Nettoyage des widgets instanciés via la fixture `cleanup_qt_widgets`.
- [ ] Isolation BDD : base de données de test en mémoire partagée SQLite (`file:memdb_test_...?mode=memory&cache=shared`).
- [ ] **100 % de Mocks LLM & RAG** : aucun appel réseau externe, aucun appel LLM réel, aucun démon local requis en test.

## 4. Internationalisation Qt Linguist (ADR 0013 / Règle 7)
- [ ] Chaîne utilisateur sous `QObject` : `self.tr("…")` ; hors `QObject` : `tr("…")`.
- [ ] **Interdiction stricte de `tr(f"…")`** ou `self.tr(f"…")` (empêche l'extraction dans le catalogue de traduction).
- [ ] Paramétrage avec marqueurs Qt Linguist : `tr("Élément : %1 sur %2", actuel, total)`.
- [ ] Langue source : français (`SOURCE_LANGUAGE = "fr"`).
- [ ] Zéro `tr()` au chargement de module : ne jamais figer de libellé traduit dans une constante globale avant l'appel d'`install_translator()`.

## 5. Design System & UI Tokens (DESIGN.md / Règle 8)
- [ ] **Zéro couleur codée en dur** (ex. `#ffffff`, `rgb(...)`) dans le code applicatif ou les feuilles de style inline.
- [ ] Utilisation exclusive des jetons sémantiques `DesignTokens` / `ThemeProfile` injectés par `StyleEngine.generate_stylesheet()`.
- [ ] Respect de la compatibilité avec les 12 thèmes et les 4 layouts (`ide`, `macos`, `dashboard`, `glassmorphism`).

## 6. Base de Données & Peewee ORM
- [ ] Intégrité référentielle : toute `ForeignKeyField` déclare une stratégie `on_delete` explicite (`CASCADE` ou `SET NULL`).
- [ ] Atomicité des transactions : les écritures interdépendantes sont encapsulées dans `with db.atomic():`.
- [ ] Requêtes N+1 : utilisation systématique de `.prefetch()` ou `.join()` lors du parcours de relations parent/enfant.
- [ ] Couverture d'index sur les colonnes filtrées ou ordonnées fréquemment.

## 7. Architecture Métier & ADRs Clés
- [ ] **ADR 0009 (Provenance par section)** : Le lien de provenance s'ancre sur le couple (document, fil d'Ariane `heading_path`), avec résolution à 4 paliers (`exact → section → page → lexical`).
- [ ] **ADR 0010 (Délimitation & Exclusion non destructive)** : Une exclusion est une règle de périmètre (`utils/region_address.py`), jamais une suppression physique. `DocumentRepository` est l'unique décideur (`is_region_excluded`, `set_region_excluded`).
- [ ] **ADR 0043 (Serveur MCP Persistant & 2-Phase Commit)** : Mutation via staged patches (`prepare_*` $\rightarrow$ `commit_*`), validation humaine systématique, pas d'écriture directe sauvage en BDD.

## 8. Complexité Cyclomatique & Risque (Score CRAP)
- [ ] Le score CRAP ($CC^2 \times (1 - \text{cov})^3 + CC$) sur le code modifié reste $\le 25$.
- [ ] Toute fonction nouvellement introduite avec $CRAP > 25$ doit soit être simplifiée (réduction de complexité cyclomatique), soit recevoir des tests unitaires ciblés augmentant sa couverture.
