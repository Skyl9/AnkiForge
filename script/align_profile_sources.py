#!/usr/bin/env python3
"""
Script utilitaire d'alignement intelligent et de synchronisation des documents et médias.
Permet :
1. De copier des documents de cours d'un profil source vers un profil cible (ex: default -> Environnement_de_travail_math_Ensimag).
2. D'exécuter l'alignement automatique des fiches Anki avec les fragments des cours (NoteChunkLinkModel).
3. De réparer les médias manquants en copiant les fichiers disponibles entre profils.

Usage:
    uv run python script/align_profile_sources.py [--profile <nom>] [--copy-from <nom>]
"""

import argparse
import logging
import sys
from pathlib import Path

# Ajouter src/ au sys.path si nécessaire
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir / "src"))

# ruff: noqa: E402
from ankiforge.database.models import DocumentModel, NoteModel, db, init_db
from ankiforge.services.audit.coverage_alignment_service import CoverageAlignmentService
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.utils.paths import get_profile_dir

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("align_profile_sources")


def main() -> None:
    parser = argparse.ArgumentParser(description="Alignement intelligent fiches-documents et synchronisation médias.")
    parser.add_argument("--profile", "-p", default="default", help="Profil cible à traiter (ex: default, Environnement_de_travail_math_Ensimag)")
    parser.add_argument("--copy-from", "-c", default=None, help="Profil source depuis lequel copier les documents manquants")
    args = parser.parse_args()

    target_prof = args.profile
    src_prof = args.copy_from

    pm = ProfileManager()
    profiles = pm.list_profiles()

    if target_prof not in profiles:
        logger.error("Le profil cible '%s' n'existe pas dans %s", target_prof, profiles)
        sys.exit(1)

    # 1. Copie éventuelle des documents depuis le profil source
    if src_prof:
        if src_prof not in profiles:
            logger.error("Le profil source '%s' n'existe pas dans %s", src_prof, profiles)
            sys.exit(1)

        logger.info("--- Copie des documents de '%s' vers '%s' ---", src_prof, target_prof)
        src_db = pm.get_db_path(src_prof)
        import sqlite3

        con = sqlite3.connect(src_db)
        cur = con.cursor()
        src_docs = cur.execute("SELECT id, title FROM documentmodel ORDER BY id").fetchall()
        con.close()

        # Initialiser la DB cible
        target_db_path = pm.get_db_path(target_prof)
        if not db.is_closed():
            db.close()
        db.init(str(target_db_path))
        init_db()

        for doc_id, doc_title in src_docs:
            existing = DocumentModel.get_or_none(DocumentModel.title == doc_title)
            if existing:
                logger.info("Document '%s' déjà présent dans le profil cible.", doc_title)
            else:
                logger.info("Copie du document '%s' (ID: %d)...", doc_title, doc_id)
                CoverageAlignmentService.copy_document_from_profile(src_prof, target_prof, doc_id)

    # 2. Basculement sur le profil cible et alignement
    target_db_path = pm.get_db_path(target_prof)
    if not db.is_closed():
        db.close()
    db.init(str(target_db_path))
    init_db()

    total_notes = NoteModel.select().count()
    docs = list(DocumentModel.select())
    logger.info("=== Alignement du profil '%s' (%d notes, %d documents) ===", target_prof, total_notes, len(docs))

    if not docs:
        logger.warning("Aucun document trouvé dans '%s'.", target_prof)
        return

    for doc in docs:
        logger.info("Traitement de '%s' (type: %s)...", doc.title, doc.file_type)
        res = CoverageAlignmentService.align_document(doc.id, min_overlap=2)
        matched = res.get("matched_notes", 0)
        total_cards = res.get("total_cards", 0)
        covered = res.get("covered_chunks", 0)
        total_c = res.get("total_chunks", 0)
        pct = res.get("coverage_pct", 0.0)
        logger.info("  -> %d cartes liées (%d totales), %d/%d sections couvertes (%.1f%%)", matched, total_cards, covered, total_c, pct)

    # 3. Synchronisation des médias manquants depuis les autres profils
    logger.info("=== Vérification et synchronisation des médias pour '%s' ===", target_prof)
    target_media_dir = get_profile_dir(target_prof) / "media"
    target_media_dir.mkdir(parents=True, exist_ok=True)

    import sqlite3

    con = sqlite3.connect(target_db_path)
    cur = con.cursor()
    # Vérifier les images référencées dans les cartes
    import re
    import shutil

    missing_found = 0
    copied_from_other = 0

    for row in cur.execute("SELECT content FROM noteversionmodel WHERE is_active = 1").fetchall():
        content = row[0]
        imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content)
        sounds = re.findall(r"\[sound:([^\]]+)\]", content)
        for media_ref in imgs + sounds:
            target_file = target_media_dir / media_ref
            if not target_file.exists():
                missing_found += 1
                # Chercher dans les autres profils
                for p_other in profiles:
                    if p_other == target_prof:
                        continue
                    other_cand = get_profile_dir(p_other) / "media" / media_ref
                    if other_cand.exists():
                        shutil.copy2(other_cand, target_file)
                        copied_from_other += 1
                        logger.info("  Média récupéré depuis '%s' : %s", p_other, media_ref)
                        break

    con.close()
    logger.info("Vérification terminée : %d médias manquants analysés, %d restaurés depuis d'autres profils.", missing_found, copied_from_other)
    logger.info("✅ Alignement et maintenance terminés avec succès pour le profil '%s' !", target_prof)


if __name__ == "__main__":
    main()
