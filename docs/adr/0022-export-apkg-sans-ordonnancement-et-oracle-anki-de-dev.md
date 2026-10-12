# Export `.apkg` sans fabrication d'ordonnancement et oracle Anki en dépendance de développement

**Statut :** accepté

L'export bâti par `ExportManager` transporte le **contenu** — notes, types de note, gabarits, CSS, médias, drapeaux 1-7 et suspension — et **jamais l'ordonnancement**. Les cartes exportées entrent dans Anki dans leur flux initial ; seul Anki planifie. Pour vérifier la non-corruption et la fidélité de ces paquets, un **oracle** s'appuie sur le backend officiel `anki` en dépendance de **développement** uniquement, exécuté en headless.

## Le défaut

- `export_manager.py:88` accepte un argument `format_type='apkg'|'colpkg'` mais **ne l'utilise jamais** : la méthode termine toujours par `genanki.Package(...).write_to_file()`, c'est-à-dire un `.apkg` (`export_manager.py:407-411`).
- `AnkiForgeCard.write_to_db` (`export_manager.py:41-65`) écrit en dur `ivl=0`, `factor=0`, `reps=0`, `lapses=0`, `type=0`, `due=0`, `left=0`, `odue=0`, `odid=0`, `data=""`. Seuls `flags` et la suspension (`queue=-1`) sont réels.
- Le dialogue d'export propose un filtre « Collections Anki (*.colpkg) » (`export_dialog.py:280`) tout en forçant le suffixe `.apkg` (`export_dialog.py:284-285, 302-303`) : l'interface **promet un artefact qu'elle ne produit pas**.
- ADR 0020 a déjà acté que la Forge ne modélise ni date d'échéance, ni `revlog`, ni état mémoire FSRS — et que l'import s'en tient à `ivl/reps/lapses/flags/suspension` (`import_manager.py:756-765, 1077-1081`).
- Aucun test n'ouvre le paquet produit par le moteur officiel : la sortie de `genanki` n'est inspectée que par des assertions ad hoc sur le zip et le SQLite.

## Options considérées

1. **Report verbatim de l'ordonnancement** (stocker `due`, `factor`, `type`, `left`, `odue`, `odid`, `data`, + `col.crt`, `revlog`, `col.conf`/`decks.conf` ; table satellite ; migration ; véritable écrivain `.colpkg`) : **rejeté**. La Forge est un IDE d'*authoring*, pas un ordonnanceur. Posséder l'état de révision la ferait diverger d'Anki dès la première révision, et rouvrirait ADR 0020 (importer l'état FSRS réel).
2. **Report partiel des compteurs** (`ivl/reps/lapses` seuls, sans `due`) : **rejeté**. Fabrique un état mi-vol — une carte « revue » sans échéance — qu'Anki peut réinitialiser ou mal interpréter à la première révision.
3. **Contenu seul + oracle sur le moteur officiel** : **retenu**.

## Conséquences

- **Frontière nette.** La Forge *reporte* zéro ordonnancement ; l'export est un canal de contenu, jamais d'ordonnancement. Aucune nouvelle colonne, aucune migration.
- **Les mensonges de l'interface sont retirés.** L'argument `format_type` et l'option `.colpkg` du dialogue d'export disparaissent : l'interface cesse de nommer une collection qu'elle ne produit pas. Un `.colpkg` authentique, s'il est un jour voulu, sera un ticket successeur.
- **Oracle `anki` confiné au développement.** Dépendance déclarée dans `dependency-groups.dev` (jamais d'exécution), chargée sous `pytest.importorskip("anki")` et marquée `slow`. Le backend est un binaire local (wheels `abi3` précompilées), donc compatible avec la règle « zéro réseau en test ».
- **Collection témoin versionnée.** Une fixture `.apkg` sous `tests/fixtures/` est ouverte par l'oracle : déterministe, hors-ligne, sans génération en CI.
- **Invariants garantis par l'oracle** : ouverture sans corruption (contrôle d'intégrité du backend sans réparation), comptes notes/cartes exacts (cloze `c1/c2` → N cartes), champs/gabarits/CSS des types de note, hiérarchie des paquets, `guid` stables et sans doublon, médias liés et identiques (MD5), drapeaux 1-7 et suspension reportés, **non-mutation** d'une carte existante non modifiée lors d'un import, et non-corruption du balisage KaTeX (jamais de rendu visuel : `QT_QPA_PLATFORM=offscreen`).
- **Ce que l'oracle ne certifie pas** : la préservation de l'ordonnancement. Une reprise fidèle du flux (option 1) reste un chantier distinct, adossé à une révision explicite d'ADR 0020 ; elle n'est pas un prérequis de l'export actuel.
