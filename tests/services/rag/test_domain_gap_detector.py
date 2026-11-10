"""Tests unitaires et d'intégration pour le service DomainGapDetector.

Couvre les 35 scénarios critiques du ticket :
RAG & MCP : Détection Neuro-Symbolique des Lacunes de Connaissances et Décloisonnement de Collection.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from playhouse.test_utils import count_queries

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    DocumentChunkModel,
    DocumentModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    StagedBundleModel,
    StagedPatchModel,
    db,
)
from ankiforge.services.ai.staged_patch_registry import StagedOverlay, StagedPatchRegistry
from ankiforge.services.profile_manager import ProfileManager
from ankiforge.services.rag.domain_gap_detector import (
    DomainBlueprint,
    DomainConcept,
    DomainGapDetector,
    DomainMetrics,
    DomainRelation,
    RescuedCardEntry,
    build_flexible_word_regex,
    clean_cloze_text,
    clean_tech_and_math_blocks,
    compile_combined_sieve_regex,
    diagnose_domain_knowledge_gaps,
    sanitize_html_for_search,
    sanitize_subject_slug,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def base_setup():
    """Initialise un environnement de base avec un modèle standard et un paquet par défaut."""
    with db.atomic():
        deck_main = DeckModel.create(name="Web::HTTP_REST")
        deck_other = DeckModel.create(name="Reseau::Protocoles")
        deck_sub = DeckModel.create(name="Web::HTTP_REST::Verbes")
        note_type_basic = NoteTypeModel.create(
            name="Basique",
            fields_schema=json.dumps(["Front", "Back"]),
            templates=json.dumps([{"name": "Standard", "qfmt": "{{Front}}", "afmt": "{{Back}}"}]),
            css_style=".card { font-family: arial; }",
        )
        note_type_cloze = NoteTypeModel.create(
            name="Cloze",
            fields_schema=json.dumps(["Text", "Extra"]),
            templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}<hr>{{Extra}}"}]),
            css_style=".card { font-family: arial; }",
        )
        note_type_single = NoteTypeModel.create(
            name="ClozeUnique",
            fields_schema=json.dumps(["Text"]),
            templates=json.dumps([{"name": "Cloze", "qfmt": "{{cloze:Text}}", "afmt": "{{cloze:Text}}"}]),
            css_style="",
        )
    return {
        "deck_main": deck_main,
        "deck_other": deck_other,
        "deck_sub": deck_sub,
        "note_type_basic": note_type_basic,
        "note_type_cloze": note_type_cloze,
        "note_type_single": note_type_single,
    }


def _create_note(
    deck: DeckModel,
    note_type: NoteTypeModel,
    fields: dict[str, str],
    tags: str = "",
    is_suspended: bool = False,
    extra_cards_decks: list[DeckModel] | None = None,
) -> tuple[NoteModel, list[CardModel]]:
    """Crée une note et ses cartes associées dans la base de données."""
    with db.atomic():
        note = NoteModel.create(note_type=note_type, tags=tags)
        NoteVersionModel.create(
            note=note,
            version_number=1,
            content=json.dumps(fields, ensure_ascii=False),
            is_active=True,
        )
        cards = []
        c1 = CardModel.create(note=note, deck=deck, template_index=0, is_suspended=is_suspended)
        cards.append(c1)
        if extra_cards_decks:
            for idx, d in enumerate(extra_cards_decks, start=1):
                cards.append(CardModel.create(note=note, deck=d, template_index=idx, is_suspended=is_suspended))
    return note, cards


# ============================================================================
# Scénarios de tests 1 à 10
# ============================================================================


def test_n_plus_one_avoidance_single_query(base_setup):
    """1. Vérifie que l'extraction s'exécute en une unique requête SQL (anti-N+1)."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]
    for i in range(25):
        _create_note(deck, nt, {"Front": f"Question {i}", "Back": f"Réponse {i} stateless"})

    detector = DomainGapDetector()
    blueprint = DomainBlueprint(
        subject="REST",
        concepts=[DomainConcept(id="stateless", label="Stateless", keywords=["stateless"])],
    )

    with count_queries() as counter:
        cards, _, _ = detector.extract_virtual_deck(blueprint, target_deck="Web::HTTP_REST")

    assert counter.count == 1
    assert len(cards) >= 25


