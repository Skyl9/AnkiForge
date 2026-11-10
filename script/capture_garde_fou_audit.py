"""Script de capture d'écran exhaustif pour l'audit de l'onglet Garde-Fou & Validation."""

import json
import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["ANKIFORGE_MOCK_WEBENGINE"] = "1"
os.environ["QTWEBENGINE_DISABLE_SANDBOX"] = "1"

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedBundleModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
from ankiforge.ui.style_engine import get_style_engine
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.consultant_view.widgets.mcp_garde_fou_widget import MCPGardeFouWidget
from ankiforge.utils.paths import get_project_root


def setup_test_db():
    from ankiforge.database.models import (
        FlagDefinitionModel,
        StagedBundleModel,
        StagedPatchModel,
    )

    models = [
        DeckModel,
        NoteTypeModel,
        NoteModel,
        CardModel,
        NoteVersionModel,
        StagedBundleModel,
        StagedPatchModel,
        FlagDefinitionModel,
    ]

    db.init(":memory:")
    db.bind(models, bind_refs=False, bind_backrefs=False)
    db.connect()
    db.execute_sql("PRAGMA foreign_keys = ON;")
    db.create_tables(models)

    # Création des modèles et données de base
    nt_basic = NoteTypeModel.create(
        name="Basique",
        fields_schema=json.dumps(["Front", "Back"]),
        templates=json.dumps([{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}]),
        css_style=".card { font-family: arial; font-size: 20px; text-align: center; color: black; background-color: white; }",
    )

    nt_cloze = NoteTypeModel.create(
        name="Texte à trous",
        fields_schema=json.dumps(["Text", "Extra"]),
        templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<br>{{Extra}}"}]),
        css_style=".cloze { font-weight: bold; color: blue; }",
    )

    deck_physique = DeckModel.create(name="Sciences::Physique Quantique", description="Notions clés de physique moderne")
    deck_japonais = DeckModel.create(name="Langues::Japonais", description="Vocabulaire JLPT N5")

    # Note 1 : Basique
    note_basic = NoteModel.create(note_type=nt_basic, tags="physique quantique formule")
    NoteVersionModel.create(
        note=note_basic,
        version_number=1,
        content=json.dumps(
            {
                "Front": "Quelle est la formule de la longueur d'onde de de Broglie ?",
                "Back": "La longueur d'onde est donnée par lambda = h / p où h est la constante de Planck et p la quantité de mouvement.",
            }
        ),
        is_active=True,
    )
    CardModel.create(note=note_basic, deck=deck_physique)

    # Note 2 : Cloze
    note_cloze = NoteModel.create(note_type=nt_cloze, tags="physique quantique heisenberg")
    NoteVersionModel.create(
        note=note_cloze,
        version_number=1,
        content=json.dumps(
            {
                "Text": "Le principe d'incertitude d'{{c1::Heisenberg}} stipule que Delta x * Delta p >= {{c2::hbar / 2}}.",
                "Extra": "Formulé en 1927 par Werner Heisenberg.",
            }
        ),
        is_active=True,
    )
    CardModel.create(note=note_cloze, deck=deck_physique)

    return {
        "nt_basic": nt_basic,
        "nt_cloze": nt_cloze,
        "deck_physique": deck_physique,
        "deck_japonais": deck_japonais,
        "note_basic": note_basic,
        "note_cloze": note_cloze,
    }


