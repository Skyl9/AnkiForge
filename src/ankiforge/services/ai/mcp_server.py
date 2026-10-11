import json
import logging
from collections.abc import Callable
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer

from ankiforge.database.models import LLMConfigModel, NoteModel, NoteTypeModel, db
from ankiforge.services.ai.consultant_engine import ConsultantToolRegistry
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.utils.jinja_sandbox import create_prompt_environment

__all__ = ["mcp", "register_mutation_listener", "run_server", "unregister_mutation_listener"]

logger = logging.getLogger(__name__)

# Écouteurs de mutations externes appliquées via les outils MCP
_mutation_listeners: list[Callable[[dict[str, Any]], None]] = []


def register_mutation_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Enregistre un écouteur de mutation de données via MCP."""
    if callback not in _mutation_listeners:
        _mutation_listeners.append(callback)


def unregister_mutation_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Retire un écouteur de mutation."""
    if callback in _mutation_listeners:
        _mutation_listeners.remove(callback)


def _notify_mcp_mutation(data: dict[str, Any]) -> None:
    """Notifie les écouteurs enregistrés et le bus d'événements central."""
    from ankiforge.utils.event_bus import MCPDataMutatedEvent, event_bus

    try:
        event_bus.publish(
            MCPDataMutatedEvent(
                mutation_type=str(data.get("type", "")),
                target_id=int(data.get("target_id") or data.get("parent_note_id") or data.get("note_id") or 0),
                target_name=str(data.get("note_type_name", "")),
                details=data,
            )
        )
    except Exception as e:
        logger.debug("Erreur publication event_bus MCPDataMutatedEvent : %s", e)

    for listener in list(_mutation_listeners):
        try:
            listener(data)
        except Exception as e:
            logger.warning("Erreur dans l'écouteur de mutation MCP : %s", e)


# Environnement Jinja2 sandboxé (partagé) pour l'interpolation des prompts.
_PROMPT_ENV = create_prompt_environment()

# Initialisation du serveur MCP AnkiForge
mcp = MCPServer("AnkiForge")


@mcp.tool()
def audit_deck_wozniak(deck_name: str) -> str:
    """Effectue un audit de qualité Wozniak complet sur un paquet (20 règles de formulation, atomicité, redondance)."""
    return ConsultantToolRegistry.audit_deck_wozniak(deck_name)


@mcp.tool()
def audit_card_wozniak(note_id: int) -> str:
    """Analyse chirurgicale d'une carte spécifique au regard des 20 règles de Piotr Wozniak."""
    return ConsultantToolRegistry.audit_card_wozniak(note_id)


@mcp.tool()
def find_duplicate_cards(deck_name: str = "", threshold: float = 0.75) -> str:
    """Détecte les cartes doublons ou formulées de manière quasi-identique dans un paquet via distance Levenshtein."""
    return ConsultantToolRegistry.find_duplicate_cards(deck_name, threshold)


@mcp.tool()
def propose_card_refactor(note_id: int, new_fields_json: str, explanation: str = "") -> str:
    """Propose une modification de carte avec Diff pour validation humaine (Garde-Fou)."""
    return ConsultantToolRegistry.propose_card_refactor(note_id, new_fields_json, explanation)


@mcp.tool()
def propose_card_split(note_id: int, new_cards_json: str, explanation: str = "") -> str:
    """Propose de scinder une carte dense en N cartes atomiques avec Diff comparatif pour validation humaine."""
    return ConsultantToolRegistry.propose_card_split(note_id, new_cards_json, explanation)


@mcp.tool()
def apply_patch(
    patch_json: str = "",
    patch_type: str = "",
    target_id: int = 0,
    target_name: str = "",
    patch_data_json: str = "{}",
    explanation: str = "",
) -> str:
    """Applique un patch validé sur une note, scission, modèle ou CSS en base SQLite avec rollback versionné."""
    result = ConsultantToolRegistry.apply_patch(
        patch_json=patch_json,
        patch_type=patch_type,
        target_id=target_id,
        target_name=target_name,
        patch_data_json=patch_data_json,
        explanation=explanation,
    )
    try:
        data = json.loads(result)
        if isinstance(data, dict) and data.get("status") == "applied":
            _notify_mcp_mutation(data)
    except Exception as e:
        logger.debug("Erreur analyse résultat apply_patch : %s", e)
    return result


