"""Sous-onglet interactif Catalogue des Outils MCP (Model Context Protocol).

Permet d'explorer, de filtrer par catégorie et de rechercher parmi les 63 outils
exposés par le serveur MCP local d'AnkiForge, avec affichage détaillé des schémas
JSON de paramètres, des règles de Two-Phase Commit et des garde-fous associés.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import (
    COMPACT_BUTTON_HEIGHT,
    FilterChipButton,
    SecondaryButton,
    apply_compact_style,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


# ── Configuration des 9 Domaines Fonctionnels MCP ──────────────────────────

DOMAIN_NOTE_TYPES = "note_types"
DOMAIN_CARDS = "cards"
DOMAIN_DECKS = "decks"
DOMAIN_TAGS = "tags"
DOMAIN_DOCUMENTS = "documents"
DOMAIN_ALBUMS = "albums"
DOMAIN_PIPELINES = "pipelines"
DOMAIN_AGENTS = "agents"
DOMAIN_DOCS = "docs"

DOMAIN_METADATA: dict[str, dict[str, str]] = {
    DOMAIN_NOTE_TYPES: {
        "label": "Types de note",
        "icon": "ph.cards",
        "variant": "accent",
    },
    DOMAIN_CARDS: {
        "label": "Notes & Cartes",
        "icon": "ph.cardholder",
        "variant": "primary",
    },
    DOMAIN_DECKS: {
        "label": "Paquets",
        "icon": "ph.stack",
        "variant": "info",
    },
    DOMAIN_TAGS: {
        "label": "Tags",
        "icon": "ph.tag",
        "variant": "warning",
    },
    DOMAIN_DOCUMENTS: {
        "label": "RAG & Documents",
        "icon": "ph.book-open",
        "variant": "neutral",
    },
    DOMAIN_ALBUMS: {
        "label": "Albums & Planches",
        "icon": "ph.image",
        "variant": "secondary",
    },
    DOMAIN_PIPELINES: {
        "label": "Pipelines & DAG",
        "icon": "ph.git-branch",
        "variant": "accent",
    },
    DOMAIN_AGENTS: {
        "label": "Agents MCP & Workspaces",
        "icon": "ph.robot",
        "variant": "primary",
    },
    DOMAIN_DOCS: {
        "label": "Documentation & Aide",
        "icon": "ph.question",
        "variant": "info",
    },
}

# Cartographie explicite des outils par domaine
TOOL_DOMAIN_MAP: dict[str, str] = {
    # 1. Types de note (8)
    "create_note_type": DOMAIN_NOTE_TYPES,
    "change_note_type": DOMAIN_NOTE_TYPES,
    "audit_note_type_conformity": DOMAIN_NOTE_TYPES,
    "preview_card_render": DOMAIN_NOTE_TYPES,
    "list_note_types": DOMAIN_NOTE_TYPES,
    "get_note_type_details": DOMAIN_NOTE_TYPES,
    "propose_note_type_refactor": DOMAIN_NOTE_TYPES,
    "delete_unused_note_type": DOMAIN_NOTE_TYPES,
    # 2. Paquets (9)
    "audit_deck_wozniak": DOMAIN_DECKS,
    "inspect_deck_deep_scan": DOMAIN_DECKS,
    "diagnose_deck_weaknesses": DOMAIN_DECKS,
    "get_deck_stats": DOMAIN_DECKS,
    "list_decks": DOMAIN_DECKS,
    "create_deck": DOMAIN_DECKS,
    "move_cards_to_deck": DOMAIN_DECKS,
    "propose_deck_rename": DOMAIN_DECKS,
    "propose_deck_deletion": DOMAIN_DECKS,
    "export_deck_apkg": DOMAIN_DECKS,
    # 3. Tags (3)
    "set_tags_bulk": DOMAIN_TAGS,
    "audit_tag_hygiene": DOMAIN_TAGS,
    "merge_tag_clusters": DOMAIN_TAGS,
    # 4. RAG & Documents (12)
    "search_knowledge_context": DOMAIN_DOCUMENTS,
    "search_document": DOMAIN_DOCUMENTS,
    "format_markdown_document": DOMAIN_DOCUMENTS,
    "get_document_outline": DOMAIN_DOCUMENTS,
    "structure_document_sections": DOMAIN_DOCUMENTS,
    "structure_transcript_for_ai": DOMAIN_DOCUMENTS,
    "query_peewee": DOMAIN_DOCUMENTS,
    "get_collection_panorama_360": DOMAIN_DOCUMENTS,
    "exclude_document_region": DOMAIN_DOCUMENTS,
    "neutralize_document_region": DOMAIN_DOCUMENTS,
    "update_document_content": DOMAIN_DOCUMENTS,
    "reindex_document": DOMAIN_DOCUMENTS,
    "trigger_manual_backup": DOMAIN_DOCUMENTS,
    # 5. Albums & Planches (3)
    "list_albums": DOMAIN_ALBUMS,
    "get_album_plates": DOMAIN_ALBUMS,
    "correct_plate_ocr": DOMAIN_ALBUMS,
    # 6. Pipelines & DAG (3)
    "list_pipelines": DOMAIN_PIPELINES,
    "get_pipeline_run": DOMAIN_PIPELINES,
    "trigger_pipeline_run": DOMAIN_PIPELINES,
    # 7. Agents MCP & Workspaces (6)
    "list_mcp_agents": DOMAIN_AGENTS,
    "get_mcp_agent_details": DOMAIN_AGENTS,
    "invoke_mcp_agent": DOMAIN_AGENTS,
    "create_or_update_mcp_agent": DOMAIN_AGENTS,
    "init_agent_workspace": DOMAIN_AGENTS,
    "check_guide_version": DOMAIN_AGENTS,
    # 8. Documentation & Aide (4)
    "search_app_documentation": DOMAIN_DOCS,
    "read_app_doc_page": DOMAIN_DOCS,
    "list_app_doc_topics": DOMAIN_DOCS,
    "get_feature_quick_help": DOMAIN_DOCS,
    # 9. Notes & Cartes (20)
    "audit_card_wozniak": DOMAIN_CARDS,
    "find_duplicate_cards": DOMAIN_CARDS,
    "propose_card_refactor": DOMAIN_CARDS,
    "propose_cards_batch_refactor": DOMAIN_CARDS,
    "propose_card_split": DOMAIN_CARDS,
    "propose_card_deletion": DOMAIN_CARDS,
    "propose_batch_card_deletion": DOMAIN_CARDS,
    "apply_patch": DOMAIN_CARDS,
    "preview_and_apply_patch": DOMAIN_CARDS,
    "propose_css_tune": DOMAIN_CARDS,
    "list_card_models_manifest": DOMAIN_CARDS,
    "refactor_cards_by_criteria": DOMAIN_CARDS,
    "get_note_full_profile_360": DOMAIN_CARDS,
    "get_cards_by_deck_or_tag": DOMAIN_CARDS,
    "get_notes_by_model": DOMAIN_CARDS,
    "create_note": DOMAIN_CARDS,
    "create_notes_batch": DOMAIN_CARDS,
    "find_cards_by_content": DOMAIN_CARDS,
    "sanitize_fields_html": DOMAIN_CARDS,
    "list_empty_cards": DOMAIN_CARDS,
    "delete_empty_cards": DOMAIN_CARDS,
    "set_card_flag": DOMAIN_CARDS,
    "suspend_card": DOMAIN_CARDS,
    "unsuspend_card": DOMAIN_CARDS,
    # Staged Bundles & Sessions 2PC (4)
    "begin_staged_bundle": DOMAIN_CARDS,
    "commit_staged_bundle": DOMAIN_CARDS,
    "abort_staged_bundle": DOMAIN_CARDS,
    "get_staged_pending_operations": DOMAIN_CARDS,
}

# Garde-fous et directives de sécurité spécifiques
TOOL_SAFEGUARDS_MAP: dict[str, list[str]] = {
    "create_note": [
        "Two-Phase Commit obligatoire : génère une proposition (StagedPatch note_create) soumise à validation humaine.",
        "Contrôle d'anti-hallucination : le paquet cible (deck_name) doit impérativement exister dans la base.",
        "Détection préventive des doublons : avertit sans bloquer si une carte similaire existe déjà.",
    ],
    "create_notes_batch": [
        "Two-Phase Commit universel : génère un unique patch groupé (batch_note_create).",
        "Transaction atomique Tout-ou-Rien : inséré via une seule transaction db.atomic().",
        "Contrôle d'anti-hallucination : validation stricte des paquets et types de note avant création.",
    ],
    "create_note_type": [
        "Two-Phase Commit obligatoire : génère un patch staged note_type_create sans altération directe de la base.",
        "Vérification des collisions : impose l'unicité du nom de type de note ou un mode explicite.",
    ],
    "change_note_type": [
        "Two-Phase Commit obligatoire : génère un patch staged note_type_change.",
        "Préservation stricte du SRS : aucune carte n'est recréée, l'historique de révision est intégralement conservé.",
        "Transaction atomique unique : rollback total en cas d'erreur de correspondance de champs.",
    ],
    "propose_card_refactor": [
        "Two-Phase Commit obligatoire : produit un StagedPatch avec diff mot-à-mot intra-ligne.",
        "Validation humaine requise avant application physique sur les cartes SRS.",
    ],
    "propose_cards_batch_refactor": [
        "Two-Phase Commit obligatoire : génère un StagedBundle multi-étapes avec diff unitaire par carte.",
        "Validation granulaire : revue carte par carte ou validation groupée en un clic (Tout valider le bloc).",
        "Plafond de sécurité strict : limité à 100 cartes maximum par appel.",
        "Gestion hybride des tags : supporte le remplacement complet (tags) ou incrémental (add_tags/remove_tags).",
    ],
    "propose_card_split": [
        "Two-Phase Commit obligatoire : propose la scission atomique en préservant la carte mère.",
    ],
    "propose_card_deletion": [
        "Two-Phase Commit obligatoire : enregistre une proposition staged (note_delete) soumise à validation humaine.",
        "Verrouillage optimiste de version : empêche la suppression si la note a été modifiée concurremment.",
    ],
    "propose_batch_card_deletion": [
        "Two-Phase Commit obligatoire : enregistre une proposition groupée staged (batch_note_delete).",
        "Transaction atomique : validation et suppression de l'ensemble du lot sous un unique verrou.",
    ],
    "propose_deck_rename": [
        "Two-Phase Commit obligatoire : enregistre une proposition staged (deck_rename) avant altération de l'arborescence.",
        "Contrôle anti-collision : vérifie l'existence du paquet source et la disponibilité du nom cible.",
    ],
    "propose_deck_deletion": [
        "Two-Phase Commit obligatoire : proposition staged (deck_delete) avec réassignation optionnelle des cartes.",
        "Préservation des cartes : autorise le déplacement préventif vers un paquet de repli avant suppression.",
    ],
    "propose_note_type_refactor": [
        "Two-Phase Commit obligatoire : modélisation de gabarit soumise à révision préalable.",
    ],
    "propose_css_tune": [
        "Two-Phase Commit obligatoire : prévisualisation du rendu stylistique et persistance d'un StagedPatch avant injection.",
    ],
    "sanitize_fields_html": [
        "Two-Phase Commit systématique (100% 2PC) : nettoyage sécurisé du balisage HTML inline sans seuil empirique.",
    ],
    "delete_unused_note_type": [
        "Intégrité référentielle stricte : la suppression est formellement rejetée si au moins une note y est rattachée.",
    ],
    "delete_empty_cards": [
        "Two-Phase Commit obligatoire : proposition staged (empty_cards_delete) des cartes à front vide sans suppression directe.",
    ],
    "exclude_document_region": [
        "Délimitation non destructive (ADR 0010) : la région est écartée du calcul de couverture et du RAG sans suppression physique.",
        "Validation stricte de l'adresse canonique (node:, heading:, page:).",
    ],
    "neutralize_document_region": [
        "Neutralisation non destructive (ADR 0010) : retire la région du dénominateur de couverture sans l'écarter du document ni des générations.",
        "Validation stricte de l'adresse canonique (node:, heading:, page:).",
    ],
    "update_document_content": [
        "Persistance pérenne en base : synchronise différentiellement les fragments pour préserver les rattachements de cartes de couverture (ADR 0009).",
        "Traçabilité et audit des modifications de contenu.",
    ],
    "reindex_document": [
        "Reconstruction vectorielle et lexicale (FAISS + BM25) : met à jour l'indexation RAG après révision ou délimitation.",
        "Recalcul des fragments par ChunkingService selon chunk_size et overlap.",
    ],
    "query_peewee": [
        "Sécurité base de données : restreint strictement aux requêtes SQL en lecture seule (SELECT).",
    ],
    "invoke_mcp_agent": [
        "Anti-escalade de privilèges : interdiction formelle de l'accès universel (*) et du shell Python.",
    ],
    "create_or_update_mcp_agent": [
        "Anti-escalade de privilèges : l'agent configuré ne peut pas s'auto-attribuer de permissions non vérifiées.",
    ],
    "set_tags_bulk": [
        "Conformité du schéma : emprunte systématiquement l'écrivain canonique des tags de note.",
    ],
    "check_guide_version": [
        "Audit d'intégrité non destructif : compare l'empreinte cryptographique SHA-256 du guide.",
    ],
    "create_deck": [
        "Écriture directe et idempotente : crée le paquet et toute son arborescence hiérarchique Parent::Enfant.",
    ],
    "begin_staged_bundle": [
        "Session transactionnelle groupée : initialise le contexte virtuel Staged Overlay pour résolution intra-bloc.",
    ],
    "commit_staged_bundle": [
        "Two-Phase Commit obligatoire : scelle le bundle au statut pending et le transmet au Garde-Fou.",
        "Contrôle de complétude : impose au moins une étape pour être scellé.",
    ],
    "abort_staged_bundle": [
        "Nettoyage transactionnel : supprime le bundle en cours de construction et toutes ses étapes associées.",
    ],
    "trigger_pipeline_run": [
        "Déclenchement asynchrone non-bloquant : exécution découplée dans QThreadPool avec sortie Staged.",
        "Contrôle anti-hallucination strict : le paquet cible (deck_name) doit impérativement exister dans la base.",
        "Finalisation Staged automatique : conversion automatique des cartes traitées en StagedBundle (batch_note_create).",
    ],
    "export_deck_apkg": [
        "Vérification d'existence du paquet cible avant génération du paquet.",
        "Production d'un fichier .apkg autonome à IDs stables préservant la compatibilité Anki.",
    ],
    "set_card_flag": [
        "Contrôle strict des couleurs de drapeau supportées (red, orange, green, blue, pink, turquoise, purple, none).",
        "Mutation directe et cohérente sur l'ensemble des cartes physiques liées à la note.",
    ],
    "suspend_card": [
        "Bascule immédiate de la carte physique à l'état suspendu (queue SRS -1).",
    ],
    "unsuspend_card": [
        "Réactivation immédiate de la carte dans le cycle de révision SRS.",
    ],
    "correct_plate_ocr": [
        "Mise à jour directe de la couche textuelle OCR sans altération de l'image source.",
    ],
    "trigger_manual_backup": [
        "Création d'un instantané atomique SQLite compatible WAL exclu de la rotation standard.",
    ],
}


@dataclass
class MCPToolItem:
    """Modèle en mémoire représentant un outil MCP et ses métadonnées techniques."""

    name: str
    domain: str
    domain_label: str
    domain_icon: str
    domain_badge_variant: str
    description: str
    summary: str
    parameters: dict[str, Any] = field(default_factory=dict)
    safeguards: list[str] = field(default_factory=list)


def get_all_mcp_tools(raw_tools: list[Any] | None = None) -> list[MCPToolItem]:
    """Extrait et classe l'ensemble des outils MCP du serveur local."""
    tools_list: list[Any] = []
    if raw_tools is not None:
        tools_list = raw_tools
    else:
        try:
            from ankiforge.services.ai.mcp_server import mcp

            tools_list = mcp._tool_manager.list_tools()
        except Exception as exc:
            logger.warning("Impossible d'introspecter mcp._tool_manager : %s", exc)
            return []

    items: list[MCPToolItem] = []
    for raw in tools_list:
        name = getattr(raw, "name", "")
        if not name:
            continue

        raw_desc = getattr(raw, "description", "") or ""
        lines = [line.strip() for line in raw_desc.splitlines() if line.strip()]
        summary = lines[0] if lines else tr("(Aucune description fournie)")

        domain = TOOL_DOMAIN_MAP.get(name)
        if not domain:
            # Règle de repli déterministe par préfixe / suffixe
            if "deck" in name:
                domain = DOMAIN_DECKS
            elif "tag" in name:
                domain = DOMAIN_TAGS
            elif "note_type" in name or "model" in name:
                domain = DOMAIN_NOTE_TYPES
            elif "album" in name:
                domain = DOMAIN_ALBUMS
            elif "pipeline" in name:
                domain = DOMAIN_PIPELINES
            elif "agent" in name or "workspace" in name:
                domain = DOMAIN_AGENTS
            elif "doc" in name or "help" in name:
                domain = DOMAIN_DOCS
            elif "doc" in name or "knowledge" in name or "outline" in name or "structure" in name:
                domain = DOMAIN_DOCUMENTS
            else:
                domain = DOMAIN_CARDS

        meta = DOMAIN_METADATA.get(
            domain,
            {"label": domain, "icon": "ph.wrench", "variant": "neutral"},
        )

        params = getattr(raw, "parameters", {})
        if not isinstance(params, dict):
            params = {}

        safeguards = TOOL_SAFEGUARDS_MAP.get(name, [])

        items.append(
            MCPToolItem(
                name=name,
                domain=domain,
                domain_label=meta["label"],
                domain_icon=meta["icon"],
                domain_badge_variant=meta["variant"],
                description=raw_desc,
                summary=summary,
                parameters=params,
                safeguards=safeguards,
            )
        )

    # Tri alphabétique par nom canonique
    items.sort(key=lambda item: item.name)
    return items