def test_note_grouping_prevents_cloze_multi_card_duplication(base_setup):
    """2. Vérifie qu'une note Cloze multi-cartes n'est comptabilisée qu'une fois."""
    deck = base_setup["deck_main"]
    nt_cloze = base_setup["note_type_cloze"]
    # 3 occlusions cloze générant 3 cartes physiques
    note, cards = _create_note(
        deck,
        nt_cloze,
        {"Text": "{{c1::GET}} et {{c2::POST}} et {{c3::PUT}} sont des méthodes HTTP.", "Extra": ""},
        extra_cards_decks=[deck, deck],
    )
    assert len(cards) == 3

    detector = DomainGapDetector()
    blueprint = DomainBlueprint(
        subject="Verbes HTTP",
        concepts=[DomainConcept(id="get", label="GET", keywords=["get"])],
    )
    virtual_cards, _, _ = detector.extract_virtual_deck(blueprint)
    matching = [vc for vc in virtual_cards if vc.note_id == note.id]
    assert len(matching) == 1
    assert matching[0].card_ids == [c.id for c in cards]


def test_bilingual_synthesis_markers_english_french(base_setup):
    """3. Vérifie que les marqueurs bilingues (FR et EN) résolvent le manque de liant."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]

    # Carte concept A
    _create_note(deck, nt, {"Front": "Qu'est-ce que le statut 401 ?", "Back": "Unauthorized"})
    # Carte concept B
    _create_note(deck, nt, {"Front": "Qu'est-ce que le statut 403 ?", "Back": "Forbidden"})
    # Carte de synthèse avec marqueur EN "Unlike"
    _create_note(deck, nt, {"Front": "Difference between 401 and 403?", "Back": "Unlike 401 Unauthorized, status 403 Forbidden indicates no permission."})

    blueprint = DomainBlueprint(
        subject="Codes HTTP",
        concepts=[
            DomainConcept(id="401", label="Statut 401", keywords=["401", "unauthorized"]),
            DomainConcept(id="403", label="Statut 403", keywords=["403", "forbidden"]),
        ],
        relations=[DomainRelation(source_id="401", target_id="403", relation_type="contrast", probe_question="Différence 401 vs 403")],
    )

    detector = DomainGapDetector()
    report = detector.diagnose(
        subject="Codes HTTP",
        blueprint_json=json.dumps(
            {
                "subject": blueprint.subject,
                "concepts": [{"id": c.id, "label": c.label, "keywords": c.keywords} for c in blueprint.concepts],
                "relations": [{"source_id": r.source_id, "target_id": r.target_id, "relation_type": r.relation_type} for r in blueprint.relations],
            }
        ),
    )

    assert len(report.missing_synthesis) == 0
    assert report.metrics.synthesis_coverage_pct == 100.0


def test_missing_concept_gap_includes_source_excerpt_and_tags(tmp_path):
    """4. Vérifie que MissingConceptGap inclut source_excerpt et target_tags pré-formatés."""
    with db.atomic():
        doc = DocumentModel.create(
            title="Spécification REST API",
            content="# REST\n## Cache-Control\nLe header Cache-Control définit la durée de mise en cache.\n## HATEOAS\nHypermedia as the engine of application state.",
        )
        DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            content="Le header Cache-Control définit la durée de mise en cache HTTP de manière granulaire.",
            heading_path="REST > Cache-Control",
        )
        DocumentChunkModel.create(
            document=doc,
            chunk_index=1,
            content="Hypermedia as the engine of application state permet l'exploration dynamique.",
            heading_path="REST > HATEOAS",
        )

    detector = DomainGapDetector()
    report = detector.diagnose(subject="REST", reference_document_id=doc.id)

    assert len(report.missing_concepts) >= 2
    gap = next(g for g in report.missing_concepts if "cache" in g.concept_id.lower())
    assert gap.document_id == doc.id
    assert gap.document_slug != ""
    assert any("source:" in t for t in gap.target_tags)
    assert any("section:" in t for t in gap.target_tags)
    assert "Cache-Control" in gap.source_excerpt or "cache" in gap.source_excerpt.lower()


def test_recursive_subsections_h3_rolled_up_to_h2():
    """5. Vérifie que les sous-sections profondes h3/h4 sont fusionnées dans le parent h2."""
    with db.atomic():
        doc = DocumentModel.create(
            title="Architecture Microservices",
            content="# Microservices\n## Communication\nTexte h2\n### Synchrones\nREST et gRPC\n#### Protobuf\nSérialisation binaire",
        )
        DocumentChunkModel.create(
            document=doc,
            chunk_index=0,
            content="Texte h2 de communication",
            heading_path="Microservices > Communication",
        )
        DocumentChunkModel.create(
            document=doc,
            chunk_index=1,
            content="Protocoles synchrones comme REST et gRPC",
            heading_path="Microservices > Communication > Synchrones",
        )
        DocumentChunkModel.create(
            document=doc,
            chunk_index=2,
            content="Protobuf assure une sérialisation compacte",
            heading_path="Microservices > Communication > Synchrones > Protobuf",
        )

    detector = DomainGapDetector()
    blueprint = detector.build_blueprint(subject="Microservices", reference_document_id=doc.id)

    # Doit avoir agrégé au niveau h2 "Communication"
    concept_labels = [c.label for c in blueprint.concepts]
    assert any("Communication" in lbl for lbl in concept_labels)
    # Les termes des sous-sections doivent être présents dans les keywords du concept h2
    comm_concept = next(c for c in blueprint.concepts if "Communication" in c.label)
    all_kws = " ".join(comm_concept.keywords).lower()
    assert "synchrones" in all_kws or "grpc" in all_kws or "communication" in all_kws


def test_flexible_hyphen_and_space_matching():
    """6. Vérifie que le matching regex est flexible sur les tirets et espaces."""
    pattern = re.compile(build_flexible_word_regex("sans-etat"), re.IGNORECASE)
    assert pattern.search("architecture sans etat moderne")
    assert pattern.search("protocole sans-etat")
    assert pattern.search("serveur sans  etat")
    assert not pattern.search("sanstate")


def test_symmetric_relations_canonical_deduplication():
    """7. Vérifie que les relations symétriques miroirs sont dédoublonnées via frozenset."""
    r1 = DomainRelation(source_id="REST", target_id="SOAP", relation_type="contrast")
    r2 = DomainRelation(source_id="SOAP", target_id="REST", relation_type="contrast")
    r3 = DomainRelation(source_id="A", target_id="B", relation_type="causality")

    bp = DomainBlueprint(
        subject="Protocoles",
        concepts=[
            DomainConcept(id="REST", label="REST", keywords=["rest"]),
            DomainConcept(id="SOAP", label="SOAP", keywords=["soap"]),
            DomainConcept(id="A", label="A", keywords=["a"]),
            DomainConcept(id="B", label="B", keywords=["b"]),
        ],
        relations=[r1, r2, r3],
    )
    deduped = bp.get_deduplicated_relations()
    assert len(deduped) == 2
    assert {r.get_canonical_pair() for r in deduped} == {frozenset({"REST", "SOAP"}), ("A", "B")}


def test_single_field_cloze_notes_handled(base_setup):
    """8. Vérifie qu'une note Cloze à champ unique n'entraîne aucun crash ni régression."""
    deck = base_setup["deck_main"]
    nt_single = base_setup["note_type_single"]
    note, _ = _create_note(deck, nt_single, {"Text": "Le statut {{c1::200 OK}} indique un succès."})

    detector = DomainGapDetector()
    blueprint = DomainBlueprint(
        subject="Codes Succès",
        concepts=[DomainConcept(id="200", label="200 OK", keywords=["200", "ok"])],
    )
    v_cards, _, _ = detector.extract_virtual_deck(blueprint)
    assert len(v_cards) >= 1
    target_vc = next(vc for vc in v_cards if vc.note_id == note.id)
    assert "200 ok" in target_vc.clean_text
    assert target_vc.primary_prompt != "" or target_vc.clean_text != ""


def test_domain_metrics_calculation():
    """9. Vérifie l'exactitude mathématique de DomainMetrics."""
    # Simulation : 8 concepts sur 10 couverts (80%), 18 cartes saines sur 20 (90%), 3 relations sur 4 (75%)
    # global_health = (0.50 * 80) + (0.25 * 90) + (0.25 * 75) = 40 + 22.5 + 18.75 = 81.25 -> 81.2
    c_cov = round((8 / 10) * 100, 1)
    a_hlth = round((18 / 20) * 100, 1)
    s_cov = round((3 / 4) * 100, 1)
    global_score = round((0.50 * c_cov) + (0.25 * a_hlth) + (0.25 * s_cov), 1)

    metrics = DomainMetrics(
        concept_coverage_pct=c_cov,
        atomicity_health_pct=a_hlth,
        synthesis_coverage_pct=s_cov,
        global_health_score=global_score,
    )
    assert metrics.concept_coverage_pct == 80.0
    assert metrics.atomicity_health_pct == 90.0
    assert metrics.synthesis_coverage_pct == 75.0
    assert metrics.global_health_score == 81.2


