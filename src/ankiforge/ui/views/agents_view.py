"""
Vue Atelier d'Agents IA — Modernisée, Conforme au Design System et au Moteur DAG / MCP.

- Système Complet de Dossiers & Sous-dossiers Récursifs :
  * Organisation arborescente multiniveaux (`PersonaFolderModel` avec relation parent-enfant).
  * Création de dossiers racines et sous-dossiers en 1-clic.
  * Dépliage/repliage récursif avec comptage dynamique d'agents.
  * Déplacement et réassignation de dossiers et sous-dossiers.
- Différenciation claire des Personas selon leur portée :
  * ⚡ Pipeline de Forge (DAG) : Conçu pour les flux d'ingestion et de création de cartes.
  * 🤝 Consultant IA (MCP) : Conçu pour l'agent conversationnel ReAct et les Tool Calls.
  * 🌐 Universel : Utilisable indifféremment dans les pipelines et dans le consultant.
- Panneau gauche (300px) :
  * Filtrage instantané par portée (Tous, Pipelines, Consultant MCP, Universels).
  * Champ de recherche textuelle rapide (recherche dans les noms d'agents, descriptions et arborescences de dossiers).
  * Arborescence complète dossiers/sous-dossiers avec badges pills ultra-arrondis (border-radius: 9999px).
  * Actions rapides (Nouvel Agent, Nouveau Dossier/Sous-Dossier, Dupliquer, Supprimer).
- Panneau droit (Flex-1) :
  * Onglet 1 (⚙️ Identité & Moteur IA) : Nom, Description, Dossier/Sous-dossier, Portée/Usage, Format et Moteur LLM dédié.
  * Onglet 2 (✨ Instructions & Prompt Jinja2) : Éditeur de System Prompt avec palette de snippets contextuels en 1-clic, aperçu interpolé Jinja2 et compteur de tokens.
  * Onglet 3 (🧰 Permissions d'Outils MCP & Python) : Grille d'activation dynamique des outils natifs, scripts personnalisés et outils MCP.
- Modale de test unitaire rapide de l'Agent IA avec simulation en direct.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from jinja2 import BaseLoader, Environment
from PySide6.QtCore import QPoint, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaFolderModel,
    PersonaModel,
    db,
)
from ankiforge.services.ai.base import MockProvider
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.ui.components import (
    Badge,
    DangerButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 12px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


# Types d'usage disponibles pour les Personas
PERSONA_TYPE_SPECS: Dict[str, Dict[str, str]] = {
    "pipeline": {
        "label": "⚡ Pipeline de Forge (DAG)",
        "badge_text": "⚡ PIPELINE",
        "badge_color": "#6366f1",
        "desc": "Conçu pour les étapes de workflow d'ingestion et de création de cartes flashcards.",
    },
    "mcp": {
        "label": "🤝 Consultant IA (Serveur MCP)",
        "badge_text": "🤝 MCP",
        "badge_color": "#10b981",
        "desc": "Conçu pour les diagnostics conversationnels, la boucle autonome ReAct et l'appel d'outils.",
    },
    "universal": {
        "label": "🌐 Universel (Forge & MCP)",
        "badge_text": "🌐 UNIVERSEL",
        "badge_color": "#f59e0b",
        "desc": "Polyvalent : disponible aussi bien dans les étapes de pipelines que pour le Consultant.",
    },
}

# Registre des outils de base MCP du Consultant
MCP_BASE_TOOLS_SPEC: Dict[str, Dict[str, str]] = {
    "query_vector_db": {
        "label": "Recherche Vectorielle (RAG)",
        "desc": "Permet d'interroger l'index sémantique FAISS des documents importés.",
        "category": "MCP",
        "color": "#06b6d4",
    },
    "read_anki_stats": {
        "label": "Statistiques Anki & Rétention",
        "desc": "Permet de lire les métriques SRS (Sangsues, taux d'oubli, distributions de notes).",
        "category": "MCP",
        "color": "#10b981",
    },
    "generate_css": {
        "label": "Stylisation CSS d'Atelier",
        "desc": "Permet de générer et d'injecter des règles CSS directement dans les modèles Anki.",
        "category": "MCP",
        "color": "#8b5cf6",
    },
}

# Snippets Jinja2 usuels pour les Prompts
JINJA2_SNIPPETS: List[tuple[str, str, str]] = [
    ("{{ text_source }}", "Texte Source", "Contenu brut du document ou de la section sélectionnée"),
    ("{{ last_output }}", "Sortie Précédente", "Résultat de l'étape DAG immédiatement antérieure"),
    ("{{ fields }}", "Champs NoteType", "Liste des champs du modèle de note cible (ex: Front, Back)"),
    ("{{ retrieved_chunks }}", "Extraits RAG", "Fragments documentaires pertinents extraits par FAISS"),
    ("{{ item }}", "Élément Lot (Map-Reduce)", "Objet ou texte en cours de traitement en boucle parallèle"),
    ("{{ initial_prompt }}", "Consigne Initiale", "Consigne d'origine saisie par l'utilisateur"),
    ("{{ state.variables.xxx }}", "Variable DAG", "Accès à une variable arbitraire du PipelineRunState"),
]


# =====================================================================
# COMPOSANT : EN-TÊTE DE DOSSIER OU SOUS-DOSSIER
# =====================================================================


class FolderHeaderWidget(QWidget):
    """Widget représentant la ligne d'un dossier ou sous-dossier dans l'arbre."""

    def __init__(self, name: str, count: int, is_root: bool = False, is_subfolder: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            FolderHeaderWidget {
                background: transparent;
            }
            FolderHeaderWidget QLabel {
                background: transparent;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 3, 4, 3)
        layout.setSpacing(6)

        icon_lbl = QLabel()
        if is_root:
            icon_name = "ph.tray"
            icon_color = "#94a3b8"
        elif is_subfolder:
            icon_name = "ph.folder-notch"
            icon_color = "#38bdf8"
        else:
            icon_name = "ph.folder"
            icon_color = "#f59e0b"

        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=icon_color).pixmap(15, 15))
        layout.addWidget(icon_lbl)

        lbl_name = QLabel(name)
        font_weight = "bold" if not is_subfolder else "600"
        font_size = "12px" if not is_subfolder else "11px"
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: {font_weight}; font-size: {font_size};")
        layout.addWidget(lbl_name, 1)

        badge_count = Badge(f"{count}", variant="status")
        apply_pill_style(badge_count, "#64748b")
        layout.addWidget(badge_count)


# =====================================================================
# COMPOSANT : CARTE D'AGENT DANS L'ARBORESCENCE
# =====================================================================


class PersonaItemWidget(QWidget):
    """Widget personnalisé pour chaque feuille Persona de l'arbre."""

    def __init__(self, persona: PersonaModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.persona = persona
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            PersonaItemWidget {
                background: transparent;
            }
            PersonaItemWidget QLabel {
                background: transparent;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(3)

        # Ligne 1 : Icône + Nom
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        p_type = getattr(persona, "persona_type", "pipeline") or "pipeline"
        type_spec = PERSONA_TYPE_SPECS.get(p_type, PERSONA_TYPE_SPECS["pipeline"])

        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color=type_spec["badge_color"]).pixmap(13, 13))
        top_row.addWidget(icon_lbl)

        self.lbl_name = QLabel(str(persona.name))
        self.lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 11px;")
        top_row.addWidget(self.lbl_name, 1)

        layout.addLayout(top_row)

        # Ligne 2 : Badges Pills Arrondis (Portée + Format)
        badges_row = QHBoxLayout()
        badges_row.setSpacing(4)

        self.badge_type = Badge(type_spec["badge_text"], variant="status")
        apply_pill_style(self.badge_type, type_spec["badge_color"])
        badges_row.addWidget(self.badge_type)

        fmt_text = (getattr(persona, "output_format", "JSON") or "JSON").upper()
        self.badge_fmt = Badge(fmt_text, variant="neutral")
        self.badge_fmt.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 9999px;
                padding: 2px 7px;
                font-size: 9px;
                font-weight: bold;
            }}
        """)
        badges_row.addWidget(self.badge_fmt)
        badges_row.addStretch()

        layout.addLayout(badges_row)


# =====================================================================
# COMPOSANT : CARTE DE PERMISSION D'OUTIL (MCP & PYTHON)
# =====================================================================


class ToolPermissionCard(QFrame):
    """Carte interactive pour cocher/décocher une permission d'outil."""

    toggled = Signal(str, bool)

    def __init__(
        self,
        tool_key: str,
        label: str,
        description: str,
        category: str = "Natif",
        category_color: str = "#3b82f6",
        is_checked: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.tool_key = tool_key
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ToolPermissionCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
                padding: 4px;
            }}
            ToolPermissionCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            ToolPermissionCard QLabel {{
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Case à cocher
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(is_checked)
        self.checkbox.setStyleSheet(f"""
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                background: {DesignTokens.BG_MAIN};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.checkbox.toggled.connect(lambda chk: self.toggled.emit(self.tool_key, chk))
        layout.addWidget(self.checkbox)

        # Textes descriptifs
        col = QVBoxLayout()
        col.setSpacing(2)

        lbl_title = QLabel(label)
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;")
        col.addWidget(lbl_title)

        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        lbl_desc.setWordWrap(True)
        col.addWidget(lbl_desc)
        layout.addLayout(col, 1)

        # Badge de catégorie arrondi
        badge = Badge(category, variant="status")
        apply_pill_style(badge, category_color)
        layout.addWidget(badge)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        super().mousePressEvent(event)

    def isChecked(self) -> bool:
        return self.checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.checkbox.setChecked(checked)


# =====================================================================
# MODALE DE PRÉVISUALISATION JINJA2 DU PROMPT
# =====================================================================


class AgentPromptPreviewDialog(QDialog):
    """Affiche la résolution dynamique du template Jinja2 du Persona avec des variables réalistes."""

    def __init__(self, template_str: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aperçu du Prompt Interpolé (Jinja2)")
        self.resize(700, 500)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QDialog QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_header = QLabel("Ce que recevra le Modèle LLM (variables interpolées) :")
        lbl_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_header)

        # Rendu Jinja2 avec état de démonstration typé
        rendered_text = ""
        try:
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(template_str)
            mock_vars: Dict[str, Any] = {
                "text_source": "Soit A une matrice carrée n x n. A est diagonalisable s'il existe une base de vecteurs propres.",
                "generated_cards": [{"Front": "Définition diagonalisation", "Back": "Existe base de vecteurs propres"}],
                "last_output": "Cartes générées avec succès.",
                "plan_cours": "1. Définition\n2. Valeurs propres\n3. Sous-espaces propres",
            }
            mock_state: Dict[str, Any] = {
                "initial_prompt": "Créer 5 flashcards sur la diagonalisation matricielle.",
                "variables": mock_vars,
            }
            rendered_text = tpl.render(
                state=mock_state,
                text_source=mock_vars["text_source"],
                last_output=mock_vars["last_output"],
                fields=["Front", "Back"],
                retrieved_chunks=["Extrait 1 : Valeurs propres et polynôme caractéristique."],
                item="Section 1 : Définition des endomorphismes",
                initial_prompt=mock_state["initial_prompt"],
            )
        except Exception as e:
            rendered_text = f"❌ Erreur de syntaxe Jinja2 dans le template :\n{e}"

        edit_rendered = QPlainTextEdit()
        edit_rendered.setReadOnly(True)
        edit_rendered.setPlainText(rendered_text)
        edit_rendered.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: #38bdf8;
                font-family: 'JetBrains Mono', 'Fira Code', Menlo, monospace;
                font-size: 12px;
                line-height: 1.4;
                padding: 10px;
                border-radius: 6px;
            }}
        """)
        layout.addWidget(edit_rendered, 1)

        btn_close = SecondaryButton("Fermer l'aperçu")
        btn_close.setIcon(load_phosphor_icon("ph.check-circle", color=DesignTokens.TEXT_PRIMARY))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)


# =====================================================================
# MODALE DE TEST UNITAIRE D'UN AGENT
# =====================================================================


class AgentTestDialog(QDialog):
    """Dialogue pour tester l'exécution unitaire d'un Persona avec un texte source."""

    def __init__(self, persona: PersonaModel, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.persona = persona
        self.ai_manager = ai_manager
        self.setWindowTitle(f"Test d'Agent : {persona.name}")
        self.resize(680, 520)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QDialog QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        lbl_input = QLabel("Texte source d'entrée (User Prompt) :")
        lbl_input.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_input)

        self.edit_user_input = QTextEdit()
        self.edit_user_input.setPlaceholderText("Saisissez un extrait de cours pour tester la génération de cet agent...")
        self.edit_user_input.setText("La photosynthèse est le processus bioénergétique qui permet aux plantes de synthétiser de la matière organique grâce à la lumière du soleil.")
        self.edit_user_input.setMaximumHeight(90)
        self.edit_user_input.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; border-radius: 4px; padding: 6px;")
        layout.addWidget(self.edit_user_input)

        lbl_output = QLabel("Réponse du Modèle IA :")
        lbl_output.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_output)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: #38bdf8; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.output_text, 1)

        h_btn = QHBoxLayout()
        self.btn_run = PrimaryButton("Exécuter le Test")
        self.btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_run.clicked.connect(self._run_test)
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        h_btn.addWidget(self.btn_run)
        h_btn.addStretch()
        h_btn.addWidget(btn_close)
        layout.addLayout(h_btn)

    def _run_test(self) -> None:
        self.output_text.clear()
        self.output_text.append("🧪 Exécution du Persona en cours...")
        user_input = self.edit_user_input.toPlainText().strip()

        # Instanciation du provider
        provider = None
        if getattr(self.persona, "llm_config", None) and self.ai_manager and hasattr(self.ai_manager, "create_provider_from_config"):
            try:
                provider = self.ai_manager.create_provider_from_config(self.persona.llm_config)
            except Exception as e:
                logger.warning(f"Impossible de créer le provider dédié : {e}")

        if not provider:
            provider = MockProvider()

        try:
            # Interpolation du template de prompt
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(str(self.persona.system_prompt or ""))
            rendered_sys = tpl.render(
                text_source=user_input,
                fields=["Front", "Back"],
                retrieved_chunks=[],
                last_output="",
            )

            res = provider.generate(
                system_prompt=rendered_sys,
                user_prompt=user_input,
                response_format=getattr(self.persona, "output_format", "json") or "json",
            )
            self.output_text.clear()
            self.output_text.append(f"<b>Prompt Système Interpolé :</b>\n{rendered_sys}\n")
            self.output_text.append(f"<b>Réponse du Modèle :</b>\n{res.content if hasattr(res, 'content') else str(res)}")
        except Exception as e:
            self.output_text.append(f"❌ Erreur d'exécution : {e}")


