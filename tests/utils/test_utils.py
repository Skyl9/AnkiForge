from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.utils.anki_renderer import render_anki_card


# ==========================================
# 1. TESTS DU MOTEUR DE RENDU HTML (Anki)
# ==========================================

def test_render_anki_card_basic_replacement():
    """Vérifie que les balises {{Champ}} sont bien remplacées par le texte."""
    raw_html = "<div class='question'>{{Front}}</div><div class='hint'>{{Indice}}</div>"
    fields = {
        "Front": "Quelle est la capitale de la France ?",
        "Indice": "C'est la ville lumière."
    }

    result = render_anki_card(raw_html=raw_html, css="", fields_dict=fields)

    assert "Quelle est la capitale de la France ?" in result
    assert "C'est la ville lumière." in result
    assert "{{Front}}" not in result


def test_render_anki_card_conditionals():
    """Vérifie que la logique conditionnelle propre à Anki fonctionne."""
    raw_html = """
    {{#Extra}}
        <div class='extra'>Contenu bonus : {{Extra}}</div>
    {{/Extra}}
    {{^Extra}}
        <div class='no-extra'>Aucun bonus.</div>
    {{/Extra}}
    """

    # Cas 1 : Le champ "Extra" est REMPLI
    fields_with_extra = {"Extra": "Une info utile."}
    result_with = render_anki_card(raw_html=raw_html, css="", fields_dict=fields_with_extra)

    assert "Contenu bonus : Une info utile." in result_with
    assert "Aucun bonus." not in result_with

    # Cas 2 : Le champ "Extra" est VIDE
    fields_without_extra = {"Extra": ""}
    result_without = render_anki_card(raw_html=raw_html, css="", fields_dict=fields_without_extra)

    assert "Contenu bonus" not in result_without
    assert "Aucun bonus." in result_without


def test_render_anki_card_mathjax_injection():
    """Vérifie que le script MathJax v3 est bien injecté dans la carte."""
    result = render_anki_card(raw_html="Test", css="", fields_dict={})
    assert "MathJax = {" in result
    assert "tex-chtml.js" in result


# ==========================================
# 2. TESTS DU MEDIA MANAGER (Images)
# ==========================================

def test_media_manager_hashing_and_replacement(tmp_path, monkeypatch):
    """
    Vérifie que les images sont hachées (MD5), copiées, et que le
    Markdown est transformé en balises HTML <img> compatibles.
    """

    # 1. PRÉPARATION DU FAUX ENVIRONNEMENT (Monkeypatch)
    # On crée un faux dossier "media" dans notre dossier temporaire (tmp_path)
    fake_media_dir = tmp_path / "fake_media"

    # On "ment" au MediaManager en lui faisant croire que son dossier MEDIA_DIR est notre faux dossier
    monkeypatch.setattr("src.services.cards.media_manager.MEDIA_DIR", str(fake_media_dir))

    # On crée un faux dossier d'extraction (comme si Marker venait de tourner)
    fake_extract_dir = tmp_path / "marker_output"
    fake_extract_dir.mkdir()

    # On y crée une fausse image JPEG
    fake_image = fake_extract_dir / "_page_1_Figure_2.jpeg"
    fake_image.write_bytes(b"ceci est le contenu binaire de mon image fake")

    # Notre texte Markdown brut (tel que craché par Marker)
    raw_markdown = "Voici un schéma explicatif : ![_page_1_Figure_2.jpeg](_page_1_Figure_2.jpeg) La suite du cours."

    # 2. EXÉCUTION
    manager = MediaManager()
    processed_markdown = manager.process_extracted_folder(
        source_folder=str(fake_extract_dir),
        markdown_content=raw_markdown
    )

    # 3. VÉRIFICATIONS (Assertions)

    # A. Est-ce que l'image a été copiée dans notre (faux) dossier media ?
    assert fake_media_dir.exists(), "Le dossier media cible n'a pas été créé."
    copied_files = list(fake_media_dir.iterdir())
    assert len(copied_files) == 1, "L'image n'a pas été copiée dans le dossier media."

    # B. Est-ce que le nom a bien été haché (il ne doit plus s'appeler _page_1...) ?
    new_image_file = copied_files[0]
    assert new_image_file.name != "_page_1_Figure_2.jpeg", "L'image n'a pas été renommée !"
    assert new_image_file.suffix == ".jpeg", "L'extension de l'image a été perdue."

    # C. Est-ce que le texte Markdown a bien été converti en HTML Anki-friendly ?
    assert "<img src=" in processed_markdown, "La balise HTML <img> n'a pas été générée."
    assert new_image_file.name in processed_markdown, "Le nouveau nom (hash) n'est pas dans la balise HTML."
    assert "![" not in processed_markdown, "Le vieux format Markdown n'a pas été effacé."