@mcp.tool()
def preview_and_apply_patch(patch_id: str) -> str:
    """Valide et applique un patch chirurgical en attente (Two-Phase Commit) avec vérification de version optimiste."""
    return ConsultantToolRegistry.preview_and_apply_patch(patch_id)


@mcp.tool()
def propose_css_tune(note_type_name: str, css_snippet: str, selector: str = "") -> str:
    """Propose un ajustement CSS pour un modèle de carte avec aperçu live avant enregistrement."""
    return ConsultantToolRegistry.propose_css_tune(note_type_name, css_snippet, selector)


@mcp.tool()
def get_collection_panorama_360() -> str:
    """Fournit une vision panoramique 360° de la collection (paquets, cartes, sangsues, santé globale)."""
    return ConsultantToolRegistry.get_collection_panorama_360()


@mcp.tool()
def inspect_deck_deep_scan(deck_name: str) -> str:
    """Effectue une analyse approfondie d'un paquet spécifique (distribution des intervalles, top cartes sangsues)."""
    return ConsultantToolRegistry.inspect_deck_deep_scan(deck_name)


@mcp.tool()
def diagnose_deck_weaknesses(deck_name: str) -> str:
    """Effectue un diagnostic chirurgical approfondi d'un paquet (sangsues, surcharge de texte, clozes excessives, Wozniak)."""
    return ConsultantToolRegistry.diagnose_deck_weaknesses(deck_name)


@mcp.tool()
def list_card_models_manifest() -> str:
    """Dresse la cartographie complète des modèles de notes (champs requis, templates HTML Recto/Verso, CSS effectif, volumétrie)."""
    return ConsultantToolRegistry.list_card_models_manifest()


@mcp.tool()
def refactor_cards_by_criteria(query: str, instruction: str = "") -> str:
    """Extrait un échantillon condensé de cartes selon un critère ('deck:Nom', 'tag:Nom', 'sangsues', 'verbeux') pour émettre des StagedPatches."""
    return ConsultantToolRegistry.refactor_cards_by_criteria(query, instruction)


@mcp.tool()
def search_knowledge_context(query: str, max_chunks: int = 5) -> str:
    """Interroge la bibliothèque documentaire locale via RAG pour extraire des passages avec citations et tags de traçabilité."""
    return ConsultantToolRegistry.search_knowledge_context(query, max_chunks=max_chunks)


@mcp.tool()
def get_note_full_profile_360(note_id: int) -> str:
    """Génère le profil complet 360° d'une note (cartes, historique Time Machine, stats SRS, tags)."""
    return ConsultantToolRegistry.get_note_full_profile_360(note_id)


@mcp.tool()
def query_peewee(sql_query: str, limit: int = 50, offset: int = 0) -> str:
    """Exécute une requête SQL en lecture seule sur la base de données SQLite avec pagination."""
    return ConsultantToolRegistry.query_peewee(sql_query, limit=limit, offset=offset)


@mcp.tool()
def get_deck_stats(deck_name: str) -> str:
    """Récupère les statistiques détaillées d'un paquet Anki (nombre total de cartes, révisions et difficultés)."""
    return ConsultantToolRegistry.get_deck_stats(deck_name)


@mcp.tool()
def get_cards_by_deck_or_tag(
    deck_name: str = "",
    tag: str = "",
    limit: int = 20,
    offset: int = 0,
    note_type_name: str = "",
    include_subdecks: bool = True,
) -> str:
    """Récupère une liste de cartes filtrée par nom de paquet (avec sous-paquets optionnels), tag ou type de note avec pagination."""
    return ConsultantToolRegistry.get_cards_by_deck_or_tag(
        deck_name=deck_name,
        tag=tag,
        limit=limit,
        offset=offset,
        note_type_name=note_type_name,
        include_subdecks=include_subdecks,
    )


