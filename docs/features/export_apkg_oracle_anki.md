# Export `.apkg` & banc oracle Anki

Cette page consigne l'**étude préalable** qui fonde l'export `.apkg` de la Forge et le banc
de tests oracle adossé au moteur Anki officiel (ADR 0022). Elle décrit les invariants du
format, le contrat d'import headless de la lib `anki` et les garanties vérifiées.

## 1. Frontière : contenu, jamais ordonnancement

`ExportManager` produit des paquets `.apkg` qui transportent le **contenu** :

- notes, valeurs de champs, tags ;
- types de note (champs, gabarits recto/verso, CSS) ;
- hiérarchie des paquets (`Parent::Enfant`) ;
- médias (images, sons TTS) ;
- drapeaux Anki 1-7 et état suspendu.

L'**ordonnancement** — date d'échéance (`due`), facteur de facilité, journal de révision
(`revlog`), paramètres FSRS/SM-2 — relève **exclusivement d'Anki** (ADR 0020, ADR 0022).
La Forge ne le modélise, ne le calcule ni ne le reconstitue : les cartes exportées
redémarrent leur flux dans Anki. Aucune colonne n'est ajoutée, aucune migration n'est requise.

## 2. Invariants du format Anki 2.1.x

Un `.apkg` est une archive ZIP contenant :

| Entrée | Rôle |
| --- | --- |
| `collection.anki2` | Base SQLite de la collection (schéma historique `ver = 11`) |
| `media` | JSON `{ "<clé numérique>": "<nom de fichier réel>" }` |
| `0`, `1`, … | Octets bruts des médias, un fichier par clé numérique |

Les versions récentes d'Anki acceptent également `collection.anki21` / `collection.anki21b`
(compressé zstd) et un manifeste média protobuf ; l'export de la Forge reste au format
classique universellement lisible.

### Table `col`

Ligne unique portant les métadonnées de collection. En schéma 11, `models`, `decks` et
`dconf` y sont stockés en **JSON** :

```sql
col(id, crt, mod, scm, ver, dty, usn, ls, conf, models, decks, dconf, tags)
```

- `ver = 11` pour le format genanki ;
- `models` : objet JSON indexé par identifiant de type de note (champs, gabarits, CSS) ;
- `decks` : objet JSON indexé par identifiant de paquet (nom, configuration).

### Table `notes`

```sql
notes(id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
```

- `guid` : identité durable de la note (déduplication à l'import) ;
- `mid` : identifiant du type de note ;
- `flds` : valeurs de champs concaténées par le séparateur `U+001F` ;
- `tags` : tags séparés par des espaces, encadrés d'espaces (`" t1 t2 "`).

### Table `cards`

```sql
cards(id, nid, did, ord, mod, usn, type, queue, due, ivl, factor,
      reps, lapses, left, odue, odid, flags, data)
```

- `nid` : note parente ; `did` : paquet ; `ord` : index du gabarit ;
- `queue = -1` : carte suspendue ;
- `flags` : drapeau de couleur 1-7 (0 = aucun) ;
- `ivl`, `factor`, `reps`, `lapses`, `type`, `due`, `left`, `odue`, `odid`, `data` : état
  d'ordonnancement — **écrits à zéro** par la Forge (contenu seul).

### Cartes cloze

Un type de note cloze (`type = 1`) dérive **une carte par numéro de trou**. Un champ
contenant `{{c1::…}}` et `{{c2::…}}` produit donc **deux cartes** (`ord` 0 et 1).

## 3. Contrat d'import headless de la lib `anki`

L'oracle s'appuie sur le backend officiel Rust via les enveloppes Python de la lib `anki`
(dépendance de **développement** uniquement, `dependency-groups.dev`) :

```python
from anki.collection import Collection, ImportAnkiPackageOptions, ImportAnkiPackageRequest

col = Collection(str(target_db_path))  # ouvre (ou crée) une collection locale
col.import_anki_package(
    ImportAnkiPackageRequest(
        package_path=str(apkg_path),
        options=ImportAnkiPackageOptions(with_scheduling=True),  # seule voie matérialisant drapeaux 1-7 et suspension
    )
)
```

- L'ouverture de la collection et l'import échouent bruyamment sur un paquet corrompu ;
- le contrôle d'intégrité SQLite non réparateur s'obtient via `col.db.scalar("pragma integrity_check")` (`"ok"` attendu) ;
- `col.media.check()` signale les médias manquants non référencés sans rien réparer ;
- le backend est un binaire local (`wheels abi3` précompilées) : **zéro réseau en test**.

L'oracle est chargé sous `pytest.importorskip("anki")` et marqué `slow` : la suite rapide
reste exécutable sans la dépendance lourde.

## 4. Invariants garantis par l'oracle

Le banc (`tests/integration/test_anki_export_oracle.py`) certifie, sur les paquets produits
par la Forge :

1. **Ouverture sans corruption** — le moteur officiel ouvre le paquet ; contrôle d'intégrité sans réparation.
2. **Fidélité de contenu** — comptes notes/cartes exacts (cloze `c1`/`c2` → N cartes),
  champs/gabarits/CSS des types de note, hiérarchie des paquets, `guid` stables sans doublon.
- **Médias** : chaque média référencé est présent et **identique par MD5**.
- **Drapeaux & suspension** : `flags` 1-7 et `queue = -1` reportés fidèlement.
- **Non-mutation** : importer un paquet n'altère pas une carte existante non modifiée.
- **KaTeX** : le balisage `\(...\)` / `\[...\]` n'est pas corrompu (jamais de rendu visuel asserté).

## 5. Ce que l'oracle ne certifie pas

La **préservation de l'ordonnancement**. Une reprise fidèle du flux de révision resterait
un chantier distinct, adossé à une révision explicite d'ADR 0020 ; elle n'est pas un
prérequis de l'export actuel.