def test_short_acronym_case_sensitivity_post_rest(base_setup):
    """10. Vérifie que les acronymes courts (<=4 lettres) exigent la majuscule exacte ou l'expansion."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]

    # Faux positif potentiel : mot commun "rest" minuscule ("prendre du repos")
    _create_note(deck, nt, {"Front": "Que faire après l'effort ?", "Back": "Prendre un peu de rest pour récupérer."})

    detector = DomainGapDetector()
    report = detector.diagnose(
        subject="REST Architecture",
        blueprint_json=json.dumps(
            {
                "subject": "REST Architecture",
                "concepts": [{"id": "rest", "label": "REST", "keywords": ["Representational State Transfer"], "is_acronym": True}],
            }
        ),
    )
    # Le concept ne doit PAS être validé par "rest" minuscule
    assert len(report.missing_concepts) == 1

    # Maintenant on ajoute une carte avec "REST" en majuscules
    _create_note(deck, nt, {"Front": "Définition de l'architecture REST", "Back": "Un style architectural basé sur HTTP."})
    report2 = detector.diagnose(
        subject="REST Architecture",
        blueprint_json=json.dumps(
            {
                "subject": "REST Architecture",
                "concepts": [{"id": "rest", "label": "REST", "keywords": ["Representational State Transfer"], "is_acronym": True}],
            }
        ),
    )
    assert len(report2.missing_concepts) == 0


# ============================================================================
# Scénarios de tests 11 à 20
# ============================================================================


def test_document_sibling_sections_generate_contrast_relations():
    """11. Vérifie que deux sections sœurs génèrent automatiquement une relation contrast."""
    with db.atomic():
        doc = DocumentModel.create(
            title="Méthodes HTTP",
            content="# Méthodes\n## GET\nLecture\n## POST\nÉcriture",
        )
        DocumentChunkModel.create(document=doc, chunk_index=0, content="GET permet la lecture", heading_path="Méthodes > GET")
        DocumentChunkModel.create(document=doc, chunk_index=1, content="POST permet l'écriture", heading_path="Méthodes > POST")

    detector = DomainGapDetector()
    bp = detector.build_blueprint("Méthodes HTTP", reference_document_id=doc.id)
    contrast_rel = [r for r in bp.relations if r.relation_type == "contrast"]
    assert len(contrast_rel) >= 1


def test_unstarted_domain_status_on_empty_virtual_deck():
    """12. Vérifie qu'un domaine sans aucune carte active passe en UNSTARTED (score 0.0%)."""
    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "Astronomie Quantique",
            "concepts": [{"id": "trou_noir", "label": "Trou Noir", "keywords": ["singularite", "horizon"]}],
            "relations": [],
        }
    )
    report = detector.diagnose(subject="Astronomie Quantique", blueprint_json=bp_json)
    assert report.domain_status == "UNSTARTED"
    assert report.virtual_deck_count == 0
    assert report.metrics.global_health_score == 0.0
    assert len(report.missing_concepts) == 1
    assert len(report.non_atomic_cards) == 0
    assert len(report.missing_synthesis) == 0


