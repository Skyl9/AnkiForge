"""Serveur MCP in-process exposant l'outillage de consultation, d'audit et de mutation."""

import hashlib
import json
import logging
from collections import namedtuple
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment
from mcp.server.mcpserver import MCPServer

from ankiforge.database.models import LLMConfigModel, NoteModel, NoteTypeModel, db
from ankiforge.services.ai.mcp_tool_registry import MCPToolRegistry
from ankiforge.services.ai.mcp_tracker import get_mcp_activity_tracker
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.utils.jinja_sandbox import create_prompt_environment

__all__ = [
    "DEFAULT_MCP_MUTATION_DOMAIN",
    "MCP_MUTATION_DOMAINS",
    "mcp",
    "normalize_mutation_type",
    "register_mutation_listener",
    "register_staged_bundle_listener",
    "register_staged_patch_listener",
    "resolve_mcp_mutation_domain",
    "run_server",
    "unregister_mutation_listener",
    "unregister_staged_bundle_listener",
    "unregister_staged_patch_listener",
]

logger = logging.getLogger(__name__)

# Écouteurs de mutations externes appliquées via les outils MCP
_mutation_listeners: list[Callable[[dict[str, Any]], None]] = []

# Écouteurs de propositions de patchs en attente (Two-Phase Commit)
_staged_patch_listeners: list[Callable[[dict[str, Any]], None]] = []

# Écouteurs de propositions de bundles en attente (Staged Bundles)
_staged_bundle_listeners: list[Callable[[dict[str, Any]], None]] = []

# Représentation légère d'un paquet virtuel intra-bundle avant écriture physique
VirtualDeck = namedtuple("VirtualDeck", ["id", "name"])

# Domaines fonctionnels exposés par une mutation MCP.
MCP_MUTATION_DOMAINS: frozenset[str] = frozenset({"cards", "decks", "models", "docs"})

#: Correspondance entre le type de mutation émis par les services et son domaine de vue.
_MUTATION_DOMAIN_BY_TYPE: dict[str, str] = {
    # Notes, cartes et opérations d'hygiène en masse.
    "note_update": "cards",
    "note_create": "cards",
    "batch_note_create": "cards",
    "card_split": "cards",
    # Types historiques émis par `MCPToolRegistry.apply_patch`.
    "card": "cards",
    "split": "cards",
    "bulk_html_sanitize": "cards",
    "sanitize_fields_html": "cards",
    "set_tags_bulk": "cards",
    "merge_tags": "cards",
    "delete_empty_cards": "cards",
    "move_cards": "cards",
    # Types de note, gabarits et CSS.
    "css_tune": "models",
    "note_type_update": "models",
    "note_type_create": "models",
    "note_type_change": "models",
    "delete_note_type": "models",
    "delete_unused_note_types": "models",
    # Types historiques émis par `MCPToolRegistry.apply_patch`.
    "model": "models",
    "css": "models",
    # Paquets et arborescence.
    "create_deck": "decks",
    "deck_create": "decks",
    "deck_update": "decks",
    "deck_delete": "decks",
    "rename_deck": "decks",
    # Bibliothèque documentaire.
    "document_create": "docs",
    "document_update": "docs",
    "document_delete": "docs",
    "document_index": "docs",
    "exclude_document_region": "docs",
    "neutralize_document_region": "docs",
    "update_document_content": "docs",
    "reindex_document": "docs",
}

DEFAULT_MCP_MUTATION_DOMAIN = "cards"


def normalize_mutation_type(data: dict[str, Any]) -> str:
    """Normalise le type de mutation porté par ``type`` ou ``mutation_type``."""
    return str(data.get("type") or data.get("mutation_type") or "").strip().lower()


def resolve_mcp_mutation_domain(data: dict[str, Any]) -> str:
    """Résout le domaine fonctionnel d'une mutation MCP.

    Un domaine explicite valide (``cards``, ``decks``, ``models`` ou ``docs``) est
    prioritaire. À défaut, le type de mutation est traduit via la table de routage,
    puis replié sur ``cards`` pour préserver la compatibilité des anciens outils.
    """
    explicit = str(data.get("domain") or "").strip().lower()
    if explicit in MCP_MUTATION_DOMAINS:
        return explicit

    mutation_type = normalize_mutation_type(data)
    domain = _MUTATION_DOMAIN_BY_TYPE.get(mutation_type)
    if domain is None:
        if mutation_type:
            logger.debug(
                "Type de mutation MCP inconnu '%s' : domaine '%s' appliqué par repli.",
                mutation_type,
                DEFAULT_MCP_MUTATION_DOMAIN,
            )
        return DEFAULT_MCP_MUTATION_DOMAIN
    return domain


def register_mutation_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Enregistre un écouteur de mutation de données via MCP."""
    if callback not in _mutation_listeners:
        _mutation_listeners.append(callback)


def unregister_mutation_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Retire un écouteur de mutation."""
    if callback in _mutation_listeners:
        _mutation_listeners.remove(callback)


def register_staged_patch_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Enregistre un écouteur de proposition de patch en attente via MCP."""
    if callback not in _staged_patch_listeners:
        _staged_patch_listeners.append(callback)


def unregister_staged_patch_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Retire un écouteur de proposition de patch."""
    if callback in _staged_patch_listeners:
        _staged_patch_listeners.remove(callback)


def _notify_mcp_mutation(data: dict[str, Any]) -> None:
    """Notifie les écouteurs enregistrés et le bus d'événements central.

    Le domaine fonctionnel est résolu une seule fois ici puis injecté dans la
    charge utile transmise aux écouteurs, afin que la GUI n'ait pas à réimplémenter
    la table de routage.
    """
    from ankiforge.utils.event_bus import MCPDataMutatedEvent, MCPDomain, event_bus

    domain = cast(MCPDomain, resolve_mcp_mutation_domain(data))
    payload = {**data, "domain": domain}

    target_id = int(data.get("target_id") or data.get("parent_note_id") or data.get("note_id") or data.get("note_type_id") or data.get("document_id") or data.get("deck_id") or 0)
    target_name = str(data.get("note_type_name") or data.get("deck_name") or data.get("document_title") or "")

    try:
        event_bus.publish(
            MCPDataMutatedEvent(
                mutation_type=normalize_mutation_type(data),
                domain=domain,
                target_id=target_id,
                target_name=target_name,
                details=payload,
            )
        )
    except Exception as e:
        logger.warning("Erreur publication event_bus MCPDataMutatedEvent : %s", e)

    for listener in list(_mutation_listeners):
        try:
            listener(payload)
        except Exception as e:
            logger.warning("Erreur dans l'écouteur de mutation MCP : %s", e)


