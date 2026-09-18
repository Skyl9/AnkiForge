# Règles Import / Export / Médias — Synchronisation Anki

Conventions et invariants de `src/ankiforge/services/cards/` pour importer/exporter des paquets Anki
sans perte de données et sans doublons.

---

## 1. Invariants fondamentaux

- **IDs stables** : `ExportManager.generate_stable_id(text)` produit un ID déterministe → un export
  puis un ré-import N'ENGENDRE pas de doublon (idempotence).
- **Atomicité** : tout import est un commit unique dans `db.atomic()` ; toute erreur → rollback intégral.
- **Collations** : `_register_anki_collations` enregistre les collations Anki (insensibilité casse/accents)
  avant toute requête sur les tables importées.
- **Isolation profils** : chaque profil a sa BDD SQLite et son dossier médias
  (`~/.ankiforge/profiles/<name>/`). Ne jamais croiser les données entre profils.

## 2. Import (.apkg / .colpkg)

Workflow : `analyze_archive()` → décision humaine éventuelle → `commit_import()`.

| Étape | Classe / Méthode | Rôle |
|---|---|---|
| Analyse | `ImportManager.analyze_archive(path, progress_callback)` | `ImportAnalysisResult` : types de colonnes, modèles, cartes neuves vs MAJ, conflits |
| Conflit | `ConflictItem` | Représente un conflit note existante vs entrante |
| Diff | `compute_field_diffs(local, incoming)` | Diff champ par champ pour décision de merge |
| Évaluation | `_evaluate_existing_note(...)` | Décide conserver / fusionner / écraser |
| Protobuf médias | `parse_media_pb(data)` / `extract_pb_string(data, field)` | Extraction des fichiers `_media` du paquet |
| Commit | `commit_import(...)` | Insertion transactionnelle (une seule atomic block) |
| Modèles | `_validate_model_structure(model_id, model)` | Valide la cohérence des note-types avant insertion |
| Txt | `_analyze_txt(txt_path)` | Analyse des fichiers `.txt` d'Anki (séparateurs) |

**Règles de merge (référence aux tests)** :
- `tests/services/cards/test_import_rule11_and_merge.py` : règle 11 — ne pas dupliquer une note
  existante à contenu identique ; fusion dans `collection` existante.
- `tests/services/cards/test_import_cards_and_fsrs.py` : préservation FSRS (due, interval, état
  de la mémoire) lors de la ré-importation.

## 3. Export (.apkg)

| Étape | Classe / Méthode | Rôle |
|---|---|---|
| Export | `ExportManager.export_deck(deck_id, output_path, export_only_new=True)` | .apkg via genanki |
| Carte | `AnkiForgeCard(ord, suspend=False, flags=0)` | Contrôle suspend/flags à l'écriture |
| Écriture | `AnkiForgeCard.write_to_db(db_cursor, ...)` | Enregistrement dans la BDD Anki du paquet |
| JSON | `AnkiForgeCard` attrs complets dans `export_deck` | Export préservant FSRS (`due`) et la suspension |

**Vérification d'usage** : exporter avec `export_only_new=True` par défaut ; re-importer le paquet
produit et contrôler qu'aucune carte n'est dupliquée.

## 4. Médias

| Méthode | Rôle | Destructif |
|---|---|---|
| `MediaManager._calculate_md5(file_path)` | Empreinte MD5 (déduplication) | non |
| `store_document_source(file_path)` | Enregistre le fichier source du profil | non |
| `store_media_bytes(data, name, mime_type)` | Stocke un média binaire dédupliqué | non |
| `process_extracted_folder(source_folder, markdown_content)` | Intègre dossier extrait (Marker) + rebase liens | non |
| `clean_orphaned_media()` | Supprime médias non référencés | **OUI** → demande explicite |
| `decompress_all_zstd_media(profile_name)` | Restaure les médias compressés zstd | non |

## 5. Duplication

- `DuplicateManager.find_duplicates(deck_id)` → triels `(NoteModel_local, stats, NoteModel_dup, stats, score)`
  (score de similarité, `strip_html` pour comparer sans balises).

## 6. Validation

```bash
uv run pytest tests/services/cards/                    # import/export/médias/dups
uv run pytest tests/services/cards/test_import_media.py
uv run pytest tests/services/cards/test_export_manager.py
```