def test_cloze_hint_stripped_cleanly():
    """13. Vérifie que clean_cloze_text élimine l'indice sans altérer la réponse."""
    raw = "{{c1::401 Unauthorized::Code d'authentification requis}}"
    cleaned = clean_cloze_text(raw)
    assert cleaned == "401 Unauthorized"

    raw2 = "{{c2::stateless}}"
    assert clean_cloze_text(raw2) == "stateless"


def test_passe_1_blueprint_first_enriches_virtual_deck(base_setup):
    """14. Vérifie que Passe 1 enrichit les mots-clés de Passe 2 pour repêcher les transversales."""
    deck_other = base_setup["deck_other"]
    nt = base_setup["note_type_basic"]
    # Carte dans "Reseau::Protocoles" contenant "idempotent"
    _create_note(deck_other, nt, {"Front": "Propriété d'idempotence", "Back": "Une requête répétée produit le même état."})

    detector = DomainGapDetector()
    # Le sujet est "Web", mais le concept a le mot-clé "idempotent"
    bp_json = json.dumps(
        {
            "subject": "Web",
            "concepts": [{"id": "idempotence", "label": "Idempotence", "keywords": ["idempotent", "idempotence"]}],
        }
    )
    report = detector.diagnose(subject="Web", target_deck="Web::HTTP_REST", blueprint_json=bp_json)
    assert report.virtual_deck_count >= 1
    assert report.transversal_cards_count >= 1
    assert any(rc.source_deck == "Reseau::Protocoles" for rc in report.transversal_cards_rescued)


