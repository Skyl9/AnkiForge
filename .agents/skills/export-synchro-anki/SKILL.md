---
name: export-synchro-anki
description: >
  Expert en import/export Anki et synchronisation pour AnkiForge. Analyse, importe et fusionne des
  paquets .apkg/.colpkg (règles de merge intelligentes, gestion des conflits), exporte des decks en
  .apkg à IDs stables (FSRS, suspend, flags), et administre les médias (déduplication MD5, compression
  zstd, nettoyage des orphelins). Intervient sur src/ankiforge/services/cards/ (ImportManager,
  ExportManager, MediaManager, DuplicateManager, CardModelIO) et l'isolation par profil.
  Use when the user asks to "importer un .apkg", "importer un .colpkg", "exporter un deck",
  "exporter un paquet anki", "fusionner des cartes", "résoudre des conflits d'import", "médias anki",
  "médias orphelins", "compresser les médias", "synchroniser avec Anki", "notes dupliquées",
  "measured anki flags", or needs import/export or media handling for Anki.
---

# 🔁 Export & Synchronisation Anki — AnkiForge

En tant qu'**Expert Synchronisation Anki**, tu importes, fusionnes et exportes des paquets Anki sans
perte de données, en respectant l'isolation par profil et l'atomicité des commits.

> **Référence** : `references/regles_import_export.md` — conventions de formats, merge et médias.
> Code source : `src/ankiforge/services/cards/`.

## 1. Périmètre & Principes

- **Périmètre** : `services/cards/` (`import_manager`, `export_manager`, `media_manager`,
  `duplicate_manager`, `card_model_io`, `album_service`, `store_manager`) + isolation profils
  (`~/.ankiforge/profiles/<name>/`, médias inclus).
- **Principes** : import **transactionnel et réversible** (`db.atomic()`), **IDs stables** pour éviter
  les doublons lors de ré-imports, jamais de paquet corrompu, aucune modification d'une base réelle
  sans demande explicite.

## 2. Importer un paquet (.apkg / .colpkg)

1. `ImportManager().analyze_archive(path, progress_callback)` → `ImportAnalysisResult` (types de
   colonnes, modèles, cartes neuves vs mises à jour, conflits `ConflictItem`).
2. **Analyser les conflits** : les notes existantes sont évaluées via `_evaluate_existing_note()`;
   décider de fusionner ou d'écraser champ par champ (`compute_field_diffs`). En cas de risque de
   perte → remonter à l'utilisateur avant commit.
3. **Commit** : `commit_import(...)` dans un unique `db.atomic()` (rollback si souci). Veiller aux
   collations (`_register_anki_collations`) et à la parse du protobuf média (`parse_media_pb`).
4. **Valider** : ré-importer ou comparer par diff de champs ; `uv run pytest tests/services/cards/`.

## 3. Exporter un deck

1. `ExportManager().export_deck(deck_id, output_path, export_only_new=True)` → `.apkg` (genanki),
   IDs stables via `generate_stable_id()` ; cartes suspendues/flags via `AnkiForgeCard(suspend, flags)`.
2. Vérifier qu'un **ré-import** du paquet n'entraîne **aucun doublon** (ids stables ⇒ idempotent).
3. `CardModelIO` : notes types exportables en JSON/bundle pour réutilisation entre profils.

## 4. Médias

- Stockage dédupliqué MD5 : `store_media_bytes()` / `store_document_source()`.
- Nettoyage : `clean_orphaned_media()` — **destructif**, uniquement sur demande explicite.
- Compression : `decompress_all_zstd_media(profile_name)` pour migrer/restaurer un profil compressé.

## 5. Doublons & référence

- `DuplicateManager.find_duplicates(deck_id)` : détection et consolidation des notes dupliquées
  (match par similarité de contenu, `strip_html`).

## Règles & Garde-fous

- **Atomicité** : un import = un `db.atomic()` ; jamais de commit partiel en cas d'erreur à mi-chemin.
- **Isolation profils** : ne jamais mélanger médias/notes entre deux profils (vérifier `profile_name`).
- **Tests** : toutes les opérations LLM/API sont mockées ; un import/export s'exécute sur un profil
  de test isolé (`file:memdb...` / profil temporaire), jamais sur la BDD utilisateur.

## ⛔ Ne PAS utiliser ce skill si...

- Le besoin est le **parsing/extraction de contenus** (PDF/YouTube/web/audio → Markdown) → `ingestion-multimedia`.
- Le besoin est une **migration de modèle Peewee / BDD** → `peewee-expert`.
- Le besoin est de **mettre à jour la doc / les skills** → `mise-a-jour-metadonnees`.
- Le besoin est une **modification d'UI** (vues d'import/export) → audit UI / composants PySide6.
- L'utilisateur veut créer des **semantic chunks pour le RAG** → `ingestion-multimedia` + pipeline RAG.
