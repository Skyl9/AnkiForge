from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from ankiforge.database.models import DocumentPageModel
from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.flexible_service import AnthropicProvider
from ankiforge.services.ai.ocr_service import OCRService, build_multimodal_payload
from ankiforge.services.ai.vision_category_service import VisionCategory, VisionCategoryService
from ankiforge.services.cards.album_service import AlbumService
from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.services.workers.album_worker import AlbumOCRWorker
from ankiforge.ui.widgets.settings_modal.dialogs.vision_category_dialog import VisionCategoryDialog
from ankiforge.ui.widgets.settings_modal.tabs.ai_engines_tab import AIEnginesTab


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
    worker.finished_signal.connect(lambda tot, succ: signals_received["finished"].append((tot, succ)))

    # Exécution synchrone de run()
    worker.run()

    assert len(signals_received["progress"]) == 2
    assert len(signals_received["pages"]) == 2
    assert signals_received["finished"] == [(2, 2)]

    pages = album_svc.get_album_pages(doc.id)
    for p in pages:
        assert p.ocr_text == "Texte extrait"
        assert p.status == "ready"


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
