"""
Script utilitaire de réparation et restauration d'un profil AnkiForge.
Restaure les NoteTypes (templates, schémas de champs, CSS), extrait l'intégralité
des fichiers médias via décompression Zstandard par flux, et remappe les contenus
de notes (de Field_1...Field_N vers les vrais noms de champs Anki).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import mimetypes
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

import zstandard as zstd

from ankiforge.database.base import db
from ankiforge.database.models import MediaModel, NoteModel, NoteTypeModel, NoteVersionModel
from ankiforge.services.cards.import_manager import ImportManager
from ankiforge.services.profile_manager import ProfileManager

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)-7s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("repair_profile")


def repair_profile(
    profile_name: str,
    colpkg_path: Path,
    env: str = "prod",
) -> dict[str, int]:
    """
    Répare un profil AnkiForge corrompu à partir de son fichier .colpkg d'origine.
    """
    if not colpkg_path.exists():
        raise FileNotFoundError(f"Fichier collection introuvable : {colpkg_path}")

    # 1. Configuration de l'environnement et du gestionnaire de profil
    profile_mgr = ProfileManager()
    if env == "prod":
        profile_mgr.profiles_dir = Path.home() / ".ankiforge" / "profiles"
    elif env == "dev":
        profile_mgr.profiles_dir = Path.home() / ".ankiforge-dev" / "profiles"

    db_path = profile_mgr.get_db_path(profile_name)
    media_dir = profile_mgr.get_media_dir(profile_name)

    if not db_path.exists():
        raise FileNotFoundError(f"Base de données du profil introuvable : {db_path}")

    media_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Démarrage de la réparation pour le profil '%s' (env: %s)", profile_name, env)
    logger.info("Base de données : %s", db_path)
    logger.info("Répertoire médias : %s", media_dir)

    # 2. Sauvegarde de sécurité de la base SQLite
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"ankiforge_backup_before_repair_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    logger.info("Sauvegarde préventive créée : %s", backup_path.name)

    # Connexion Peewee
    profile_mgr.switch_profile(profile_name)
    db.init(str(db_path))
    db.connect(reuse_if_open=True)

    # 3. Analyse du package pour récupérer les vrais modèles et médias
    logger.info("Analyse de l'archive source : %s ...", colpkg_path.name)
    im = ImportManager()

    temp_dir = tempfile.mkdtemp(prefix="ankiforge_repair_")
    temp_p = Path(temp_dir)
    media_count = 0
    notetypes_repaired = 0
    notes_remapped = 0

    try:
        with zipfile.ZipFile(colpkg_path, "r") as zf:
            zf.extractall(temp_p)

        # A. Décompression et extraction des médias
        raw_media_bytes = b""
        media_file = temp_p / "media"
        media_zstd = temp_p / "media.zstd"
        target_mf = media_file if media_file.exists() else (media_zstd if media_zstd.exists() else None)

        media_map: dict[str, str] = {}
        if target_mf and target_mf.exists():
            with open(target_mf, "rb") as mf:
                raw_media_bytes = mf.read()

            if raw_media_bytes.startswith(b"\x28\xb5\x2f\xfd"):
                try:
                    dctx = zstd.ZstdDecompressor()
                    with dctx.stream_reader(io.BytesIO(raw_media_bytes)) as reader:
                        raw_media_bytes = reader.read()
                    logger.info("Décompression Zstandard du fichier média réussie (%d octets)", len(raw_media_bytes))
                except Exception as z_err:
                    logger.warning("Erreur décompression Zstandard média : %s", z_err)

            try:
                text_cand = raw_media_bytes.decode("utf-8")
                if text_cand.strip().startswith("{"):
                    media_map = json.loads(text_cand)
            except Exception:
                pass

            if not media_map:
                media_map = im.parse_media_pb(raw_media_bytes)

        logger.info("%d entrées identifiées dans l'index média", len(media_map))

        # Copie physique et enregistrement en base des médias
        with db.atomic():
            for file_id, filename in media_map.items():
                src_file = temp_p / file_id
                if src_file.exists() and src_file.is_file():
                    dest_file = media_dir / filename
                    try:
                        shutil.copy2(src_file, dest_file)
                        sha256 = hashlib.sha256()
                        with open(dest_file, "rb") as f_in:
                            for chunk in iter(lambda: f_in.read(65536), b""):
                                sha256.update(chunk)
                        checksum = sha256.hexdigest()

                        mime_type, _ = mimetypes.guess_type(str(dest_file))
                        mime_type = mime_type or "application/octet-stream"

                        MediaModel.get_or_create(
                            checksum=checksum,
                            defaults={
                                "filename": filename,
                                "original_name": filename,
                                "mime_type": mime_type,
                            },
                        )
                        media_count += 1
                    except Exception as m_err:
                        logger.warning("Échec copie média '%s' (%s): %s", file_id, filename, m_err)

        logger.info("Extraction achevée : %d médias copiés et enregistrés", media_count)

        # B. Restauration des NoteTypes depuis collection.anki21b
        anki21b_path = temp_p / "collection.anki21b"
        sqlite_db = temp_p / "uncompressed.db"
        if anki21b_path.exists():
            dctx = zstd.ZstdDecompressor()
            with open(anki21b_path, "rb") as cf, open(sqlite_db, "wb") as uf:
                dctx.copy_stream(cf, uf)
        elif (temp_p / "collection.anki21").exists():
            sqlite_db = temp_p / "collection.anki21"
        elif (temp_p / "collection.anki2").exists():
            sqlite_db = temp_p / "collection.anki2"

        raw_models: dict[str, dict[str, Any]] = {}
        if sqlite_db.exists():
            s_conn = sqlite3.connect(str(sqlite_db))
            s_cur = s_conn.cursor()

            s_cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {r[0] for r in s_cur.fetchall()}

            if "notetypes" in tables:
                s_cur.execute("SELECT id, name, config FROM notetypes")
                for row in s_cur.fetchall():
                    mid, name, config_blob = row
                    field_names: list[str] = []
                    if "fields" in tables:
                        s_cur.execute("SELECT name FROM fields WHERE ntid=? ORDER BY ord", (mid,))
                        field_names = [f[0] for f in s_cur.fetchall()]

                    css_style = im.extract_pb_string(config_blob, 3) if config_blob else ""
                    tmpls: list[dict[str, str]] = []
                    if "templates" in tables:
                        s_cur.execute("SELECT name, config FROM templates WHERE ntid=? ORDER BY ord", (mid,))
                        for t_row in s_cur.fetchall():
                            t_name, t_config = t_row
                            qfmt = im.extract_pb_string(t_config, 1) if t_config else ""
                            afmt = im.extract_pb_string(t_config, 2) if t_config else ""
                            tmpls.append({"name": t_name, "qfmt": qfmt, "afmt": afmt})

                    raw_models[name] = {
                        "name": name,
                        "fields": field_names,
                        "templates": tmpls,
                        "css": css_style,
                    }
            s_conn.close()

        logger.info("%d modèles extraits de l'archive", len(raw_models))

        # Application des modèles réparés en base
        model_name_to_fields: dict[str, list[str]] = {}
        with db.atomic():
            for nt_name, m_info in raw_models.items():
                fields_list = m_info["fields"]
                tmpls_list = m_info["templates"]
                css_style = m_info["css"]
                model_name_to_fields[nt_name] = fields_list

                nt_obj = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_name)
                if nt_obj:
                    nt_obj.fields_schema = json.dumps(fields_list)
                    nt_obj.templates = json.dumps(tmpls_list, ensure_ascii=False)
                    if css_style:
                        nt_obj.css_style = css_style
                    nt_obj.save()
                    notetypes_repaired += 1
                else:
                    NoteTypeModel.create(
                        name=nt_name,
                        fields_schema=json.dumps(fields_list),
                        templates=json.dumps(tmpls_list, ensure_ascii=False),
                        css_style=css_style,
                    )
                    notetypes_repaired += 1

        logger.info("%d modèles NoteType mis à jour avec succès", notetypes_repaired)

        # C. Remapping des champs des notes (Field_1... -> vrais champs)
        logger.info("Remapping des champs des notes...")
        with db.atomic():
            for note in NoteModel.select().prefetch(NoteVersionModel):
                nt_name = note.note_type.name if note.note_type else ""
                expected_fields = model_name_to_fields.get(nt_name, [])
                if not expected_fields:
                    continue

                for ver in note.versions:
                    try:
                        content = json.loads(str(ver.content))
                    except Exception:
                        continue

                    keys = list(content.keys())
                    needs_remap = any(k.startswith("Field_") for k in keys) or (len(keys) == len(expected_fields) and keys != expected_fields)

                    if needs_remap:
                        values = list(content.values())
                        new_content: dict[str, str] = {}
                        for idx, val in enumerate(values):
                            f_name = expected_fields[idx] if idx < len(expected_fields) else f"Field_{idx + 1}"
                            new_content[f_name] = str(val)

                        ver.content = json.dumps(new_content, ensure_ascii=False)
                        ver.save()
                        notes_remapped += 1

        logger.info("%d versions de notes remappées avec succès", notes_remapped)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    summary = {
        "media_extracted": media_count,
        "notetypes_repaired": notetypes_repaired,
        "notes_remapped": notes_remapped,
    }
    logger.info("🎉 Réparation achevée avec succès : %s", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Réparation de profil AnkiForge suite à un import partiel.")
    parser.add_argument(
        "--profile",
        default="Environnement_de_travail_math_Ensimag",
        help="Nom du profil à réparer",
    )
    parser.add_argument(
        "--colpkg",
        default=str(Path.home() / "Downloads" / "collection-2026-09-05@08-55-34.colpkg"),
        help="Chemin vers le fichier .colpkg d'origine",
    )
    parser.add_argument(
        "--env",
        default="prod",
        choices=["prod", "dev"],
        help="Environnement cible (prod ou dev)",
    )
    args = parser.parse_args()

    repair_profile(
        profile_name=args.profile,
        colpkg_path=Path(args.colpkg),
        env=args.env,
    )


if __name__ == "__main__":
    main()