def _notify_mcp_patch_staged(data: dict[str, Any]) -> None:
    """Notifie les écouteurs enregistrés et le bus d'événements lors de la création d'un patch staged."""
    from ankiforge.utils.event_bus import MCPPatchStagedEvent, event_bus

    p_id = str(data.get("patch_id", ""))
    p_type = str(data.get("type") or data.get("patch_type") or "card")
    t_id = int(data.get("note_id") or data.get("target_id") or 0)
    title = str(data.get("title") or f"Proposition — {p_type} #{t_id}")

    try:
        event_bus.publish(
            MCPPatchStagedEvent(
                patch_id=p_id,
                patch_type=p_type,
                target_id=t_id,
                title=title,
                details=data,
            )
        )
    except Exception as e:
        logger.debug("Erreur publication event_bus MCPPatchStagedEvent : %s", e)

    for listener in list(_staged_patch_listeners):
        try:
            listener(data)
        except Exception as e:
            logger.warning("Erreur dans l'écouteur de patch staged MCP : %s", e)


def register_staged_bundle_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Enregistre un écouteur appelé lors du scellement d'un Staged Bundle."""
    if callback not in _staged_bundle_listeners:
        _staged_bundle_listeners.append(callback)


def unregister_staged_bundle_listener(callback: Callable[[dict[str, Any]], None]) -> None:
    """Retire un écouteur de Staged Bundle."""
    if callback in _staged_bundle_listeners:
        _staged_bundle_listeners.remove(callback)


def _notify_mcp_bundle_staged(data: dict[str, Any]) -> None:
    """Notifie les écouteurs enregistrés et le bus d'événements lors du commit d'un Staged Bundle."""
    from ankiforge.utils.event_bus import MCPBundleStagedEvent, event_bus

    b_id = str(data.get("bundle_id", ""))
    title = str(data.get("title", ""))
    total_steps = int(data.get("total_steps", 0))

    try:
        event_bus.publish(
            MCPBundleStagedEvent(
                bundle_id=b_id,
                title=title,
                total_steps=total_steps,
                details=data,
            )
        )
    except Exception as e:
        logger.debug("Erreur publication event_bus MCPBundleStagedEvent : %s", e)

    for listener in list(_staged_bundle_listeners):
        try:
            listener(data)
        except Exception as e:
            logger.warning("Erreur dans l'écouteur de bundle staged MCP : %s", e)


# Environnement Jinja2 sandboxé (partagé) pour l'interpolation des prompts.
_PROMPT_ENV = create_prompt_environment()

# Répertoire des templates d'amorçage d'agent MCP.
_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_GUIDE_AGENT_FILENAMES: dict[str, str] = {
    "claude": "CLAUDE.md",
    "gemini": "GEMINI.md",
    "cursor": ".cursorrules",
    "generic": "ANKIFORGE_GUIDE.md",
    "agy": "GEMINI.md",
}
# Environnement Jinja2 sandboxé dédié au rendu des guides d'amorçage (inclut les fichiers).
_GUIDE_ENV = SandboxedEnvironment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,  # B701 non applicable : sortie Markdown texte
)


def _compute_guide_version_hash() -> str:
    """Calcule le hash SHA-256 de version à partir des templates d'amorçage."""
    h = hashlib.sha256()
    if _TEMPLATES_DIR.exists():
        for path in sorted(_TEMPLATES_DIR.glob("*.j2")):
            try:
                h.update(path.read_bytes())
            except OSError:
                continue
    return h.hexdigest()


_GUIDE_VERSION_HASH: str = _compute_guide_version_hash()

mcp = MCPServer("AnkiForge")
get_mcp_activity_tracker().attach_to_server(mcp)


@mcp.tool()
def audit_deck_wozniak(deck_name: str) -> str:
    """Effectue un audit de qualité Wozniak complet sur un paquet (20 règles de formulation, atomicité, redondance)."""
    return MCPToolRegistry.audit_deck_wozniak(deck_name)


@mcp.tool()
def audit_card_wozniak(note_id: int) -> str:
    """Analyse chirurgicale d'une carte spécifique au regard des 20 règles de Piotr Wozniak."""
    return MCPToolRegistry.audit_card_wozniak(note_id)


@mcp.tool()
def find_duplicate_cards(deck_name: str = "", threshold: float = 0.75) -> str:
    """Détecte les cartes doublons ou formulées de manière quasi-identique dans un paquet via distance Levenshtein."""
    return MCPToolRegistry.find_duplicate_cards(deck_name, threshold)


@mcp.tool()
def propose_card_refactor(note_id: int, new_fields_json: str, explanation: str = "") -> str:
    """Propose une modification de carte avec Diff pour validation humaine (Garde-Fou)."""
    return MCPToolRegistry.propose_card_refactor(note_id, new_fields_json, explanation)


@mcp.tool()
def propose_card_split(note_id: int, new_cards_json: str, explanation: str = "") -> str:
    """Propose de scinder une carte dense en N cartes atomiques avec Diff comparatif pour validation humaine."""
    return MCPToolRegistry.propose_card_split(note_id, new_cards_json, explanation)


@mcp.tool()
def apply_patch(
    patch_id: str = "",
    patch_json: str = "",
    patch_type: str = "",
    target_id: int = 0,
    target_name: str = "",
    patch_data_json: str = "{}",
    explanation: str = "",
) -> str:
    """Applique un patch validé sur une note, scission, modèle ou CSS en base SQLite avec rollback versionné."""
    p_id = patch_id.strip() or (patch_json.strip() if patch_json.strip().startswith("patch_") else "")
    if p_id:
        result = MCPToolRegistry.preview_and_apply_patch(p_id)
    else:
        result = MCPToolRegistry.apply_patch(
            patch_json=patch_json,
            patch_type=patch_type,
            target_id=target_id,
            target_name=target_name,
            patch_data_json=patch_data_json,
            explanation=explanation,
        )
    try:
        data = json.loads(result)
        # Le chemin staged (`preview_and_apply_patch`) notifie déjà via
        # `StagedPatchRegistry` avec un type canonique : ne pas doubler la mutation.
        if isinstance(data, dict) and data.get("status") == "applied" and normalize_mutation_type(data):
            _notify_mcp_mutation(data)
    except Exception as e:
        logger.debug("Erreur analyse résultat apply_patch : %s", e)
    return result


