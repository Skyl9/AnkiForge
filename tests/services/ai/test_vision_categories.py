import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from pypdf import PdfReader

from ankiforge.database.models import DocumentPageModel, LLMConfigModel
from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.flexible_service import AnthropicProvider
from ankiforge.services.ai.ocr_service import OCRService, build_multimodal_payload
from ankiforge.services.ai.vision_category_service import VisionCategory, VisionCategoryService
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.workers.album_worker import AlbumOCRWorker, AlbumPDFWorker
from ankiforge.ui.widgets.settings_modal.dialogs.vision_category_dialog import VisionCategoryDialog
from ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab

pytestmark = pytest.mark.integration


def _create_test_img(path: Path, color: str = "blue") -> Path:
    img = Image.new("RGB", (60, 40), color=color)
    img.save(path)
    return path


def test_default_categories():
    """Vérifie que les 4 catégories par défaut sont initialisées avec les standards 2025-2026."""
    defaults = VisionCategoryService.get_default_categories()
    assert len(defaults) == 4
    cat_ids = [c.id for c in defaults]
    assert "reasoning" in cat_ids
    assert "massive" in cat_ids
    assert "structured" in cat_ids
    assert "hardware" in cat_ids

    reasoning = next(c for c in defaults if c.id == "reasoning")
    assert reasoning.thinking_budget == 2048
    assert reasoning.provider == "anthropic"


def test_get_and_save_category():
    """Vérifie la mise à jour et la persistance d'une catégorie."""
    cat = VisionCategoryService.get_category_by_id("reasoning")
    assert cat is not None

    cat.model_id = "claude-3-7-sonnet-custom"
    cat.thinking_budget = 4096
    VisionCategoryService.save_category(cat)

    reloaded = VisionCategoryService.get_category_by_id("reasoning")
    assert reloaded is not None
    assert reloaded.model_id == "claude-3-7-sonnet-custom"
    assert reloaded.thinking_budget == 4096


def test_add_and_delete_custom_category():
    """Vérifie l'ajout d'une catégorie sur-mesure et sa suppression."""
    new_cat = VisionCategory(
        id="medical_diagrams",
        name="Diagrammes Médicaux",
        description="Schémas anatomiques haute résolution",
        icon="ph.heart",
        provider="anthropic",
        model_id="claude-3-7-sonnet-20250219",
        thinking_budget=1024,
    )
    VisionCategoryService.save_category(new_cat)

    fetched = VisionCategoryService.get_category_by_id("medical_diagrams")
    assert fetched is not None
    assert fetched.name == "Diagrammes Médicaux"

    deleted = VisionCategoryService.delete_category("medical_diagrams")
    assert deleted is True
    assert VisionCategoryService.get_category_by_id("medical_diagrams") is None


def test_reset_to_defaults():
    """Vérifie le rétablissement des catégories par défaut."""
    VisionCategoryService.delete_category("massive")
    assert VisionCategoryService.get_category_by_id("massive") is None

    resetted = VisionCategoryService.reset_to_defaults()
    assert len(resetted) == 4
    assert VisionCategoryService.get_category_by_id("massive") is not None


