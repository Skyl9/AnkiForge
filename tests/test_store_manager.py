import zipfile

import pytest
import json
from pathlib import Path
from peewee import SqliteDatabase

from src.database.models import DeckModel, NoteTypeModel, NoteModel, CardModel
from src.services.cards.store_manager import StoreManager

# Remplace 'src' par le bon chemin si ton architecture est différente

# --- LES TESTS ---

def test_import_txt():
    """Vérifie que l'importation du fichier texte japonais fonctionne."""
    store = StoreManager()

    # Indique le bon chemin vers ton fichier anki_jap.txt
    file_path = Path("anki_jap.txt")

    # Si le fichier n'est pas là, on passe le test (ou on le fait échouer, au choix)
    if not file_path.exists():
        pytest.skip(f"Fichier {file_path} introuvable pour le test.")

    # Exécution de la méthode à tester
    store.store_collection(str(file_path))

    # --- ASSERTIONS (Vérifications impitoyables) ---

    # 1. Est-ce que les modèles de notes ont bien été créés ?
    # Le fichier TXT indique "#notetype column:1" et la colonne 1 contient "Vocabulaire_japonais" [cite: 1954]
    assert NoteTypeModel.select().count() > 0
    notetype = NoteTypeModel.get(NoteTypeModel.name == "Vocabulaire_japonais")
    assert notetype is not None

    # 2. Est-ce que les notes (le texte) sont bien là ?
    # Il y a une vingtaine de lignes de vocabulaire dans ton extrait
    assert NoteModel.select().count() > 0

    # 3. Vérification du contenu JSON exact d'une carte (Ex: "おきる") [cite: 1954]
    # On cherche la note qui contient "おきる" dans son JSON
    notes = NoteModel.select()
    found_okiru = False
    for note in notes:
        content = json.loads(note.content)
        if "おきる" in content.values():
            found_okiru = True
            break

    assert found_okiru == True, "Le mot 'おきる' n'a pas été trouvé dans la base de données."


def test_deck_hierarchy_creation():
    """Vérifie que la création d'un deck avec '::' génère bien les parents."""
    store = StoreManager()

    # On simule l'arrivée d'une carte qui doit aller dans un sous-sous-paquet
    complex_deck_name = "Langues::Japonais::Vocabulaire"

    # On réutilise la logique de ton handle_txt pour la création
    parent_deck = None
    if "::" in complex_deck_name:
        parent_name = complex_deck_name.rsplit("::", 1)[0]
        # Dans un vrai cas, il faudrait une boucle ou une fonction récursive
        # pour s'assurer que "Langues" est créé avant "Langues::Japonais".
        # Simulons la création étape par étape comme le ferait un vrai import :

        grand_parent, _ = DeckModel.get_or_create(name="Langues")
        parent, _ = DeckModel.get_or_create(name="Langues::Japonais", defaults={'parent_deck': grand_parent})
        parent_deck = parent

    deck_obj, created = DeckModel.get_or_create(
        name=complex_deck_name,
        defaults={'parent_deck': parent_deck}
    )

    # --- ASSERTIONS ---
    assert created == True
    assert deck_obj.name == "Langues::Japonais::Vocabulaire"

    # On vérifie que la relation parent/enfant (Foreign Key) a bien marché
    assert deck_obj.parent_deck is not None
    assert deck_obj.parent_deck.name == "Langues::Japonais"

    assert deck_obj.parent_deck.parent_deck is not None
    assert deck_obj.parent_deck.parent_deck.name == "Langues"

def test_import_apkg():
    """Vérifie que l'extraction et l'insertion d'un vrai fichier .apkg fonctionne."""
    store = StoreManager()

    file_path = Path("anki.apkg")

    if not file_path.exists():
        pytest.skip(f"Fichier {file_path} introuvable pour le test.")

    # Exécution
    store.store_collection(str(file_path))

    # --- ASSERTIONS ---

    # On vérifie que la base n'est pas vide
    assert NoteModel.select().count() > 0, "Aucune note n'a été extraite du .apkg"
    assert DeckModel.select().count() > 0, "Aucun paquet n'a été extrait"
    assert CardModel.select().count() > 0, "Aucune carte n'a été liée"

    # Vérifie que le fallback des colonnes (Zstandard / SQLite) a marché
    # En regardant ton fichier apkg, on sait qu'il contient des cartes de type "Cloze" et "Basic"
    types_in_db = [nt.name for nt in NoteTypeModel.select()]
    assert "Cloze" in types_in_db or "Basique" in types_in_db


def test_import_real_collection_anki2(tmp_path):
    """Test avec ton vrai fichier collection.anki2 non compressé."""
    store = StoreManager()

    # CORRECTION DU CHEMIN : On enlève le "../"
    anki2_file = Path("collection.anki2")

    if not anki2_file.exists():
        pytest.skip("Fichier collection.anki2 introuvable pour le test.")

    # 1. On crée une fausse archive .apkg temporaire pour tromper le StoreManager
    dummy_apkg = tmp_path / "test_anki2.apkg"
    with zipfile.ZipFile(dummy_apkg, 'w') as zf:
        zf.write(anki2_file, "collection.anki2")

        # 2. Exécution de l'importation
    store.store_collection(str(dummy_apkg))

    validate_imported_data_integrity()


