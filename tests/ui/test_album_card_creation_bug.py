import json
from unittest.mock import MagicMock

import pytest

from ankiforge.database.models import (
    DeckModel,
    DocumentModel,
    DocumentPageModel,
    MediaModel,
    NoteTypeModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
)
from ankiforge.services.ai.base import LLMResult, MockProvider
from ankiforge.ui.views.creation_view.view import CreationView

pytestmark = pytest.mark.ui


class CapturedProvider(MockProvider):
    def __init__(self) -> None:
        super().__init__()
        self.captured_prompts: list[str] = []
        self.captured_multimodal_payloads: list[list[dict]] = []

    def generate_response(self, system_prompt: str, user_prompt: str | list[dict], **kwargs) -> LLMResult:
        if isinstance(user_prompt, list):
            self.captured_multimodal_payloads.append(user_prompt)
            text_parts = [p.get("text", "") for p in user_prompt if p.get("type") == "text"]
            self.captured_prompts.append(" ".join(text_parts))
        else:
            self.captured_prompts.append(str(user_prompt))
        return LLMResult(
            content=json.dumps([{"Front": "Q1", "Back": "A1"}]),
            raw_response="ok",
        )


@pytest.fixture
def album_with_transcription(mock_db, tmp_path):
    """Crée un album avec des planches dont le texte OCR est transcrit."""
    media1 = MediaModel.create(filename="p1.png", media_type="image", original_name="p1.png", checksum="chk1", mime_type="image/png")
    media2 = MediaModel.create(filename="p2.png", media_type="image", original_name="p2.png", checksum="chk2", mime_type="image/png")

    doc = DocumentModel.create(
        title="Atlas Anatomie",
        file_type="album",
        total_pages=2,
        content="",  # Comme créé par AlbumService.create_album_from_images !
    )
    p1 = DocumentPageModel.create(
        document=doc,
        media=media1,
        page_number=1,
        ocr_text="Ventricule gauche et aorte descendante.",
        status="ready",
    )
    p2 = DocumentPageModel.create(
        document=doc,
        media=media2,
        page_number=2,
        ocr_text="Oreillette droite et veine cave supérieure.",
        status="ready",
    )
    return doc, [p1, p2]


def test_album_transcription_reaches_generation_prompt(qtbot, album_with_transcription, mock_db):
    """
    Repro : vérifie que lorsqu'un utilisateur navigue vers CreationView depuis un album transcrit
    et clique sur Générer, le prompt envoyé au LLM contient effectivement le texte OCR extrait.
    """
    doc, pages = album_with_transcription
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Front", "Back"]),
        templates="[]",
        css_style="",
    )
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(
        name="Extracteur",
        system_prompt="Extrais des cartes flash.",
        output_format="json",
    )
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    provider = CapturedProvider()
    ai_mgr = MagicMock()
    ai_mgr.create_provider_from_config.return_value = provider

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    # 1. Navigation depuis DocumentsView (comme fait par forge_requested -> request_navigation)
    view.load_context({"doc_id": doc.id})

    # 2. Vérification que l'éditeur est bien ouvert et contient le texte
    editor = view.open_editors.get(doc.title)
    assert editor is not None, "L'onglet de l'album doit être ouvert dans l'éditeur"

    # 3. L'utilisateur déclenche la génération depuis l'éditeur
    editor.btn_generate.click()

    # Attendre que l'orchestrateur termine
    assert view.orchestrator is not None, "L'orchestrateur doit être instancié"
    # Comme le provider est synchrone/mock, vérifions l'état injecté
    state = view.orchestrator.state
    text_source = state.get_variable("text_source", "")

    # VÉRIFICATION CRITIQUE : Le texte extrait doit atteindre le pipeline
    assert "Ventricule gauche et aorte descendante" in text_source, f"Le texte OCR de la planche 1 est absent de text_source ! Reçu: {text_source!r}"
    assert "Oreillette droite et veine cave supérieure" in text_source, f"Le texte OCR de la planche 2 est absent de text_source ! Reçu: {text_source!r}"