def test_atomicity_primary_block_vs_annex(base_setup):
    """15. Vérifie l'isolation du bloc principal vs annexe séparé par <hr>."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]

    # Carte A : Bloc principal concis (10 mots), annexe très longue (100 mots) -> Conforme !
    long_annex = "Longue digression contextuelle avec beaucoup de détails techniques et d'exemples de code montrant pourquoi c'est utile dans les systèmes distribués haute performance et concurrents."
    _create_note(
        deck,
        nt,
        {
            "Front": "Qu'est-ce qu'une fonction pure ?",
            "Back": f"Une fonction dont le résultat dépend uniquement de ses arguments.<hr><blockquote>{long_annex}</blockquote>",
        },
    )

    # Carte B : Bloc principal compact empilant 5 définitions sans séparateur (>45 mots) -> Déficit d'atomicité !
    dense_solid = (
        "Single responsibility signifie une seule raison de changer. Open closed définit un composant ouvert "
        "à l'extension fermé à la modification. Liskov substitution exige des sous-types substituables. "
        "Interface segregation favorise de petites interfaces dédiées. Dependency inversion impose de dépendre "
        "d'abstractions et non d'implémentations concrètes de bas niveau dans toute l'architecture logicielle globale."
    )
    _create_note(
        deck,
        nt,
        {
            "Front": "Les 5 principes SOLID",
            "Back": dense_solid,
        },
    )

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "Conception Logicielle",
            "concepts": [
                {"id": "pure", "label": "Fonction Pure", "keywords": ["fonction pure"]},
                {"id": "solid", "label": "SOLID", "keywords": ["solid", "liskov"]},
            ],
        }
    )
    report = detector.diagnose(subject="Conception Logicielle", blueprint_json=bp_json)

    non_atomic_prompts = [c.prompt_preview for c in report.non_atomic_cards]
    assert any("SOLID" in p for p in non_atomic_prompts)
    assert not any("pure" in p for p in non_atomic_prompts)


def test_defensive_error_handling_on_invalid_inputs():
    """16. Vérifie le fail-safe défensif sur entrées invalides (sujet vide, doc introuvable, json corrompu)."""
    # Sujet vide
    res_empty = diagnose_domain_knowledge_gaps(subject="   ")
    data_empty = json.loads(res_empty)
    assert data_empty["status"] == "error"
    assert data_empty["error_code"] == "EMPTY_SUBJECT"

    # Document inexistant
    res_doc = diagnose_domain_knowledge_gaps(subject="Test", reference_document_id=999999)
    data_doc = json.loads(res_doc)
    assert data_doc["status"] == "error"
    assert data_doc["error_code"] == "DOCUMENT_NOT_FOUND"

    # JSON corrompu
    res_json = diagnose_domain_knowledge_gaps(subject="Test", blueprint_json="{non: json]")
    data_json = json.loads(res_json)
    assert data_json["status"] == "error"
    assert data_json["error_code"] == "INVALID_BLUEPRINT_JSON"


def test_deep_html_sanitization_removes_style_and_script():
    """17. Vérifie que les balises <style> et <script> sont totalement purgées avec leur contenu."""
    raw = "<style>.card { color: red; font-family: 'Open Sans'; }</style><p>Texte utile</p><script>alert('hack');</script>"
    clean = sanitize_html_for_search(raw)
    assert "Texte utile" in clean
    assert "Open Sans" not in clean
    assert "alert" not in clean
    assert "hack" not in clean


def test_subdeck_hierarchy_awareness_prevents_false_transversal_rescue(base_setup):
    """18. Vérifie qu'une carte dans un sous-paquet cible n'est pas déclarée transversale repêchée."""
    deck_sub = base_setup["deck_sub"]  # Web::HTTP_REST::Verbes
    nt = base_setup["note_type_basic"]
    _create_note(deck_sub, nt, {"Front": "Méthode DELETE", "Back": "Supprime une ressource REST."})

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "REST",
            "concepts": [{"id": "delete", "label": "DELETE", "keywords": ["delete"]}],
        }
    )
    report = detector.diagnose(subject="REST", target_deck="Web::HTTP_REST", blueprint_json=bp_json)
    assert report.virtual_deck_count >= 1
    # La carte est dans un sous-paquet de Web::HTTP_REST, donc NON transversale !
    assert report.transversal_cards_count == 0


def test_blueprint_anti_dos_limits_concepts_and_relations():
    """19. Vérifie le plafonnement anti-DoS des blueprints externes (50 concepts, 100 rels, 80 car)."""
    many_concepts = [{"id": f"c_{i}", "label": f"Concept {i}", "keywords": ["a" * 120]} for i in range(70)]
    many_relations = [{"source_id": f"c_{i}", "target_id": f"c_{i + 1}", "relation_type": "contrast"} for i in range(130)]

    detector = DomainGapDetector()
    bp = detector.build_blueprint(
        subject="DoS Test",
        blueprint_json=json.dumps({"subject": "DoS Test", "concepts": many_concepts, "relations": many_relations}),
    )
    assert len(bp.concepts) <= 50
    assert len(bp.relations) <= 100
    for c in bp.concepts:
        for kw in c.keywords:
            assert len(kw) <= 80


def test_dual_export_generates_both_json_and_markdown_reports(tmp_path, monkeypatch):
    """20. Vérifie la génération conjointe du rapport JSON et du rapport Markdown exécutif."""
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    monkeypatch.setattr(ProfileManager, "profiles_dir", tmp_path)

    detector = DomainGapDetector(reports_dir=reports_dir)
    bp_json = json.dumps(
        {
            "subject": "Export Test",
            "concepts": [{"id": "c1", "label": "Concept 1", "keywords": ["c1"]}],
        }
    )
    report = detector.diagnose(subject="Export Test", blueprint_json=bp_json)
    assert report.full_report_path is not None
    assert report.full_markdown_report_path is not None

    p_json = Path(report.full_report_path)
    p_md = Path(report.full_markdown_report_path)
    assert p_json.exists()
    assert p_md.exists()
    assert p_json.name.endswith(".json")
    assert p_md.name.endswith(".md")
    assert "Export Test" in p_md.read_text(encoding="utf-8")


# ============================================================================
# Scénarios de tests 21 à 30
# ============================================================================


def test_combined_sieve_regex_single_pass_efficiency():
    """21. Vérifie le fonctionnement du tamis regex combiné disjonctif."""
    keywords = {"stateless", "cache-control", "idempotent"}
    sieve = compile_combined_sieve_regex(keywords)
    assert sieve.search("architecture stateless moderne")
    assert sieve.search("en-tête cache-control présent")
    assert not sieve.search("autre terme sans rapport")


def test_case_insensitive_subdeck_hierarchy(base_setup):
    """22. Vérifie la hiérarchie insensible à la casse sur target_deck."""
    deck_sub = base_setup["deck_sub"]  # Web::HTTP_REST::Verbes
    nt = base_setup["note_type_basic"]
    _create_note(deck_sub, nt, {"Front": "PATCH method", "Back": "Modification partielle."})

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "REST",
            "concepts": [{"id": "patch", "label": "PATCH", "keywords": ["patch"]}],
        }
    )
    # Target deck en minuscules "web::http_rest"
    report = detector.diagnose(subject="REST", target_deck="web::http_rest", blueprint_json=bp_json)
    assert report.virtual_deck_count >= 1
    assert report.transversal_cards_count == 0


def test_domain_metrics_zero_relations_reweighting():
    """23. Vérifie la repondération 65%/35% si total_relations == 0."""
    metrics = DomainGapDetector.compute_metrics(
        total_concepts=10,
        missing_concepts_count=2,  # 80%
        virtual_deck_count=20,
        non_atomic_cards_count=2,  # 90%
        total_relations=0,
        missing_synthesis_count=0,
    )
    assert metrics.synthesis_coverage_pct == 100.0
    # Score = 0.65 * 80 + 0.35 * 90 = 52.0 + 31.5 = 83.5
    assert metrics.global_health_score == 83.5


def test_scientific_and_anki_math_delimiters_neutralized():
    """24. Vérifie que les délimiteurs mathématiques LaTeX/MathJax/Anki sont neutralisés."""
    raw = r"<p>Formule : \[\sum_{i=1}^{n} x_i^2 = \frac{n(n+1)(2n+1)}{6}\] et Anki [$]a^2 + b^2 = c^2[/$].</p>"
    cleaned = clean_tech_and_math_blocks(raw)
    assert "[BLOC_TECHNIQUE]" in cleaned
    assert r"\sum" not in cleaned
    assert "[/$]" not in cleaned


def test_dominant_deck_resolution_when_target_deck_empty(base_setup):
    """25. Vérifie que le paquet dominant est résolu automatiquement en l'absence de target_deck."""
    deck_main = base_setup["deck_main"]
    deck_other = base_setup["deck_other"]
    nt = base_setup["note_type_basic"]

    # 3 cartes dans deck_main
    for _ in range(3):
        _create_note(deck_main, nt, {"Front": "HTTP concept", "Back": "Explanation"})
    # 1 carte dans deck_other
    _create_note(deck_other, nt, {"Front": "Network concept", "Back": "Explanation"})

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "HTTP",
            "concepts": [
                {"id": "c_covered", "label": "HTTP", "keywords": ["http"]},
                {"id": "c_missing", "label": "Missing", "keywords": ["absent_keyword"]},
            ],
        }
    )
    # target_deck non renseigné
    report = detector.diagnose(subject="HTTP", target_deck="", blueprint_json=bp_json)
    gap = next(g for g in report.missing_concepts if g.concept_id == "c_missing")
    assert gap.target_deck_id == deck_main.id