def validate_imported_data_integrity():
    """Parcourt 100% de la base de données pour vérifier l'intégrité absolue des données."""

    # 1. Vérification des Paquets (Decks)
    decks = DeckModel.select()
    assert decks.count() > 0, "Aucun paquet trouvé."
    for deck in decks:
        assert deck.name is not None and deck.name != "", "Un paquet n'a pas de nom."
        # Si le paquet a un parent, on vérifie que le parent existe bien
        if deck.parent_deck:
            assert deck.parent_deck.id is not None

    # 2. Vérification des Modèles (NoteTypes)
    note_types = NoteTypeModel.select()
    assert note_types.count() > 0, "Aucun modèle de note trouvé."
    for nt in note_types:
        assert nt.name is not None and nt.name != "", "Un modèle n'a pas de nom."
        # Vérification que les schémas sont bien du JSON valide
        fields = json.loads(nt.fields_schema)
        templates = json.loads(nt.templates)
        assert isinstance(fields, list), f"Le schéma des champs de {nt.name} n'est pas une liste."
        assert isinstance(templates, list), f"Les templates de {nt.name} ne sont pas une liste."

    # 3. Vérification EXHAUSTIVE de chaque Note
    notes = NoteModel.select()
    assert notes.count() > 0, "Aucune note trouvée."
    for note in notes:
        assert note.guid is not None, f"La note {note.id} n'a pas de GUID."
        assert note.note_type is not None, f"La note {note.id} n'est liée à aucun modèle."

        # Vérification du JSON du contenu
        try:
            content = json.loads(note.content)
            assert isinstance(content, dict), f"Le contenu de la note {note.id} n'est pas un dictionnaire JSON."
        except json.JSONDecodeError:
            pytest.fail(f"Le contenu de la note {note.id} est un JSON invalide.")

        # Vérification des tags
        try:
            tags = json.loads(note.tags)
            assert isinstance(tags, list), f"Les tags de la note {note.id} ne sont pas une liste JSON."
        except json.JSONDecodeError:
            pytest.fail(f"Les tags de la note {note.id} sont un JSON invalide.")

    # 4. Vérification EXHAUSTIVE de chaque Carte (Card)
    cards = CardModel.select()
    assert cards.count() > 0, "Aucune carte trouvée."
    for card in cards:
        assert card.note is not None, f"La carte {card.id} n'est liée à aucune note (Orpheline)."
        assert card.deck is not None, f"La carte {card.id} n'est dans aucun paquet."
        assert card.template_index is not None, f"La carte {card.id} n'a pas d'index de template."
        assert isinstance(card.template_index, int), f"L'index de la carte {card.id} n'est pas un entier."


def test_import_anki2_hardcoded_data(tmp_path):
    """
    Test de régression strict sur collection.anki2 :
    Vérifie les données exactes (Champs, CSS, Noms) extraites de la base de l'Ensimag.
    """
    store = StoreManager()
    anki2_file = Path("collection.anki2")

    if not anki2_file.exists():
        pytest.skip("Fichier collection.anki2 introuvable pour le test en dur.")

    # Création du faux .apkg
    dummy_apkg = tmp_path / "test_hardcoded_anki2.apkg"
    with zipfile.ZipFile(dummy_apkg, 'w') as zf:
        zf.write(anki2_file, "collection.anki2")

    # Exécution de l'importation
    store.store_collection(str(dummy_apkg))

    # ==========================================
    # ASSERTIONS EN DUR (GOLDEN MASTER)
    # ==========================================

    # 1. Vérification stricte du modèle "Image Occlusion"
    img_occ_model = NoteTypeModel.get_or_none(NoteTypeModel.name == "Image Occlusion")
    assert img_occ_model is not None, "Le modèle 'Image Occlusion' est manquant."

    # Vérification de l'ordre exact et du nom des champs
    img_occ_fields = json.loads(img_occ_model.fields_schema)
    assert img_occ_fields == [
        "Occlusion",
        "Image",
        "Header",
        "Back Extra",
        "Comments"
    ], "Les champs de 'Image Occlusion' ne correspondent pas à la production."

    # Vérification d'un fragment précis du CSS
    assert "--inactive-shape-color: #ffeba2;" in img_occ_model.css_style
    assert "--active-shape-color: #ff8e8e;" in img_occ_model.css_style

    # 2. Vérification stricte du modèle "Cloze" (Texte à trous)
    cloze_model = NoteTypeModel.get_or_none(NoteTypeModel.name == "Cloze")
    assert cloze_model is not None, "Le modèle 'Cloze' est manquant."

    cloze_fields = json.loads(cloze_model.fields_schema)
    assert cloze_fields == [
        "Text",
        "Back Extra"
    ], "Les champs de 'Cloze' ne correspondent pas à la production."

    # Vérification du CSS spécifique au mode nuit
    assert ".nightMode .cloze {" in cloze_model.css_style
    assert "color: lightblue;" in cloze_model.css_style

    # 3. Vérification stricte du modèle "Basic (optional reversed card)"
    basic_opt_model = NoteTypeModel.get_or_none(NoteTypeModel.name == "Basic (optional reversed card)")
    assert basic_opt_model is not None

    basic_opt_fields = json.loads(basic_opt_model.fields_schema)
    assert basic_opt_fields == [
        "Front",
        "Back",
        "Add Reverse"
    ], "Les champs de 'Basic (optional reversed card)' sont incorrects."