# ── Composant Ligne de la Liste d'Outils ──────────────────────────────────


class MCPToolListRowWidget(QWidget):
    """Ligne personnalisée affichant le nom, le badge de domaine et le résumé de l'outil."""

    def __init__(self, tool: MCPToolItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tool = tool
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Ligne supérieure : Nom canonique + Badge de domaine
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        self.lbl_name = QLabel(self.tool.name)
        self.lbl_name.setStyleSheet(f"""
            QLabel {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 12px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
        """)
        top_row.addWidget(self.lbl_name, 1)

        self.badge = Badge(self.tool.domain_label, variant=self.tool.domain_badge_variant)
        self.badge.setMinimumWidth(self.badge.sizeHint().width())
        top_row.addWidget(self.badge)
        layout.addLayout(top_row)

        # Ligne inférieure : Résumé court (1 ligne)
        self.lbl_summary = QLabel(self.tool.summary)
        self.lbl_summary.setStyleSheet(f"""
            QLabel {{
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
        """)
        self.lbl_summary.setWordWrap(False)
        layout.addWidget(self.lbl_summary)


# ── Composant Principal du Catalogue d'Outils ─────────────────────────────


class MCPToolCatalogWidget(QWidget):
    """Catalogue interactif et pédagogique des 58 outils du serveur MCP local."""

    def __init__(
        self,
        raw_tools: list[Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("MCPToolCatalogWidget")

        self._tools = get_all_mcp_tools(raw_tools)
        self._filtered_tools: list[MCPToolItem] = list(self._tools)
        self._current_tool: MCPToolItem | None = None
        self._active_domain: str | None = None  # None = Tous

        self._setup_ui()
        self._populate_list()

    @property
    def current_selected_tool(self) -> MCPToolItem | None:
        """Outil actuellement sélectionné et affiché dans la fiche technique."""
        return self._current_tool

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # ── 1. EN-TÊTE : RECHERCHE ET RUBAN DE PUCES ─────────────────────
        top_header_layout = QHBoxLayout()
        top_header_layout.setContentsMargins(0, 0, 0, 0)
        top_header_layout.setSpacing(12)

        # Champ de recherche avec loupe vectorielle
        self.edit_search = QLineEdit(self)
        self.edit_search.setObjectName("mcp_catalog_search_input")
        self.edit_search.setPlaceholderText(tr("Rechercher un outil (nom, description, paramètre)..."))
        self.edit_search.setFixedHeight(32)
        self.edit_search.setClearButtonEnabled(True)
        self.edit_search.setStyleSheet(f"""
            QLineEdit#mcp_catalog_search_input {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 0 10px;
                font-size: 12px;
            }}
            QLineEdit#mcp_catalog_search_input:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.edit_search.textChanged.connect(self._apply_filters)
        top_header_layout.addWidget(self.edit_search, 1)

        # Compteur d'outils
        self.lbl_tool_count = QLabel(self)
        self.lbl_tool_count.setObjectName("mcp_catalog_count_label")
        self.lbl_tool_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; font-weight: 600;")
        top_header_layout.addWidget(self.lbl_tool_count)

        main_layout.addLayout(top_header_layout)

        # Ruban horizontal défilable de puces de domaines (FilterChipButton)
        chips_scroll = QScrollArea(self)
        chips_scroll.setObjectName("mcp_catalog_chips_scroll")
        chips_scroll.setWidgetResizable(True)
        chips_scroll.setFixedHeight(46)
        chips_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chips_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        chips_scroll.setStyleSheet(f"""
            QScrollArea#mcp_catalog_chips_scroll {{
                background: transparent;
                border: none;
            }}
            QScrollArea#mcp_catalog_chips_scroll QScrollBar:horizontal {{
                height: 4px;
                background: transparent;
                margin: 0px;
            }}
            QScrollArea#mcp_catalog_chips_scroll QScrollBar::handle:horizontal {{
                background-color: {DesignTokens.BORDER_COLOR};
                border-radius: 2px;
                min-width: 24px;
            }}
            QScrollArea#mcp_catalog_chips_scroll QScrollBar::handle:horizontal:hover {{
                background-color: {DesignTokens.TEXT_MUTED};
            }}
            QScrollArea#mcp_catalog_chips_scroll QScrollBar::add-line:horizontal,
            QScrollArea#mcp_catalog_chips_scroll QScrollBar::sub-line:horizontal {{
                width: 0px;
                height: 0px;
                border: none;
            }}
        """)

        chips_container = QWidget(chips_scroll)
        chips_container.setStyleSheet("background: transparent;")
        chips_layout = QHBoxLayout(chips_container)
        chips_layout.setContentsMargins(2, 2, 2, 6)
        chips_layout.setSpacing(6)
        chips_layout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetMinAndMaxSize)

        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)

        # Puce 'Tous'
        total_count = len(self._tools)
        self.chip_all = FilterChipButton(
            tr("Tous (%1)", total_count),
            icon_name="ph.wrench",
            parent=chips_container,
        )
        self.chip_all.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.chip_all.setMinimumWidth(self.chip_all.sizeHint().width() + 6)
        self.chip_all.setChecked(True)
        self.chip_all.clicked.connect(lambda: self._on_domain_chip_clicked(None))
        self._chip_group.addButton(self.chip_all)
        chips_layout.addWidget(self.chip_all)

        # 9 Puces de domaines
        self.domain_chips: dict[str, FilterChipButton] = {}
        for domain_key, meta in DOMAIN_METADATA.items():
            count = sum(1 for t in self._tools if t.domain == domain_key)
            chip = FilterChipButton(
                tr("%1 (%2)", tr(str(meta["label"])), count),
                icon_name=meta["icon"],
                parent=chips_container,
            )
            chip.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            chip.setMinimumWidth(chip.sizeHint().width() + 6)
            chip.clicked.connect(lambda _, dk=domain_key: self._on_domain_chip_clicked(dk))
            self._chip_group.addButton(chip)
            chips_layout.addWidget(chip)
            self.domain_chips[domain_key] = chip

        chips_layout.addStretch()
        chips_scroll.setWidget(chips_container)
        main_layout.addWidget(chips_scroll)

        # ── 2. CORPS : SPLITTER HORIZONTAL 50% / 50% ─────────────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setObjectName("mcp_catalog_splitter")
        self.splitter.setChildrenCollapsible(False)

        # ── VOLET GAUCHE : LISTE DES OUTILS ──
        self.left_pane = QFrame(self.splitter)
        self.left_pane.setObjectName("mcp_catalog_left_pane")
        self.left_pane.setStyleSheet(f"""
            QFrame#mcp_catalog_left_pane {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        left_layout = QVBoxLayout(self.left_pane)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)

        self.lbl_list_header = QLabel(tr("OUTILS DISPONIBLES"), self.left_pane)
        self.lbl_list_header.setStyleSheet(f"""
            QLabel {{
                color: {DesignTokens.TEXT_MUTED};
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.5px;
                border: none;
                background: transparent;
            }}
        """)
        left_layout.addWidget(self.lbl_list_header)

        self.tool_list = QListWidget(self.left_pane)
        self.tool_list.setObjectName("mcp_catalog_tool_list")
        self.tool_list.setFrameShape(QFrame.Shape.NoFrame)
        self.tool_list.setStyleSheet(f"""
            QListWidget#mcp_catalog_tool_list {{
                background-color: transparent;
                border: none;
            }}
            QListWidget#mcp_catalog_tool_list::item {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 4px;
                padding: 2px;
            }}
            QListWidget#mcp_catalog_tool_list::item:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget#mcp_catalog_tool_list::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.tool_list.currentItemChanged.connect(self._on_item_selection_changed)
        left_layout.addWidget(self.tool_list, 1)

        self.splitter.addWidget(self.left_pane)

        # ── VOLET DROIT : FICHE TECHNIQUE DÉTAILLÉE ──
        self.right_pane = QFrame(self.splitter)
        self.right_pane.setObjectName("mcp_catalog_right_pane")
        self.right_pane.setStyleSheet(f"""
            QFrame#mcp_catalog_right_pane {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        right_layout = QVBoxLayout(self.right_pane)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.detail_stack = QStackedWidget(self.right_pane)

        # Page 0 : État vide (aucun outil sélectionné)
        self.page_empty = QWidget(self.detail_stack)
        empty_layout = QVBoxLayout(self.page_empty)
        empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.setSpacing(12)

        icon_empty = QLabel(self.page_empty)
        icon_empty.setPixmap(load_phosphor_icon("ph.wrench", color=DesignTokens.TEXT_MUTED).pixmap(48, 48))
        icon_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_empty.setStyleSheet("border: none; background: transparent; opacity: 0.6;")
        empty_layout.addWidget(icon_empty)

        lbl_empty_title = QLabel(tr("Sélectionnez un outil"), self.page_empty)
        lbl_empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: 700; border: none;")
        empty_layout.addWidget(lbl_empty_title)

        lbl_empty_desc = QLabel(
            tr("Choisissez un outil dans le volet gauche pour inspecter sa description, ses paramètres et ses garde-fous."),
            self.page_empty,
        )
        lbl_empty_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_empty_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; border: none;")
        lbl_empty_desc.setWordWrap(True)
        lbl_empty_desc.setMaximumWidth(360)
        empty_layout.addWidget(lbl_empty_desc)

        self.detail_stack.addWidget(self.page_empty)

        # Page 1 : Fiche technique complète dans une QScrollArea
        self.detail_scroll = QScrollArea(self.detail_stack)
        self.detail_scroll.setObjectName("mcp_catalog_detail_scroll")
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_scroll.setStyleSheet("QScrollArea#mcp_catalog_detail_scroll { background: transparent; border: none; }")

        self.detail_container = QWidget(self.detail_scroll)
        self.detail_container.setStyleSheet("background: transparent;")
        self._setup_detail_view(self.detail_container)

        self.detail_scroll.setWidget(self.detail_container)
        self.detail_stack.addWidget(self.detail_scroll)

        right_layout.addWidget(self.detail_stack)
        self.splitter.addWidget(self.right_pane)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([450, 450])

        main_layout.addWidget(self.splitter, 1)

    def _setup_detail_view(self, container: QWidget) -> None:
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── En-tête de la fiche technique ──
        header_box = QHBoxLayout()
        header_box.setContentsMargins(0, 0, 0, 0)
        header_box.setSpacing(10)

        self.lbl_detail_icon = QLabel(container)
        self.lbl_detail_icon.setFixedSize(28, 28)
        self.lbl_detail_icon.setStyleSheet("border: none; background: transparent;")
        header_box.addWidget(self.lbl_detail_icon)

        self.lbl_detail_name = QLabel(container)
        self.lbl_detail_name.setObjectName("mcp_catalog_detail_name")
        self.lbl_detail_name.setStyleSheet(f"""
            QLabel#mcp_catalog_detail_name {{
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 16px;
                font-weight: 700;
                border: none;
            }}
        """)
        header_box.addWidget(self.lbl_detail_name)

        self.lbl_detail_badge = Badge("", variant="primary")
        header_box.addWidget(self.lbl_detail_badge)

        header_box.addStretch()

        self.btn_copy_tool_name = SecondaryButton(tr("Copier le nom"), parent=container)
        self.btn_copy_tool_name.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(self.btn_copy_tool_name, height=COMPACT_BUTTON_HEIGHT)
        self.btn_copy_tool_name.clicked.connect(self._copy_tool_name)
        header_box.addWidget(self.btn_copy_tool_name)

        layout.addLayout(header_box)

        # ── Carte Description complète ──
        self.desc_frame = QFrame(container)
        self.desc_frame.setObjectName("mcp_catalog_desc_frame")
        self.desc_frame.setStyleSheet(f"""
            QFrame#mcp_catalog_desc_frame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 10px;
            }}
        """)
        desc_layout = QVBoxLayout(self.desc_frame)
        desc_layout.setContentsMargins(8, 8, 8, 8)
        desc_layout.setSpacing(4)

        lbl_desc_title = QLabel(tr("DESCRIPTION DE LA FONCTION :"), self.desc_frame)
        lbl_desc_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 700; border: none;")
        desc_layout.addWidget(lbl_desc_title)

        self.lbl_detail_desc = QLabel(self.desc_frame)
        self.lbl_detail_desc.setWordWrap(True)
        self.lbl_detail_desc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_detail_desc.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12.5px; line-height: 1.4; border: none;")
        desc_layout.addWidget(self.lbl_detail_desc)

        layout.addWidget(self.desc_frame)

        # ── Carte Garde-fous et Directives de Sécurité ──
        self.frame_safeguards = QFrame(container)
        self.frame_safeguards.setObjectName("mcp_catalog_safeguards_frame")
        self.frame_safeguards.setStyleSheet(f"""
            QFrame#mcp_catalog_safeguards_frame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.COLOR_ORANGE};
                border-left: 4px solid {DesignTokens.COLOR_ORANGE};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
            }}
        """)
        sg_layout = QVBoxLayout(self.frame_safeguards)
        sg_layout.setContentsMargins(8, 6, 8, 6)
        sg_layout.setSpacing(4)

        sg_header = QHBoxLayout()
        sg_header.setSpacing(6)
        icon_sg = QLabel(self.frame_safeguards)
        icon_sg.setPixmap(load_phosphor_icon("ph.shield-check", color=DesignTokens.COLOR_ORANGE).pixmap(16, 16))
        icon_sg.setStyleSheet("border: none; background: transparent;")
        sg_header.addWidget(icon_sg)

        lbl_sg_title = QLabel(tr("GARDE-FOUS & SÉCURITÉ"), self.frame_safeguards)
        lbl_sg_title.setStyleSheet(f"color: {DesignTokens.COLOR_ORANGE}; font-size: 11px; font-weight: 700; border: none;")
        sg_header.addWidget(lbl_sg_title)
        sg_header.addStretch()
        sg_layout.addLayout(sg_header)

        self.lbl_safeguards_content = QLabel(self.frame_safeguards)
        self.lbl_safeguards_content.setWordWrap(True)
        self.lbl_safeguards_content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_safeguards_content.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11.5px; border: none;")
        sg_layout.addWidget(self.lbl_safeguards_content)

        layout.addWidget(self.frame_safeguards)

        # ── Section Tableau des Paramètres ──
        self.lbl_params_title = QLabel(tr("PARAMÈTRES D'APPEL"), container)
        self.lbl_params_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; border: none;")
        layout.addWidget(self.lbl_params_title)

        self.lbl_no_params = QLabel(tr("(Cet outil ne requiert aucun paramètre d'entrée)"), container)
        self.lbl_no_params.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 12px; font-style: italic; border: none;")
        layout.addWidget(self.lbl_no_params)

        self.params_table = QTableWidget(container)
        self.params_table.setObjectName("mcp_catalog_params_table")
        self.params_table.setColumnCount(4)
        self.params_table.setHorizontalHeaderLabels(
            [
                tr("Nom"),
                tr("Type"),
                tr("Requis ?"),
                tr("Description / Valeur par défaut"),
            ]
        )
        self.params_table.verticalHeader().setVisible(False)
        self.params_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.params_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.params_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.params_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.params_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.params_table.setColumnWidth(2, 95)
        self.params_table.horizontalHeader().setStretchLastSection(True)
        self.params_table.setStyleSheet(f"""
            QTableWidget#mcp_catalog_params_table {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                gridline-color: {DesignTokens.BORDER_COLOR};
                font-size: 11.5px;
            }}
            QHeaderView::section {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_SECONDARY};
                font-size: 10px;
                font-weight: 700;
                padding: 4px;
                border: none;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
            }}
        """)
        layout.addWidget(self.params_table)

        # ── Section Signature JSON d'exemple ──
        sig_header = QHBoxLayout()
        sig_header.setSpacing(8)

        lbl_sig = QLabel(tr("SIGNATURE D'APPEL JSON :"), container)
        lbl_sig.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 700; border: none;")
        sig_header.addWidget(lbl_sig)
        sig_header.addStretch()

        self.btn_copy_json_signature = SecondaryButton(tr("Copier la signature JSON"), parent=container)
        self.btn_copy_json_signature.setIcon(load_phosphor_icon("ph.code", color=DesignTokens.TEXT_PRIMARY))
        apply_compact_style(self.btn_copy_json_signature, height=COMPACT_BUTTON_HEIGHT)
        self.btn_copy_json_signature.clicked.connect(self._copy_json_signature)
        sig_header.addWidget(self.btn_copy_json_signature)
        layout.addLayout(sig_header)

        self.edit_json_signature = QPlainTextEdit(container)
        self.edit_json_signature.setObjectName("mcp_catalog_json_signature")
        self.edit_json_signature.setReadOnly(True)
        self.edit_json_signature.setMaximumHeight(120)
        self.edit_json_signature.setStyleSheet(f"""
            QPlainTextEdit#mcp_catalog_json_signature {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                font-family: {DesignTokens.FONT_CODE};
                font-size: 11px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.edit_json_signature)

        layout.addStretch()

    # ── Logique de Filtrage et Peuplement ────────────────────────────────────

    def _on_domain_chip_clicked(self, domain_key: str | None) -> None:
        """Gère le basculement d'une puce de domaine."""
        self._active_domain = domain_key
        self._apply_filters()

    def _apply_filters(self) -> None:
        """Applique les filtres combinés par domaine et par texte de recherche."""
        search_query = self.edit_search.text().strip().lower()

        filtered: list[MCPToolItem] = []
        for tool in self._tools:
            # 1. Filtre par domaine
            if self._active_domain is not None and tool.domain != self._active_domain:
                continue

            # 2. Filtre par texte
            if search_query:
                in_name = search_query in tool.name.lower()
                in_desc = search_query in tool.description.lower()
                in_params = any(search_query in p_name.lower() for p_name in tool.parameters.get("properties", {}))
                if not (in_name or in_desc or in_params):
                    continue

            filtered.append(tool)

        self._filtered_tools = filtered
        self._populate_list()

    def _populate_list(self) -> None:
        """Remplit la liste gauche avec les outils filtrés."""
        self.tool_list.blockSignals(True)
        self.tool_list.clear()

        for tool in self._filtered_tools:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, tool)
            item.setSizeHint(QSize(0, 52))

            row_widget = MCPToolListRowWidget(tool)
            self.tool_list.addItem(item)
            self.tool_list.setItemWidget(item, row_widget)

        self.tool_list.blockSignals(False)

        # Mise à jour du libellé de comptage
        total = len(self._tools)
        visible = len(self._filtered_tools)
        if visible == total:
            self.lbl_tool_count.setText(tr("%1 outils disponibles", total))
        else:
            self.lbl_tool_count.setText(tr("%1 / %2 outils", visible, total))

        # Sélection par défaut du premier élément s'il y en a
        if self._filtered_tools:
            self.tool_list.setCurrentRow(0)
            self._display_tool_detail(self._filtered_tools[0])
            self.detail_stack.setCurrentIndex(1)
        else:
            self._current_tool = None
            self.detail_stack.setCurrentIndex(0)

    def _on_item_selection_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        """Réagit à la sélection d'un outil dans la liste gauche."""
        if not current:
            self._current_tool = None
            self.detail_stack.setCurrentIndex(0)
            return

        tool = current.data(Qt.ItemDataRole.UserRole)
        if isinstance(tool, MCPToolItem):
            self._display_tool_detail(tool)
            self.detail_stack.setCurrentIndex(1)

    def select_tool_by_name(self, name: str) -> bool:
        """Sélectionne un outil par son nom canonique dans la liste."""
        for row in range(self.tool_list.count()):
            item = self.tool_list.item(row)
            tool = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(tool, MCPToolItem) and tool.name == name:
                self.tool_list.setCurrentRow(row)
                return True
        return False

    def _display_tool_detail(self, tool: MCPToolItem) -> None:
        """Met à jour l'ensemble des composants de la fiche technique."""
        self._current_tool = tool

        # En-tête
        self.lbl_detail_icon.setPixmap(load_phosphor_icon(tool.domain_icon, color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        self.lbl_detail_name.setText(tool.name)
        self.lbl_detail_badge.setText(tool.domain_label)
        self.lbl_detail_badge.set_variant(tool.domain_badge_variant)

        # Description complète
        self.lbl_detail_desc.setText(tool.description)

        # Garde-fous et sécurité
        if tool.safeguards:
            bullets = "\n".join(f"• {sg}" for sg in tool.safeguards)
            self.lbl_safeguards_content.setText(bullets)
            self.frame_safeguards.show()
        else:
            self.frame_safeguards.hide()

        # Paramètres d'appel
        props = tool.parameters.get("properties", {})
        required_list = tool.parameters.get("required", [])

        if not props:
            self.lbl_no_params.show()
            self.params_table.hide()
            self.lbl_params_title.setText(tr("PARAMÈTRES D'APPEL (0)"))
        else:
            self.lbl_no_params.hide()
            self.params_table.show()
            self.lbl_params_title.setText(tr("PARAMÈTRES D'APPEL (%1)", len(props)))
            self._populate_params_table(props, required_list)

        # Signature JSON d'exemple
        sample_args: dict[str, Any] = {}
        for p_name, p_info in props.items():
            p_type = p_info.get("type", "string")
            if "default" in p_info:
                sample_args[p_name] = p_info["default"]
            elif p_type == "integer":
                sample_args[p_name] = 0
            elif p_type == "number":
                sample_args[p_name] = 0.0
            elif p_type == "boolean":
                sample_args[p_name] = False
            elif p_type == "array":
                sample_args[p_name] = []
            elif p_type == "object":
                sample_args[p_name] = {}
            else:
                sample_args[p_name] = f"<{p_name}>"

        sig_payload = {
            "name": tool.name,
            "arguments": sample_args,
        }
        self.edit_json_signature.setPlainText(json.dumps(sig_payload, indent=2, ensure_ascii=False))

    def _populate_params_table(self, props: dict[str, Any], required_list: list[str]) -> None:
        """Remplit le tableau des paramètres avec les types et les badges."""
        self.params_table.clearContents()
        self.params_table.setRowCount(len(props))

        for row, (p_name, p_info) in enumerate(props.items()):
            # 1. Nom
            item_name = QTableWidgetItem(p_name)
            font_code = QFont(DesignTokens.FONT_CODE, 10)
            font_code.setBold(True)
            item_name.setFont(font_code)
            item_name.setForeground(QColor(DesignTokens.TEXT_PRIMARY))
            self.params_table.setItem(row, 0, item_name)

            # 2. Type
            p_type = p_info.get("type", "any")
            item_type = QTableWidgetItem(p_type)
            item_type.setForeground(QColor(DesignTokens.TEXT_MUTED))
            self.params_table.setItem(row, 1, item_type)

            # 3. Requis ?
            is_req = p_name in required_list
            item_req = QTableWidgetItem(tr("Requis") if is_req else tr("Optionnel"))
            item_req.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            font_req = QFont(DesignTokens.FONT_MAIN, 10)
            font_req.setBold(is_req)
            item_req.setFont(font_req)
            if is_req:
                item_req.setForeground(QColor(DesignTokens.COLOR_RED))
            else:
                item_req.setForeground(QColor(DesignTokens.TEXT_MUTED))
            self.params_table.setItem(row, 2, item_req)

            # 4. Description et valeur par défaut
            desc_parts: list[str] = []
            if "description" in p_info and p_info["description"]:
                desc_parts.append(str(p_info["description"]))
            if "default" in p_info:
                desc_parts.append(tr("(défaut: %1)", str(p_info["default"])))

            desc_text = " ".join(desc_parts) if desc_parts else "—"
            item_desc = QTableWidgetItem(desc_text)
            self.params_table.setItem(row, 3, item_desc)

            self.params_table.setRowHeight(row, 32)

        # Ajustement de la hauteur du tableau
        table_height = min(240, 36 + len(props) * 32)
        self.params_table.setFixedHeight(table_height)

    # ── Actions Utilisateur ──────────────────────────────────────────────────

    def _copy_tool_name(self) -> None:
        """Copie le nom canonique de l'outil dans le presse-papiers."""
        if not self._current_tool:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._current_tool.name)
            show_toast(self, tr("Nom d'outil '%1' copié.", self._current_tool.name))

    def _copy_json_signature(self) -> None:
        """Copie la signature JSON d'exemple de l'outil dans le presse-papiers."""
        text = self.edit_json_signature.toPlainText()
        if not text:
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
            show_toast(self, self.tr("Signature JSON copiée dans le presse-papiers."))

    # ── Thème Dynamique ──────────────────────────────────────────────────────

    def refresh_theme(self, profile: Any = None) -> None:
        """Adapte l'ensemble des styles aux jetons du thème actif."""
        bg_panel = profile.bg_panel if profile else DesignTokens.BG_PANEL
        bg_input = profile.bg_input if profile else DesignTokens.BG_INPUT
        border_col = profile.border_color if profile else DesignTokens.BORDER_COLOR
        accent_primary = profile.accent_primary if profile else DesignTokens.ACCENT_PRIMARY

        self.left_pane.setStyleSheet(f"""
            QFrame#mcp_catalog_left_pane {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.right_pane.setStyleSheet(f"""
            QFrame#mcp_catalog_right_pane {{
                background-color: {bg_panel};
                border: 1px solid {border_col};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        self.tool_list.setStyleSheet(f"""
            QListWidget#mcp_catalog_tool_list {{
                background-color: transparent;
                border: none;
            }}
            QListWidget#mcp_catalog_tool_list::item {{
                background-color: {bg_input};
                border: 1px solid {border_col};
                border-radius: {DesignTokens.RADIUS_SM}px;
                margin-bottom: 4px;
                padding: 2px;
            }}
            QListWidget#mcp_catalog_tool_list::item:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget#mcp_catalog_tool_list::item:selected {{
                background-color: {DesignTokens.BG_ACTIVE};
                border-color: {accent_primary};
            }}
        """)

        # Actualisation des puces
        if hasattr(self, "chip_all"):
            self.chip_all.refresh_theme(profile)
        for chip in self.domain_chips.values():
            chip.refresh_theme(profile)

        # Actualisation de l'icône de détail
        if self._current_tool and hasattr(self, "lbl_detail_icon"):
            self.lbl_detail_icon.setPixmap(load_phosphor_icon(self._current_tool.domain_icon, color=accent_primary).pixmap(24, 24))

        # Actualisation du volet droit de détail
        color_orange = getattr(profile, "color_orange", DesignTokens.COLOR_ORANGE)
        text_secondary = getattr(profile, "text_secondary", DesignTokens.TEXT_SECONDARY)
        text_primary = getattr(profile, "text_primary", DesignTokens.TEXT_PRIMARY)

        if hasattr(self, "desc_frame") and self.desc_frame is not None:
            self.desc_frame.setStyleSheet(f"""
                QFrame#mcp_catalog_desc_frame {{
                    background-color: {bg_input};
                    border: 1px solid {border_col};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 10px;
                }}
            """)

        if hasattr(self, "frame_safeguards") and self.frame_safeguards is not None:
            self.frame_safeguards.setStyleSheet(f"""
                QFrame#mcp_catalog_safeguards_frame {{
                    background-color: {bg_input};
                    border: 1px solid {color_orange};
                    border-left: 4px solid {color_orange};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 8px;
                }}
            """)

        if hasattr(self, "params_table") and self.params_table is not None:
            self.params_table.setStyleSheet(f"""
                QTableWidget#mcp_catalog_params_table {{
                    background-color: {bg_input};
                    border: 1px solid {border_col};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    gridline-color: {border_col};
                    font-size: 11.5px;
                }}
                QHeaderView::section {{
                    background-color: {bg_panel};
                    color: {text_secondary};
                    font-size: 10px;
                    font-weight: 700;
                    padding: 4px;
                    border: none;
                    border-bottom: 1px solid {border_col};
                }}
            """)

        if hasattr(self, "edit_json_signature") and self.edit_json_signature is not None:
            self.edit_json_signature.setStyleSheet(f"""
                QPlainTextEdit#mcp_catalog_json_signature {{
                    background-color: {bg_input};
                    color: {text_primary};
                    border: 1px solid {border_col};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    font-family: {DesignTokens.FONT_CODE};
                    font-size: 11.5px;
                    padding: 8px;
                }}
            """)


__all__ = [
    "MCPToolCatalogWidget",
    "MCPToolItem",
    "MCPToolListRowWidget",
    "get_all_mcp_tools",
]
