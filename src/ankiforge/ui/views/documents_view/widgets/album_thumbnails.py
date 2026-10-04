"""
Plaque de vignettes hors du thread GUI (ticket S1).

La grille d'album ouvrait chaque planche **en pleine résolution** sur le thread GUI,
puis la transformait : sur un scan A4 à 300 dpi (~2500×3500 px) et 200 planches, une
rotation déclenchait autant de décodages et de transformations — « tourner 90° freeze
l'image ».

Le décodage est le vrai coût, pas la mise à l'échelle. On plafonne donc **avant**
transformation (Pillow `thumbnail` décode par bandes) et on met le travail dans un
`QThreadPool`.

Deux invariants portent le reste du ticket :

* **la clé de cache inclut la rotation** — une rotation invalide naturellement sa propre
  entrée, aucune invalidation manuelle n'est nécessaire ni oubliée ;
* **la couture est la seule source d'orientation** — la clé lit `page.rotation` pour
  identifier une variante, jamais pour produire l'image ; l'orientation vient de
  `AlbumService.render_page_image`.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from ankiforge.services.cards.album_service import AlbumService

if TYPE_CHECKING:
    from PySide6.QtGui import QImage

    from ankiforge.database.models import DocumentPageModel

logger = logging.getLogger(__name__)

#: Paliers de taille servies par le cache. Une demande de 181 px et de 190 px partagent
#: la même entrée : sans cela, un redimensionnement de fenêtre ferait manquer le cache
#: en continu, et le cache ne servirait à rien.
SIZE_BUCKETS: tuple[int, ...] = (128, 180, 256, 384, 512, 768, 1024, 1536, 2048, 3072)


def size_bucket(px: int) -> int:
    """Palier de cache correspondant à une taille demandée (jamais plus petit que la demande)."""
    requested = max(1, int(px))
    for bucket in SIZE_BUCKETS:
        if bucket >= requested:
            return bucket
    return requested


class ThumbnailCache:
    """
    Cache LRU en mémoire de vignettes déjà rendues, clé `(media_id, rotation, bucket)`.

    La rotation dans la clé est ce qui rend le cache juste sans travail d'invalidation :
    pivoter une planche produit une clé différente, donc une entrée neuve, et l'ancienne
    entrée — celle qui correspondait à l'orientation précédente — n'est simplement plus
    demandée. Une invalidation manuelle, elle, serait un oubli en puissance.
    """

    def __init__(self, max_entries: int = 256) -> None:
        self._entries: OrderedDict[tuple[int, int, str, int], QImage] = OrderedDict()
        self._max_entries = max_entries
        # Verrou : le cache est partagé et appelé depuis tous les threads du QThreadPool.
        # `while len > max: popitem()` n'est pas atomique — deux threads qui évintent
        # simultanément vidaient le dictionnaire et faisaient lever un `KeyError` **dans**
        # `ThumbnailTask.run()`, que PySide6 avale : la carte restait sur « Chargement… »
        # indéfiniment, sans trace et sans signal.
        self._lock = threading.Lock()

    @staticmethod
    def key_for(page: DocumentPageModel, size_px: int) -> tuple[int, int, str, int]:
        media_id = page.media_id if page.media_id is not None else -1
        return (int(media_id), int(page.rotation or 0) % 360, str(page.crop_data or ""), size_bucket(size_px))

    def get(self, key: tuple[int, int, str, int]) -> QImage | None:
        with self._lock:
            image = self._entries.get(key)
            if image is not None:
                self._entries.move_to_end(key)
            return image

    def put(self, key: tuple[int, int, str, int], image: QImage) -> None:
        with self._lock:
            self._entries[key] = image
            self._entries.move_to_end(key)
            while len(self._entries) > self._max_entries:
                self._entries.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


#: Cache partagé : la rotation d'une planche ne doit pas invalider les vignettes des
#: 199 autres, et deux vues du même album ne doivent pas décoder deux fois la même image.
GLOBAL_THUMBNAIL_CACHE = ThumbnailCache()


class ThumbnailSignals(QObject):
    """Signaux d'un runnable : Qt exige un `QObject` porteur, le `QRunnable` ne peut pas en avoir."""

    ready = Signal(int, int, object)  # (page_id, size_px, QImage) — jamais un QPixmap
    failed = Signal(int, str)  # (page_id, message)


class ThumbnailTask(QRunnable):
    """
    Rend une vignette **dans un thread de fond** et la publie via un signal.

    Le worker produit une `QImage`, pas un `QPixmap` : Qt refuse de créer un `QPixmap`
    hors du thread GUI, et le refus est silencieux — un `QPixmap` nul qui se lit comme
    « vignette absente ». La conversion en `QPixmap` se fait donc à la réception, sur le
    thread GUI, où elle est légitime.
    """

    def __init__(
        self,
        page: DocumentPageModel,
        size_px: int,
        cache: ThumbnailCache | None = None,
        album_service: AlbumService | None = None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.page = page
        self.size_px = size_px
        self.cache = cache if cache is not None else GLOBAL_THUMBNAIL_CACHE
        self.album_service = album_service or AlbumService()
        self.signals = ThumbnailSignals()
        self._key = self.cache.key_for(page, size_px)

    @Slot()
    def run(self) -> None:
        # L'émission depuis ce thread est sûre : la connexion du récepteur étant en
        # mode auto (queued), Qt marshalle la livraison sur le thread GUI.
        cached = self.cache.get(self._key)
        if cached is not None:
            self.signals.ready.emit(self.page.id, self.size_px, cached)
            return

        try:
            # `max_size` plafonne **avant** transformation : la grille ne charge jamais
            # une planche native. L'orientation vient de la couture.
            image = self.album_service.render_page_qimage(self.page, max_size=self.size_px)
        except Exception as e:
            logger.warning("Vignette indisponible pour la planche %d : %s", self.page.id, e)
            self.signals.failed.emit(self.page.id, str(e))
            return

        if image.isNull():
            self.signals.failed.emit(self.page.id, "Image illisible")
            return

        self.cache.put(self._key, image)
        self.signals.ready.emit(self.page.id, self.size_px, image)


def request_thumbnail(
    page: DocumentPageModel,
    size_px: int,
    on_ready: Callable[[int, int, QImage], None],
    on_failed: Callable[[int, str], None] | None = None,
    cache: ThumbnailCache | None = None,
    album_service: AlbumService | None = None,
    thread_pool: QThreadPool | None = None,
) -> ThumbnailTask:
    """
    Demande une vignette en arrière-plan et branche les callbacks.

    **L'appelant doit conserver la task retournée** : son `QRunnable` est auto-supprimé
    à la fin de `run()`, et son `QObject` porteur de signaux disparaît avec la dernière
    référence. Un ramassage prématuré ne lève aucune erreur — le travail est fait, le
    cache rempli, et le signal.emit() ne trouve plus personne. Un widget qui stocke ses
    vignettes en cours peut s'en servir pour les annuler.
    """
    task = ThumbnailTask(page, size_px, cache=cache, album_service=album_service)
    task.signals.ready.connect(on_ready)
    if on_failed is not None:
        task.signals.failed.connect(on_failed)
    pool = thread_pool if thread_pool is not None else QThreadPool.globalInstance()
    pool.start(task)
    return task
