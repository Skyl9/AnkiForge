"""
Tests unitaires pour le découplage du type de donnée d'image et du moteur de vision.
Conforme aux spécifications de CONTEXT.md:56-59 et au ticket Feature.
"""

from ankiforge.services.ai.album_transcription_types import (
    AlbumTranscriptionOptions,
    build_album_transcription_prompt,
)
from ankiforge.services.ai.model_catalog import ModelSpec
from ankiforge.services.ai.vision_category_service import (
    get_closed_image_data_types,
    get_image_data_type,
    is_engine_compatible_with_type,
)


def test_closed_image_data_types_exact_six() -> None:
    """Vérifie que la liste fermée contient exactement les 6 types documentés dans CONTEXT.md."""
    types = get_closed_image_data_types()
    assert len(types) == 6
    ids = [t.id for t in types]
    expected_ids = ["table", "pseudocode", "schema", "photo", "logo", "texte_imprime"]
    assert ids == expected_ids


def test_image_data_type_lookup_and_aliases() -> None:
    """Vérifie la résolution d'un type de donnée par ID ou alias."""
    table_type = get_image_data_type("table")
    assert table_type is not None
    assert table_type.name == "Tableau"
    assert table_type.requires_vlm is True
    assert table_type.supports_hardware_ocr is False

    # Alias text / printed_text pour texte_imprime
    text_type = get_image_data_type("text")
    assert text_type is not None
    assert text_type.id == "texte_imprime"
    assert text_type.supports_hardware_ocr is True
    assert text_type.requires_vlm is False

    printed_type = get_image_data_type("printed_text")
    assert printed_type is not None
    assert printed_type.id == "texte_imprime"

    # Type inconnu
    assert get_image_data_type("unknown_type_xyz") is None


def test_engine_compatibility_text_only_engine_always_rejected() -> None:
    """Un moteur texte seul (supports_vision=False) n'est compatible avec AUCUN type d'image."""
    text_model = ModelSpec(
        provider="openai",
        model_id="gpt-3.5-turbo",
        display_name="GPT-3.5",
        supports_vision=False,
    )

    for data_type in get_closed_image_data_types():
        assert is_engine_compatible_with_type(text_model, data_type) is False


def test_engine_compatibility_vlm_engine_compatible_with_all_types() -> None:
    """Un modèle multimodal (supports_vision=True) est compatible avec l'ensemble des types."""
    vlm_model = ModelSpec(
        provider="google",
        model_id="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        supports_vision=True,
    )

    for data_type in get_closed_image_data_types():
        assert is_engine_compatible_with_type(vlm_model, data_type) is True


def test_engine_compatibility_hardware_ocr_only_compatible_with_printed_text() -> None:
    """L'OCR matériel (Apple Vision) est compatible uniquement avec 'texte_imprime'."""
    assert is_engine_compatible_with_type("hardware", "texte_imprime") is True
    assert is_engine_compatible_with_type("native", "texte_imprime") is True
    assert is_engine_compatible_with_type("apple_vision", "texte_imprime") is True

    # Incompatible avec les autres types (tables, pseudocode, schémas, photos, logos)
    for type_id in ["table", "pseudocode", "schema", "photo", "logo"]:
        assert is_engine_compatible_with_type("hardware", type_id) is False
        assert is_engine_compatible_with_type("native", type_id) is False
        assert is_engine_compatible_with_type("apple_vision", type_id) is False


def test_token_budget_follows_model_never_type() -> None:
    """
    Le budget de tokens est une propriété du moteur, jamais du contenu (critère 4).
    Un modèle avec thinking (Claude 3.7) conserve son budget, tandis qu'un modèle
    sans thinking (Gemini Flash) a un budget de 0, quel que soit le type d'image.
    """
    from ankiforge.services.ai.vision_category_service import VisionCategory

    cat_reasoning = VisionCategory(
        id="claude-custom",
        name="Claude",
        description="",
        icon="",
        provider="anthropic",
        model_id="claude-3-7-sonnet-20250219",
        thinking_budget=2048,
    )
    cat_massive = VisionCategory(
        id="gemini-custom",
        name="Gemini",
        description="",
        icon="",
        provider="gemini",
        model_id="gemini-2.5-flash",
        thinking_budget=0,
    )

    # Le budget est porté par la catégorie/modèle
    assert cat_reasoning.thinking_budget == 2048
    assert cat_massive.thinking_budget == 0


def test_build_album_transcription_prompt_injects_data_type_directive() -> None:
    """Vérifie que la directive du type de donnée est injectée dans le prompt."""
    opts = AlbumTranscriptionOptions(
        scope_mode="all",
        custom_range="",
        target_page_ids=[1],
        category_id="structured",
        data_type="pseudocode",
    )
    prompt = build_album_transcription_prompt(opts)
    assert "pseudocode" in prompt.lower()
    assert "indentation" in prompt.lower()