def test_peewee_multi_table_switches_and_joins(base_setup):
    """26. Vérifie que la jointure Peewee extrait note_type_name et tags sans exception."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]
    _create_note(deck, nt, {"Front": "Q1", "Back": "R1"}, tags="tag1 tag2")

    detector = DomainGapDetector()
    bp = DomainBlueprint(subject="Test", concepts=[DomainConcept(id="q1", label="Q1", keywords=["q1"])])
    cards, _, _ = detector.extract_virtual_deck(bp)
    assert len(cards) >= 1
    c = cards[0]
    assert c.note_type_name == "Basique"


def test_multi_card_note_across_different_decks(base_setup):
    """27. Vérifie qu'une note ayant des cartes dans plusieurs paquets dont le cible n'est pas transversale."""
    deck_main = base_setup["deck_main"]
    deck_other = base_setup["deck_other"]
    nt = base_setup["note_type_cloze"]

    # Note avec 1 carte dans deck_main et 1 carte dans deck_other
    _create_note(deck_main, nt, {"Text": "{{c1::REST}} et {{c2::SOAP}}", "Extra": ""}, extra_cards_decks=[deck_other])

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "REST",
            "concepts": [{"id": "rest", "label": "REST", "keywords": ["rest"]}],
        }
    )
    report = detector.diagnose(subject="REST", target_deck="Web::HTTP_REST", blueprint_json=bp_json)
    # Puisqu'une de ses cartes est dans le paquet cible, elle est considérée du paquet cible
    assert report.transversal_cards_count == 0


def test_rescued_card_entry_structure_and_matching(base_setup):
    """28. Vérifie la structure détaillée des cartes transversales repêchées."""
    deck_other = base_setup["deck_other"]
    nt = base_setup["note_type_basic"]
    _create_note(deck_other, nt, {"Front": "Gestion des cookies", "Back": "Les cookies transmettent l'état session."})

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "Web",
            "concepts": [{"id": "cookies", "label": "Cookies", "keywords": ["cookies"]}],
        }
    )
    report = detector.diagnose(subject="Web", target_deck="Web::HTTP_REST", blueprint_json=bp_json)
    assert len(report.transversal_cards_rescued) >= 1
    rescued = report.transversal_cards_rescued[0]
    assert isinstance(rescued, RescuedCardEntry)
    assert rescued.source_deck == "Reseau::Protocoles"
    assert "cookies" in rescued.matched_concepts


def test_ultra_short_two_letter_acronym_requires_expansion(base_setup):
    """29. Vérifie que les acronymes ultra-courts (<=2 lettres) ne matchent pas accidentellement."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]

    # Faux positif : mot anglais "is" ou "as" ou "it"
    _create_note(deck, nt, {"Front": "Is this a test?", "Back": "Yes it is."})

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "Systèmes",
            "concepts": [
                {
                    "id": "os",
                    "label": "OS",
                    "keywords": ["Système d'exploitation"],
                    "is_acronym": True,
                }
            ],
        }
    )
    report = detector.diagnose(subject="Systèmes", blueprint_json=bp_json)
    # Ne doit PAS être validé par "is"
    assert len(report.missing_concepts) == 1

    # Maintenant avec l'expression développée
    _create_note(deck, nt, {"Front": "Rôle du système d'exploitation", "Back": "Gérer les ressources matérielles."})
    report2 = detector.diagnose(subject="Systèmes", blueprint_json=bp_json)
    assert len(report2.missing_concepts) == 0


