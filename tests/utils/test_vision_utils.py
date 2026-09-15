import base64

from ankiforge.utils.vision_utils import (
    _encode_image_base64,
    prepare_multimodal_payload,
    strip_image_tags,
)


def test_strip_image_tags():
    """Vérifie que les balises Markdown et HTML sont bien purgées."""
    text = "Graphe Markdown ![alt](media/img1.png) et HTML <img src='media/img2.jpg'>."
    expected = "Graphe Markdown [IMAGE IGNORÉE] et HTML [IMAGE IGNORÉE]."
    assert strip_image_tags(text) == expected


def test_encode_image_base64(tmp_path):
    """Vérifie l'encodage et la gestion des fichiers manquants."""
    # 1. Cas : L'image n'existe pas
    fake_path = tmp_path / "ghost.jpg"
    assert _encode_image_base64(fake_path) is None

    # 2. Cas : L'image existe
    real_img_path = tmp_path / "test.jpg"
    # On simule un fichier binaire d'image
    real_img_path.write_bytes(b"fake_image_data")

    expected_b64 = base64.b64encode(b"fake_image_data").decode("utf-8")
    assert _encode_image_base64(real_img_path) == expected_b64


def test_prepare_multimodal_payload_no_images(tmp_path):
    """Si pas d'images, le payload ne doit contenir qu'un seul bloc de texte."""
    text = "Un cours très classique sans illustration."
    payload = prepare_multimodal_payload(text, media_dir=tmp_path)

    assert len(payload) == 1
    assert payload[0]["type"] == "text"
    assert payload[0]["text"] == text


def test_prepare_multimodal_payload_with_images_and_duplicates(tmp_path):
    """Vérifie la création du payload, le type MIME et l'ignorance des doublons."""
    # On crée de fausses images dans notre dossier temporaire
    img1 = tmp_path / "schema.png"
    img1.write_bytes(b"data_png")

    img2 = tmp_path / "photo.jpg"
    img2.write_bytes(b"data_jpg")

    # Un texte avec 2 images différentes et 1 doublon !
    text = "Voici le schéma 1 : ![schema](media/schema.png). Voici la photo : <img src='photo.jpg'>. Rappel du schéma 1 : ![doublon](media/schema.png)."

    payload = prepare_multimodal_payload(text, media_dir=tmp_path)

    # On attend EXACTEMENT 3 blocs : 1 texte + 2 images uniques
    assert len(payload) == 3

    # 1. Vérification du bloc Texte (les balises doivent être masquées)
    assert payload[0]["type"] == "text"
    assert "[IMAGE IGNORÉE]" in payload[0]["text"]
    assert "media/schema.png" not in payload[0]["text"]

    # 2. Vérification des blocs Images
    assert payload[1]["type"] == "image_url"
    assert payload[2]["type"] == "image_url"

    urls = [payload[1]["image_url"]["url"], payload[2]["image_url"]["url"]]

    # On vérifie que les MIME types ont bien été déduits depuis l'extension
    assert any("image/png" in url for url in urls)
    assert any("image/jpeg" in url for url in urls)
