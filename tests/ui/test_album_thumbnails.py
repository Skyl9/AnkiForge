"""
Tests de la plaque de vignettes (ticket S1) : cache LRU, plafonnement avant
transformation, et orientation venue de la couture.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from PIL import Image
from PySide6.QtCore import QThreadPool

from ankiforge.services.cards.album_service import AlbumService
from ankiforge.ui.views.documents_view.widgets.album_thumbnails import (
    GLOBAL_THUMBNAIL_CACHE,
    ThumbnailCache,
    request_thumbnail,
    size_bucket,
)

pytestmark = pytest.mark.ui


def _create_witness_image(path: Path, width: int = 120, height: int = 60) -> Path:
    img = Image.new("RGB", (width, height), color="white")
    for x in range(width // 3):
        for y in range(height // 3):
            img.putpixel((x, y), (0, 0, 255))
    img.save(path)
    return path


@pytest.fixture
def album_page(tmp_path):
    """Une planche réelle, orientable, dans un album."""
    service = AlbumService()
    img = _create_witness_image(tmp_path / "witness.png")
    doc = service.create_album_from_images("Album vignettes", [img], sort_mode="none")
    return service.get_album_pages(doc.id)[0], service


def test_size_bucket_never_returns_less_than_requested():
    """Le cache ne doit jamais servir une vignette plus petite que demandé."""
    assert size_bucket(1) == 128
    assert size_bucket(128) == 128
    assert size_bucket(181) == 256
    assert size_bucket(256) == 256
    assert size_bucket(999_999) == 999_999


def test_cache_key_includes_the_rotation(album_page):
    """
    La rotation fait partie de la clé : pivoter invalide l'entrée de sa propre clé,
    sans qu'aucune invalidation manuelle soit nécessaire — donc sans qu'aucune puisse
    être oubliée.
    """
    page, _service = album_page
    before = ThumbnailCache.key_for(page, 180)

    page.rotation = 90
    after = ThumbnailCache.key_for(page, 180)

    assert before != after
    assert after[1] == 90


def test_cache_key_bucket_groups_nearby_sizes(album_page):
    """Deux tailles proches partagent une entrée, sinon le cache ne servirait à rien."""
    page, _service = album_page
    # 130 et 150 tombent tous deux dans le palier 180.
    assert ThumbnailCache.key_for(page, 130) == ThumbnailCache.key_for(page, 150)
    # Un palier réellement différent, en revanche, ne doit pas être confondu.
    assert ThumbnailCache.key_for(page, 130) != ThumbnailCache.key_for(page, 300)


def test_cache_evicts_least_recently_used():
    """Un cache borné écarte l'entrée la moins récemment utilisée."""
    from PySide6.QtGui import QImage

    cache = ThumbnailCache(max_entries=2)
    a, b, c = (1, 0, 128), (2, 0, 128), (3, 0, 128)
    for key in (a, b):
        cache.put(key, QImage(10, 10, QImage.Format.Format_RGB888))
    cache.get(a)  # `a` devient la plus récemment utilisée
    cache.put(c, QImage(10, 10, QImage.Format.Format_RGB888))

    assert len(cache) == 2
    assert cache.get(a) is not None
    assert cache.get(c) is not None
    assert cache.get(b) is None


def test_thumbnail_is_capped_before_display(qtbot, album_page):
    """
    La vignette servie tient dans la taille demandée.

    Une planche A4 à 300 dpi ferait 2500×3500 px : la grille ne doit jamais charger cela
    sur le thread GUI. On vérifie le plafond, pas seulement que « ça marche ».
    """
    page, service = album_page
    results: list[tuple[int, int, object]] = []
    failures: list[tuple[int, str]] = []

    task = request_thumbnail(
        page,
        180,
        on_ready=lambda pid, size, image: results.append((pid, size, image)),
        on_failed=lambda pid, msg: failures.append((pid, msg)),
        album_service=service,
    )
    QThreadPool.globalInstance().waitForDone(5000)
    qtbot.wait(150)

    assert not failures, f"vignette en échec : {failures}"
    assert len(results) == 1
    pid, size, image = results[0]
    assert pid == page.id
    assert size == 180
    assert image.width() <= 180
    assert image.height() <= 180
    # La planche native fait 120×60 : rien à réduire, mais la vignette reste bien rendue.
    assert task is not None


def test_thumbnail_honours_the_planche_rotation(qtbot, album_page):
    """
    L'orientation de la vignette vient de la couture, pas d'une transformation locale.

    Une planche paysage doit être servie en portrait une fois pivotée à 90°.
    """
    page, service = album_page
    page.rotation = 90
    page.save()

    results: list[tuple[int, int, object]] = []
    task = request_thumbnail(
        page,
        180,
        on_ready=lambda pid, size, image: results.append((pid, size, image)),
        on_failed=lambda pid, msg: results.append((pid, msg)),
        album_service=service,
    )
    QThreadPool.globalInstance().waitForDone(5000)
    qtbot.wait(150)
    assert task is not None

    assert len(results) == 1
    image = results[0][2]
    assert image.height() > image.width(), "la vignette devrait être en portrait après rotation de 90°"