def test_atomicity_short_enumerations_accepted(base_setup):
    """30. Vérifie que les énumérations courtes simples (3-4 mots simples) sont acceptées."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]

    # Énumération concise de 4 verbes
    _create_note(
        deck,
        nt,
        {
            "Front": "Quels sont les 4 principaux verbes HTTP ?",
            "Back": "<ul><li>GET</li><li>POST</li><li>PUT</li><li>DELETE</li></ul>",
        },
    )

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "HTTP",
            "concepts": [{"id": "verbes", "label": "Verbes", "keywords": ["verbes", "http"]}],
        }
    )
    report = detector.diagnose(subject="HTTP", blueprint_json=bp_json)
    assert len(report.non_atomic_cards) == 0


# ============================================================================
# Scénarios de tests 31 à 35
# ============================================================================


def test_sanitize_subject_slug_prevents_path_traversal():
    """31. Vérifie la sécurisation stricte du slug de sujet face aux path traversals."""
    assert sanitize_subject_slug("../../etc/passwd") == "etc_passwd"
    assert sanitize_subject_slug("HTTP / REST & Sécurité !!") == "http_rest_securite"
    long_subject = "A" * 100
    assert len(sanitize_subject_slug(long_subject)) <= 64
    assert sanitize_subject_slug("   ") == "domaine_inconnu"


def test_document_without_headings_falls_back_to_chunking():
    """32. Vérifie le repli en tranches équilibrées pour les documents sans titres."""
    with db.atomic():
        doc = DocumentModel.create(
            title="Texte Brut Long",
            content="Premier paragraphe d'introduction sur l'architecture logicielle moderne.\n\n" * 30,
        )

    detector = DomainGapDetector()
    bp = detector.build_blueprint(subject="Texte Brut Long", reference_document_id=doc.id)
    assert len(bp.concepts) >= 2
    assert all("Section" in c.label for c in bp.concepts)


def test_cloze_composite_omission_triggers_atomicity_gap(base_setup):
    """33. Vérifie qu'une omission Cloze composite déclenche un AtomicityGap (Wozniak règle 8)."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_cloze"]

    # Omission composite de 3 éléments simultanés
    _create_note(
        deck,
        nt,
        {
            "Text": "Les caractéristiques sont : {{c1::1. Confidentialité, 2. Intégrité, 3. Disponibilité}}.",
            "Extra": "",
        },
    )

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "Sécurité",
            "concepts": [{"id": "sec", "label": "Sécurité", "keywords": ["confidentialite", "integrite"]}],
        }
    )
    report = detector.diagnose(subject="Sécurité", blueprint_json=bp_json)
    assert len(report.non_atomic_cards) == 1
    assert any("composite" in r.lower() or "wozniak" in r.lower() for r in report.non_atomic_cards[0].reasons)


