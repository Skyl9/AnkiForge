"""
Gestionnaire de persistance et curation de notes pour AnkiForge.
Fournit les utilitaires d'approbation, suppression et délégation d'importation vers ImportManager.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable, List, Optional

from ankiforge.database.models import (
    NoteModel,
    NoteVersionModel,
    db,
)
from ankiforge.services.cards.import_manager import ImportManager

logger = logging.getLogger(__name__)


class StoreManager:
    """Gestionnaire de persistance et curation de notes."""

    def __init__(self) -> None:
        self.import_manager = ImportManager()

    def store_collection(
        self,
        collection_path: str | Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Délègue l'ingestion de paquets ou fichiers texte vers ImportManager."""
        analysis = self.import_manager.analyze_archive(collection_path, progress_callback=progress_callback)
        self.import_manager.commit_import(analysis, progress_callback=progress_callback)

    @classmethod
    def import_apkg(
        cls,
        collection_path: str | Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Alias de classe pour importer une collection ou paquet (.apkg, .colpkg, .txt)."""
        instance = cls()
        instance.store_collection(collection_path, progress_callback=progress_callback)

    def handle_apkg(
        self,
        apkg_path: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Méthode de compatibilité appelant ImportManager."""
        self.store_collection(apkg_path, progress_callback=progress_callback)

    def handle_txt(
        self,
        txt_path: Path,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Méthode de compatibilité appelant ImportManager."""
        self.store_collection(txt_path, progress_callback=progress_callback)

    def approve_notes(self, note_ids: List[int]) -> None:
        """Approuve une liste de notes en mettant leur statut à 'new'."""
        with db.atomic():
            NoteModel.update(status="new").where(NoteModel.id.in_(note_ids)).execute()
        logger.info("Approbation de %d notes (statut basculé à 'new').", len(note_ids))

    def delete_notes(self, note_ids: List[int]) -> None:
        """Supprime une liste de notes de la base de données."""
        with db.atomic():
            NoteModel.delete().where(NoteModel.id.in_(note_ids)).execute()
        logger.info("Suppression définitive de %d notes en base de données.", len(note_ids))

    def apply_linter_suggestion(self, note_id: int, suggestion: dict) -> None:
        """Applique les suggestions du linter à une note via StoreManager."""
        with db.atomic():
            note = NoteModel.get_by_id(note_id)
            active_version = NoteVersionModel.get_or_none(note=note, is_active=True)
            if active_version:
                content = json.loads(active_version.content)
                content.update(suggestion)
                note.add_version(content, source="Linter AI")
                logger.info("Correction Linter IA appliquée sur la note ID=%d (nouvelle version générée).", note_id)