@mcp.tool()
def get_notes_by_model(
    note_type_name: str,
    include_subdecks: bool = True,
    deck_name: str = "",
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Liste les notes rattachées à un type de note spécifique, avec descente optionnelle dans les sous-paquets et pagination."""
    return ConsultantToolRegistry.get_cards_by_deck_or_tag(
        deck_name=deck_name,
        limit=limit,
        offset=offset,
        note_type_name=note_type_name,
        include_subdecks=include_subdecks,
    )


@mcp.tool()
def create_note_type(
    name: str,
    fields_json: str,
    templates_json: str,
    css: str = "",
    description: str = "",
    on_conflict: str = "error",
) -> str:
    """Propose la création d'un type de note complet via un StagedPatch (Two-Phase Commit). Rien n'est écrit directement en BDD."""
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
        from ankiforge.services.cards.note_type_service import NoteTypeService

        name_clean = name.strip()
        if not name_clean:
            return json.dumps({"status": "error", "message": "Le nom du type de note ne peut pas être vide."}, ensure_ascii=False)

        try:
            fields = json.loads(fields_json) if isinstance(fields_json, str) else fields_json
            if not isinstance(fields, list):
                return json.dumps({"status": "error", "message": "fields_json doit être une liste JSON de noms de champs."}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"fields_json invalide : {e}"}, ensure_ascii=False)

        try:
            templates = json.loads(templates_json) if isinstance(templates_json, str) else templates_json
            if not isinstance(templates, list):
                return json.dumps({"status": "error", "message": "templates_json doit être une liste JSON de gabarits."}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": f"templates_json invalide : {e}"}, ensure_ascii=False)

        model_dict = {
            "name": name_clean,
            "fields_schema": fields,
            "templates": templates,
            "css_style": css,
            "description": description,
            "on_conflict": on_conflict,
        }

        is_valid, errors = NoteTypeService.validate_structure(model_dict)
        if not is_valid:
            return json.dumps({"status": "error", "message": f"Validation échouée : {'; '.join(errors)}", "errors": errors}, ensure_ascii=False)

        if on_conflict == "error" and NoteTypeModel.get_or_none(NoteTypeModel.name == name_clean):
            return json.dumps({"status": "error", "message": f"Un type de note portant le nom '{name_clean}' existe déjà."}, ensure_ascii=False)

        patch = StagedPatchRegistry.create_patch(
            patch_type="note_type_create",
            diff_payload={
                "type": "note_type_create",
                "name": name_clean,
                "fields_schema": fields,
                "templates": templates,
                "css_style": css,
                "description": description,
                "on_conflict": on_conflict,
                "title": f"Proposition de Création de Type de Note — '{name_clean}'",
                "explanation": f"Création du type de note '{name_clean}' avec {len(fields)} champs et {len(templates)} gabarits.",
            },
        )

        return json.dumps(
            {
                "status": "staged_diff",
                "patch_id": patch.patch_id,
                "type": "note_type_create",
                "name": name_clean,
                "fields_schema": fields,
                "templates_count": len(templates),
                "message": f"Proposition de création du type de note '{name_clean}' enregistrée sous le patch {patch.patch_id}. En attente de validation humaine.",
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logger.error("Erreur create_note_type : %s", e)
        return json.dumps({"status": "error", "message": f"Erreur lors de la préparation de création du type de note : {e}"}, ensure_ascii=False)


@mcp.tool()
def change_note_type(
    note_ids_json: str,
    target_model: str,
    mapping_champs_json: str = "",
) -> str:
    """Propose la migration d'un lot de notes vers un autre type de note via un StagedPatch (Two-Phase Commit)."""
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry
        from ankiforge.services.cards.note_type_service import NoteTypeService

        try:
            if isinstance(note_ids_json, list):
                note_ids = [int(x) for x in note_ids_json]
            else:
                raw_parsed = json.loads(note_ids_json)
                note_ids = [int(x) for x in raw_parsed] if isinstance(raw_parsed, list) else [int(raw_parsed)]
        except Exception:
            try:
                note_ids = [int(x.strip()) for x in str(note_ids_json).replace("[", "").replace("]", "").split(",") if x.strip()]
            except Exception as e:
                return json.dumps({"status": "error", "message": f"Format invalide pour note_ids_json : {e}"}, ensure_ascii=False)

        if not note_ids:
            return json.dumps({"status": "error", "message": "Aucun identifiant de note valide fourni."}, ensure_ascii=False)

        try:
            target_nt = NoteTypeService.resolve_target_model(target_model)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

        mapping_champs = None
        if mapping_champs_json:
            try:
                mapping_champs = json.loads(mapping_champs_json) if isinstance(mapping_champs_json, str) else mapping_champs_json
            except Exception as e:
                return json.dumps({"status": "error", "message": f"mapping_champs_json invalide : {e}"}, ensure_ascii=False)

        warnings = []
        target_tmpls_count = len(json.loads(target_nt.templates)) if target_nt.templates else 0
        warned_sources = set()
        for nid in note_ids:
            n = NoteModel.get_or_none(NoteModel.id == nid)
            if not n:
                return json.dumps({"status": "error", "message": f"Note #{nid} introuvable en base."}, ensure_ascii=False)
            if n.note_type and n.note_type.id not in warned_sources:
                warned_sources.add(n.note_type.id)
                s_tmpls_count = len(json.loads(n.note_type.templates)) if n.note_type.templates else 0
                if s_tmpls_count != target_tmpls_count:
                    warnings.append(f"Le modèle source '{n.note_type.name}' possède {s_tmpls_count} gabarit(s) vs {target_tmpls_count} pour '{target_nt.name}'.")

        patch = StagedPatchRegistry.create_patch(
            patch_type="note_type_change",
            diff_payload={
                "type": "note_type_change",
                "note_ids": note_ids,
                "target_model": target_nt.name,
                "target_model_id": target_nt.id,
                "mapping_champs": mapping_champs,
                "warnings": warnings,
                "title": f"Proposition de Migration de {len(note_ids)} note(s) vers '{target_nt.name}'",
                "explanation": f"Migration atomique de {len(note_ids)} note(s) vers le type de note '{target_nt.name}'.",
            },
        )

        return json.dumps(
            {
                "status": "staged_diff",
                "patch_id": patch.patch_id,
                "type": "note_type_change",
                "count": len(note_ids),
                "target_model": target_nt.name,
                "warnings": warnings,
                "message": f"Proposition de migration de {len(note_ids)} note(s) vers '{target_nt.name}' enregistrée sous le patch {patch.patch_id}. En attente de validation humaine.",
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logger.error("Erreur change_note_type : %s", e)
        return json.dumps({"status": "error", "message": f"Erreur lors de la préparation de migration : {e}"}, ensure_ascii=False)


@mcp.tool()
def audit_note_type_conformity(
    note_type_name: str,
    regles: str = "",
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Audite la conformité structurelle d'un type de note (champs vides, HTML inline, son hors audio, doublons, gabarits) de manière 100% déterministe."""
    try:
        from ankiforge.services.cards.note_type_service import NoteTypeService

        res = NoteTypeService.audit_conformity(
            note_type_name=note_type_name,
            regles=regles,
            limit=limit,
            offset=offset,
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erreur audit_note_type_conformity : %s", e)
        return json.dumps({"status": "error", "message": f"Erreur lors de l'audit de conformité : {e}"}, ensure_ascii=False)


@mcp.tool()
def preview_card_render(
    note_id: int,
    fields_json: str = "",
    template_index: int | None = None,
    is_dark_mode: bool = False,
) -> str:
    """Génère le rendu HTML officiel (recto/verso et CSS) d'une note existante avec support des surcharges pour prévisualiser un état proposé."""
    try:
        from ankiforge.services.cards.note_type_service import NoteTypeService

        res = NoteTypeService.preview_card_render(
            note_id=note_id,
            fields_json=fields_json,
            template_index=template_index,
            is_dark_mode=is_dark_mode,
        )
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erreur preview_card_render : %s", e)
        return json.dumps({"status": "error", "message": f"Erreur lors du rendu de la carte : {e}"}, ensure_ascii=False)


@mcp.tool()
def find_cards_by_content(query: str, deck_name: str = "", limit: int = 10, offset: int = 0) -> str:
    """Recherche des cartes par mot-clé dans leur question/réponse pour retrouver facilement leur note_id avec pagination."""
    return ConsultantToolRegistry.find_cards_by_content(query, deck_name, limit=limit, offset=offset)


@mcp.tool()
def list_note_types() -> str:
    """Liste tous les modèles de cartes (Note Types) disponibles dans la collection."""
    return ConsultantToolRegistry.list_note_types()


@mcp.tool()
def get_note_type_details(note_type_name: str) -> str:
    """Consulte les détails complets d'un modèle de carte (champs requis, templates HTML Recto/Verso, CSS)."""
    return ConsultantToolRegistry.get_note_type_details(note_type_name)


@mcp.tool()
def propose_note_type_refactor(
    note_type_name: str,
    new_fields_schema_json: str = "",
    new_css: str = "",
    new_templates_json: str = "",
    new_description: str = "",
    explanation: str = "",
) -> str:
    """Propose une modification structurelle d'un modèle de carte avec Garde-Fou."""
    return ConsultantToolRegistry.propose_note_type_refactor(note_type_name, new_fields_schema_json, new_css, new_templates_json, new_description, explanation)


@mcp.tool()
def search_document(query: str, document_id: int) -> str:
    """Recherche une information précise dans un document spécifique via FAISS."""
    logger.info("Recherche dans le document %d avec la requête : %s", document_id, query)

    llm_config = LLMConfigModel.select().first()
    if not llm_config:
        return "Erreur : Aucun moteur IA configuré. Impossible d'effectuer la recherche vectorielle."

    try:
        rag = RAGService(llm_config)
        results = rag.search(str(document_id), query, top_k=3)

        snippets = []
        for r in results:
            content = getattr(r, "page_content", getattr(r, "text", str(r)))
            snippets.append(content)

        if not snippets:
            return "Aucun passage pertinent trouvé dans ce document pour cette requête."

        return "Passages pertinents extraits :\n\n" + "\n---\n".join(snippets)

    except Exception as e:
        logger.error("Erreur lors de la recherche RAG dans le serveur MCP : %s", e)
        return "Erreur lors de la recherche vectorielle : impossible de traiter la requête."


# =====================================================================
# OUTILS D'HYGIÈNE EN MASSE DES NOTES ET CARTES
# =====================================================================


@mcp.tool()
def sanitize_fields_html(
    note_ids: list[int] | str,
    strip_tags: list[str] | str = "",
    strip_all_html: bool = False,
    force_apply: bool = False,
    stage_threshold: int = 5,
) -> str:
    """Nettoie le HTML inline des champs d'un lot de notes. Si le volume dépasse stage_threshold, génère un StagedPatch (Two-Phase Commit)."""
    return ConsultantToolRegistry.sanitize_fields_html(
        note_ids=note_ids,
        strip_tags=strip_tags,
        strip_all_html=strip_all_html,
        force_apply=force_apply,
        stage_threshold=stage_threshold,
    )


@mcp.tool()
def set_tags_bulk(
    note_ids: list[int] | str,
    tags: list[str] | str,
    mode: str = "add",
    allow_remove_provenance_tags: bool = False,
) -> str:
    """Pose, retire ou remplace des tags sur un lot de notes via l'écrivain canonique JSON."""
    return ConsultantToolRegistry.set_tags_bulk(
        note_ids=note_ids,
        tags=tags,
        mode=mode,
        allow_remove_provenance_tags=allow_remove_provenance_tags,
    )


@mcp.tool()
def delete_unused_note_type(
    name: str,
    confirm: bool = False,
) -> str:
    """Supprime un type de note uniquement si 0 note y sont rattachées (garde-fou référentiel). Si name='all_unused', supprime tous les modèles orphelins."""
    return ConsultantToolRegistry.delete_unused_note_type(name=name, confirm=confirm)


@mcp.tool()
def move_cards_to_deck(
    card_ids: list[int] | str,
    deck: str,
) -> str:
    """Déplace un lot de cartes physiques vers un paquet ou sous-paquet hiérarchique ('Parent::Enfant')."""
    return ConsultantToolRegistry.move_cards_to_deck(card_ids=card_ids, deck=deck)


@mcp.tool()
def list_empty_cards(
    deck_name: str = "",
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Détecte les cartes physiques dont le recto (question) est vide après substitution du gabarit."""
    return ConsultantToolRegistry.list_empty_cards(deck_name=deck_name, limit=limit, offset=offset)


@mcp.tool()
def delete_empty_cards(
    card_ids: list[int] | str = "",
    deck_name: str = "",
    confirm: bool = False,
) -> str:
    """Supprime définitivement les cartes à front vide (détection auto ou par identifiants). Action destructive nécessitant confirm=True."""
    return ConsultantToolRegistry.delete_empty_cards(card_ids=card_ids, deck_name=deck_name, confirm=confirm)


# =====================================================================
# OUTILS DE FORMATAGE ET STRUCTURATION MARKDOWN
# =====================================================================


@mcp.tool()
def format_markdown_document(
    document_id: int = 0,
    content: str = "",
    dehyphenate_ocr: bool = True,
    normalize_katex: bool = True,
    align_tables: bool = True,
    normalize_headings: bool = True,
    clean_whitespace: bool = True,
) -> str:
    """Nettoie, normalise et formate un document Markdown (césures OCR, KaTeX, tables GFM, titres ATX)."""
    return ConsultantToolRegistry.format_markdown_document(
        document_id=document_id,
        content=content,
        dehyphenate_ocr=dehyphenate_ocr,
        normalize_katex=normalize_katex,
        align_tables=align_tables,
        normalize_headings=normalize_headings,
        clean_whitespace=clean_whitespace,
    )


@mcp.tool()
def get_document_outline(document_id: int = 0, content: str = "") -> str:
    """Extrait l'arborescence hiérarchique des titres (Outline) d'un document Markdown."""
    return ConsultantToolRegistry.get_document_outline(document_id=document_id, content=content)


@mcp.tool()
def structure_document_sections(document_id: int = 0, content: str = "", max_tokens: int = 800) -> str:
    """Découpe un document Markdown en sections sémantiques enrichies avec breadcrumbs et statistiques pour le RAG."""
    return ConsultantToolRegistry.structure_document_sections(
        document_id=document_id,
        content=content,
        max_tokens=max_tokens,
    )


@mcp.tool()
def structure_transcript_for_ai(
    document_id: int = 0,
    content: str = "",
    profile: str = "didactic",
    target_language: str = "fr",
    preserve_timestamps: bool = True,
    normalize_latex: bool = True,
    add_summary: bool = True,
    add_key_takeaways: bool = True,
) -> str:
    """Restructure un texte brut ou une retranscription (YouTube, cours, audio) en Markdown pédagogique structuré."""
    return ConsultantToolRegistry.structure_transcript_for_ai(
        document_id=document_id,
        content=content,
        profile=profile,
        target_language=target_language,
        preserve_timestamps=preserve_timestamps,
        normalize_latex=normalize_latex,
        add_summary=add_summary,
        add_key_takeaways=add_key_takeaways,
    )


# =====================================================================
# OUTILS DE DOCUMENTATION & BASE DE CONNAISSANCES INTERNE (ZENSICAL)
# =====================================================================


@mcp.tool()
def search_app_documentation(query: str, category: str = "", limit: int = 5) -> str:
    """Recherche des explications, guides et références d'architecture dans la documentation officielle d'AnkiForge via SQLite FTS5 BM25."""
    return ConsultantToolRegistry.search_app_documentation(query, category, limit)


@mcp.tool()
def read_app_doc_page(doc_path: str, section_anchor: str = "") -> str:
    """Consulte le contenu intégral ou une section d'une page de documentation officielle d'AnkiForge (ex: 'features/consultant_mcp.md')."""
    return ConsultantToolRegistry.read_app_doc_page(doc_path, section_anchor)


@mcp.tool()
def list_app_doc_topics(category: str = "") -> str:
    """Consulte le sommaire exhaustif de la documentation officielle d'AnkiForge classé par thématiques."""
    return ConsultantToolRegistry.list_app_doc_topics(category)


@mcp.tool()
def get_feature_quick_help(feature_name: str) -> str:
    """Obtient une synthèse immédiate d'une fonctionnalité clé (Ollama, KaTeX, DAG, RAG, Wozniak, Nuitka, Smart Merge, MCP)."""
    return ConsultantToolRegistry.get_feature_quick_help(feature_name)


# =====================================================================
# RESSOURCES MCP (EXPLORATION DIRECTE DE LA DOCUMENTATION)
# =====================================================================


@mcp.resource("docs://topics")
def get_docs_topics_resource() -> str:
    """Retourne la liste hiérarchique complète des chapitres et pages de la documentation officielle."""
    return ConsultantToolRegistry.list_app_doc_topics()


@mcp.resource("docs://page/{doc_path}")
def get_doc_page_resource(doc_path: str) -> str:
    """Fournit le contenu brut Markdown d'une page de documentation officielle."""
    return ConsultantToolRegistry.read_app_doc_page(doc_path)


# =====================================================================
# PROMPTS MCP (MODÈLES DE GUIDAGE IA)
# =====================================================================


@mcp.prompt("explain_ankiforge_feature")
def prompt_explain_feature(feature_name: str) -> str:
    """Prompt guidé pour expliquer pas à pas une fonctionnalité d'AnkiForge avec extraits officiels."""
    doc_summary = ConsultantToolRegistry.get_feature_quick_help(feature_name)
    return _PROMPT_ENV.from_string(
        "Tu es un expert d'AnkiForge. Explique la fonctionnalité '{{ feature_name }}' en t'appuyant sur la documentation officielle ci-dessous :\n\n"
        "<<< CONTENU UTILISATEUR (FONCTIONNALITÉ) >>>\n{{ feature_name }}\n<<< FIN >>>\n\n"
        "<<< CONTENU DOCUMENTATION OFFICIELLE >>>\n{{ doc_summary }}\n<<< FIN >>>\n\n"
        "Donne des exemples concrets d'utilisation et les bonnes pratiques recommandées."
    ).render(feature_name=feature_name, doc_summary=doc_summary)


@mcp.prompt("audit_architecture_compliance")
def prompt_audit_architecture(target_code_or_rule: str) -> str:
    """Prompt guidé pour vérifier la conformité d'un code ou d'une conception avec les 9 dossiers d'architecture AnkiForge."""
    arch_doc = ConsultantToolRegistry.read_app_doc_page("Dossier_architecture/02_architecture_technique.md")
    return _PROMPT_ENV.from_string(
        "Tu es l'architecte en chef d'AnkiForge. Vérifie que le code ou la proposition suivante respecte les principes architecturaux "
        "décrits dans la documentation :\n\n"
        "<<< CONTENU DOCUMENTATION ARCHITECTURE >>>\n{{ arch_doc }}...\n<<< FIN >>>\n\n"
        "Élément à auditer :\n<<< CONTENU UTILISATEUR >>>\n{{ target_code_or_rule }}\n<<< FIN >>>"
    ).render(arch_doc=arch_doc[:2500], target_code_or_rule=target_code_or_rule)


# =====================================================================
# GESTION DES AGENTS DÉDIÉS AU SERVEUR MCP
# =====================================================================


@mcp.tool()
def list_mcp_agents(scope: str = "mcp") -> str:
    """Liste tous les agents dédiés enregistrés (Auditeur Wozniak, Architecte CSS, Analyste SRS...) avec leurs outils."""
    return ConsultantToolRegistry.list_mcp_agents(scope)


@mcp.tool()
def get_mcp_agent_details(agent_name: str) -> str:
    """Consulte la configuration détaillée d'un agent dédié (prompt système Jinja2, modèle assigné, liste des outils)."""
    return ConsultantToolRegistry.get_mcp_agent_details(agent_name)


@mcp.tool()
def invoke_mcp_agent(agent_name: str, message: str, conversation_history_json: str = "[]") -> str:
    """Délègue une tâche ou une question à un agent dédié spécifique selon ses autorisations d'outils et son prompt."""
    return ConsultantToolRegistry.invoke_mcp_agent(agent_name, message, conversation_history_json)


@mcp.tool()
def create_or_update_mcp_agent(
    name: str,
    description: str,
    system_prompt: str,
    allowed_tools_json: str = "[]",
    persona_type: str = "mcp",
) -> str:
    """Crée ou met à jour la configuration d'un agent dédié dans la collection."""
    from ankiforge.database.models import PersonaModel

    # Garde-fou anti-escalade : ce tool est exposé au client MCP (donc atteignable
    # par une chaîne d'agents LLM). On refuse l'accès universel ('*'/'all') et
    # l'outil d'exécution Python arbitraire, qui couplés à un system_prompt libre
    # permettraient une exécution persistante non maîtrisée via invoke_mcp_agent.
    try:
        requested_tools = json.loads(allowed_tools_json.strip() or "[]")
    except json.JSONDecodeError:
        return "Erreur : allowed_tools_json doit être une liste JSON valide."
    if not isinstance(requested_tools, list) or not all(isinstance(t, str) for t in requested_tools):
        return "Erreur : allowed_tools_json doit être une liste JSON de noms d'outils."
    if any(t in {"*", "all"} for t in requested_tools) or "execute_python_tool" in requested_tools:
        logger.warning(
            "Refus d'accorder des autorisations dangereuses via create_or_update_mcp_agent : %s",
            requested_tools,
        )
        return "Erreur : l'accès universel ('*') ou l'outil 'execute_python_tool' ne peuvent pas être accordés via MCP."

    allowed_tools = json.dumps(sorted(set(requested_tools)))
    try:
        agent, created = PersonaModel.get_or_create(
            name=name.strip(),
            defaults={
                "description": description.strip(),
                "system_prompt": system_prompt.strip(),
                "allowed_tools": allowed_tools,
                "persona_type": persona_type.strip(),
            },
        )
        if not created:
            agent.description = description.strip()
            agent.system_prompt = system_prompt.strip()
            agent.allowed_tools = allowed_tools
            agent.persona_type = persona_type.strip()
            agent.save()
            action_str = "mis à jour"
        else:
            action_str = "créé"

        return f"Succès : L'agent dédié '{agent.name}' a été {action_str} avec succès (portée: {agent.persona_type})."
    except Exception as e:
        logger.error("Erreur create_or_update_mcp_agent : %s", e)
        return "Erreur lors de l'enregistrement de l'agent : échec du traitement des paramètres."


@mcp.resource("agents://list")
def get_agents_list_resource() -> str:
    """Retourne la liste hiérarchique de tous les agents dédiés au format texte/JSON."""
    return ConsultantToolRegistry.list_mcp_agents(scope="all")


@mcp.resource("agents://{agent_name}")
def get_agent_profile_resource(agent_name: str) -> str:
    """Fournit le profil et la consigne système d'un agent dédié spécifique."""
    return ConsultantToolRegistry.get_mcp_agent_details(agent_name)


@mcp.prompt("run_with_agent")
def prompt_run_with_agent(agent_name: str, task: str) -> str:
    """Prompt guidé pour exécuter une tâche en adoptant la posture et les outils d'un agent dédié."""
    agent_info = ConsultantToolRegistry.get_mcp_agent_details(agent_name)
    return _PROMPT_ENV.from_string(
        "Tu incarnes l'agent spécialisé '{{ agent_name }}'. Voici ton profil et tes consignes strictes :\n\n"
        "<<< CONTENU BDD (PROFIL AGENT) >>>\n{{ agent_info }}\n<<< FIN >>>\n\n"
        "### Mission à accomplir :\n<<< CONTENU UTILISATEUR >>>\n{{ task }}\n<<< FIN >>>\n\n"
        "Respecte strictement tes compétences et ton périmètre d'action."
    ).render(agent_name=agent_name, agent_info=agent_info, task=task)


def run_server(transport: Literal["stdio", "sse", "streamable-http"] = "streamable-http") -> None:
    """Démarre le serveur FastMCP en mode asynchrone sécurisé (transport par défaut: streamable-http)."""
    logger.info("Démarrage du serveur MCP AnkiForge (transport: %s)...", transport)
    if db.is_closed():
        db.connect()

    try:
        if transport == "streamable-http":
            mcp.run(transport="streamable-http")
        elif transport == "sse":
            mcp.run(transport="sse")
        else:
            mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Arrêt du serveur MCP AnkiForge.")
    finally:
        if not db.is_closed():
            db.close()


if __name__ == "__main__":
    run_server()