def main():
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont(DesignTokens.FONT_MAIN, DesignTokens.FONT_SIZE_BASE))

    engine = get_style_engine()
    engine.apply_theme("ide", app)

    out_dir = get_project_root() / "temp" / "screens" / "garde_fou"
    out_dir.mkdir(parents=True, exist_ok=True)

    entities = setup_test_db()

    # -------------------------------------------------------------
    # 1. ÉTAT VIDE
    # -------------------------------------------------------------
    widget = MCPGardeFouWidget()
    widget.resize(1280, 800)
    widget.show()
    widget.reload_pending_patches()
    app.processEvents()

    path_empty = out_dir / "01_garde_fou_empty.png"
    widget.grab().save(str(path_empty))
    print(f"✅ Capture 1 (Vide) : {path_empty}")

    # -------------------------------------------------------------
    # PEUPLEMENT DES DIFFÉRENTS TYPES DE PATCHS
    # -------------------------------------------------------------
    # A. Patch 1 : Modification Carte Basique (Note Update)
    patch_basic = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=entities["note_basic"].id,
        diff_payload={
            "type": "card",
            "note_id": entities["note_basic"].id,
            "title": "Optimisation formule de Broglie (Wozniak #4)",
            "original": {
                "Front": "Quelle est la formule de la longueur d'onde de de Broglie ?",
                "Back": "La longueur d'onde est donnée par lambda = h / p où h est la constante de Planck et p la quantité de mouvement.",
            },
            "modified": {
                "Front": "Longueur d'onde de matière de <b>de Broglie</b> (lambda = ?) :",
                "Back": "<b>lambda = h / p</b><br><small>h : cte de Planck, p : quantité de mouvement</small>",
            },
        },
    )

    # B. Patch 2 : Modification Carte Cloze (Texte à trous)
    patch_cloze = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=entities["note_cloze"].id,
        diff_payload={
            "type": "card",
            "note_id": entities["note_cloze"].id,
            "title": "Précision historique incertitude Heisenberg",
            "original": {
                "Text": "Le principe d'incertitude d'{{c1::Heisenberg}} stipule que Delta x * Delta p >= {{c2::hbar / 2}}.",
                "Extra": "Formulé en 1927 par Werner Heisenberg.",
            },
            "modified": {
                "Text": "Le principe d'incertitude formulé par {{c1::Werner Heisenberg}} (1927) relie position et impulsion par Delta x * Delta p >= {{c2::hbar / 2}}.",
                "Extra": "Conséquence directe de la nature ondulatoire quantique.",
            },
        },
    )

    # C. Patch 3 : Création de Carte (Note Create)
    patch_create = StagedPatchRegistry.create_patch(
        patch_type="note_create",
        diff_payload={
            "title": "Nouvelle carte : Vocabulaire 猫 (chat)",
            "deck_id": entities["deck_japonais"].id,
            "deck_name": entities["deck_japonais"].name,
            "model_id": entities["nt_basic"].id,
            "model_name": entities["nt_basic"].name,
            "fields": {
                "Front": "猫 (kanji & lecture) :",
                "Back": "<b>ねこ</b> (neko) — Chat 🐱",
            },
            "tags": "japonais vocabulaire animaux n5",
        },
    )

    # D. Patch 4 : Suppression de cartes (Impact Deletion)
    patch_delete = StagedPatchRegistry.create_patch(
        patch_type="batch_card_deletion",
        target_id=entities["note_basic"].id,
        diff_payload={
            "title": "Suppression cartes obsolètes hors programme",
            "card_ids": [entities["note_basic"].id],
            "impact_summary": {
                "cards_count": 3,
                "notes_count": 1,
                "decks_affected": ["Sciences::Physique Quantique"],
                "reviews_lost": 42,
            },
            "reason": "Doublon détecté avec le cours d'électromagnétisme",
        },
    )

    # E. Patch 5 : Modification de Tags (Tag Diff)
    patch_tags = StagedPatchRegistry.create_patch(
        patch_type="set_tags",
        target_id=entities["note_basic"].id,
        diff_payload={
            "title": "Nettoyage taxonomie tags physique",
            "note_id": entities["note_basic"].id,
            "tags_before": ["physique", "quantique", "formule", "brouillon"],
            "tags_after": ["sciences::physique", "physique-quantique", "examen::juin"],
            "tags_added": ["sciences::physique", "physique-quantique", "examen::juin"],
            "tags_removed": ["physique", "quantique", "formule", "brouillon"],
        },
    )

    # F. Patch 6 & 7 dans un Staged Bundle multi-étapes
    bundle = StagedBundleModel.create(
        bundle_id="bnd_quantum_pack_2026",
        title="Restructuration du module Physique Quantique",
        explanation="Création du sous-paquet et injection des théorèmes fondamentaux",
        total_steps=2,
        current_step=1,
        status="pending",
    )

    patch_bundle_step1 = StagedPatchModel.create(
        patch_id="patch_bnd_step_1",
        bundle=bundle,
        step_order=1,
        patch_type="deck_create",
        status="pending",
        diff_payload=json.dumps(
            {
                "title": "Créer sous-paquet Sciences::Physique Quantique::Ondes",
                "deck_name": "Sciences::Physique Quantique::Ondes",
                "description": "Étude des fonctions d'onde et de l'équation de Schrödinger",
            }
        ),
    )

    StagedPatchModel.create(
        patch_id="patch_bnd_step_2",
        bundle=bundle,
        step_order=2,
        patch_type="card",
        target_id=entities["note_basic"].id,
        status="pending",
        diff_payload=json.dumps(
            {
                "title": "Déplacement vers le nouveau paquet et reformulation",
                "original": {"Front": "Question A", "Back": "Réponse A"},
                "modified": {"Front": "Équation de Schrödinger indépendante du temps :", "Back": "H |psi> = E |psi>"},
            }
        ),
    )

    # H. Patch 9 : Scission atomique de carte (card_split)
    patch_split = StagedPatchRegistry.create_patch(
        patch_type="card_split",
        target_id=entities["note_basic"].id,
        diff_payload={
            "type": "card_split",
            "note_id": entities["note_basic"].id,
            "title": "Scission atomique : Dualité onde-corpuscule",
            "original": {
                "Front": "Expliquer la dualité onde-corpuscule et donner la formule de de Broglie.",
                "Back": "La matière possède à la fois des propriétés d'ondes et de particules. La longueur d'onde associée est lambda = h / p.",
            },
            "modified": [
                {
                    "Front": "Qu'énonce le principe de <b>dualité onde-corpuscule</b> ?",
                    "Back": "Toute particule matérielle manifeste simultanément des propriétés ondulatoires et corpusculaires.",
                },
                {
                    "Front": "Formule de la <b>longueur d'onde de de Broglie</b> (lambda = ?) :",
                    "Back": "lambda = h / p (avec h cte de Planck, p impulsion)",
                },
            ],
        },
    )

    # I. Patch 10 : Lot de création de notes (batch_note_create)
    patch_batch_create = StagedPatchRegistry.create_patch(
        patch_type="batch_note_create",
        diff_payload={
            "title": "Lot de 3 kanjis JLPT N5",
            "deck_id": entities["deck_japonais"].id,
            "deck_name": entities["deck_japonais"].name,
            "model_id": entities["nt_basic"].id,
            "model_name": entities["nt_basic"].name,
            "notes": [
                {"fields": {"Front": "日 (sens & lecture)", "Back": "Jour, Soleil — にち (nichi) / ひ (hi)"}, "tags": "kanji n5"},
                {"fields": {"Front": "月 (sens & lecture)", "Back": "Lune, Mois — げつ (getsu) / つき (tsuki)"}, "tags": "kanji n5"},
                {"fields": {"Front": "木 (sens & lecture)", "Back": "Arbre, Bois — もく (moku) / き (ki)"}, "tags": "kanji n5"},
            ],
        },
    )

    # J. Patch 11 : Refactorisation de modèle de note (note_type_refactor)
    patch_model_refactor = StagedPatchRegistry.create_patch(
        patch_type="note_type_refactor",
        target_id=entities["nt_basic"].id,
        diff_payload={
            "title": "Modernisation typographique du modèle Basique",
            "note_type_id": entities["nt_basic"].id,
            "note_type_name": "Basique",
            "templates_before": [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"}],
            "templates_after": [{"name": "Carte 1", "qfmt": "<div class='card front'>{{Front}}</div>", "afmt": "{{FrontSide}}<hr id=answer><div class='card back'>{{Back}}</div>"}],
            "css_before": ".card { font-family: arial; font-size: 20px; }",
            "css_after": ".card { font-family: 'Inter', sans-serif; font-size: 18px; line-height: 1.5; color: #1e293b; }\n.front { font-weight: 600; }\n.back { color: #334155; }",
        },
    )
    patch_aborted = StagedPatchRegistry.create_patch(
        patch_type="card",
        target_id=entities["note_basic"].id,
        diff_payload={
            "title": "Proposition rejetée par auto-critique LLM",
            "original": {"Front": "Question X", "Back": "Réponse X"},
            "modified": {"Front": "Question trop longue avec plein de détails superflus...", "Back": "Réponse..."},
        },
    )
    patch_aborted.status = "aborted"
    patch_aborted.reason = "Violation règle #4 Wozniak (plus de 50 mots) détectée par le linter interne"
    patch_aborted.save()

    # Recharger le widget avec tous les patches
    widget.reload_pending_patches()
    app.processEvents()

    # -------------------------------------------------------------
    # 2. CAPTURE : Modification Carte Basique (Diff sémantique)
    # -------------------------------------------------------------
    # Sélectionner le premier patch (patch_basic)
    widget._display_patch(patch_basic)
    app.processEvents()
    path_basic = out_dir / "02_garde_fou_basic_card_diff.png"
    widget.grab().save(str(path_basic))
    print(f"✅ Capture 2 (Basic Diff) : {path_basic}")

    # -------------------------------------------------------------
    # 3. CAPTURE : Modification Carte Basique (Aperçu Anki si onglet existe)
    # -------------------------------------------------------------
    if hasattr(widget.diff_viewer, "tab_widget"):
        widget.diff_viewer.tab_widget.setCurrentIndex(1)
        app.processEvents()
        path_preview = out_dir / "03_garde_fou_basic_card_preview.png"
        widget.grab().save(str(path_preview))
        print(f"✅ Capture 3 (Basic Preview) : {path_preview}")
        widget.diff_viewer.tab_widget.setCurrentIndex(0)
        app.processEvents()

    # -------------------------------------------------------------
    # 4. CAPTURE : Modification Carte Texte à trous (Cloze Diff)
    # -------------------------------------------------------------
    widget._display_patch(patch_cloze)
    app.processEvents()
    path_cloze = out_dir / "04_garde_fou_cloze_card_diff.png"
    widget.grab().save(str(path_cloze))
    print(f"✅ Capture 4 (Cloze Diff) : {path_cloze}")

    # -------------------------------------------------------------
    # 5. CAPTURE : Création de Carte (Card Create View)
    # -------------------------------------------------------------
    widget._display_patch(patch_create)
    app.processEvents()
    path_create_screen = out_dir / "05_garde_fou_card_create.png"
    widget.grab().save(str(path_create_screen))
    print(f"✅ Capture 5 (Card Create) : {path_create_screen}")

    # -------------------------------------------------------------
    # 6. CAPTURE : Suppression de Cartes (Impact Deletion)
    # -------------------------------------------------------------
    widget._display_patch(patch_delete)
    app.processEvents()
    path_delete_screen = out_dir / "06_garde_fou_card_delete_impact.png"
    widget.grab().save(str(path_delete_screen))
    print(f"✅ Capture 6 (Delete Impact) : {path_delete_screen}")

    # -------------------------------------------------------------
    # 7. CAPTURE : Modification de Tags (Tag Diff)
    # -------------------------------------------------------------
    widget._display_patch(patch_tags)
    app.processEvents()
    path_tags_screen = out_dir / "07_garde_fou_tag_diff.png"
    widget.grab().save(str(path_tags_screen))
    print(f"✅ Capture 7 (Tag Diff) : {path_tags_screen}")

    # -------------------------------------------------------------
    # 8. CAPTURE : Bundle multi-étapes
    # -------------------------------------------------------------
    widget._display_patch(patch_bundle_step1)
    app.processEvents()
    path_bundle_screen = out_dir / "08_garde_fou_bundle_step1.png"
    widget.grab().save(str(path_bundle_screen))
    print(f"✅ Capture 8 (Bundle Step 1) : {path_bundle_screen}")

    # -------------------------------------------------------------
    # 9. CAPTURE : Filtre Annulés et Patch Annulé
    # -------------------------------------------------------------
    widget._set_status_filter("aborted")
    app.processEvents()
    widget._display_patch(patch_aborted)
    app.processEvents()
    path_aborted_screen = out_dir / "09_garde_fou_aborted_patch.png"
    widget.grab().save(str(path_aborted_screen))
    print(f"✅ Capture 9 (Aborted) : {path_aborted_screen}")

    # Revenir en filtre pending
    widget._set_status_filter("pending")
    app.processEvents()

    # -------------------------------------------------------------
    # 11. CAPTURE : Scission Atomique de Carte (card_split)
    # -------------------------------------------------------------
    widget._display_patch(patch_split)
    app.processEvents()
    path_split_screen = out_dir / "11_garde_fou_card_split.png"
    widget.grab().save(str(path_split_screen))
    print(f"✅ Capture 11 (Card Split) : {path_split_screen}")

    # -------------------------------------------------------------
    # 12. CAPTURE : Lot de Création de Cartes (batch_note_create)
    # -------------------------------------------------------------
    widget._display_patch(patch_batch_create)
    app.processEvents()
    path_batch_create_screen = out_dir / "12_garde_fou_batch_create.png"
    widget.grab().save(str(path_batch_create_screen))
    print(f"✅ Capture 12 (Batch Create) : {path_batch_create_screen}")

    # -------------------------------------------------------------
    # 13. CAPTURE : Refactorisation Modèle de Note (note_type_refactor)
    # -------------------------------------------------------------
    widget._display_patch(patch_model_refactor)
    app.processEvents()
    path_model_refactor_screen = out_dir / "13_garde_fou_note_type_refactor.png"
    widget.grab().save(str(path_model_refactor_screen))
    print(f"✅ Capture 13 (Model Refactor) : {path_model_refactor_screen}")

    # -------------------------------------------------------------
    # 14. CAPTURE : Thème Clair (JetBrains Light)
    # -------------------------------------------------------------
    engine.apply_theme("jetbrains_light", app)
    widget.refresh_theme(engine.current_theme)
    app.processEvents()
    widget._display_patch(patch_basic)
    app.processEvents()
    path_light_screen = out_dir / "14_garde_fou_light_clean.png"
    widget.grab().save(str(path_light_screen))
    print(f"✅ Capture 14 (Light Theme) : {path_light_screen}")

    # Rétablir le thème sombre IDE
    engine.apply_theme("jetbrains_dark", app)
    widget.refresh_theme(engine.current_theme)
    app.processEvents()


if __name__ == "__main__":
    main()
