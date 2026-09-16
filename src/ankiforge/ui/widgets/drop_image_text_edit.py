# src/ankiforge/ui/widgets/drop_image_text_edit.py
import logging
import os
import shutil
import uuid
from pathlib import Path

from PySide6.QtCore import QMimeData, QObject, QRunnable, QThreadPool, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QTextEdit, QWidget

from ankiforge.utils.paths import get_media_dir

logger = logging.getLogger(__name__)


class _CopySignals(QObject):
    """Signals émis depuis le worker de copie d'image hors thread principal."""

    done = Signal(str)  # émet new_name une fois la copie terminée
    failed = Signal(str, str)  # émet (new_name, message_erreur)


class _ImageCopyWorker(QRunnable):
    """
    Worker léger (QRunnable) qui exécute la copie de fichier image dans QThreadPool,
    hors du thread Qt principal, pour éviter tout gel de l'interface.
    """

    def __init__(self, src: str, dest: Path, new_name: str) -> None:
        super().__init__()
        self._src = src
        self._dest = dest
        self._new_name = new_name
        self.signals = _CopySignals()

    @Slot()
    def run(self) -> None:
        try:
            shutil.copy2(self._src, self._dest)
            self.signals.done.emit(self._new_name)
        except Exception as exc:
            logger.warning("Échec copie image vers média dir (%s) : %s", self._dest, exc)
            self.signals.failed.emit(self._new_name, str(exc))


class _ImageSaveWorker(QRunnable):
    """
    Worker léger (QRunnable) qui sauvegarde une QImage sur disque hors thread principal.
    Utilisé pour le Ctrl+V d'une capture d'écran ou d'une image du presse-papier.
    """

    def __init__(self, image: QImage, dest: Path, new_name: str) -> None:
        super().__init__()
        self._image = image
        self._dest = dest
        self._new_name = new_name
        self.signals = _CopySignals()

    @Slot()
    def run(self) -> None:
        try:
            self._image.save(str(self._dest))
            self.signals.done.emit(self._new_name)
        except Exception as exc:
            logger.warning("Échec sauvegarde image presse-papier (%s) : %s", self._dest, exc)
            self.signals.failed.emit(self._new_name, str(exc))


class DropImageTextEdit(QTextEdit):
    """
    Un éditeur de texte brut qui intercepte les images (Drag&Drop et Ctrl+V)
    et écrit automatiquement la balise HTML correspondante.
    La copie/sauvegarde de fichier est déportée dans QThreadPool (non-bloquante).
    """

    image_inserted = Signal(str)
    image_failed = Signal(str, str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._active_workers: list[QRunnable] = []

    def _insert_img_tag(self, new_name: str, worker: QRunnable | None = None) -> None:
        """Insère la balise <img> dans le curseur courant — appelé depuis le thread Qt."""
        if worker is not None and worker in self._active_workers:
            self._active_workers.remove(worker)
        self.textCursor().insertText(f'<img src="{new_name}">\n')
        self.image_inserted.emit(new_name)

    def _on_copy_failed(self, new_name: str, err: str, worker: QRunnable | None = None) -> None:
        if worker is not None and worker in self._active_workers:
            self._active_workers.remove(worker)
        logger.error("Impossible de copier l'image '%s' dans le répertoire média : %s", new_name, err)
        self.image_failed.emit(new_name, err)

    def insertFromMimeData(self, source: QMimeData) -> None:
        media_dir = get_media_dir()
        media_dir.mkdir(parents=True, exist_ok=True)

        inserted_image = False

        # 1. Cas : Fichier image glissé-déposé
        if source.hasUrls():
            for url in source.urls():
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    ext = os.path.splitext(file_path)[1].lower()

                    if ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]:
                        new_name = f"img_{uuid.uuid4().hex[:8]}{ext}"
                        dest_path = media_dir / new_name

                        worker = _ImageCopyWorker(file_path, dest_path, new_name)
                        worker.signals.done.connect(lambda name, w=worker: self._insert_img_tag(name, w))
                        worker.signals.failed.connect(lambda name, err, w=worker: self._on_copy_failed(name, err, w))
                        self._active_workers.append(worker)
                        QThreadPool.globalInstance().start(worker)
                        inserted_image = True

            if inserted_image:
                return

        # 2. Cas : Ctrl+V d'une image (Presse-papier / Capture d'écran)
        if source.hasImage():
            image = source.imageData()
            if isinstance(image, QImage):
                new_name = f"img_{uuid.uuid4().hex[:8]}.png"
                dest_path = media_dir / new_name

                worker_save = _ImageSaveWorker(image, dest_path, new_name)
                worker_save.signals.done.connect(lambda name, w=worker_save: self._insert_img_tag(name, w))
                worker_save.signals.failed.connect(lambda name, err, w=worker_save: self._on_copy_failed(name, err, w))
                self._active_workers.append(worker_save)
                QThreadPool.globalInstance().start(worker_save)
                return

        # 3. Fallback : Comportement normal si c'est juste du texte
        super().insertFromMimeData(source)