def test_album_tab_reloads_after_subsequent_ocr(qtbot, mock_db):
    """
    Repro Bug : Si un album a été ouvert dans CreationView AVANT la transcription OCR,
    puis transcrit dans DocumentsView, le retour dans CreationView doit recharger le texte OCR
    dans l'éditeur au lieu de conserver l'ancien texte '_Planche non transcrite...'.
    """
    media = MediaModel.create(filename="p1.png", media_type="image", original_name="p1.png", checksum="chk1", mime_type="image/png")
    doc = DocumentModel.create(title="Album Cardio", file_type="album", total_pages=1, content="")
    page = DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="", status="ready")

    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(name="Extracteur", system_prompt="Extrais.", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    provider = CapturedProvider()
    ai_mgr = MagicMock()
    ai_mgr.create_provider_from_config.return_value = provider

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    # 1. Première ouverture alors que l'album n'est pas encore transcrit
    view.load_context({"doc_id": doc.id})
    editor = view.open_editors.get(doc.title)
    assert editor is not None
    assert "Planche non transcrite" in editor.get_text()

    # 2. L'OCR est exécuté en arrière-plan (mise à jour de la page en base)
    page.ocr_text = "Thrombose veineuse profonde fémorale."
    page.save()

    # 3. L'utilisateur clique 'Forger des cartes' depuis l'album (navigation vers CreationView)
    view.load_context({"doc_id": doc.id})

    editor_text = editor.get_text()
    assert "Thrombose veineuse profonde fémorale" in editor_text, f"L'éditeur n'a pas été rechargé après la transcription ! Texte: {editor_text!r}"


def test_untranscribed_album_blocks_generation_with_clear_message(qtbot, mock_db):
    """
    Critère d'acceptation 3 : Si le texte extrait est vide (OCR non fait),
    un message clair invite à transcrire avant génération au lieu d'expédier
    du placeholder au LLM.
    """
    media = MediaModel.create(filename="p1.png", media_type="image", original_name="p1.png", checksum="chk1", mime_type="image/png")
    doc = DocumentModel.create(title="Album Non Transcrit", file_type="album", total_pages=1, content="")
    DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="", status="ready")

    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(name="Extracteur", system_prompt="Extrais.", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    provider = CapturedProvider()
    ai_mgr = MagicMock()
    ai_mgr.create_provider_from_config.return_value = provider

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    view.load_context({"doc_id": doc.id})
    editor = view.open_editors.get(doc.title)
    assert editor is not None

    # L'utilisateur clique sur Générer alors qu'aucune planche n'est transcrite et Vision est OFF
    editor.btn_generate.click()

    # Vérification : l'orchestrateur NE DOIT PAS être lancé sur du texte vide/placeholder
    assert view.orchestrator is None or not view.orchestrator.state.get_variable("text_source", "").startswith("### Planche 1\n\n_Planche non transcrite"), (
        "Le pipeline a été lancé sur le placeholder sans avertir l'utilisateur !"
    )
    assert len(provider.captured_prompts) == 0, "Un appel LLM a été envoyé sur un album non transcrit au lieu de bloquer avec un message !"


def test_album_vision_mode_sends_images_and_ignores_ocr_text(qtbot, mock_db, tmp_path):
    """
    Directive Vision : En Mode Vision, l'extraction de texte OCR est ignorée,
    et le pipeline envoie directement les images des planches sélectionnées en base64 au VLM.
    """
    from PIL import Image

    from ankiforge.utils.paths import get_media_dir

    # Créer un vrai fichier image dans le répertoire média
    media_dir = get_media_dir()
    media_dir.mkdir(parents=True, exist_ok=True)
    img_file = media_dir / "album_vis_p1.png"
    img = Image.new("RGB", (100, 100), color="blue")
    img.save(img_file)

    media = MediaModel.create(filename="album_vis_p1.png", media_type="image", original_name="album_vis_p1.png", checksum="chk_vis", mime_type="image/png")
    doc = DocumentModel.create(title="Album Vision Test", file_type="album", total_pages=1, content="")
    DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="", status="ready")

    from ankiforge.database.models import LLMConfigModel

    engine = LLMConfigModel.create(
        display_name="GPT-4o Vision",
        provider="openai",
        model_id="gpt-4o",
        supports_vision=True,
    )
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(name="VisionExtracteur", system_prompt="Analyse l'image.", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    provider = CapturedProvider()
    ai_mgr = MagicMock()
    ai_mgr.create_provider_from_config.return_value = provider

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()
    # Sélectionner le moteur vision
    for i in range(view.engine_combo.count()):
        if getattr(view.engine_combo.itemData(i), "id", None) == engine.id:
            view.engine_combo.setCurrentIndex(i)
            break

    # Activer le mode Vision
    view.vision_cb.setChecked(True)
    view.load_context({"doc_id": doc.id})
    editor = view.open_editors.get(doc.title)
    assert editor is not None

    # Lancer la génération
    editor.btn_generate.click()

    # Vérifications
    assert view.orchestrator is not None, "L'orchestrateur aurait dû démarrer en mode Vision"
    qtbot.waitUntil(lambda: len(provider.captured_multimodal_payloads) > 0, timeout=5000)
    payload = provider.captured_multimodal_payloads[0]
    img_parts = [p for p in payload if p.get("type") == "image_url"]
    assert len(img_parts) == 1, f"Une image base64 devait être incluse dans le payload ! Reçu: {payload}"
    assert "data:image/png;base64," in img_parts[0]["image_url"]["url"]

    # Vérifier que le texte OCR placeholder n'a pas pollué le prompt
    text_parts = [p.get("text", "") for p in payload if p.get("type") == "text"]
    full_text = " ".join(text_parts)
    assert "Planche non transcrite" not in full_text
    assert "Analyse visuelle multimodale" in full_text


def test_segment_inspector_displays_album_planches(qtbot, mock_db):
    """
    Hypothèse 2 : SegmentInspectorWidget doit afficher les planches de l'album
    avec leurs titres, tokens et cases à cocher au lieu d'afficher 0 fragment.
    """
    from ankiforge.ui.widgets.segment_inspector_widget import SegmentInspectorWidget

    media1 = MediaModel.create(filename="p1.png", media_type="image", original_name="p1.png", checksum="chk1", mime_type="image/png")
    media2 = MediaModel.create(filename="p2.png", media_type="image", original_name="p2.png", checksum="chk2", mime_type="image/png")

    doc = DocumentModel.create(title="Album Cardio", file_type="album", total_pages=2, content="")
    DocumentPageModel.create(document=doc, media=media1, page_number=1, ocr_text="Aorte thoracique descendante.", status="ready")
    DocumentPageModel.create(document=doc, media=media2, page_number=2, ocr_text="", status="ready")

    inspector = SegmentInspectorWidget()
    qtbot.addWidget(inspector)
    inspector.set_document(doc)

    # Vérification : 2 planches doivent être affichées dans la liste
    assert inspector.segments_list.count() == 2, f"L'inspecteur doit afficher 2 planches ! Trouvé : {inspector.segments_list.count()}"

    active_segs = inspector.get_active_segments()
    assert len(active_segs) == 2, "Les 2 planches doivent être cochées par défaut"
    assert active_segs[0]["title"] == "Planche 1"
    assert "Aorte thoracique descendante" in active_segs[0]["content"]
    assert active_segs[0]["tokens"] > 0

    assert active_segs[1]["title"] == "Planche 2"
    assert active_segs[1]["tokens"] == 0


def test_album_vision_mode_synergy_ocr_and_image(qtbot, mock_db, tmp_path):
    """
    ADR 0018 : En Mode Vision, quand la planche a une transcription OCR,
    le prompt multimodal transmet à la fois le texte extrait ET la planche en haute fidélité.
    """
    from PIL import Image

    from ankiforge.database.models import LLMConfigModel
    from ankiforge.utils.paths import get_media_dir

    media_dir = get_media_dir()
    media_dir.mkdir(parents=True, exist_ok=True)
    img_file = media_dir / "album_synergy_p1.png"
    img = Image.new("RGB", (100, 100), color="purple")
    img.save(img_file)

    media = MediaModel.create(filename="album_synergy_p1.png", media_type="image", original_name="album_synergy_p1.png", checksum="chk_syn", mime_type="image/png")
    doc = DocumentModel.create(title="Album Synergie", file_type="album", total_pages=1, content="")
    DocumentPageModel.create(document=doc, media=media, page_number=1, ocr_text="Crosse de l'aorte et tronc brachiocéphalique.", status="ready")

    engine = LLMConfigModel.create(display_name="GPT-4o Vision", provider="openai", model_id="gpt-4o", supports_vision=True)
    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(name="Extractor", system_prompt="Extrais.", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    provider = CapturedProvider()
    ai_mgr = MagicMock()
    ai_mgr.create_provider_from_config.return_value = provider

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    for i in range(view.engine_combo.count()):
        if getattr(view.engine_combo.itemData(i), "id", None) == engine.id:
            view.engine_combo.setCurrentIndex(i)
            break

    view.vision_cb.setChecked(True)
    view.load_context({"doc_id": doc.id})
    editor = view.open_editors.get(doc.title)
    assert editor is not None
    editor.btn_generate.click()

    qtbot.waitUntil(lambda: len(provider.captured_multimodal_payloads) > 0, timeout=5000)
    payload = provider.captured_multimodal_payloads[0]

    # Vérification 1 : L'image est incluse
    img_parts = [p for p in payload if p.get("type") == "image_url"]
    assert len(img_parts) == 1, "La planche d'album doit être jointe en image"

    # Vérification 2 : Le texte OCR est aussi inclus (Synergie Texte + Image)
    text_parts = [p.get("text", "") for p in payload if p.get("type") == "text"]
    full_text = " ".join(text_parts)
    assert "Crosse de l'aorte et tronc brachiocéphalique" in full_text, "Le texte extrait doit être présent dans le prompt multimodal"
    assert "Voici la transcription textuelle extraite des planches" in full_text


def test_album_vision_mode_anthropic_limit_blocked(qtbot, mock_db, tmp_path, monkeypatch):
    """
    ADR 0018 : Si plus de 20 planches sont sélectionnées avec un modèle Anthropic,
    la génération est bloquée avec une invitation à utiliser la Batch Factory.
    """
    from ankiforge.database.models import LLMConfigModel

    engine = LLMConfigModel.create(display_name="Claude 3.5 Sonnet", provider="anthropic", model_id="claude-3-5-sonnet", supports_vision=True)
    doc = DocumentModel.create(title="Gros Album", file_type="album", total_pages=25, content="")
    media = MediaModel.create(filename="dummy.png", media_type="image", original_name="dummy.png", checksum="chk_dum", mime_type="image/png")
    for p_num in range(1, 26):
        DocumentPageModel.create(document=doc, media=media, page_number=p_num, ocr_text="", status="ready")

    deck = DeckModel.create(name="Default")
    nt = NoteTypeModel.create(name="Basique", fields_schema=json.dumps(["Front", "Back"]), templates="[]", css_style="")
    pipe = PipelineModel.create(name="Standard")
    persona = PersonaModel.create(name="Extractor", system_prompt="Extrais.", output_format="json")
    PipelineStepModel.create(pipeline=pipe, persona=persona, step_order=1)

    provider = CapturedProvider()
    ai_mgr = MagicMock()
    ai_mgr.create_provider_from_config.return_value = provider

    view = CreationView(ai_manager=ai_mgr)
    qtbot.addWidget(view)
    view.current_deck = deck
    view.current_model = nt
    view.refresh_data()

    for i in range(view.engine_combo.count()):
        if getattr(view.engine_combo.itemData(i), "id", None) == engine.id:
            view.engine_combo.setCurrentIndex(i)
            break

    view.vision_cb.setChecked(True)
    view.load_context({"doc_id": doc.id})
    editor = view.open_editors.get(doc.title)
    assert editor is not None

    # Sélectionner toutes les 25 planches via le preset "Tout" de l'inspecteur de segments
    view.segment_inspector.btn_preset_all.click()

    toasts = []
    monkeypatch.setattr("ankiforge.ui.views.creation_view.view.show_toast", lambda parent, msg, **kwargs: toasts.append(msg))

    editor.btn_generate.click()

    # Doit être bloqué avant lancement de l'orchestrateur
    assert view.orchestrator is None, "L'orchestrateur ne doit pas être lancé si la limite d'images est dépassée"
    assert len(toasts) == 1
    assert "20 images maximum" in toasts[0]
    assert "Batch Factory" in toasts[0]