def test_second_request_is_served_from_cache(qtbot, album_page):
    """Une vignette déjà rendue ne redécode pas l'image."""
    page, service = album_page
    cache = ThumbnailCache()
    pool = QThreadPool()

    first: list[object] = []
    task_a = request_thumbnail(page, 180, on_ready=lambda pid, size, image: first.append(image), cache=cache, album_service=service, thread_pool=pool)
    pool.waitForDone(5000)
    qtbot.wait(100)
    assert task_a is not None
    assert len(first) == 1
    assert len(cache) == 1

    second: list[object] = []
    task_b = request_thumbnail(page, 180, on_ready=lambda pid, size, image: second.append(image), cache=cache, album_service=service, thread_pool=pool)
    pool.waitForDone(5000)
    qtbot.wait(100)
    assert task_b is not None

    assert len(second) == 1
    # La même instance sort du cache : aucune relecture du fichier.
    assert second[0] is first[0]


def test_rotating_produces_a_new_cache_entry(qtbot, album_page):
    """Après rotation, l'ancienne entrée ne sert plus et une nouvelle est produite."""
    page, service = album_page
    cache = ThumbnailCache()
    pool = QThreadPool()

    before: list[object] = []
    task_a = request_thumbnail(page, 180, on_ready=lambda pid, size, image: before.append(image), cache=cache, album_service=service, thread_pool=pool)
    pool.waitForDone(5000)
    qtbot.wait(100)
    assert task_a is not None

    page.rotation = 90
    page.save()

    after: list[object] = []
    task_b = request_thumbnail(page, 180, on_ready=lambda pid, size, image: after.append(image), cache=cache, album_service=service, thread_pool=pool)
    pool.waitForDone(5000)
    qtbot.wait(100)
    assert task_b is not None

    assert len(before) == 1
    assert len(after) == 1
    assert after[0] is not before[0], "la rotation doit produire une vignette distincte"
    assert len(cache) == 2


def test_rotating_a_multi_page_album_never_renders_on_the_gui_thread(qtbot, tmp_path):
    """
    Un album de N planches ne rend **aucune** vignette sur le thread GUI.

    « Tourner 90° freeze l'image » venait de là : la grille décodait chaque planche en
    pleine résolution, sur le thread qui dessine la fenêtre. On vérifie la propriété qui
    rend le gel impossible — le décodage a lieu ailleurs — plutôt qu'une durée, qu'une
    machine chargée ferait varier sans que rien de faux se soit produit.
    """
    service = AlbumService()
    images = []
    for i in range(12):
        path = tmp_path / f"planche_{i}.png"
        image = Image.new("RGB", (400, 300), color=(i * 10 % 255, 40, 60))
        image.putpixel((3, 3), (0, 0, 255))
        image.save(path)
        images.append(path)
    doc = service.create_album_from_images("Album freezes", images)
    pages = service.get_album_pages(doc.id)

    render_threads: list[int] = []
    real_render = service.render_page_qimage

    def recording_render(page, max_size=None):
        render_threads.append(threading.get_ident())
        return real_render(page, max_size=max_size)

    service.render_page_qimage = recording_render  # type: ignore[method-assign]
    main_thread = threading.get_ident()

    delivered: list[int] = []
    tasks = [request_thumbnail(page, 180, on_ready=lambda pid, size, image: delivered.append(pid), album_service=service) for page in pages]

    QThreadPool.globalInstance().waitForDone(10000)
    qtbot.wait(500)

    assert len(render_threads) == len(pages), "chaque planche doit avoir été rendue"
    assert main_thread not in render_threads, "une vignette a été décodée sur le thread GUI : c'est le gel de S1"
    assert sorted(delivered) == sorted(page.id for page in pages)
    assert all(task is not None for task in tasks)


def test_missing_file_reports_failure_instead_of_hanging(qtbot, album_page):
    """Une planche sans fichier signale son échec au lieu de laisser la vignette muette."""
    page, service = album_page
    (service.media_manager.media_dir / page.media.filename).unlink()

    failures: list[tuple[int, str]] = []
    # Cache privé : le cache global peut déjà porter cette planche d'un test précédent,
    # et une entrée en cache court-circuite la lecture du disque — donc l'échec.
    task = request_thumbnail(
        page,
        180,
        on_ready=lambda pid, size, image: None,
        on_failed=lambda pid, msg: failures.append((pid, msg)),
        album_service=service,
        cache=ThumbnailCache(),
    )
    QThreadPool.globalInstance().waitForDone(5000)
    qtbot.wait(150)
    assert task is not None

    assert len(failures) == 1
    assert failures[0][0] == page.id
    assert "manquant" in failures[0][1].lower() or "introuvable" in failures[0][1].lower()


def test_global_cache_is_shared_between_requests():
    """Le cache global est bien un cache (et non une fonction sans état)."""
    assert isinstance(GLOBAL_THUMBNAIL_CACHE, ThumbnailCache)