# =====================================================================
# VUE PRINCIPALE : ATELIER D'AGENTS AVEC SOUS-DOSSIERS (AGENTSVIEW)
# =====================================================================


class AgentsView(QWidget):
    """
    Vue Atelier d'Agents IA — Architecture Maître-Détail avec dossiers et sous-dossiers récursifs.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_agent: Optional[PersonaModel] = None
        self._current_folder: Optional[PersonaFolderModel] = None
        self._tool_cards: Dict[str, ToolPermissionCard] = {}
        self._tool_checkboxes: Dict[str, QCheckBox] = {}  # Rétrocompatibilité tests
        self._cached_personas: List[PersonaModel] = []
        self._cached_folders: List[PersonaFolderModel] = []
        self._current_scope_filter: str = "all"  # 'all', 'pipeline', 'mcp', 'universal'

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # ── 1. Panneau Gauche : Arborescence Dossiers & Personas ───────────────
        self.list_panel = IdePanel(detachable=True)
        self.list_panel.setMinimumWidth(300)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        # Header liste avec badge pill arrondi
        h_row = QHBoxLayout()
        lbl_list_title = QLabel("DOSSIERS & PERSONAS :")
        lbl_list_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        h_row.addWidget(lbl_list_title)
        h_row.addStretch()

        self.lbl_count_badge = Badge("0 agents", variant="status")
        apply_pill_style(self.lbl_count_badge, "#8b5cf6")
        h_row.addWidget(self.lbl_count_badge)
        list_layout.addLayout(h_row)

        # Barre de recherche instantanée
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("🔍 Filtrer par nom, rôle, dossier...")
        self.edit_search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 6px 10px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.edit_search.textChanged.connect(self._apply_filters)
        list_layout.addWidget(self.edit_search)

        # Filtre Segmented par Portée (Pills)
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(4)

        self.btn_filter_all = QPushButton("Tous")
        self.btn_filter_pipe = QPushButton("⚡ Pipeline")
        self.btn_filter_mcp = QPushButton("🤝 MCP")
        self.btn_filter_univ = QPushButton("🌐 Univ.")

        self._filter_buttons = [
            (self.btn_filter_all, "all"),
            (self.btn_filter_pipe, "pipeline"),
            (self.btn_filter_mcp, "mcp"),
            (self.btn_filter_univ, "universal"),
        ]

        for btn, scope in self._filter_buttons:
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 9999px;
                    color: {DesignTokens.TEXT_MUTED};
                    font-size: 10px;
                    font-weight: bold;
                    padding: 3px 8px;
                }}
                QPushButton:hover {{
                    color: {DesignTokens.TEXT_PRIMARY};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
                QPushButton:checked {{
                    background-color: rgba(99, 102, 241, 0.2);
                    border-color: #8b5cf6;
                    color: #a5b4fc;
                }}
            """)
            btn.clicked.connect(lambda _, s=scope: self._set_scope_filter(s))
            filter_bar.addWidget(btn)

        self.btn_filter_all.setChecked(True)
        list_layout.addLayout(filter_bar)

        # Arbre des dossiers et personas (QTreeWidget)
        self.persona_tree = QTreeWidget()
        self.persona_tree.setHeaderHidden(True)
        self.persona_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.persona_tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        self.persona_tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: transparent;
                border: none;
                color: {DesignTokens.TEXT_PRIMARY};
                outline: none;
            }}
            QTreeWidget::item {{
                padding: 2px 0px;
                border-radius: 4px;
                margin-bottom: 2px;
            }}
            QTreeWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QTreeWidget::item:selected {{
                background-color: rgba(99, 102, 241, 0.14);
                border-left: 2px solid #8b5cf6;
            }}
        """)
        list_layout.addWidget(self.persona_tree, 1)

        # Barre d'actions inférieure
        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(4)

        self.btn_new = PrimaryButton("Nouvel Agent")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))

        self.btn_new_folder = SecondaryButton("Dossier")
        self.btn_new_folder.setIcon(load_phosphor_icon("ph.folder-plus", color=DesignTokens.TEXT_PRIMARY))

        self.btn_clone = SecondaryButton("Dupliquer")
        self.btn_clone.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))

        self.btn_del = DangerButton("Supprimer", ghost=True)
        self.btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        list_toolbar.addWidget(self.btn_new, 1)
        list_toolbar.addWidget(self.btn_new_folder)
        list_toolbar.addWidget(self.btn_clone)
        list_toolbar.addWidget(self.btn_del)
        list_layout.addLayout(list_toolbar)

        self.list_panel.add_tab("Arborescence d'Agents", list_content, "ph.folder-simple", closable=False)
        self.main_splitter.addWidget(self.list_panel)

        # ── 2. Panneau Droit : Éditeur Riche à Onglets ─────────────────────────
        self.editor_panel = IdePanel(detachable=True)

        # Actions d'en-tête
        self.btn_test = SecondaryButton("Tester l'Agent")
        self.btn_test.setIcon(load_phosphor_icon("ph.flask", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test.clicked.connect(self._on_test_agent)

        self.btn_save = PrimaryButton("Enregistrer les Modifications")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))

        self.editor_panel.add_header_widget(self.btn_test)
        self.editor_panel.add_header_widget(self.btn_save)
        self.editor_panel.add_header_separator()

        # Onglets de configuration
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background: {DesignTokens.BG_MAIN};
                border-radius: 6px;
                padding: 12px;
            }}
            QTabBar::tab {{
                background: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 12px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # ── ONGLET 1 : Identité & Moteur IA ──
        tab_identity = QWidget()
        layout_identity = QVBoxLayout(tab_identity)
        layout_identity.setContentsMargins(12, 12, 12, 12)
        layout_identity.setSpacing(14)

        # Nom
        lbl_name = QLabel("NOM DU PERSONA :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout_identity.addWidget(lbl_name)
        self.name_edit = StyledLineEdit()
        self.name_edit.setPlaceholderText("ex: Architecte de Cours, Linteur Wozniak, Consultant SRS...")
        layout_identity.addWidget(self.name_edit)

        # Description
        lbl_desc = QLabel("DESCRIPTION & RÔLE :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout_identity.addWidget(lbl_desc)
        self.desc_edit = StyledLineEdit()
        self.desc_edit.setPlaceholderText("ex: Découpe le cours en concepts atomiques selon la règle de formulation minimale.")
        layout_identity.addWidget(self.desc_edit)

        # Ligne : Dossier & Portée & Format
        row_props = QHBoxLayout()
        row_props.setSpacing(12)

        # Dossier / Sous-dossier de classement
        col_folder = QVBoxLayout()
        col_folder.setSpacing(4)
        lbl_folder_title = QLabel("DOSSIER D'APPARTENANCE :")
        lbl_folder_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        col_folder.addWidget(lbl_folder_title)
        self.folder_combo = StyledComboBox()
        self.folder_combo.currentIndexChanged.connect(self._on_folder_combo_changed)
        col_folder.addWidget(self.folder_combo)
        row_props.addLayout(col_folder, 1)

        # Portée / Type d'usage (Pipeline vs MCP vs Universel)
        col_scope = QVBoxLayout()
        col_scope.setSpacing(4)
        lbl_scope_title = QLabel("PORTÉE / USAGE DE L'AGENT :")
        lbl_scope_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        col_scope.addWidget(lbl_scope_title)
        self.scope_combo = StyledComboBox()
        for s_key, s_spec in PERSONA_TYPE_SPECS.items():
            self.scope_combo.addItem(s_spec["label"], userData=s_key)
        self.scope_combo.currentIndexChanged.connect(self._on_scope_changed)
        col_scope.addWidget(self.scope_combo)
        row_props.addLayout(col_scope, 1)

        # Format de sortie
        col_fmt = QVBoxLayout()
        col_fmt.setSpacing(4)
        lbl_format = QLabel("FORMAT DE SORTIE :")
        lbl_format.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        col_fmt.addWidget(lbl_format)
        self.format_combo = StyledComboBox()
        self.format_combo.addItems(["json", "cloze", "markdown", "text"])
        col_fmt.addWidget(self.format_combo)
        row_props.addLayout(col_fmt, 1)

        layout_identity.addLayout(row_props)

        # Carte d'aide contextuelle sur la Portée
        self.scope_info_card = QFrame()
        self.scope_info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid rgba(99, 102, 241, 0.3);
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        layout_scope_info = QHBoxLayout(self.scope_info_card)
        layout_scope_info.setContentsMargins(8, 8, 8, 8)
        self.lbl_scope_info = QLabel(PERSONA_TYPE_SPECS["pipeline"]["desc"])
        self.lbl_scope_info.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        self.lbl_scope_info.setWordWrap(True)
        layout_scope_info.addWidget(self.lbl_scope_info)
        layout_identity.addWidget(self.scope_info_card)

        # Moteur IA Dédié
        lbl_engine = QLabel("MOTEUR IA DÉDIÉ (OPTIONNEL) :")
        lbl_engine.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        layout_identity.addWidget(lbl_engine)
        self.engine_combo = StyledComboBox()
        layout_identity.addWidget(self.engine_combo)

        # Carte d'info moteur
        self.engine_info_card = QFrame()
        self.engine_info_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
                padding: 8px;
            }}
            QFrame QLabel {{
                background: transparent;
            }}
        """)
        layout_engine_info = QHBoxLayout(self.engine_info_card)
        layout_engine_info.setContentsMargins(8, 8, 8, 8)
        self.lbl_engine_info = QLabel("⚙️ Cet agent utilisera le modèle IA global par défaut défini dans les Paramètres.")
        self.lbl_engine_info.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        layout_engine_info.addWidget(self.lbl_engine_info)
        layout_identity.addWidget(self.engine_info_card)

        layout_identity.addStretch()
        self.tabs.addTab(tab_identity, "⚙️ Identité & Moteur IA")

        # ── ONGLET 2 : Instructions & Prompt Jinja2 ──
        tab_prompt = QWidget()
        layout_prompt = QVBoxLayout(tab_prompt)
        layout_prompt.setContentsMargins(12, 12, 12, 12)
        layout_prompt.setSpacing(10)

        # Barre d'outils de Snippets
        snippets_header = QHBoxLayout()
        lbl_prompt_title = QLabel("INSTRUCTIONS SYSTÈME (JINJA2 TEMPLATE) :")
        lbl_prompt_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        snippets_header.addWidget(lbl_prompt_title)
        snippets_header.addStretch()

        self.btn_preview_prompt = SecondaryButton("Aperçu Interpolé (Jinja2)")
        self.btn_preview_prompt.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
        self.btn_preview_prompt.clicked.connect(self._on_preview_prompt)
        snippets_header.addWidget(self.btn_preview_prompt)
        layout_prompt.addLayout(snippets_header)

        # Snippets pills bar
        snippets_bar = QHBoxLayout()
        snippets_bar.setSpacing(6)
        lbl_snip = QLabel("Insérer :")
        lbl_snip.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        snippets_bar.addWidget(lbl_snip)

        for template_code, display_name, tooltip in JINJA2_SNIPPETS:
            btn_snip = QPushButton(display_name)
            btn_snip.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_snip.setToolTip(f"{tooltip}\nInsère : {template_code}")
            btn_snip.setStyleSheet(f"""
                QPushButton {{
                    background: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_SECONDARY};
                    font-size: 11px;
                    padding: 3px 10px;
                    border-radius: 9999px;
                }}
                QPushButton:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: #a5b4fc;
                }}
            """)
            btn_snip.clicked.connect(lambda _, code=template_code: self._insert_jinja_snippet(code))
            snippets_bar.addWidget(btn_snip)
        snippets_bar.addStretch()
        layout_prompt.addLayout(snippets_bar)

        # Éditeur de Prompt
        self.prompt_edit = StyledTextEdit()
        self.prompt_edit.setPlaceholderText("Tu es un agent expert en création de flashcards Anki...\nUtilisez {{ text_source }} et les variables Jinja2.")
        self.prompt_edit.setMinimumHeight(240)
        self.prompt_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: #a5b4fc;
                font-family: 'JetBrains Mono', 'Fira Code', Menlo, monospace;
                font-size: 12px;
                line-height: 1.5;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 12px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.prompt_edit.textChanged.connect(self._update_tokens_count)
        layout_prompt.addWidget(self.prompt_edit, 1)

        # Compteur de tokens
        self.lbl_tokens = QLabel("Aa 0 caractères  |  ~0 Tokens estimés")
        self.lbl_tokens.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-family: monospace;")
        layout_prompt.addWidget(self.lbl_tokens)

        self.tabs.addTab(tab_prompt, "✨ Instructions & Prompt")

        # ── ONGLET 3 : Permissions d'Outils MCP & Python ──
        tab_tools = QWidget()
        layout_tools = QVBoxLayout(tab_tools)
        layout_tools.setContentsMargins(12, 12, 12, 12)
        layout_tools.setSpacing(10)

        # En-tête outils
        tools_header = QHBoxLayout()
        lbl_tools_title = QLabel("PERMISSIONS D'OUTILS (MCP & OUTILS PYTHON DÉTERMINISTES) :")
        lbl_tools_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        tools_header.addWidget(lbl_tools_title)
        tools_header.addStretch()

        btn_select_all = SecondaryButton("Tout Cocher")
        btn_select_all.clicked.connect(lambda: self._set_all_tools(True))
        btn_deselect_all = SecondaryButton("Tout Décocher")
        btn_deselect_all.clicked.connect(lambda: self._set_all_tools(False))
        tools_header.addWidget(btn_select_all)
        tools_header.addWidget(btn_deselect_all)
        layout_tools.addLayout(tools_header)

        # ScrollArea pour la grille d'outils
        tools_scroll = QScrollArea()
        tools_scroll.setWidgetResizable(True)
        tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        tools_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        self.tools_container = QWidget()
        self.tools_layout = QVBoxLayout(self.tools_container)
        self.tools_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_layout.setSpacing(8)

        self._build_tools_cards()

        tools_scroll.setWidget(self.tools_container)
        layout_tools.addWidget(tools_scroll, 1)

        self.tabs.addTab(tab_tools, "🧰 Permissions d'Outils")

        self.editor_panel.add_tab("Éditeur de Persona", self.tabs, "ph.sparkle", closable=False)
        self.main_splitter.addWidget(self.editor_panel)
        self.main_splitter.setSizes([300, 700])

    def _build_tools_cards(self) -> None:
        """Construit les cartes de permissions pour les outils MCP et les outils Python enregistrés."""
        while self.tools_layout.count() > 0:
            item = self.tools_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._tool_cards.clear()
        self._tool_checkboxes.clear()

        # 1. Outils MCP Consultant
        lbl_mcp = QLabel("OUTILS MCP CONSULTANT & SYSTÈME :")
        lbl_mcp.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 4px;")
        self.tools_layout.addWidget(lbl_mcp)

        for key, spec in MCP_BASE_TOOLS_SPEC.items():
            card = ToolPermissionCard(
                tool_key=key,
                label=spec["label"],
                description=spec["desc"],
                category=spec["category"],
                category_color=spec["color"],
            )
            self._tool_cards[key] = card
            self._tool_checkboxes[key] = card.checkbox
            self.tools_layout.addWidget(card)

        # 2. Outils Python Déterministes (Built-in et Custom)
        lbl_py = QLabel("OUTILS PYTHON DÉTERMINISTES (MOTEUR DAG) :")
        lbl_py.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px; margin-top: 8px;")
        self.tools_layout.addWidget(lbl_py)

        try:
            tools = ToolService.list_tools()
            for t in tools:
                cat = "Natif" if t.is_builtin else "Script Custom"
                col = "#3b82f6" if t.is_builtin else "#f97316"
                card = ToolPermissionCard(
                    tool_key=t.name,
                    label=t.display_name,
                    description=t.description or "Script Python utilitaire.",
                    category=cat,
                    category_color=col,
                )
                self._tool_cards[t.name] = card
                self._tool_checkboxes[t.name] = card.checkbox
                self.tools_layout.addWidget(card)
        except Exception as e:
            logger.warning("Erreur chargement des outils Python : %s", e)

        self.tools_layout.addStretch()

    def _set_all_tools(self, state: bool) -> None:
        for card in self._tool_cards.values():
            card.setChecked(state)

    def _connect_signals(self) -> None:
        self.persona_tree.currentItemChanged.connect(self._on_tree_item_selected)
        self.btn_new.clicked.connect(self._on_new_agent)
        self.btn_new_folder.clicked.connect(self._on_new_folder)
        self.btn_clone.clicked.connect(self._on_clone_agent)
        self.btn_del.clicked.connect(self._on_delete_selected)
        self.btn_save.clicked.connect(self._on_save_agent)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_changed)

    def refresh_data(self) -> None:
        """Recharge la liste des dossiers, des agents et des moteurs LLM depuis Peewee DB."""
        try:
            # 1. Recharger les moteurs LLM
            self.engine_combo.blockSignals(True)
            self.engine_combo.clear()
            self.engine_combo.addItem("⚙️ Hériter du réglage global de l'application", userData=None)

            llm_configs = list(LLMConfigModel.select())
            for cfg in llm_configs:
                display = cfg.display_name or f"{cfg.provider} ({cfg.model_id})"
                self.engine_combo.addItem(f"🤖 {display}", userData=cfg)
            self.engine_combo.blockSignals(False)

            # 2. Recharger les dossiers dans le combo de l'éditeur
            self._cached_folders = list(PersonaFolderModel.select().order_by(PersonaFolderModel.name.asc()))
            self._populate_folder_combo()

            # 3. Recharger les outils
            self._build_tools_cards()

            # 4. Recharger les personas
            self._cached_personas = list(PersonaModel.select().order_by(PersonaModel.name.asc()))
            self._apply_filters()

            # Sélectionner le premier persona disponible si aucun sélectionné
            if self._cached_personas and not self._current_agent:
                self._select_first_persona_in_tree()

        except Exception as e:
            logger.warning("Erreur refresh_data agents_view: %s", e)

    def _populate_folder_combo(self) -> None:
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItem("📁 Aucun dossier (Racine)", userData=None)

        # Construction récursive de l'arborescence des dossiers pour le combobox
        def _add_folders_recursive(parent_id: Optional[int], prefix: str = "") -> None:
            children = [f for f in self._cached_folders if (f.parent.id if f.parent else None) == parent_id]
            for child in children:
                icon_prefix = "📁 " if parent_id is None else "↳ 📁 "
                self.folder_combo.addItem(f"{prefix}{icon_prefix}{child.name}", userData=child.id)
                _add_folders_recursive(child.id, prefix=prefix + "   ")

        _add_folders_recursive(None)

        self.folder_combo.addItem("➕ Créer un nouveau dossier racine...", userData="__NEW_ROOT__")
        self.folder_combo.addItem("➕ Créer un sous-dossier ici...", userData="__NEW_SUB__")
        self.folder_combo.blockSignals(False)

    @Slot(int)
    def _on_folder_combo_changed(self, idx: int) -> None:
        val = self.folder_combo.currentData()
        if val in ("__NEW_ROOT__", "__NEW_SUB__"):
            parent_folder = self._current_folder if val == "__NEW_SUB__" else None
            prompt_title = f"Nouveau sous-dossier dans '{parent_folder.name}'" if parent_folder else "Nouveau Dossier Racine"
            name, ok = QInputDialog.getText(self, "Création de Dossier", f"{prompt_title} :")
            if ok and name.strip():
                try:
                    new_f = PersonaFolderModel.create(name=name.strip(), parent=parent_folder)
                    self._cached_folders = list(PersonaFolderModel.select().order_by(PersonaFolderModel.name.asc()))
                    self._populate_folder_combo()
                    idx_f = self.folder_combo.findData(new_f.id)
                    if idx_f != -1:
                        self.folder_combo.setCurrentIndex(idx_f)
                    self.refresh_data()
                    show_toast(self, f"Dossier '{name.strip()}' créé !")
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {e}")
                    self.folder_combo.setCurrentIndex(0)
            else:
                self.folder_combo.setCurrentIndex(0)

    def _set_scope_filter(self, scope: str) -> None:
        self._current_scope_filter = scope
        for btn, s in self._filter_buttons:
            btn.setChecked(s == scope)
        self._apply_filters()

    def _apply_filters(self) -> None:
        q = self.edit_search.text().strip().lower()
        scope = self._current_scope_filter

        filtered: List[PersonaModel] = []
        for ag in self._cached_personas:
            p_type = getattr(ag, "persona_type", "pipeline") or "pipeline"
            if scope != "all" and p_type != scope:
                continue
            folder_path = ag.folder.get_full_path().lower() if getattr(ag, "folder", None) else ""
            if q and (q not in str(ag.name).lower() and q not in str(ag.description or "").lower() and q not in folder_path):
                continue
            filtered.append(ag)

        self._render_tree(filtered)

    def _render_tree(self, personas: List[PersonaModel]) -> None:
        self.persona_tree.blockSignals(True)
        self.persona_tree.clear()

        self.lbl_count_badge.setText(f"{len(personas)} agent{'s' if len(personas) > 1 else ''}")

        # Grouper les personas par folder_id
        personas_by_folder: Dict[Optional[int], List[PersonaModel]] = {}
        for p in personas:
            f_id = p.folder.id if getattr(p, "folder", None) else None
            personas_by_folder.setdefault(f_id, []).append(p)

        # Ensemble des dossiers nécessaires pour afficher l'arborescence filtrée
        active_filter = self._current_scope_filter != "all" or bool(self.edit_search.text().strip())

        def _count_total_personas_in_folder_subtree(folder: PersonaFolderModel) -> int:
            cnt = len(personas_by_folder.get(folder.id, []))
            subfolders = [f for f in self._cached_folders if (f.parent.id if f.parent else None) == folder.id]
            for sf in subfolders:
                cnt += _count_total_personas_in_folder_subtree(sf)
            return cnt

        def _render_folder_recursive(parent_id: Optional[int], parent_tree_item: Optional[QTreeWidgetItem]) -> None:
            children_folders = [f for f in self._cached_folders if (f.parent.id if f.parent else None) == parent_id]
            for folder in children_folders:
                direct_personas = personas_by_folder.get(folder.id, [])
                total_cnt = _count_total_personas_in_folder_subtree(folder)

                if active_filter and total_cnt == 0:
                    continue

                if parent_tree_item is None:
                    folder_item = QTreeWidgetItem(self.persona_tree)
                else:
                    folder_item = QTreeWidgetItem(parent_tree_item)

                folder_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", folder))
                is_sub = folder.parent is not None
                folder_widget = FolderHeaderWidget(folder.name, total_cnt, is_root=False, is_subfolder=is_sub)
                self.persona_tree.setItemWidget(folder_item, 0, folder_widget)
                folder_item.setExpanded(True)

                # 1. Rendu des sous-dossiers récursifs
                _render_folder_recursive(folder.id, folder_item)

                # 2. Rendu des personas directs dans ce dossier
                for p in direct_personas:
                    child_item = QTreeWidgetItem(folder_item)
                    child_item.setData(0, Qt.ItemDataRole.UserRole, ("persona", p))
                    p_widget = PersonaItemWidget(p)
                    self.persona_tree.setItemWidget(child_item, 0, p_widget)

        # 1. Rendu des dossiers racines
        _render_folder_recursive(None, None)

        # 2. Rendu des personas "Sans dossier" (Racine)
        unfiled_personas = personas_by_folder.get(None, [])
        if unfiled_personas:
            root_item = QTreeWidgetItem(self.persona_tree)
            root_item.setData(0, Qt.ItemDataRole.UserRole, ("folder", None))
            root_widget = FolderHeaderWidget("Sans dossier", len(unfiled_personas), is_root=True)
            self.persona_tree.setItemWidget(root_item, 0, root_widget)
            root_item.setExpanded(True)

            for p in unfiled_personas:
                child_item = QTreeWidgetItem(root_item)
                child_item.setData(0, Qt.ItemDataRole.UserRole, ("persona", p))
                p_widget = PersonaItemWidget(p)
                self.persona_tree.setItemWidget(child_item, 0, p_widget)

        self.persona_tree.blockSignals(False)

    def _select_first_persona_in_tree(self) -> None:
        def _find_first_persona(item: QTreeWidgetItem) -> Optional[QTreeWidgetItem]:
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "persona":
                return item
            for i in range(item.childCount()):
                res = _find_first_persona(item.child(i))
                if res:
                    return res
            return None

        for i in range(self.persona_tree.topLevelItemCount()):
            top_item = self.persona_tree.topLevelItem(i)
            found = _find_first_persona(top_item)
            if found:
                self.persona_tree.setCurrentItem(found)
                return

    def is_dirty(self) -> bool:
        return False

    def _insert_jinja_snippet(self, snippet: str) -> None:
        """Insère un snippet Jinja2 à la position courante du curseur."""
        cursor = self.prompt_edit.textCursor()
        cursor.insertText(snippet)
        self.prompt_edit.setTextCursor(cursor)
        self.prompt_edit.setFocus()

    def _update_tokens_count(self) -> None:
        text = self.prompt_edit.toPlainText()
        chars = len(text)
        tokens = int(chars / 4) if chars > 0 else 0
        self.lbl_tokens.setText(f"Aa {chars} caractères  |  ~{tokens} Tokens estimés")

    @Slot()
    def _on_scope_changed(self) -> None:
        scope_key = self.scope_combo.currentData() or "pipeline"
        spec = PERSONA_TYPE_SPECS.get(scope_key, PERSONA_TYPE_SPECS["pipeline"])
        self.lbl_scope_info.setText(spec["desc"])

    @Slot()
    def _on_engine_changed(self) -> None:
        cfg = self.engine_combo.currentData()
        if cfg:
            self.lbl_engine_info.setText(f"🤖 Moteur dédié : {cfg.provider.upper()} ({cfg.model_id}) avec configuration dédiée.")
        else:
            self.lbl_engine_info.setText("⚙️ Cet agent utilisera le modèle IA global par défaut défini dans les Paramètres.")

    @Slot()
    def _on_preview_prompt(self) -> None:
        prompt_text = self.prompt_edit.toPlainText()
        dlg = AgentPromptPreviewDialog(prompt_text, parent=self)
        dlg.exec()

    @Slot()
    def _on_test_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à tester.", is_error=True)
            return
        dlg = AgentTestDialog(self._current_agent, ai_manager=self.ai_manager, parent=self)
        dlg.exec()

    @Slot()
    def _on_tree_item_selected(self, current: Optional[QTreeWidgetItem], previous: Optional[QTreeWidgetItem]) -> None:
        if not current:
            return

        data = current.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, obj = data
        if item_type == "folder":
            self._current_folder = obj
            return

        if item_type == "persona" and isinstance(obj, PersonaModel):
            self._current_agent = obj
            self._load_persona_into_editor(obj)

    def _load_persona_into_editor(self, ag: PersonaModel) -> None:
        self.name_edit.setText(str(ag.name) if ag.name else "")
        self.desc_edit.setText(str(ag.description) if ag.description else "")
        self.prompt_edit.setPlainText(str(ag.system_prompt) if ag.system_prompt else "")
        self._update_tokens_count()

        # Dossier
        self.folder_combo.blockSignals(True)
        f_id = ag.folder.id if getattr(ag, "folder", None) else None
        idx_f = self.folder_combo.findData(f_id)
        if idx_f != -1:
            self.folder_combo.setCurrentIndex(idx_f)
        else:
            self.folder_combo.setCurrentIndex(0)
        self.folder_combo.blockSignals(False)

        # Portée (pipeline, mcp, universal)
        p_type = getattr(ag, "persona_type", "pipeline") or "pipeline"
        idx_scope = self.scope_combo.findData(p_type)
        if idx_scope != -1:
            self.scope_combo.setCurrentIndex(idx_scope)
        else:
            self.scope_combo.setCurrentIndex(0)
        self._on_scope_changed()

        # Format de sortie
        fmt = getattr(ag, "output_format", "json").lower()
        idx = self.format_combo.findText(fmt, Qt.MatchFlag.MatchFixedString)
        if idx != -1:
            self.format_combo.setCurrentIndex(idx)
        else:
            self.format_combo.setCurrentText("json")

        # Moteur IA dédié
        self.engine_combo.blockSignals(True)
        if getattr(ag, "llm_config", None):
            cfg_id = ag.llm_config.id
            idx_e = -1
            for i in range(self.engine_combo.count()):
                cfg_item = self.engine_combo.itemData(i)
                if cfg_item and getattr(cfg_item, "id", None) == cfg_id:
                    idx_e = i
                    break
            self.engine_combo.setCurrentIndex(idx_e if idx_e != -1 else 0)
        else:
            self.engine_combo.setCurrentIndex(0)
        self.engine_combo.blockSignals(False)
        self._on_engine_changed()

        # Outils autorisés (allowed_tools)
        allowed_list = []
        try:
            raw_tools = getattr(ag, "allowed_tools", "[]") or "[]"
            allowed_list = json.loads(raw_tools)
        except Exception:
            allowed_list = []

        for tool_key, card in self._tool_cards.items():
            card.setChecked(tool_key in allowed_list)

    @Slot(QPoint)
    def _on_tree_context_menu(self, pos: QPoint) -> None:
        item = self.persona_tree.itemAt(pos)
        if not item:
            return

        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, obj = data
        menu = QMenu(self)

        if item_type == "folder" and obj is not None:
            action_subfolder = menu.addAction(load_phosphor_icon("ph.folder-plus"), "Nouveau sous-dossier")
            action_rename = menu.addAction(load_phosphor_icon("ph.pencil-simple"), "Renommer le dossier")
            action_delete = menu.addAction(load_phosphor_icon("ph.trash"), "Supprimer le dossier")

            action = menu.exec(self.persona_tree.viewport().mapToGlobal(pos))
            if action == action_subfolder:
                sub_name, ok = QInputDialog.getText(self, "Nouveau sous-dossier", f"Nom du sous-dossier dans '{obj.name}' :")
                if ok and sub_name.strip():
                    PersonaFolderModel.create(name=sub_name.strip(), parent=obj)
                    self.refresh_data()
            elif action == action_rename:
                new_name, ok = QInputDialog.getText(self, "Renommer le dossier", "Nouveau nom :", text=obj.name)
                if ok and new_name.strip():
                    obj.name = new_name.strip()
                    obj.save()
                    self.refresh_data()
            elif action == action_delete:
                confirm = QMessageBox.question(
                    self,
                    "Supprimer le dossier",
                    f"Supprimer le dossier '{obj.name}' et ses sous-dossiers ? (Les agents seront déplacés vers 'Sans dossier')",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                )
                if confirm == QMessageBox.StandardButton.Yes:
                    self._delete_folder_recursive(obj)
                    self.refresh_data()

        elif item_type == "persona":
            action_clone = menu.addAction(load_phosphor_icon("ph.copy"), "Dupliquer l'agent")
            action_del = menu.addAction(load_phosphor_icon("ph.trash"), "Supprimer l'agent")

            action = menu.exec(self.persona_tree.viewport().mapToGlobal(pos))
            if action == action_clone:
                self._current_agent = obj
                self._on_clone_agent()
            elif action == action_del:
                self._current_agent = obj
                self._on_delete_selected()

    def _delete_folder_recursive(self, folder: PersonaFolderModel) -> None:
        """Supprime récursivement un dossier et ses sous-dossiers en libérant les agents."""
        # 1. Libérer les personas directement contenus
        PersonaModel.update(folder=None).where(PersonaModel.folder == folder).execute()

        # 2. Traiter récursivement les sous-dossiers
        subfolders = list(PersonaFolderModel.select().where(PersonaFolderModel.parent == folder))
        for sf in subfolders:
            self._delete_folder_recursive(sf)

        folder.delete_instance()

    @Slot()
    def _on_new_folder(self) -> None:
        parent_folder = self._current_folder
        prompt_title = f"Nouveau sous-dossier dans '{parent_folder.name}'" if parent_folder else "Nouveau Dossier Racine"
        name, ok = QInputDialog.getText(self, "Nouveau Dossier", f"{prompt_title} :")
        if ok and name.strip():
            try:
                PersonaFolderModel.create(name=name.strip(), parent=parent_folder)
                self.refresh_data()
                show_toast(self, f"Dossier '{name.strip()}' créé !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le dossier : {e}")

    @Slot()
    def _on_new_agent(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouvel Agent IA", "Nom de l'agent :")
        if ok and name.strip():
            try:
                ag_name = name.strip()
                default_prompt = "Tu es un agent IA expert en création et optimisation de flashcards Anki selon la règle de formulation minimale."
                folder_id = self._current_folder.id if self._current_folder else None

                new_p = PersonaModel.create(
                    name=ag_name,
                    description="Nouvel agent IA configuré par l'utilisateur.",
                    system_prompt=default_prompt,
                    output_format="json",
                    persona_type=self._current_scope_filter if self._current_scope_filter in ("pipeline", "mcp", "universal") else "pipeline",
                    folder=folder_id,
                    allowed_tools="[]",
                )
                self.refresh_data()
                self._current_agent = new_p
                self._load_persona_into_editor(new_p)
                show_toast(self, f"Agent '{ag_name}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer l'agent : {str(e)}")

    @Slot()
    def _on_clone_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à dupliquer.", is_error=True)
            return

        clone_name = f"{self._current_agent.name} (Copie)"
        try:
            cloned = PersonaModel.create(
                name=clone_name,
                description=self._current_agent.description,
                system_prompt=self._current_agent.system_prompt,
                output_format=self._current_agent.output_format,
                persona_type=getattr(self._current_agent, "persona_type", "pipeline"),
                folder=self._current_agent.folder,
                allowed_tools=self._current_agent.allowed_tools,
                llm_config=self._current_agent.llm_config,
            )
            self.refresh_data()
            self._current_agent = cloned
            self._load_persona_into_editor(cloned)
            show_toast(self, f"Agent dupliqué sous le nom '{clone_name}' !")
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible de dupliquer l'agent : {str(e)}")

    @Slot()
    def _on_delete_selected(self) -> None:
        current_item = self.persona_tree.currentItem()
        if not current_item:
            show_toast(self, "Rien n'est sélectionné.", is_error=True)
            return

        data = current_item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return

        item_type, obj = data
        if item_type == "folder" and obj is not None:
            confirm = QMessageBox.question(
                self,
                "Supprimer le dossier",
                f"Supprimer le dossier '{obj.name}' et ses sous-dossiers ? (Les agents seront déplacés vers 'Sans dossier')",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self._delete_folder_recursive(obj)
                self._current_folder = None
                self.refresh_data()
                show_toast(self, "Dossier supprimé.")

        elif item_type == "persona" and isinstance(obj, PersonaModel):
            confirm = QMessageBox.question(
                self,
                "Supprimer l'agent",
                f"Voulez-vous vraiment supprimer l'agent '{obj.name}' ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                try:
                    obj.delete_instance()
                    self._current_agent = None
                    self.refresh_data()
                    show_toast(self, "Agent supprimé de la base de données.")
                except Exception as e:
                    QMessageBox.critical(self, "Erreur", f"Impossible de supprimer l'agent : {str(e)}")

    @Slot()
    def _on_save_agent(self) -> None:
        if not self._current_agent:
            show_toast(self, "Aucun agent sélectionné à sauvegarder.", is_error=True)
            return

        try:
            name = self.name_edit.text().strip()
            if not name:
                show_toast(self, "Le nom de l'agent ne peut pas être vide.", is_error=True)
                return

            # Outils cochés
            selected_tools = [key for key, card in self._tool_cards.items() if card.isChecked()]
            selected_engine: Optional[LLMConfigModel] = self.engine_combo.currentData()
            selected_scope: str = self.scope_combo.currentData() or "pipeline"
            selected_folder_id: Optional[int] = self.folder_combo.currentData()
            if selected_folder_id in ("__NEW_ROOT__", "__NEW_SUB__"):
                selected_folder_id = None

            with db.atomic():
                self._current_agent.name = str(name)
                self._current_agent.description = str(self.desc_edit.text().strip())
                self._current_agent.system_prompt = str(self.prompt_edit.toPlainText())
                self._current_agent.output_format = str(self.format_combo.currentText().lower())
                self._current_agent.persona_type = str(selected_scope)
                self._current_agent.folder_id = selected_folder_id
                self._current_agent.allowed_tools = str(json.dumps(selected_tools))
                self._current_agent.llm_config_id = selected_engine.id if selected_engine else None
                self._current_agent.save()

            show_toast(self, f"Agent '{name}' enregistré avec succès !")
            self.refresh_data()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec de l'enregistrement de l'agent : {str(e)}")


AgentsTab = AgentsView