@mcp.tool()
def preview_and_apply_patch(patch_id: str) -> str:
    """Valide et applique un patch chirurgical en attente (Two-Phase Commit) avec vérification de version optimiste."""
    return MCPToolRegistry.preview_and_apply_patch(patch_id)


@mcp.tool()
def begin_staged_bundle(title: str, explanation: str = "") -> str:
    """Ouvre une session transactionnelle groupée (Staged Bundle) permettant d'enchaîner plusieurs mutations sans interruption.

    Retourne l'identifiant du bundle ouvert ('bundle_id') et initialise le contexte virtuel (Staged Overlay).
    """
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        bundle_id = StagedPatchRegistry.begin_bundle(title=title, explanation=explanation)
        return json.dumps(
            {
                "status": "bundle_opened",
                "bundle_id": bundle_id,
                "title": title.strip() or "Nouveau Bundle",
                "explanation": explanation.strip(),
                "message": (
                    f"Session de bundle '{bundle_id}' ouverte avec succès. Toutes les mutations subséquentes seront "
                    f"enregistrées comme étapes de ce bundle avec résolution virtuelle intra-bloc (Staged Overlay) jusqu'à l'appel de 'commit_staged_bundle'."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error("Erreur begin_staged_bundle : %s", e)
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def commit_staged_bundle(bundle_id: str) -> str:
    """Scelle un Staged Bundle au statut 'pending' et le transmet au Garde-Fou pour validation humaine.

    Vérifie que le bundle contient au moins une étape.
    """
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        res = StagedPatchRegistry.commit_bundle(bundle_id=bundle_id)
        return json.dumps(
            {
                "status": "staged",
                "bundle_id": res["bundle_id"],
                "title": res["title"],
                "total_steps": res["total_steps"],
                "message": (f"Bundle '{res['bundle_id']}' scellé avec succès avec {res['total_steps']} étape(s). Transmis au Garde-Fou pour validation humaine séquentielle ou tout-en-un."),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error("Erreur commit_staged_bundle : %s", e)
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def abort_staged_bundle(bundle_id: str) -> str:
    """Annule et supprime un Staged Bundle en cours de construction ainsi que toutes ses étapes associées."""
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        ok = StagedPatchRegistry.abort_bundle(bundle_id=bundle_id)
        if not ok:
            return json.dumps({"status": "error", "message": f"Bundle '{bundle_id}' introuvable ou déjà supprimé."}, ensure_ascii=False)
        return json.dumps(
            {
                "status": "aborted",
                "bundle_id": bundle_id,
                "message": f"Bundle '{bundle_id}' et toutes ses étapes associées ont été supprimés avec succès.",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error("Erreur abort_staged_bundle : %s", e)
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_staged_pending_operations(bundle_id: str = "") -> str:
    """Consulte les bundles et propositions d'opérations en attente de validation humaine avec l'état virtuel de l'overlay."""
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        res = StagedPatchRegistry.get_staged_pending_operations(bundle_id=bundle_id)
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erreur get_staged_pending_operations : %s", e)
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def propose_css_tune(note_type_name: str, css_snippet: str, selector: str = "") -> str:
    """Propose un ajustement CSS pour un modèle de carte avec aperçu live avant enregistrement."""
    return MCPToolRegistry.propose_css_tune(note_type_name, css_snippet, selector)


@mcp.tool()
def get_collection_panorama_360() -> str:
    """Fournit une vision panoramique 360° de la collection (paquets, cartes, sangsues, santé globale)."""
    return MCPToolRegistry.get_collection_panorama_360()


@mcp.tool()
def inspect_deck_deep_scan(deck_name: str) -> str:
    """Effectue une analyse approfondie d'un paquet spécifique (distribution des intervalles, top cartes sangsues)."""
    return MCPToolRegistry.inspect_deck_deep_scan(deck_name)


@mcp.tool()
def diagnose_deck_weaknesses(deck_name: str) -> str:
    """Effectue un diagnostic chirurgical approfondi d'un paquet (sangsues, surcharge de texte, clozes excessives, Wozniak)."""
    return MCPToolRegistry.diagnose_deck_weaknesses(deck_name)


@mcp.tool()
def list_card_models_manifest() -> str:
    """Dresse la cartographie complète des modèles de notes (champs requis, templates HTML Recto/Verso, CSS effectif, volumétrie)."""
    return MCPToolRegistry.list_card_models_manifest()


@mcp.tool()
def refactor_cards_by_criteria(query: str, instruction: str = "") -> str:
    """Extrait un échantillon condensé de cartes selon un critère ('deck:Nom', 'tag:Nom', 'sangsues', 'verbeux') pour émettre des StagedPatches."""
    return MCPToolRegistry.refactor_cards_by_criteria(query, instruction)


@mcp.tool()
def search_knowledge_context(query: str, max_chunks: int = 5) -> str:
    """Interroge la bibliothèque documentaire locale via RAG pour extraire des passages avec citations et tags de traçabilité."""
    return MCPToolRegistry.search_knowledge_context(query, max_chunks=max_chunks)


@mcp.tool()
def get_note_full_profile_360(note_id: int) -> str:
    """Génère le profil complet 360° d'une note (cartes, historique Time Machine, stats SRS, tags)."""
    return MCPToolRegistry.get_note_full_profile_360(note_id)


@mcp.tool()
def query_peewee(sql_query: str, limit: int = 50, offset: int = 0) -> str:
    """Exécute une requête SQL en lecture seule sur la base de données SQLite avec pagination."""
    return MCPToolRegistry.query_peewee(sql_query, limit=limit, offset=offset)


@mcp.tool()
def get_deck_stats(deck_name: str) -> str:
    """Récupère les statistiques détaillées d'un paquet Anki (nombre total de cartes, révisions et difficultés)."""
    return MCPToolRegistry.get_deck_stats(deck_name)


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
    return MCPToolRegistry.get_cards_by_deck_or_tag(
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
    return MCPToolRegistry.get_cards_by_deck_or_tag(
        deck_name=deck_name,
        limit=limit,
        offset=offset,
        note_type_name=note_type_name,
        include_subdecks=include_subdecks,
    )


@mcp.tool()
def list_decks(filter: str = "") -> str:
    """Liste tous les paquets et sous-paquets hiérarchiques disponibles dans la collection avec filtrage optionnel."""
    try:
        from ankiforge.database.models import DeckModel

        query = DeckModel.select().order_by(DeckModel.name.asc())
        decks = list(query)
        if filter.strip():
            f_lower = filter.strip().lower()
            decks = [d for d in decks if f_lower in d.name.lower()]

        res = {
            "status": "success",
            "count": len(decks),
            "decks": [{"id": d.id, "name": d.name, "description": d.description or ""} for d in decks],
        }
        return json.dumps(res, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erreur list_decks : %s", e)
        return json.dumps({"status": "error", "message": f"Erreur lors du listage des paquets : {e}"}, ensure_ascii=False)


@mcp.tool()
def create_deck(deck_name: str, description: str = "") -> str:
    """Crée un paquet et toute son arborescence hiérarchique ('Parent::Enfant') en écriture directe et idempotente."""
    try:
        from ankiforge.database.models import DeckModel
        from ankiforge.repositories.deck_repository import DeckRepository

        dk_clean = deck_name.strip()
        if not dk_clean:
            return json.dumps({"status": "error", "message": "Le nom du paquet ne peut pas être vide."}, ensure_ascii=False)

        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        existing = DeckModel.get_or_none(DeckModel.name == dk_clean)
        is_new = existing is None

        # Si un bundle est actif et que le paquet est nouveau, enregistrer l'étape staged dans le bundle
        bundle_id = StagedPatchRegistry.get_active_bundle_id()
        if bundle_id and is_new:
            patch = StagedPatchRegistry.create_patch(
                patch_type="deck_create",
                diff_payload={
                    "deck_name": dk_clean,
                    "description": description.strip(),
                    "title": f"Création du paquet '{dk_clean}'",
                    "explanation": f"Proposition de création du paquet hiérarchique '{dk_clean}' (étape de bundle).",
                },
                bundle_id=bundle_id,
            )
            return json.dumps(
                {
                    "status": "staged",
                    "patch_id": patch.patch_id,
                    "bundle_id": bundle_id,
                    "step_order": patch.step_order,
                    "deck_name": dk_clean,
                    "message": f"Création du paquet '{dk_clean}' enregistrée comme étape {patch.step_order} du bundle {bundle_id}.",
                },
                ensure_ascii=False,
                indent=2,
            )

        repo = DeckRepository()
        deck = repo.get_or_create_deck_hierarchical(dk_clean, description=description.strip())

        if is_new:
            _notify_mcp_mutation(
                {
                    "type": "create_deck",
                    "domain": "decks",
                    "target_id": deck.id,
                    "target_name": deck.name,
                    "deck_id": deck.id,
                    "deck_name": deck.name,
                }
            )

        return json.dumps(
            {
                "status": "success",
                "deck_id": deck.id,
                "deck_name": deck.name,
                "is_new": is_new,
                "message": f"Paquet '{deck.name}' {'créé avec succès' if is_new else 'existant récupéré'}.",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error("Erreur create_deck : %s", e)
        return json.dumps({"status": "error", "message": f"Erreur lors de la création du paquet : {e}"}, ensure_ascii=False)


def _check_first_field_duplicate(deck_id: int, note_type_id: int, first_field_value: str) -> int | None:
    """Vérifie si une note active dans le deck cible partage déjà le même premier champ."""
    val_clean = first_field_value.strip().lower()
    if not val_clean:
        return None
    from ankiforge.database.models import CardModel, NoteModel, NoteVersionModel

    candidates = (
        NoteModel.select(NoteModel.id)
        .join(CardModel, on=(CardModel.note_id == NoteModel.id))
        .where((CardModel.deck_id == deck_id) & (NoteModel.note_type_id == note_type_id) & (NoteModel.status != "archived"))
        .distinct()
        .limit(300)
    )
    for c_note in candidates:
        n_obj = NoteModel.get_or_none(NoteModel.id == c_note.id)
        if not n_obj:
            continue
        v = n_obj.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
        if v:
            try:
                cnt = json.loads(v.content) if isinstance(v.content, str) else v.content
                if isinstance(cnt, dict):
                    first_val = next(iter(cnt.values()), "")
                    if str(first_val).strip().lower() == val_clean:
                        return n_obj.id
            except Exception:
                pass
    return None


def _validate_note_creation_data(
    note_type_name: str,
    deck_name: str,
    fields_input: str | dict[str, Any],
    bundle_id: str | None = None,
) -> tuple[NoteTypeModel, Any, dict[str, str], list[str]]:
    """Valide les paramètres d'une note. Lève ValueError si invalide.

    Retourne (NoteTypeModel, DeckModel, sanitized_fields, warnings).
    """

    from ankiforge.database.models import DeckModel, NoteTypeModel
    from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

    # 1. Contrôle du deck (anti-hallucination avec support Staged Overlay)
    dk_clean = deck_name.strip()
    if not dk_clean:
        raise ValueError("Le nom du paquet cible ne peut pas être vide.")

    db_deck = DeckModel.get_or_none(DeckModel.name == dk_clean)
    overlay = StagedPatchRegistry.get_active_overlay(bundle_id)
    is_in_overlay = overlay is not None and overlay.is_deck_available(dk_clean)

    if not db_deck and not is_in_overlay:
        avail = [d.name for d in DeckModel.select().limit(5)]
        avail_str = f" Exemples de paquets existants : {avail}." if avail else ""
        raise ValueError(
            f"Paquet '{dk_clean}' introuvable en base.{avail_str} Pour éviter toute création de paquet fantôme par hallucination, "
            f"veuillez utiliser un paquet existant ou le créer préalablement via 'create_deck'."
        )

    deck: Any = db_deck if db_deck is not None else VirtualDeck(id=0, name=dk_clean)

    # 2. Contrôle du type de note
    nt_clean = note_type_name.strip()
    if not nt_clean:
        raise ValueError("Le nom du type de note ne peut pas être vide.")

    nt = NoteTypeModel.get_or_none(NoteTypeModel.name == nt_clean)
    if not nt:
        raise ValueError(f"Type de note '{nt_clean}' introuvable en base.")

    # 3. Contrôle des champs
    if isinstance(fields_input, str):
        try:
            fields_dict = json.loads(fields_input)
        except Exception as e:
            raise ValueError(f"Format JSON invalide pour fields_json : {e}") from e
    elif isinstance(fields_input, dict):
        fields_dict = fields_input
    else:
        raise ValueError("fields_json doit être un dictionnaire ou une chaîne JSON.")

    schema = json.loads(str(nt.fields_schema)) if nt.fields_schema else []
    if not isinstance(schema, list) or not schema:
        raise ValueError(f"Le type de note '{nt.name}' ne possède aucun champ dans son schéma.")

    unknown = set(fields_dict.keys()) - set(schema)
    if unknown:
        raise ValueError(f"Champs inconnus pour le type de note '{nt.name}' : {sorted(list(unknown))}. Champs valides attendus : {schema}.")

    sanitized: dict[str, str] = {k: str(fields_dict.get(k, "")).strip() for k in schema}

    if not any(v for v in sanitized.values()):
        raise ValueError(f"Tous les champs de la note pour le type '{nt.name}' sont vides.")

    # 4. Warnings (doublons sur premier champ physique et virtuel)
    warnings: list[str] = []
    first_field_name = schema[0] if schema else None
    if first_field_name and sanitized.get(first_field_name):
        val_first = sanitized[first_field_name]
        deck_id = int(getattr(deck, "id", 0))
        deck_name_str = str(getattr(deck, "name", dk_clean))
        if deck_id > 0:
            dup_id = _check_first_field_duplicate(deck_id, nt.id, val_first)
            if dup_id:
                warnings.append(f"Doublon potentiel : la note #{dup_id} dans le paquet '{deck_name_str}' possède déjà la valeur '{val_first[:50]}' pour le champ '{first_field_name}'.")
        if overlay and overlay.has_duplicate_first_field(deck_name_str, val_first):
            warnings.append(
                f"Doublon potentiel intra-bundle : une note créée plus tôt dans ce bundle dans le paquet '{deck_name_str}' "
                f"possède déjà la valeur '{val_first[:50]}' pour le champ '{first_field_name}'."
            )

    return nt, deck, sanitized, warnings


@mcp.tool()
def create_note(
    note_type_name: str,
    fields_json: str,
    deck_name: str,
    tags: str = "",
) -> str:
    """Propose la création d'une nouvelle note via un StagedPatch (Two-Phase Commit). Rejette strictement les paquets inexistants."""
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        nt, deck, sanitized_fields, warnings = _validate_note_creation_data(
            note_type_name=note_type_name,
            deck_name=deck_name,
            fields_input=fields_json,
        )

        tags_list = [t.strip() for t in tags.split(",") if t.strip()] if isinstance(tags, str) else list(tags)

        first_field_name = next(iter(sanitized_fields.keys()), "Front")
        first_val = sanitized_fields.get(first_field_name, "")

        diff_payload = {
            "type": "note_create",
            "note_type_name": nt.name,
            "note_type_id": nt.id,
            "deck_name": deck.name,
            "deck_id": deck.id,
            "fields": sanitized_fields,
            "tags": tags_list,
            "warnings": warnings,
            "modified": {
                "Front": first_val,
                "fields": sanitized_fields,
                "deck": deck.name,
                "note_type": nt.name,
                "tags": tags_list,
                "warnings": warnings,
            },
            "title": f"Création de Note dans '{deck.name}' ({nt.name})",
            "explanation": f"Proposition de création d'une note dans le paquet '{deck.name}' avec le type de note '{nt.name}'.",
        }

        patch = StagedPatchRegistry.create_patch(
            patch_type="note_create",
            diff_payload=diff_payload,
        )

        return json.dumps(
            {
                "status": "staged",
                "patch_id": patch.patch_id,
                "note_type": nt.name,
                "deck": deck.name,
                "fields": sanitized_fields,
                "warnings": warnings,
                "message": f"Proposition de création de note enregistrée sous le patch {patch.patch_id}. En attente de validation humaine.",
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error("Erreur create_note : %s", e)
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


@mcp.tool()
def create_notes_batch(
    notes_json: str,
    default_deck: str = "",
    default_note_type: str = "",
    default_tags: str = "",
) -> str:
    """Propose la création d'un lot de notes via un StagedPatch groupé atomique (Two-Phase Commit, validation Tout-ou-Rien)."""
    try:
        from ankiforge.services.ai.staged_patch_registry import StagedPatchRegistry

        try:
            notes_raw = json.loads(notes_json) if isinstance(notes_json, str) else notes_json
        except Exception as e:
            return json.dumps({"status": "error", "message": f"Format JSON invalide pour notes_json : {e}"}, ensure_ascii=False)

        if not isinstance(notes_raw, list) or not notes_raw:
            return json.dumps({"status": "error", "message": "notes_json doit être une liste JSON non vide de notes."}, ensure_ascii=False)

        def_tags_list = [t.strip() for t in default_tags.split(",") if t.strip()] if isinstance(default_tags, str) else list(default_tags)

        validated_notes: list[dict[str, Any]] = []
        all_warnings: list[str] = []

        # Validation Tout-ou-Rien
        for idx, item in enumerate(notes_raw, 1):
            if not isinstance(item, dict):
                return json.dumps({"status": "error", "message": f"Note #{idx} invalide : chaque élément doit être un objet JSON."}, ensure_ascii=False)

            nt_name = str(item.get("note_type") or item.get("note_type_name") or default_note_type).strip()
            dk_name = str(item.get("deck") or item.get("deck_name") or default_deck).strip()
            fields_val = item.get("fields") or item.get("content_dict") or {}

            try:
                nt_obj, dk_obj, sanitized_fields, warnings = _validate_note_creation_data(
                    note_type_name=nt_name,
                    deck_name=dk_name,
                    fields_input=fields_val,
                )
            except ValueError as err:
                return json.dumps({"status": "error", "message": f"Note #{idx} invalide : {err}"}, ensure_ascii=False)

            item_tags = item.get("tags")
            if item_tags is None:
                combined_tags = list(def_tags_list)
            elif isinstance(item_tags, str):
                combined_tags = list(dict.fromkeys(def_tags_list + [t.strip() for t in item_tags.split(",") if t.strip()]))
            else:
                combined_tags = list(dict.fromkeys(def_tags_list + list(item_tags)))

            validated_notes.append(
                {
                    "note_type": nt_obj.name,
                    "deck": dk_obj.name,
                    "fields": sanitized_fields,
                    "tags": combined_tags,
                    "warnings": warnings,
                }
            )
            if warnings:
                all_warnings.extend([f"Note #{idx} : {w}" for w in warnings])

        diff_payload = {
            "type": "batch_note_create",
            "notes": validated_notes,
            "count": len(validated_notes),
            "default_deck": default_deck,
            "default_note_type": default_note_type,
            "default_tags": def_tags_list,
            "warnings": all_warnings,
            "modified": {
                "notes": validated_notes,
                "count": len(validated_notes),
                "warnings": all_warnings,
            },
            "title": f"Création par lot de {len(validated_notes)} note(s)",
            "explanation": f"Proposition de création groupée de {len(validated_notes)} notes via Two-Phase Commit atomique.",
        }

        patch = StagedPatchRegistry.create_patch(
            patch_type="batch_note_create",
            diff_payload=diff_payload,
        )

        return json.dumps(
            {
                "status": "staged",
                "patch_id": patch.patch_id,
                "count": len(validated_notes),
                "warnings": all_warnings,
                "message": f"Proposition de création de {len(validated_notes)} note(s) enregistrée sous le patch {patch.patch_id}. En attente de validation humaine.",
            },
            ensure_ascii=False,
            indent=2,
        )

    except Exception as e:
        logger.error("Erreur create_notes_batch : %s", e)
        return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)


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
    return MCPToolRegistry.find_cards_by_content(query, deck_name, limit=limit, offset=offset)


@mcp.tool()
def list_note_types() -> str:
    """Liste tous les modèles de cartes (Note Types) disponibles dans la collection."""
    return MCPToolRegistry.list_note_types()


@mcp.tool()
def get_note_type_details(note_type_name: str) -> str:
    """Consulte les détails complets d'un modèle de carte (champs requis, templates HTML Recto/Verso, CSS)."""
    return MCPToolRegistry.get_note_type_details(note_type_name)


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
    return MCPToolRegistry.propose_note_type_refactor(note_type_name, new_fields_schema_json, new_css, new_templates_json, new_description, explanation)


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
    return MCPToolRegistry.sanitize_fields_html(
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
    return MCPToolRegistry.set_tags_bulk(
        note_ids=note_ids,
        tags=tags,
        mode=mode,
        allow_remove_provenance_tags=allow_remove_provenance_tags,
    )


@mcp.tool()
def audit_tag_hygiene(
    note_ids: list[int] | str = "",
    deck_id: int | str = "",
    include_levenshtein: bool = True,
) -> str:
    """Analyse la collection pour détecter les grappes de tags sensibles à la casse ou proches selon Levenshtein."""
    return MCPToolRegistry.audit_tag_hygiene(
        note_ids=note_ids or None,
        deck_id=deck_id or None,
        include_levenshtein=include_levenshtein,
    )


@mcp.tool()
def merge_tag_clusters(
    merges: list[dict[str, Any]] | str,
    note_ids: list[int] | str = "",
    deck_id: int | str = "",
) -> str:
    """Applique des fusions de tags planifiées ({tags_to_merge: [...], target_tag: '...'}) sous transaction atomique."""
    return MCPToolRegistry.merge_tag_clusters(
        merges=merges,
        note_ids=note_ids or None,
        deck_id=deck_id or None,
    )


@mcp.tool()
def delete_unused_note_type(
    name: str,
    confirm: bool = False,
) -> str:
    """Supprime un type de note uniquement si 0 note y sont rattachées (garde-fou référentiel). Si name='all_unused', supprime tous les modèles orphelins."""
    return MCPToolRegistry.delete_unused_note_type(name=name, confirm=confirm)


@mcp.tool()
def move_cards_to_deck(
    card_ids: list[int] | str,
    deck: str,
) -> str:
    """Déplace un lot de cartes physiques vers un paquet ou sous-paquet hiérarchique ('Parent::Enfant')."""
    return MCPToolRegistry.move_cards_to_deck(card_ids=card_ids, deck=deck)


@mcp.tool()
def list_empty_cards(
    deck_name: str = "",
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Détecte les cartes physiques dont le recto (question) est vide après substitution du gabarit."""
    return MCPToolRegistry.list_empty_cards(deck_name=deck_name, limit=limit, offset=offset)


@mcp.tool()
def delete_empty_cards(
    card_ids: list[int] | str = "",
    deck_name: str = "",
    confirm: bool = False,
) -> str:
    """Supprime définitivement les cartes à front vide (détection auto ou par identifiants). Action destructive nécessitant confirm=True."""
    return MCPToolRegistry.delete_empty_cards(card_ids=card_ids, deck_name=deck_name, confirm=confirm)


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
    return MCPToolRegistry.format_markdown_document(
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
    return MCPToolRegistry.get_document_outline(document_id=document_id, content=content)


@mcp.tool()
def structure_document_sections(document_id: int = 0, content: str = "", max_tokens: int = 800) -> str:
    """Découpe un document Markdown en sections sémantiques enrichies avec breadcrumbs et statistiques pour le RAG."""
    return MCPToolRegistry.structure_document_sections(
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
    return MCPToolRegistry.structure_transcript_for_ai(
        document_id=document_id,
        content=content,
        profile=profile,
        target_language=target_language,
        preserve_timestamps=preserve_timestamps,
        normalize_latex=normalize_latex,
        add_summary=add_summary,
        add_key_takeaways=add_key_takeaways,
    )


@mcp.tool()
def exclude_document_region(
    document_id: int,
    region_address: str,
    reason: str = "",
) -> str:
    """Écarte une région du document (titre, fil d'Ariane ou page) du dénominateur de couverture et du RAG sans destruction physique (ADR 0010)."""
    return MCPToolRegistry.exclude_document_region(
        document_id=document_id,
        region_address=region_address,
        reason=reason,
    )


@mcp.tool()
def neutralize_document_region(
    document_id: int,
    region_address: str,
    neutralized: bool = True,
) -> str:
    """Neutralise une région pour la retirer du dénominateur de couverture sans l'écarter du document ni des générations (ADR 0010)."""
    return MCPToolRegistry.neutralize_document_region(
        document_id=document_id,
        region_address=region_address,
        neutralized=neutralized,
    )


@mcp.tool()
def update_document_content(
    document_id: int,
    content: str,
    reason: str = "",
) -> str:
    """Pérennise en base le contenu Markdown mis à jour d'un document existant et resynchronise différentiellement ses fragments (ADR 0010, ADR 0042)."""
    return MCPToolRegistry.update_document_content(
        document_id=document_id,
        content=content,
        reason=reason,
    )


@mcp.tool()
def reindex_document(
    document_id: int,
    chunk_size: int = 500,
    overlap: int = 50,
) -> str:
    """Re-découpe un document selon chunk_size et overlap et reconstruit son index vectoriel FAISS et BM25 (ADR 0042)."""
    return MCPToolRegistry.reindex_document(
        document_id=document_id,
        chunk_size=chunk_size,
        overlap=overlap,
    )


# =====================================================================
# OUTILS DE DOCUMENTATION & BASE DE CONNAISSANCES INTERNE (ZENSICAL)
# =====================================================================


@mcp.tool()
def search_app_documentation(query: str, category: str = "", limit: int = 5) -> str:
    """Recherche des explications, guides et références d'architecture dans la documentation officielle d'AnkiForge via SQLite FTS5 BM25."""
    return MCPToolRegistry.search_app_documentation(query, category, limit)


@mcp.tool()
def read_app_doc_page(doc_path: str, section_anchor: str = "") -> str:
    """Consulte le contenu intégral ou une section d'une page de documentation officielle d'AnkiForge (ex: 'features/consultant_mcp.md')."""
    return MCPToolRegistry.read_app_doc_page(doc_path, section_anchor)


@mcp.tool()
def list_app_doc_topics(category: str = "") -> str:
    """Consulte le sommaire exhaustif de la documentation officielle d'AnkiForge classé par thématiques."""
    return MCPToolRegistry.list_app_doc_topics(category)


@mcp.tool()
def get_feature_quick_help(feature_name: str) -> str:
    """Obtient une synthèse immédiate d'une fonctionnalité clé (Ollama, KaTeX, DAG, RAG, Wozniak, Nuitka, Smart Merge, MCP)."""
    return MCPToolRegistry.get_feature_quick_help(feature_name)


# =====================================================================
# RESSOURCES MCP (EXPLORATION DIRECTE DE LA DOCUMENTATION)
# =====================================================================


@mcp.resource("docs://topics")
def get_docs_topics_resource() -> str:
    """Retourne la liste hiérarchique complète des chapitres et pages de la documentation officielle."""
    return MCPToolRegistry.list_app_doc_topics()


@mcp.resource("docs://page/{doc_path}")
def get_doc_page_resource(doc_path: str) -> str:
    """Fournit le contenu brut Markdown d'une page de documentation officielle."""
    return MCPToolRegistry.read_app_doc_page(doc_path)


# =====================================================================
# PROMPTS MCP (MODÈLES DE GUIDAGE IA)
# =====================================================================


@mcp.prompt("explain_ankiforge_feature")
def prompt_explain_feature(feature_name: str) -> str:
    """Prompt guidé pour expliquer pas à pas une fonctionnalité d'AnkiForge avec extraits officiels."""
    doc_summary = MCPToolRegistry.get_feature_quick_help(feature_name)
    return _PROMPT_ENV.from_string(
        "Tu es un expert d'AnkiForge. Explique la fonctionnalité '{{ feature_name }}' en t'appuyant sur la documentation officielle ci-dessous :\n\n"
        "<<< CONTENU UTILISATEUR (FONCTIONNALITÉ) >>>\n{{ feature_name }}\n<<< FIN >>>\n\n"
        "<<< CONTENU DOCUMENTATION OFFICIELLE >>>\n{{ doc_summary }}\n<<< FIN >>>\n\n"
        "Donne des exemples concrets d'utilisation et les bonnes pratiques recommandées."
    ).render(feature_name=feature_name, doc_summary=doc_summary)


@mcp.prompt("audit_architecture_compliance")
def prompt_audit_architecture(target_code_or_rule: str) -> str:
    """Prompt guidé pour vérifier la conformité d'un code ou d'une conception avec les 9 dossiers d'architecture AnkiForge."""
    arch_doc = MCPToolRegistry.read_app_doc_page("Dossier_architecture/02_architecture_technique.md")
    return _PROMPT_ENV.from_string(
        "Tu es l'architecte en chef d'AnkiForge. Vérifie que le code ou la proposition suivante respecte les principes architecturaux "
        "décrits dans la documentation :\n\n"
        "<<< CONTENU DOCUMENTATION ARCHITECTURE >>>\n{{ arch_doc }}...\n<<< FIN >>>\n\n"
        "Élément à auditer :\n<<< CONTENU UTILISATEUR >>>\n{{ target_code_or_rule }}\n<<< FIN >>>"
    ).render(arch_doc=arch_doc[:2500], target_code_or_rule=target_code_or_rule)


# =====================================================================
# OUTILS D'ACCÈS AUX ALBUMS D'IMAGES ET PLANCHES
# =====================================================================


@mcp.tool()
def list_albums(limit: int = 50, offset: int = 0, folder_name: str = "") -> str:
    """Liste les albums d'images et livres scannés enregistrés dans la collection (titre, nombre de planches, dossier, statut d'analyse)."""
    return MCPToolRegistry.list_albums(limit=limit, offset=offset, folder_name=folder_name)


@mcp.tool()
def get_album_plates(
    album_id: int = 0,
    album_title: str = "",
    limit: int = 50,
    offset: int = 0,
    include_ocr_text: bool = True,
) -> str:
    """Consulte la liste ordonnée des planches / pages d'un album avec leurs métadonnées (numéro, rotation, recadrage, statut, texte OCR, fichier média)."""
    return MCPToolRegistry.get_album_plates(
        album_id=album_id,
        album_title=album_title,
        limit=limit,
        offset=offset,
        include_ocr_text=include_ocr_text,
    )


# =====================================================================
# OUTILS DE GESTION DES PIPELINES DAG
# =====================================================================


@mcp.tool()
def list_pipelines(limit: int = 50, offset: int = 0) -> str:
    """Liste les pipelines DAG configurés dans AnkiForge (id, nom, description, étapes ordonnées, branchements, statut du dernier run)."""
    return MCPToolRegistry.list_pipelines(limit=limit, offset=offset)


@mcp.tool()
def get_pipeline_run(run_id: int = 0, pipeline_id: int = 0) -> str:
    """Consulte l'état détaillé d'une exécution de pipeline DAG (statut, étape courante, tokens consommés, erreurs, variables de sortie)."""
    return MCPToolRegistry.get_pipeline_run(run_id=run_id, pipeline_id=pipeline_id)


@mcp.tool()
def trigger_pipeline_run(
    pipeline_id: int,
    deck_name: str,
    cards_json: str,
    note_type_name: str = "",
    document_id: int | None = None,
    variables_json: str = "{}",
) -> str:
    """Déclenche l'exécution asynchrone d'un pipeline DAG de finition sur un lot de cartes pré-générées avec sortie staged (Two-Phase Commit)."""
    return MCPToolRegistry.trigger_pipeline_run(
        pipeline_id=pipeline_id,
        deck_name=deck_name,
        cards_json=cards_json,
        note_type_name=note_type_name,
        document_id=document_id,
        variables_json=variables_json,
    )


# =====================================================================
# GESTION DES AGENTS DÉDIÉS AU SERVEUR MCP
# =====================================================================


@mcp.tool()
def list_mcp_agents(scope: str = "mcp") -> str:
    """Liste tous les agents dédiés enregistrés (Auditeur Wozniak, Architecte CSS, Analyste SRS...) avec leurs outils."""
    return MCPToolRegistry.list_mcp_agents(scope)


@mcp.tool()
def get_mcp_agent_details(agent_name: str) -> str:
    """Consulte la configuration détaillée d'un agent dédié (prompt système Jinja2, modèle assigné, liste des outils)."""
    return MCPToolRegistry.get_mcp_agent_details(agent_name)


@mcp.tool()
def invoke_mcp_agent(agent_name: str, message: str, conversation_history_json: str = "[]") -> str:
    """Délègue une tâche ou une question à un agent dédié spécifique selon ses autorisations d'outils et son prompt."""
    return MCPToolRegistry.invoke_mcp_agent(agent_name, message, conversation_history_json)


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
    return MCPToolRegistry.list_mcp_agents(scope="all")


@mcp.resource("agents://{agent_name}")
def get_agent_profile_resource(agent_name: str) -> str:
    """Fournit le profil et la consigne système d'un agent dédié spécifique."""
    return MCPToolRegistry.get_mcp_agent_details(agent_name)


@mcp.prompt("run_with_agent")
def prompt_run_with_agent(agent_name: str, task: str) -> str:
    """Prompt guidé pour exécuter une tâche en adoptant la posture et les outils d'un agent dédié."""
    agent_info = MCPToolRegistry.get_mcp_agent_details(agent_name)
    return _PROMPT_ENV.from_string(
        "Tu incarnes l'agent spécialisé '{{ agent_name }}'. Voici ton profil et tes consignes strictes :\n\n"
        "<<< CONTENU BDD (PROFIL AGENT) >>>\n{{ agent_info }}\n<<< FIN >>>\n\n"
        "### Mission à accomplir :\n<<< CONTENU UTILISATEUR >>>\n{{ task }}\n<<< FIN >>>\n\n"
        "Respecte strictement tes compétences et ton périmètre d'action."
    ).render(agent_name=agent_name, agent_info=agent_info, task=task)


def _normalise_agent_type(agent_type: str) -> str:
    value = (agent_type or "generic").strip().lower()
    if value == "agy":
        return "gemini"
    return value if value in _GUIDE_AGENT_FILENAMES else "generic"


def _build_tool_catalogue() -> str:
    """Construit le catalogue catégorisé des outils MCP à partir de l'introspection du serveur."""
    try:
        tools = mcp._tool_manager.list_tools()
    except Exception as e:
        logger.warning("Impossible d'introspecter les outils MCP : %s", e)
        return "Catalogue non disponible."
    lines: list[str] = []
    for tool in sorted(tools, key=lambda t: t.name):
        desc = (tool.description or "").strip().replace("\n", " ")
        lines.append(f"- **{tool.name}** : {desc}")
    return "\n".join(lines)


def _build_agents_list() -> str:
    """Renvoie la liste textuelle des agents MCP configurés par l'utilisateur."""
    try:
        return MCPToolRegistry.list_mcp_agents(scope="all")
    except Exception as e:
        logger.warning("Impossible de lister les agents MCP : %s", e)
        return "Aucun agent configuré (erreur de lecture)."


def _render_guide(agent_type: str, include_catalogue: bool) -> str:
    name = _normalise_agent_type(agent_type)
    template_name = f"mcp_init_guide_{name}.md.j2"
    catalogue = _build_tool_catalogue() if include_catalogue else "(catalogue désactivé)"
    agents = _build_agents_list()
    template = _GUIDE_ENV.get_template(template_name)
    return template.render(
        version_hash=_GUIDE_VERSION_HASH,
        include_catalogue=include_catalogue,
        catalogue=catalogue,
        agents=agents,
    )


@mcp.tool()
def init_agent_workspace(
    agent_type: str = "generic",
    workspace_path: str = "",
    include_catalogue: bool = True,
) -> str:
    """Génère un guide méthodologique adapté au type d'agent, dans son répertoire de travail. Si `workspace_path` est vide, renvoie le contenu sans écriture."""
    try:
        content = _render_guide(agent_type, include_catalogue)
    except Exception as e:
        logger.error("Erreur rendu guide d'amorçage : %s", e)
        return f"Erreur lors de la génération du guide : {e}"

    name = _normalise_agent_type(agent_type)
    filename = _GUIDE_AGENT_FILENAMES[name]

    if workspace_path and workspace_path.strip():
        target_dir = Path(workspace_path).expanduser()
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error("Impossible de créer le répertoire %s : %s", target_dir, e)
            return f"Erreur : répertoire inaccessible ({e}). Contenu non écrit.\n\n{content}"
        target_file = target_dir / filename
        try:
            target_file.write_text(content, encoding="utf-8")
        except OSError as e:
            logger.error("Impossible d'écrire %s : %s", target_file, e)
            return f"Erreur : écriture impossible ({e}). Contenu non écrit.\n\n{content}"
        logger.info("Guide d'amorçage généré : %s", target_file)

    return content


@mcp.tool()
def check_guide_version(
    workspace_path: str = "",
    file_path: str = "",
    guide_path: str = "",
    path: str = "",
    agent_type: str = "generic",
) -> str:
    """Compare le hash de version d'un guide sur disque avec la version courante du serveur."""
    import re

    normalised = _normalise_agent_type(agent_type)
    filename = _GUIDE_AGENT_FILENAMES[normalised]

    candidate = ""
    for raw in (file_path, guide_path, path):
        if raw and raw.strip():
            candidate = raw.strip()
            break

    if candidate:
        target = Path(candidate).expanduser()
        # Si un répertoire est fourni, on y cherche le fichier adapté.
        if target.is_dir():
            target = target / filename
    elif workspace_path and workspace_path.strip():
        target = Path(workspace_path).expanduser() / filename
    else:
        return json.dumps(
            {"current_hash": _GUIDE_VERSION_HASH, "stale": False, "file_path": None},
            ensure_ascii=False,
        )

    stale = True
    found_hash: str | None = None
    try:
        if target.exists():
            text = target.read_text(encoding="utf-8")
            match = re.search(r"ankiforge-guide-version:\s*sha256:([0-9a-fA-F]+)", text)
            if match:
                found_hash = match.group(1).lower()
                stale = found_hash != _GUIDE_VERSION_HASH
    except OSError:
        stale = True

    payload = {
        "current_hash": _GUIDE_VERSION_HASH,
        "stale": stale,
        "file_path": str(target),
    }
    if found_hash is not None:
        payload["file_hash"] = found_hash
    return json.dumps(payload, ensure_ascii=False)


@mcp.resource("workspace://agent-guide")
def get_workspace_agent_guide_resource() -> str:
    """Sert le contenu du guide d'amorçage (version generic) en lecture temps réel."""
    return _render_guide("generic", True)


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