def test_build_multimodal_payload(tmp_path: Path):
    """Vérifie que build_multimodal_payload encode proprement les images en base64."""
    img_path = _create_test_img(tmp_path / "test.png")
    payload = build_multimodal_payload("Prompt OCR", [img_path])

    assert len(payload) == 2
    assert payload[0]["type"] == "text"
    assert payload[0]["text"] == "Prompt OCR"
    assert payload[1]["type"] == "image_url"
    assert payload[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_anthropic_multimodal_and_thinking_support():
    """Vérifie que AnthropicProvider traduit les blocs d'images et filtre les blocs de réflexion."""
    provider = AnthropicProvider(api_key="test_key", model_name="claude-3-7-sonnet-20250219", thinking_budget=2048)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "content": [
            {"type": "thinking", "thinking": "Analyse mathématique pas-à-pas..."},
            {"type": "text", "text": "## Résumé du Cours\nFormule extraite : $E = mc^2$"},
        ],
        "usage": {"input_tokens": 150, "output_tokens": 40},
    }

    with patch("requests.post", return_value=mock_resp) as mock_post:
        user_prompt = [
            {"type": "text", "text": "Analyse cette image"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,QUJDRA=="}},
        ]
        res = provider.generate("System", user_prompt, response_format="text")

        assert res == "## Résumé du Cours\nFormule extraite : $E = mc^2$"
        assert mock_post.called

        _, kwargs = mock_post.call_args
        sent_payload = kwargs["json"]
        assert sent_payload["model"] == "claude-3-7-sonnet-20250219"
        assert sent_payload["thinking"] == {"type": "enabled", "budget_tokens": 2048}

        # Vérification du format d'image Anthropic
        sent_messages = sent_payload["messages"]
        assert sent_messages[0]["content"][1]["type"] == "image"
        assert sent_messages[0]["content"][1]["source"]["type"] == "base64"
        assert sent_messages[0]["content"][1]["source"]["media_type"] == "image/jpeg"


def test_ocr_service_transcribe_image(tmp_path: Path):
    """Vérifie la transcription d'image via OCRService avec un provider mocké."""
    service = OCRService()
    img_path = _create_test_img(tmp_path / "ocr_test.png")

    class CustomMockProvider(MockProvider):
        def generate(self, system_prompt, user_prompt, response_format="json"):
            return "Transcription mockée réussie"

    text = service.transcribe_image(img_path, category_id="structured", provider_override=CustomMockProvider())
    assert text == "Transcription mockée réussie"


def test_native_hardware_category_never_falls_back_to_cloud_ai(tmp_path: Path):
    """
    Vérifie qu'un échec ou indisponibilité d'Apple Vision lève une exception et
    ne déclenche aucun repli automatique silencieux vers un LLM cloud/distant.
    """
    service = OCRService()
    img_path = _create_test_img(tmp_path / "apple_test.png")

    # Cas 1 : Apple Vision indisponible sur la machine
    with patch.object(service, "is_apple_vision_available", return_value=False), pytest.raises(RuntimeError, match="Apple Vision n'est pas disponible"):
        service.transcribe_image(img_path, category_id="hardware")

    # Cas 2 : Apple Vision disponible mais renvoyant None (échec OCR ou timeout)
    with (
        patch.object(service, "is_apple_vision_available", return_value=True),
        patch.object(service, "transcribe_with_apple_vision", return_value=None),
        pytest.raises(RuntimeError, match="Apple Vision a échoué ou a dépassé le délai"),
    ):
        service.transcribe_image(img_path, category_id="hardware")


def test_ocr_service_transcribe_page_db_update(tmp_path: Path):
    """Vérifie la transcription d'une DocumentPageModel et la mise à jour en BDD SQLite."""
    manager = MediaManager()
    album_svc = AlbumService(media_manager=manager)
    ocr_svc = OCRService(media_manager=manager)

    img = _create_test_img(tmp_path / "page_test.png")
    doc = album_svc.create_album_from_images("Album OCR Test", [img])
    page = album_svc.get_album_pages(doc.id)[0]

    class CustomMockProvider(MockProvider):
        def generate(self, system_prompt, user_prompt, response_format="json"):
            return "# Page Transcrite\nContenu extrait"

    updated = ocr_svc.transcribe_page(page.id, category_id="reasoning", provider_override=CustomMockProvider())
    assert updated.status == "ready"
    assert "Page Transcrite" in updated.ocr_text

    # Vérification rechargée depuis la base
    reloaded = DocumentPageModel.get_by_id(page.id)
    assert reloaded.ocr_text == "# Page Transcrite\nContenu extrait"
    assert reloaded.status == "ready"


def test_transcribe_page_sends_the_rotated_planche(tmp_path: Path):
    """
    Le modèle reçoit la planche **dans son orientation**, jamais le fichier brut.

    On intercepte l'image effectivement encodée dans le payload : la preuve porte sur
    ce que le LLM voit, pas sur un appel de méthode. Sans cela, transcrire une planche
    de travers produirait un texte faux — l'état le plus difficile à rattraper, car il
    est syntaxiquement valide et sémantiquement faux.
    """
    manager = MediaManager()
    album_svc = AlbumService(media_manager=manager)
    ocr_svc = OCRService(media_manager=manager)

    # Planche témoin : plus large que haute, le témoin bleu en haut à gauche.
    img = Image.new("RGB", (120, 60), color="white")
    for x in range(40):
        for y in range(20):
            img.putpixel((x, y), (0, 0, 255))
    img_path = tmp_path / "témoin.png"
    img.save(img_path)

    doc = album_svc.create_album_from_images("Planche pivotée", [img_path], sort_mode="none")
    page = album_svc.get_album_pages(doc.id)[0]
    album_svc.rotate_page(page.id, 90)
    page = DocumentPageModel.get_by_id(page.id)
    assert page.rotation == 90

    seen: list[Image.Image] = []

    class SpyProvider(MockProvider):
        def generate(self, system_prompt, user_prompt, response_format="json"):
            payload = user_prompt if isinstance(user_prompt, list) else [user_prompt]
            for part in payload:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    import base64

                    encoded = part["image_url"]["url"].split(",", 1)[1]
                    seen.append(Image.open(__import__("io").BytesIO(base64.b64decode(encoded))))
            return "ok"

    ocr_svc.transcribe_page(page.id, category_id="structured", provider_override=SpyProvider())

    assert len(seen) == 1
    try:
        # Portrait : la rotation a bien été appliquée avant l'envoi.
        assert seen[0].height > seen[0].width
        # Le témoin a migré en haut à droite : rouge minimal (le bleu vaut 0, le blanc 255).
        corners = {
            "top_left": seen[0].getpixel((2, 2)),
            "top_right": seen[0].getpixel((seen[0].width - 3, 2)),
            "bottom_left": seen[0].getpixel((2, seen[0].height - 3)),
            "bottom_right": seen[0].getpixel((seen[0].width - 3, seen[0].height - 3)),
        }
        assert min(corners, key=lambda name: corners[name][0]) == "top_right"
    finally:
        for img_seen in seen:
            img_seen.close()


def test_album_ocr_worker_execution(tmp_path: Path):
    """Vérifie l'exécution d'AlbumOCRWorker et l'émission des signaux Qt."""
    album_svc = AlbumService()
    imgs = [
        _create_test_img(tmp_path / "p1.png"),
        _create_test_img(tmp_path / "p2.png"),
    ]
    doc = album_svc.create_album_from_images("Worker Test", imgs)

    class FastMock(MockProvider):
        def generate(self, system_prompt, user_prompt, response_format="json"):
            return "Texte extrait"

    worker = AlbumOCRWorker(
        document_id=doc.id,
        category_id="structured",
        provider_override=FastMock(),
    )

    signals_received = {
        "progress": [],
        "pages": [],
        "finished": [],
    }

    worker.progress.connect(lambda cur, tot: signals_received["progress"].append((cur, tot)))
    worker.page_processed.connect(lambda pid, pnum, txt: signals_received["pages"].append((pid, pnum, txt)))
    worker.finished_signal.connect(lambda succ, err: signals_received["finished"].append((succ, err)))

    # Exécution synchrone de run()
    worker.run()

    assert len(signals_received["progress"]) == 2
    assert len(signals_received["pages"]) == 2
    # (succès, erreurs) — l'ordre reversed annonçait « 2 pages sur 2 » sur un album vide.
    assert signals_received["finished"] == [(2, 0)]

    pages = album_svc.get_album_pages(doc.id)
    for p in pages:
        assert p.ocr_text == "Texte extrait"
        assert p.status == "ready"


def test_album_ocr_worker_carries_the_category_down_to_transcription(tmp_path: Path):
    """
    La catégorie choisie descend jusqu'à l'appel de transcription, et n'est pas perdue.

    Le worker transporte `category_id` jusqu'à `OCRService.transcribe_page`, qui en déduit le
    modèle. Le sélecteur de l'interface ne servait donc à rien si le worker se rabattait
    sur un défaut en cours de route — un modèle que l'utilisateur n'a pas choisi.
    """
    album_svc = AlbumService()
    img = _create_test_img(tmp_path / "p1.png")
    doc = album_svc.create_album_from_images("Album catégorie", [img])

    seen: list[str] = []

    class SpyOCRService:
        def transcribe_page(self, page_id, category_id=None, provider_override=None):
            seen.append(category_id)
            return album_svc.get_album_pages(doc.id)[0]

    worker = AlbumOCRWorker(
        document_id=doc.id,
        category_id="vision-vraie",
        provider_override=MockProvider(),
    )
    worker.ocr_service = SpyOCRService()  # type: ignore[assignment]
    worker.run()

    assert seen == ["vision-vraie"], "la catégorie choisie n'a pas atteint la transcription"


def test_album_ocr_worker_reports_failures_instead_of_silence(tmp_path: Path):
    """Un album dont toutes les planches échouent ne doit pas s'annoncer « transcrit »."""
    album_svc = AlbumService()
    imgs = [_create_test_img(tmp_path / "p1.png"), _create_test_img(tmp_path / "p2.png")]
    doc = album_svc.create_album_from_images("Album en échec", imgs)

    class FailingProvider(MockProvider):
        def generate(self, system_prompt, user_prompt, response_format="json"):
            raise RuntimeError("modèle indisponible")

    worker = AlbumOCRWorker(document_id=doc.id, category_id="structured", provider_override=FailingProvider())

    received: dict[str, list] = {"finished": [], "cancelled": [], "error": []}
    worker.finished_signal.connect(lambda succ, err: received["finished"].append((succ, err)))
    worker.cancelled_signal.connect(lambda done, total: received["cancelled"].append((done, total)))
    worker.error_signal.connect(lambda msg: received["error"].append(msg))

    worker.run()

    assert received["finished"] == [(0, 2)]
    assert received["cancelled"] == []
    assert received["error"] == []


def test_album_ocr_worker_cancellation_is_not_completion(tmp_path: Path):
    """Une transcription interrompue se distingue d'une transcription terminée."""
    album_svc = AlbumService()
    imgs = [_create_test_img(tmp_path / f"p{i}.png") for i in range(1, 4)]
    doc = album_svc.create_album_from_images("Album interrompu", imgs)

    class StopAfterFirstProvider(MockProvider):
        def __init__(self) -> None:
            self.calls = 0

        def generate(self, system_prompt, user_prompt, response_format="json"):
            self.calls += 1
            return "Texte extrait"

    provider = StopAfterFirstProvider()
    worker = AlbumOCRWorker(document_id=doc.id, category_id="structured", provider_override=provider)
    worker._is_cancelled = True

    received: dict[str, list] = {"finished": [], "cancelled": []}
    worker.finished_signal.connect(lambda succ, err: received["finished"].append((succ, err)))
    worker.cancelled_signal.connect(lambda done, total: received["cancelled"].append((done, total)))

    worker.run()

    assert provider.calls == 0
    assert received["finished"] == []
    assert received["cancelled"] == [(0, 3)]


def test_album_pdf_worker_compiles_off_thread(tmp_path: Path):
    """AlbumPDFWorker produit le PDF au chemin choisi et rend compte de sa progression."""
    album_svc = AlbumService()
    imgs = [_create_test_img(tmp_path / f"p{i}.png", color=color) for i, color in enumerate(("blue", "red", "green"), start=1)]
    doc = album_svc.create_album_from_images("Album PDF", imgs)
    out = tmp_path / "compiled.pdf"

    worker = AlbumPDFWorker(document_id=doc.id, output_path=out, album_service=album_svc)

    received: dict[str, list] = {"progress": [], "finished": [], "error": [], "cancelled": []}
    worker.progress.connect(lambda cur, total: received["progress"].append((cur, total)))
    worker.finished_signal.connect(lambda path: received["finished"].append(path))
    worker.error_signal.connect(lambda msg: received["error"].append(msg))
    worker.cancelled_signal.connect(lambda done, total: received["cancelled"].append((done, total)))

    worker.run()

    assert received["progress"] == [(1, 3), (2, 3), (3, 3)]
    assert received["error"] == []
    assert received["cancelled"] == []
    assert received["finished"] == [str(out)]
    assert out.exists()
    # `pypdf` et non PIL : ouvrir un PDF par Pillow exige Ghostscript, absent en CI.
    reader = PdfReader(str(out))
    assert len(reader.pages) == 3, "le PDF doit contenir une page par planche"


def test_album_pdf_worker_applies_the_planche_rotation(tmp_path: Path):
    """
    Les planches du PDF sont rendues **à leur orientation propre**, via la couture S2a.

    La compilation annonçait des « rotations fidèlement appliquées » sans jamais passer
    par la couture : une planche à 90° sortait couchée du PDF. On le vérifie sur la
    géométrie réelle du fichier produit, pas sur l'intention du code.
    """
    album_svc = AlbumService()
    img = _create_test_img(tmp_path / "landscape.png", color="blue")
    doc = album_svc.create_album_from_images("Album PDF orienté", [img])
    page = album_svc.get_album_pages(doc.id)[0]
    # La planche source est paysage (60×40) ; pivotée, elle doit sortir portrait.
    album_svc.rotate_page(page.id, 90)

    out = tmp_path / "oriented.pdf"
    worker = AlbumPDFWorker(document_id=doc.id, output_path=out, album_service=album_svc)
    worker.run()

    assert out.exists()
    page_box = PdfReader(str(out)).pages[0].mediabox
    width, height = float(page_box.width), float(page_box.height)
    assert height > width, "la planche pivotée à 90° doit sortir en portrait du PDF"


@pytest.mark.ui
def test_album_pdf_compilation_never_runs_on_the_gui_thread(qtbot, tmp_path: Path):
    """
    La boucle de compilation ne s'exécute jamais sur le thread GUI, un album de N planches.

    « La compilation PDF d'image plante » venait de là : ouvrir chaque planche en pleine
    résolution depuis le slot qui dessine la fenêtre gelait l'interface. On vérifie la
    propriété qui l'exclut — le décodage a lieu ailleurs — plutôt qu'une durée, qu'une
    machine chargée ferait varier sans qu'aucune faute soit commise.
    """
    album_svc = AlbumService()
    images = []
    for i in range(40):
        path = tmp_path / f"many_{i}.png"
        Image.new("RGB", (120, 90), color=(30, i * 5 % 255, 90)).save(path)
        images.append(path)
    doc = album_svc.create_album_from_images("Album 200", images)
    out = tmp_path / "many.pdf"

    render_threads: list[int] = []
    real_render = album_svc.render_page_image

    def recording_render(page, max_size=None):
        render_threads.append(threading.get_ident())
        return real_render(page, max_size=max_size)

    album_svc.render_page_image = recording_render  # type: ignore[method-assign]

    worker = AlbumPDFWorker(document_id=doc.id, output_path=out, album_service=album_svc)
    seen: list[tuple[int, int]] = []
    worker.progress.connect(lambda cur, total: seen.append((cur, total)))

    worker.start()
    with qtbot.waitSignal(worker.finished_signal, timeout=120000):
        pass

    # `finished_signal` est émis depuis `run()` : attendre ce signal ne garantit pas que le
    # thread a rendu la main. Sans ce `wait()`, il pouvait encore tenir une connexion peewee
    # au moment où la fixture supprime les tables — « database table is locked », puis une
    # contrainte `UNIQUE` violée dans le test suivant. Un test qui casse la suite entière
    # n'est pas un test, c'est une panne.
    assert worker.wait(60000), "le thread de compilation n'a pas rendu la main"

    assert len(render_threads) == 40, "chaque planche doit avoir été rendue"
    assert threading.get_ident() not in render_threads, "une planche a été rendue sur le thread GUI : c'est le gel de S3"
    assert seen == [(i, 40) for i in range(1, 41)]
    assert out.exists()


def test_album_pdf_worker_releases_every_intermediate_image(tmp_path: Path, monkeypatch):
    """
    Les planches PIL rendues par la couture sont réellement fermées, chemin compris l'annulation.

    200 planches non libérées en fin de compilation ou d'annulation saturent la mémoire
    d'images décodées d'un album réel. On instrumente `close()` : observer le fichier de la
    source ne prouve rien, puisque c'est le `with` **de la couture** qui la ferme — ce sont
    les copies rendues, tenues par la boucle du worker, qu'il faut voir refermées.
    """
    album_svc = AlbumService()
    imgs = [_create_test_img(tmp_path / f"p{i}.png") for i in range(1, 4)]
    doc = album_svc.create_album_from_images("Album libération", imgs)

    rendered: list[Image.Image] = []
    closed: list[Image.Image] = []
    real_render = album_svc.render_page_image
    real_close = Image.Image.close

    def recording_render(page, max_size=None):
        image = real_render(page, max_size=max_size)
        rendered.append(image)
        return image

    def recording_close(self):
        closed.append(self)
        return real_close(self)

    monkeypatch.setattr(album_svc, "render_page_image", recording_render)
    monkeypatch.setattr(Image.Image, "close", recording_close)

    out = tmp_path / "released.pdf"
    AlbumPDFWorker(document_id=doc.id, output_path=out, album_service=album_svc).run()

    assert out.exists()
    assert rendered, "aucune planche observée : le test ne prouve rien"
    assert len(rendered) == 3
    assert all(any(c is im for c in closed) for im in rendered), "une planche rendue est restée ouverte après compilation"

    # Même exigence sur le chemin de l'annulation, mais en annulant **après** la première
    # planche : annuler avant la boucle n'ouvrait aucune image, et l'assertion passait
    # donc sur une liste vide — le test ne prouvait rien du tout.
    rendered.clear()
    closed.clear()
    worker = AlbumPDFWorker(document_id=doc.id, output_path=tmp_path / "x.pdf", album_service=album_svc)

    def cancel_after_first_page(current: int, total: int) -> None:
        if current == 1:
            worker.cancel()

    worker.progress.connect(cancel_after_first_page)
    received: dict[str, list] = {"cancelled": []}
    worker.cancelled_signal.connect(lambda done, total: received["cancelled"].append((done, total)))
    worker.run()

    assert rendered, "l'annulation a été demandée avant tout rendu : rien à libérer, rien de prouvé"
    assert all(any(c is im for c in closed) for im in rendered), "une planche rendue est restée ouverte après annulation"
    assert received["cancelled"] == [(1, 3)]


def test_album_pdf_worker_cancel_is_not_an_error(tmp_path: Path):
    """Une compilation annulée ne doit pas être signalée comme un échec."""
    album_svc = AlbumService()
    imgs = [_create_test_img(tmp_path / "p1.png"), _create_test_img(tmp_path / "p2.png")]
    doc = album_svc.create_album_from_images("Album PDF annulé", imgs)
    out = tmp_path / "cancelled.pdf"

    worker = AlbumPDFWorker(document_id=doc.id, output_path=out, album_service=album_svc)
    worker._is_cancelled = True

    received: dict[str, list] = {"finished": [], "error": [], "cancelled": []}
    worker.finished_signal.connect(lambda path: received["finished"].append(path))
    worker.error_signal.connect(lambda msg: received["error"].append(msg))
    worker.cancelled_signal.connect(lambda done, total: received["cancelled"].append((done, total)))

    worker.run()

    assert received["finished"] == []
    assert received["error"] == []
    assert received["cancelled"] == [(0, 2)]
    # Aucun fichier partiel laissé derrière : un PDF à moitié écrit se ferait passer
    # pour un album complet au prochaine ouverture.
    assert not out.exists()


def test_album_pdf_worker_surfaces_a_real_failure(tmp_path: Path):
    """Une panne réelle remonte par `error_signal`, pas comme une annulation."""
    album_svc = AlbumService()
    imgs = [_create_test_img(tmp_path / "p1.png")]
    doc = album_svc.create_album_from_images("Album en panne", imgs)

    worker = AlbumPDFWorker(document_id=doc.id, output_path=tmp_path / "x.pdf", album_service=album_svc)

    def boom(*_args, **_kwargs):
        raise RuntimeError("disque plein")

    worker.album_service.compile_album_to_pdf = boom  # type: ignore[method-assign]

    received: dict[str, list] = {"finished": [], "error": [], "cancelled": []}
    worker.finished_signal.connect(lambda path: received["finished"].append(path))
    worker.error_signal.connect(lambda msg: received["error"].append(msg))
    worker.cancelled_signal.connect(lambda done, total: received["cancelled"].append((done, total)))

    worker.run()

    assert received["finished"] == []
    assert received["cancelled"] == []
    assert received["error"] == ["disque plein"]


def test_category_declares_vision_refuses_a_declared_text_only_engine():
    """
    Un moteur déclaré « sans Vision » fait **refuser** la transcription.

    C'est le refus que S4 livre réellement ; le cas « modèle absent » est vérifié à part.
    L'assertion précédente acceptait `None` **et** `False`, donc ne prouvait rien.
    """
    VisionCategoryService.save_all_categories(VisionCategoryService.get_default_categories())

    text_only_engine = LLMConfigModel.create(
        display_name="Moteur texte seul de test",
        provider="openai",
        model_id="gpt-4o-mini-test",
        supports_vision=False,
    )
    try:
        category = VisionCategory.from_dict(
            {
                "id": "texte-seul",
                "name": "Texte seul",
                "provider": "openai",
                "model_id": text_only_engine.model_id,
            }
        )
        VisionCategoryService.save_category(category)

        assert VisionCategoryService.category_declares_vision(category) is False
    finally:
        text_only_engine.delete_instance()


def test_category_declares_vision_never_guesses_on_an_unknown_model():
    """
    Un moteur introuvable n'est pas une preuve d'incompatibilité.

    Condamner ici fermerait la transcription sur un moteur multimodal encore absent du
    catalogue local — un refus sans fondement sur une configuration valide.
    """
    VisionCategoryService.save_all_categories(VisionCategoryService.get_default_categories())

    unknown = VisionCategory.from_dict(
        {
            "id": "moteur-inconnu",
            "name": "Moteur inconnu",
            "provider": "openai",
            "model_id": "modele-qui-nexiste-pas",
        }
    )

    assert VisionCategoryService.category_declares_vision(unknown) is None


def test_category_declares_vision_accepts_a_declared_vision_engine():
    """Symétrique du refus : un moteur multimodal déclaré reste utilisable."""
    VisionCategoryService.save_all_categories(VisionCategoryService.get_default_categories())

    vision_engine = LLMConfigModel.create(
        display_name="Moteur multimodal de test",
        provider="openai",
        model_id="gpt-4o-test",
        supports_vision=True,
    )
    try:
        category = VisionCategory.from_dict(
            {
                "id": "multimodal",
                "name": "Multimodal",
                "provider": "openai",
                "model_id": vision_engine.model_id,
            }
        )
        VisionCategoryService.save_category(category)

        assert VisionCategoryService.category_declares_vision(category) is True
    finally:
        vision_engine.delete_instance()


def test_native_ocr_category_is_not_judged_as_a_model():
    """L'OCR natif ne reçoit pas d'image à refuser : il n'a pas de capacité Vision."""
    native = next(cat for cat in VisionCategoryService.get_categories() if cat.provider == "native")

    assert VisionCategoryService.category_declares_vision(native) is None


def test_vision_category_dialog_ui(qtbot):
    """Vérifie l'instanciation et la sauvegarde de VisionCategoryDialog."""
    cat = VisionCategoryService.get_category_by_id("reasoning")
    dialog = VisionCategoryDialog(category=cat)
    qtbot.addWidget(dialog)

    # Modification des champs
    dialog.le_name.setText("Raisonnement Modifié")
    dialog.spin_thinking.setValue(4096)
    dialog._on_save()

    res_cat = dialog.get_category()
    assert res_cat is not None
    assert res_cat.name == "Raisonnement Modifié"
    assert res_cat.thinking_budget == 4096


def test_ai_engines_tab_ui(qtbot):
    """Vérifie le rendu complet d'AIEnginesTab avec les cartes de catégories de vision."""
    tab = AIEnginesTab()
    qtbot.addWidget(tab)

    # Vérification des sections
    assert tab.lbl_sec_keys is not None
    assert tab.lbl_sec_ollama is not None
    assert tab.lbl_sec_cat is not None
    assert tab.lbl_sec_vision is not None

    # Les 4 cartes de catégories de vision sont générées
    assert len(tab.vision_cards) >= 4