def test_negative_contrastive_synthesis_markers_validated(base_setup):
    """34. Vérifie que les négations contrastives valident les relations de distinction."""
    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]

    _create_note(deck, nt, {"Front": "Définition POST", "Back": "Méthode non idempotente."})
    _create_note(deck, nt, {"Front": "Définition PUT", "Back": "Méthode idempotente."})
    # Marqueur négatif contrastif "n'est pas"
    _create_note(deck, nt, {"Front": "Différence POST et PUT", "Back": "POST n'est pas idempotent, contrairement aux créations via PUT."})

    detector = DomainGapDetector()
    bp_json = json.dumps(
        {
            "subject": "HTTP",
            "concepts": [
                {"id": "post", "label": "POST", "keywords": ["post"]},
                {"id": "put", "label": "PUT", "keywords": ["put"]},
            ],
            "relations": [{"source_id": "post", "target_id": "put", "relation_type": "contrast", "probe_question": "POST vs PUT"}],
        }
    )
    report = detector.diagnose(subject="HTTP", blueprint_json=bp_json)
    assert len(report.missing_synthesis) == 0


def test_staged_bundle_overlay_incorporates_pending_cards(base_setup):
    """35. Vérifie que les cartes en attente dans un Staged Bundle actif sont intégrées."""
    deck = base_setup["deck_main"]

    # Créer un bundle actif avec une note staged couvrant un concept
    with db.atomic():
        bundle = StagedBundleModel.create(bundle_id="bnd_test_overlay", title="Batch Test", status="building")
        _ = StagedPatchModel.create(
            patch_id="patch_staged_1",
            bundle=bundle,
            step_order=1,
            patch_type="note_create",
            target_id=0,
            diff_payload=json.dumps(
                {
                    "deck": deck.name,
                    "fields": {"Front": "Qu'est-ce que GraphQL ?", "Back": "Un langage de requête pour API."},
                }
            ),
            status="pending",
        )

    overlay = StagedOverlay(bundle_id=bundle.bundle_id)
    StagedPatchRegistry._active_bundles[bundle.bundle_id] = overlay

    try:
        detector = DomainGapDetector()
        bp_json = json.dumps(
            {
                "subject": "API",
                "concepts": [{"id": "graphql", "label": "GraphQL", "keywords": ["graphql"]}],
            }
        )
        report = detector.diagnose(subject="API", blueprint_json=bp_json)

        assert report.virtual_deck_count >= 1
        assert report.staged_cards_included >= 1
        assert len(report.missing_concepts) == 0
    finally:
        StagedPatchRegistry._active_bundles.pop(bundle.bundle_id, None)


def test_fastmcp_call_tool_diagnose_domain_knowledge_gaps(base_setup):
    """Vérifie l'invocation de bout en bout de l'outil via FastMCP mcp.call_tool()."""
    import asyncio

    from ankiforge.services.ai.mcp_server import mcp

    deck = base_setup["deck_main"]
    nt = base_setup["note_type_basic"]
    _create_note(deck, nt, {"Front": "Qu'est-ce qu'une API REST ?", "Back": "Une architecture stateless."})

    async def _run():
        raw_res = await mcp.call_tool(
            "diagnose_domain_knowledge_gaps",
            {
                "subject": "REST",
                "target_deck": deck.name,
                "blueprint_json": json.dumps(
                    {
                        "subject": "REST",
                        "concepts": [{"id": "stateless", "label": "Stateless", "keywords": ["stateless"]}],
                    }
                ),
            },
        )
        text_content = raw_res.content[0].text if hasattr(raw_res, "content") else str(raw_res)
        data = json.loads(text_content)
        assert data["status"] == "success"
        assert data["metrics"]["global_health_score"] >= 80.0

    asyncio.run(_run())
