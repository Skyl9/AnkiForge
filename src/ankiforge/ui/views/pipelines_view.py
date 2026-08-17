"""Vue Pipelines (Éditeur de Chaînes DAG et d'Actions Système) — Conforme au Design System JetBrains et au Moteur DAG.

- Architecture Maître-Détail JetBrains via QSplitter (Liste/Flux à gauche, Inspecteur de configuration à droite).
- Supporte les Agents IA (Personas) et les Actions Système (RAG, Pause Copilote, Map-Reduce, Outil Python).
- Configuration visuelle des transitions et branchements conditionnels (on_success_step, on_failure_step, failure_behavior).
- Surcharge ponctuelle du prompt Jinja2 avec palette de chips d'insertion et prévisualisation en direct.
- Surcharge du modèle LLM avec tarification et contexte dynamique.
- Linter et diagnostic visuel en direct du DAG (détection d'incohérences de variables et de cycles).
- Bannière de flux interactive (clic sur un nœud pour naviguer directement vers l'étape).
- En-tête épuré avec menu d'actions secondaires groupées (Nouveau, Dupliquer, Modèles, Export/Import, Supprimer).
- Bibliothèque de modèles de pipelines prédéfinis.
- Persistance atomique dans la base de données Peewee (PipelineModel & PipelineStepModel).
- 100% Icônes Phosphor natives.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from jinja2 import BaseLoader, Environment
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QCursor, QFont
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    LLMConfigModel,
    PersonaModel,
    PipelineModel,
    PipelineStepModel,
    db,
)
from ankiforge.services.ai.base import MockProvider
from ankiforge.services.ai.orchestrator import PipelineOrchestrator
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.ui.components import (
    Badge,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
)
from ankiforge.ui.dialogs.tool_editor_dialog import ToolEditorDialog
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

# Métadonnées des types d'étapes DAG
STEP_TYPES_META: Dict[str, Dict[str, Any]] = {
    "LLM_PROMPT": {
        "label": "Agent IA (LLM)",
        "badge": "LLM",
        "badge_variant": "status",
        "badge_color": "#8b5cf6",
        "icon": "ph.sparkle",
        "default_title": "Exécution d'un Agent IA",
        "requires_persona": True,
        "default_input": "text_source",
        "default_output": "generated_cards",
    },
    "HUMAN_VALIDATION": {
        "label": "Pause Copilote (Validation)",
        "badge": "PAUSE",
        "badge_variant": "warning",
        "badge_color": "#f59e0b",
        "icon": "ph.pause-circle",
        "default_title": "Pause Copilote (Validation Humaine)",
        "requires_persona": False,
        "default_input": "plan_cours",
        "default_output": "plan_valide",
    },
    "RAG_RETRIEVAL": {
        "label": "Recherche RAG Vectorielle",
        "badge": "RAG",
        "badge_variant": "info",
        "badge_color": "#06b6d4",
        "icon": "ph.database",
        "default_title": "Recherche Sémantique Documentaire",
        "requires_persona": False,
        "default_input": "initial_prompt",
        "default_output": "text_source",
    },
    "MAP_REDUCE": {
        "label": "Génération Parallèle (par lots)",
        "badge": "PARALLÈLE",
        "badge_variant": "success",
        "badge_color": "#10b981",
        "icon": "ph.stack",
        "default_title": "Génération Parallèle par Lots",
        "requires_persona": True,
        "default_input": "text_source",
        "default_output": "generated_cards",
    },
    "PYTHON_TOOL": {
        "label": "Outil Python Déterministe",
        "badge": "OUTIL",
        "badge_variant": "neutral",
        "badge_color": "#f97316",
        "icon": "ph.code",
        "default_title": "Exécution d'un Script / Outil",
        "requires_persona": False,
        "default_input": "generated_cards",
        "default_output": "generated_cards",
    },
}

# Modèles de pipelines prédéfinis
PRESET_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "Pipeline Standard Cours",
        "description": "Workflow équilibré : Extraction RAG ➔ Architecte IA ➔ Linter Wozniak.",
        "steps": [
            {"type": "RAG_RETRIEVAL", "title": "Recherche Contexte", "config": {"top_k": 4, "input_variable": "initial_prompt", "output_variable": "text_source"}},
            {"type": "LLM_PROMPT", "title": "Architecte de Flashcards", "config": {"input_variable": "text_source", "output_variable": "generated_cards", "output_format": "json"}},
            {"type": "PYTHON_TOOL", "title": "Nettoyage HTML/LaTeX", "config": {"tool_name": "clean_html_latex", "input_variable": "generated_cards", "output_variable": "generated_cards"}},
            {"type": "LLM_PROMPT", "title": "Linter Wozniak (Audit)", "config": {"input_variable": "generated_cards", "output_variable": "generated_cards", "output_format": "json"}},
        ],
    },
    {
        "name": "Pipeline Copilote avec Validation Humaine",
        "description": "Recherche RAG ➔ Plan de Cours ➔ 🤝 Pause Humaine ➔ Forge Finale ➔ Déduplication.",
        "steps": [
            {"type": "RAG_RETRIEVAL", "title": "Recherche Documentaire", "config": {"top_k": 5, "input_variable": "initial_prompt", "output_variable": "text_source"}},
            {"type": "LLM_PROMPT", "title": "Générateur de Plan", "config": {"input_variable": "text_source", "output_variable": "plan_cours"}},
            {"type": "HUMAN_VALIDATION", "title": "Validation du Plan", "config": {"human_title": "Validez le plan avant génération"}},
            {"type": "LLM_PROMPT", "title": "Forge des Cartes Anki", "config": {"input_variable": "plan_cours", "output_variable": "generated_cards", "output_format": "json"}},
            {
                "type": "PYTHON_TOOL",
                "title": "Déduplication Levenshtein",
                "config": {"tool_name": "deduplicate_cards_levenshtein", "input_variable": "generated_cards", "output_variable": "generated_cards"},
            },
        ],
    },
    {
        "name": "Pipeline Haute Précision (Map-Reduce & RAG)",
        "description": "Découpage par lots parallèles pour les longs documents et cours denses.",
        "steps": [
            {"type": "RAG_RETRIEVAL", "title": "Vectorisation & Contexte", "config": {"top_k": 6, "input_variable": "initial_prompt", "output_variable": "text_source"}},
            {"type": "MAP_REDUCE", "title": "Forge Parallèle par Lots", "config": {"batch_size": 3, "split_mode": "page", "input_variable": "text_source", "output_variable": "generated_cards"}},
            {"type": "PYTHON_TOOL", "title": "Validation Schéma JSON", "config": {"tool_name": "validate_json_schema", "input_variable": "generated_cards", "output_variable": "generated_cards"}},
            {"type": "LLM_PROMPT", "title": "Synthèse et Audit", "config": {"input_variable": "generated_cards", "output_variable": "generated_cards", "output_format": "json"}},
        ],
    },
]


def audit_pipeline_dag(steps: List[Dict[str, Any]]) -> List[str]:
    """Analyse statique et linter du graphe DAG pour détecter les incohérences ou risques de cycles."""
    issues: List[str] = []
    if not steps:
        return ["Workflow vide : ajoutez au moins une étape pour démarrer."]

    produced_vars = {"initial_prompt", "text_source", "raw_document", "media_url", "generated_cards"}

    for idx, s in enumerate(steps, start=1):
        stype = s.get("type", "LLM_PROMPT")
        cfg = s.get("config", {})

        # 1. Vérification des Personas pour LLM
        if stype in ("LLM_PROMPT", "MAP_REDUCE") and not s.get("persona") and not cfg.get("prompt_override"):
            issues.append(f"Étape {idx} : Aucun agent IA ni prompt personnalisé assigné.")

        # 2. Vérification des variables d'entrée consommées
        in_var = cfg.get("input_variable")
        if in_var and in_var not in produced_vars and not in_var.startswith("state."):
            issues.append(f"Étape {idx} : Variable d'entrée '{in_var}' requise mais pas encore produite en amont.")

        # 3. Enregistrement de la variable produite
        out_var = cfg.get("output_variable") or ("generated_cards" if stype == "LLM_PROMPT" else f"output_{idx}")
        produced_vars.add(out_var)

        # 4. Vérification des cycles de saut
        succ_order = s.get("on_success_order")
        if succ_order and succ_order <= idx:
            issues.append(f"Étape {idx} : Saut conditionnel vers une étape antérieure ({succ_order}) pouvant créer une boucle infinie.")

    return issues


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15);
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 11px;
            padding: 2px 10px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


# =====================================================================
# BLOC 2 : BANNIÈRE VISUELLE DE FLUX DAG INTERACTIVE & LINTER
# =====================================================================


class StatusPillBadge(QFrame):
    """Badge capsule arrondi avec icône Phosphor native et texte (ex: DAG Valide, Alerte)."""

    clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 3, 10, 3)
        layout.setSpacing(6)

        self.lbl_icon = QLabel()
        self.lbl_text = QLabel("DAG Valide")
        self.lbl_text.setStyleSheet("font-size: 11px; font-weight: bold;")

        layout.addWidget(self.lbl_icon)
        layout.addWidget(self.lbl_text)

        self.set_status(is_valid=True, message="DAG Valide", tooltip="Le graphe DAG est cohérent et valide.")

    def set_status(self, is_valid: bool, message: str, tooltip: str = "") -> None:
        color = DesignTokens.COLOR_GREEN if is_valid else "#f59e0b"
        bg_alpha = "rgba(16, 185, 129, 0.15)" if is_valid else "rgba(245, 158, 11, 0.15)"
        border_alpha = "rgba(16, 185, 129, 0.35)" if is_valid else "rgba(245, 158, 11, 0.35)"
        icon_name = "ph.check-circle" if is_valid else "ph.warning-circle"

        self.lbl_icon.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(14, 14))
        self.lbl_text.setText(message)
        self.lbl_text.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: bold;")
        self.setStyleSheet(f"""
            StatusPillBadge {{
                background-color: {bg_alpha};
                border: 1px solid {border_alpha};
                border-radius: 12px;
            }}
            StatusPillBadge:hover {{
                border-color: {color};
            }}
            StatusPillBadge QLabel {{
                background: transparent;
            }}
        """)
        self.setToolTip(tooltip)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class DagFlowOverviewWidget(QFrame):
    """Bannière visuelle représentant le flux interactif du graphe DAG avec diagnostic en direct."""

    step_selected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DagFlowOverview")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QFrame#DagFlowOverview {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
            }}
            QFrame#DagFlowOverview QLabel {{
                background: transparent;
            }}
        """)
        self.layout_main = QHBoxLayout(self)
        self.layout_main.setContentsMargins(12, 6, 12, 6)
        self.layout_main.setSpacing(8)

        # Conteneur des étapes horizontales
        self.nodes_layout = QHBoxLayout()
        self.nodes_layout.setSpacing(6)
        self.nodes_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.layout_main.addLayout(self.nodes_layout, 1)

        # Badge d'état de santé du DAG avec icône Phosphor native
        self.health_badge = StatusPillBadge()
        self.layout_main.addWidget(self.health_badge)

    def render_flow(self, steps: List[Dict[str, Any]], active_index: int = 0) -> None:
        """Re-dessine les badges interactifs du flux d'étapes et évalue la santé du graphe."""
        while self.nodes_layout.count():
            item = self.nodes_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        if not steps:
            lbl_empty = QLabel("Workflow vide. Ajoutez des étapes ci-dessous.")
            lbl_empty.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic;")
            self.nodes_layout.addWidget(lbl_empty)
            self.health_badge.set_status(is_valid=False, message="Workflow vide", tooltip="Ajoutez au moins une étape pour valider le pipeline.")
            return

        # 1. Diagnostic Linter DAG
        issues = audit_pipeline_dag(steps)
        if issues:
            self.health_badge.set_status(is_valid=False, message=f"{len(issues)} Alerte(s)", tooltip="\n".join(issues))
        else:
            self.health_badge.set_status(is_valid=True, message="DAG Valide", tooltip="Le graphe DAG est cohérent, sans cycle et toutes les variables sont résolues.")

        # 2. Point de départ
        lbl_start = QLabel()
        lbl_start.setPixmap(load_phosphor_icon("ph.play-circle", color=DesignTokens.TEXT_MUTED).pixmap(14, 14))
        lbl_start.setToolTip("Point d'entrée du pipeline")
        self.nodes_layout.addWidget(lbl_start)

        for idx, step_data in enumerate(steps, start=1):
            # Flèche de liaison
            arrow = QLabel("➔")
            arrow.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
            self.nodes_layout.addWidget(arrow)

            step_type = step_data.get("type", "LLM_PROMPT")
            meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])
            persona = step_data.get("persona")
            title = step_data.get("custom_title") or (persona.name if persona else meta["badge"])

            is_active = (idx - 1) == active_index

            btn_node = QPushButton(f"{idx}. {title}")
            btn_node.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_node.setIcon(load_phosphor_icon(meta["icon"], color=meta["badge_color"]))
            border_color = meta["badge_color"] if is_active else DesignTokens.BORDER_COLOR
            bg_color = "rgba(99, 102, 241, 0.15)" if is_active else DesignTokens.BG_INPUT

            btn_node.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    border: 1px solid {border_color};
                    border-radius: 12px;
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-size: 11px;
                    font-weight: {"bold" if is_active else "normal"};
                    padding: 3px 10px;
                }}
                QPushButton:hover {{
                    border-color: {meta["badge_color"]};
                    background-color: {DesignTokens.BG_HOVER};
                }}
            """)
            btn_node.clicked.connect(lambda _, step_idx=idx - 1: self.step_selected.emit(step_idx))
            self.nodes_layout.addWidget(btn_node)

            # Indicateur de saut conditionnel
            succ_order = step_data.get("on_success_order")
            if succ_order:
                lbl_jump = QLabel(f"↳ {succ_order}")
                lbl_jump.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-size: 10px; font-weight: bold;")
                lbl_jump.setToolTip(f"Saute directement vers l'étape {succ_order} en cas de succès")
                self.nodes_layout.addWidget(lbl_jump)

        # Point d'arrivée
        arrow_end = QLabel("➔")
        arrow_end.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        self.nodes_layout.addWidget(arrow_end)

        lbl_end = QLabel()
        lbl_end.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(14, 14))
        lbl_end.setToolTip("Sortie finale : cartes forgées et prêtes")
        self.nodes_layout.addWidget(lbl_end)


# =====================================================================
# BLOC 3 : CARTE D'ÉTAPE DANS LA LISTE MAÎTRE (StepItemWidget)
# =====================================================================


class StepItemWidget(QFrame):
    """Ligne représentant une étape dans la liste de gauche (sélectionnable, enrichie et ergonomique)."""

    clicked = Signal(int)

    def __init__(
        self,
        order: int,
        step_data: Dict[str, Any],
        is_selected: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.order = order
        self.step_data = step_data
        self.is_selected = is_selected

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(8)

        # 1. Poignée
        handle_lbl = QLabel()
        handle_lbl.setPixmap(load_phosphor_icon("ph.dots-six-vertical", color=DesignTokens.TEXT_MUTED).pixmap(16, 16))
        layout.addWidget(handle_lbl)

        # 2. Icône du type
        step_type = step_data.get("type", "LLM_PROMPT")
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(meta["icon"], color=meta["badge_color"]).pixmap(18, 18))
        layout.addWidget(icon_lbl)

        # 3. Titre et sous-titre des variables de flux
        col_text = QVBoxLayout()
        col_text.setSpacing(2)

        persona = step_data.get("persona")
        title = step_data.get("custom_title") or (persona.name if persona else meta["default_title"])
        self.title_lbl = QLabel(f"<b>{order}.</b> {title}")
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px;")
        col_text.addWidget(self.title_lbl)

        # Variables de flux
        cfg = step_data.get("config", {})
        var_in = cfg.get("input_variable", meta.get("default_input", "text_source"))
        var_out = cfg.get("output_variable", meta.get("default_output", "generated_cards"))
        lbl_vars = QLabel(f"📥 {var_in} ➔ 📤 {var_out}")
        lbl_vars.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-family: monospace;")
        col_text.addWidget(lbl_vars)

        layout.addLayout(col_text, 1)

        # 4. Badge de rôle en capsule pill arrondie
        badge = Badge(meta["badge"], variant="status")
        apply_pill_style(badge, meta["badge_color"])
        layout.addWidget(badge)

        # 5. Boutons Monter / Descendre / Supprimer (Phosphor Icons)
        self.btn_up = IconButton("ph.arrow-up", tooltip="Monter d'un rang", size=16)
        self.btn_down = IconButton("ph.arrow-down", tooltip="Descendre d'un rang", size=16)
        self.btn_delete = IconButton("ph.trash", tooltip="Supprimer cette étape", size=16)

        layout.addWidget(self.btn_up)
        layout.addWidget(self.btn_down)
        layout.addWidget(self.btn_delete)

    def _apply_style(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bg = DesignTokens.BG_HOVER if self.is_selected else DesignTokens.BG_PANEL
        border = DesignTokens.ACCENT_PRIMARY if self.is_selected else DesignTokens.BORDER_COLOR
        self.setStyleSheet(f"""
            StepItemWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {DesignTokens.RADIUS_SM}px;
            }}
            StepItemWidget:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            StepItemWidget QLabel {{
                background: transparent;
            }}
        """)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.order - 1)
        super().mousePressEvent(event)


# =====================================================================
# BLOC D'INSERTION CONTEXTUELLE ET DE SÉLECTION D'ACTIONS/AGENTS
# =====================================================================


class InlineInsertButton(QWidget):
    """Bouton d'insertion contextuelle discret et élégant entre deux étapes du workflow."""

    clicked = Signal(int)

    def __init__(self, insert_index: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.insert_index = insert_index
        self.setFixedHeight(22)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        line_left = QFrame()
        line_left.setFrameShape(QFrame.Shape.HLine)
        line_left.setStyleSheet(f"border: none; border-top: 1px dashed {DesignTokens.BORDER_COLOR};")
        layout.addWidget(line_left, 1)

        self.btn = QPushButton("+")
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setToolTip(f"Insérer une étape à la position {insert_index + 1}")
        self.btn.setFixedSize(20, 20)
        self.btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 10px;
                color: {DesignTokens.TEXT_MUTED};
                font-size: 12px;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        self.btn.clicked.connect(lambda: self.clicked.emit(self.insert_index))
        layout.addWidget(self.btn)

        line_right = QFrame()
        line_right.setFrameShape(QFrame.Shape.HLine)
        line_right.setStyleSheet(f"border: none; border-top: 1px dashed {DesignTokens.BORDER_COLOR};")
        layout.addWidget(line_right, 1)


class StepPickerCard(QFrame):
    """Carte cliquable pour un élément dans le sélecteur d'étape."""

    clicked = Signal(dict)

    def __init__(
        self,
        payload: Dict[str, Any],
        icon_name: str,
        title: str,
        subtitle: str,
        badge_text: str,
        badge_color: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.payload = payload
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            StepPickerCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
            StepPickerCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
                background-color: {DesignTokens.BG_HOVER};
            }}
            StepPickerCard QLabel {{
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Icône
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=badge_color).pixmap(20, 20))
        layout.addWidget(icon_lbl)

        # Texte principal et descriptif
        col = QVBoxLayout()
        col.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; font-weight: bold;")
        col.addWidget(lbl_t)

        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        lbl_sub.setWordWrap(True)
        col.addWidget(lbl_sub)
        layout.addLayout(col, 1)

        # Badge de rôle
        badge = Badge(badge_text, variant="status")
        apply_pill_style(badge, badge_color)
        layout.addWidget(badge)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.payload)
        super().mousePressEvent(event)


class StepPickerDialog(QDialog):
    """Catalogue & Palette de sélection en 2 colonnes (Prompts/Agents et Actions Système)."""

    def __init__(self, personas: List[PersonaModel], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.personas = personas
        self.selected_step_data: Optional[Dict[str, Any]] = None
        self.setWindowTitle("Ajouter une Étape au Workflow")
        self.resize(780, 520)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
        """)

        layout_main = QVBoxLayout(self)
        layout_main.setContentsMargins(18, 18, 18, 18)
        layout_main.setSpacing(14)

        # Champ de recherche instantanée
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("Rechercher un agent, un prompt ou une action système...")
        self.edit_search.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-size: 12px;
                padding: 8px 12px;
            }}
            QLineEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.edit_search.textChanged.connect(self._filter_items)
        layout_main.addWidget(self.edit_search)

        # Conteneur horizontal à 2 colonnes
        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(14)

        self._cards: List[tuple[StepPickerCard, str]] = []

        # ── Colonne 1 : AGENTS IA & PROMPTS ──────────────────────────────────
        col1_widget = QWidget()
        col1_layout = QVBoxLayout(col1_widget)
        col1_layout.setContentsMargins(0, 0, 0, 0)
        col1_layout.setSpacing(8)

        lbl_col1_header = QLabel("AGENTS IA & PROMPTS")
        lbl_col1_header.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        col1_layout.addWidget(lbl_col1_header)

        scroll1 = QScrollArea()
        scroll1.setWidgetResizable(True)
        scroll1.setFrameShape(QFrame.Shape.NoFrame)
        scroll1.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner1 = QWidget()
        self.col1_cards_layout = QVBoxLayout(inner1)
        self.col1_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.col1_cards_layout.setSpacing(8)

        # Option Prompt Pur (sans Persona prédéfini)
        card_prompt_pure = StepPickerCard(
            payload={"type": "LLM_PROMPT", "persona": None},
            icon_name="ph.sparkle",
            title="Agent IA (Prompt Libre)",
            subtitle="Étape LLM sans persona prédéfini avec prompt personnalisé à rédiger.",
            badge_text="PROMPT",
            badge_color="#8b5cf6",
        )
        card_prompt_pure.clicked.connect(self._on_item_selected)
        self.col1_cards_layout.addWidget(card_prompt_pure)
        self._cards.append((card_prompt_pure, "agent ia prompt libre personnalise prompt pur".lower()))

        if not self.personas:
            lbl_no_p = QLabel("Aucun persona configuré. Créez des agents dans l'Atelier d'Agents.")
            lbl_no_p.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic; margin-left: 6px;")
            self.col1_cards_layout.addWidget(lbl_no_p)

        for p in self.personas:
            p_desc = p.system_prompt.strip().replace("\n", " ") if p.system_prompt else "Agent IA spécialisé"
            if len(p_desc) > 85:
                p_desc = p_desc[:82] + "..."
            card = StepPickerCard(
                payload={"type": "LLM_PROMPT", "persona": p},
                icon_name="ph.sparkle",
                title=f"Agent : {p.name}",
                subtitle=p_desc,
                badge_text="LLM",
                badge_color="#8b5cf6",
            )
            card.clicked.connect(self._on_item_selected)
            self.col1_cards_layout.addWidget(card)
            self._cards.append((card, f"{p.name} {p_desc}".lower()))

        self.col1_cards_layout.addStretch()
        scroll1.setWidget(inner1)
        col1_layout.addWidget(scroll1, 1)
        cols_layout.addWidget(col1_widget, 1)

        # Séparateur vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"border: none; border-left: 1px solid {DesignTokens.BORDER_COLOR};")
        cols_layout.addWidget(sep)

        # ── Colonne 2 : ACTIONS SYSTÈME & OUTILS ──────────────────────────────
        col2_widget = QWidget()
        col2_layout = QVBoxLayout(col2_widget)
        col2_layout.setContentsMargins(0, 0, 0, 0)
        col2_layout.setSpacing(8)

        lbl_col2_header = QLabel("ACTIONS SYSTÈME & OUTILS")
        lbl_col2_header.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        col2_layout.addWidget(lbl_col2_header)

        scroll2 = QScrollArea()
        scroll2.setWidgetResizable(True)
        scroll2.setFrameShape(QFrame.Shape.NoFrame)
        scroll2.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner2 = QWidget()
        self.col2_cards_layout = QVBoxLayout(inner2)
        self.col2_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.col2_cards_layout.setSpacing(8)

        actions = [
            (
                {"type": "RAG_RETRIEVAL"},
                "ph.database",
                "Recherche RAG Vectorielle",
                "Extraction sémantique FAISS des documents indexés pour injecter du contexte documentaire précis.",
                "RAG",
                "#06b6d4",
            ),
            (
                {"type": "MAP_REDUCE"},
                "ph.stack",
                "Forge Parallèle (Map-Reduce)",
                "Découpe les documents volumineux par pages ou sections et génère les cartes par lots.",
                "PARALLÈLE",
                "#10b981",
            ),
            (
                {"type": "HUMAN_VALIDATION"},
                "ph.pause-circle",
                "Pause Copilote (Validation)",
                "Interrompt l'exécution du workflow pour permettre à l'utilisateur de réviser ou valider les données.",
                "PAUSE",
                "#f59e0b",
            ),
            (
                {"type": "PYTHON_TOOL"},
                "ph.code",
                "Outil Python Déterministe",
                "Exécute un script ou outil utilitaire (nettoyage LaTeX/HTML, déduplication Levenshtein).",
                "OUTIL",
                "#f97316",
            ),
        ]

        for payload, icon_n, title, desc, badge_t, badge_c in actions:
            card = StepPickerCard(
                payload=payload,
                icon_name=icon_n,
                title=title,
                subtitle=desc,
                badge_text=badge_t,
                badge_color=badge_c,
            )
            card.clicked.connect(self._on_item_selected)
            self.col2_cards_layout.addWidget(card)
            self._cards.append((card, f"{title} {desc}".lower()))

        self.col2_cards_layout.addStretch()
        scroll2.setWidget(inner2)
        col2_layout.addWidget(scroll2, 1)
        cols_layout.addWidget(col2_widget, 1)

        layout_main.addLayout(cols_layout, 1)

    def _filter_items(self, query: str) -> None:
        q = query.strip().lower()
        for card, text in self._cards:
            card.setVisible(not q or q in text)

    def _on_item_selected(self, payload: Dict[str, Any]) -> None:
        self.selected_step_data = payload
        self.accept()


class PersonaSelectorDialog(QDialog):
    """Dialogue compact pour sélectionner un Persona ou passer en Prompt Pur."""

    def __init__(self, personas: List[PersonaModel], current_persona: Optional[PersonaModel] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.personas = personas
        self.selected_persona: Optional[PersonaModel] = None
        self.setWindowTitle("Changer d'Agent IA")
        self.resize(460, 380)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QScrollArea, QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Option : Aucun Agent (Prompt Pur)
        card_none = StepPickerCard(
            payload={"persona": None},
            icon_name="ph.sparkle",
            title="Aucun Agent (Prompt Pur)",
            subtitle="Utiliser uniquement le prompt personnalisé défini dans l'étape sans persona de base.",
            badge_text="PROMPT",
            badge_color="#64748b",
        )
        card_none.clicked.connect(self._on_selected)
        layout.addWidget(card_none)

        lbl_sep = QLabel("AGENTS DISPONIBLES :")
        lbl_sep.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; margin-top: 6px;")
        layout.addWidget(lbl_sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(6)

        for p in self.personas:
            p_desc = p.system_prompt.strip().replace("\n", " ") if p.system_prompt else "Agent IA"
            if len(p_desc) > 80:
                p_desc = p_desc[:77] + "..."
            card = StepPickerCard(
                payload={"persona": p},
                icon_name="ph.sparkle",
                title=str(p.name),
                subtitle=p_desc,
                badge_text="PERSONA",
                badge_color="#8b5cf6",
            )
            card.clicked.connect(self._on_selected)
            inner_layout.addWidget(card)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, 1)

    def _on_selected(self, payload: Dict[str, Any]) -> None:
        self.selected_persona = payload.get("persona")
        self.accept()


class PersonaIdentityCard(QFrame):
    """Carte d'identité stylée et enrichie du Persona IA dans l'Inspecteur."""

    change_persona_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PersonaIdentityCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 8px;
                padding: 10px;
            }}
            PersonaIdentityCard QLabel {{
                background: transparent;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Header Row
        h_row = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color="#8b5cf6").pixmap(18, 18))
        h_row.addWidget(icon_lbl)

        self.lbl_title = QLabel("<b>Agent : Non défini</b>")
        self.lbl_title.setStyleSheet(f"font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
        h_row.addWidget(self.lbl_title, 1)

        self.badge_role = Badge("Agent IA", variant="status")
        apply_pill_style(self.badge_role, "#8b5cf6")
        h_row.addWidget(self.badge_role)
        layout.addLayout(h_row)

        # Description / System Prompt preview
        self.lbl_desc = QLabel("Prompt système...")
        self.lbl_desc.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED}; font-style: italic;")
        self.lbl_desc.setWordWrap(True)
        layout.addWidget(self.lbl_desc)

        # Action button
        b_row = QHBoxLayout()
        self.btn_switch = SecondaryButton("Changer d'Agent...")
        self.btn_switch.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))
        self.btn_switch.setStyleSheet(f"background: {DesignTokens.BG_PANEL}; font-size: 11px; padding: 3px 10px;")
        self.btn_switch.clicked.connect(self.change_persona_requested.emit)
        b_row.addWidget(self.btn_switch)
        b_row.addStretch()
        layout.addLayout(b_row)

    def set_persona(self, persona: Optional[PersonaModel]) -> None:
        if persona:
            self.lbl_title.setText(f"<b>Agent : {persona.name}</b>")
            desc = persona.system_prompt.strip().replace("\n", " ") if persona.system_prompt else "Agent IA spécialisé."
            if len(desc) > 95:
                desc = desc[:92] + "..."
            self.lbl_desc.setText(f"« {desc} »")
            self.badge_role.setText("Agent IA")
            apply_pill_style(self.badge_role, "#8b5cf6")
        else:
            self.lbl_title.setText("<b>Aucun Agent IA (Prompt Pur)</b>")
            self.lbl_desc.setText("L'étape s'exécutera avec le prompt personnalisé ci-dessous sans persona de base.")
            self.badge_role.setText("Prompt Pur")
            apply_pill_style(self.badge_role, "#64748b")


# =====================================================================
# MODALE DE PRÉVISUALISATION JINJA2 DU PROMPT
# =====================================================================


class PromptPreviewDialog(QDialog):
    """Affiche la résolution dynamique du template Jinja2 avec des données échantillons réalistes."""

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

        lbl_header = QLabel("👁️ Ce que recevra l'Agent IA (variables résolues) :")
        lbl_header.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_header)

        # Rendu Jinja2 avec état de démonstration (texte brut pour invite LLM)
        rendered_text = ""
        try:
            env = Environment(loader=BaseLoader(), autoescape=False)  # nosec B701
            tpl = env.from_string(template_str)
            mock_state = {
                "initial_prompt": "Créer 5 flashcards sur la diagonalisation matricielle.",
                "variables": {
                    "text_source": "Soit A une matrice carrée n x n. A est diagonalisable s'il existe une base de vecteurs propres.",
                    "generated_cards": [{"Front": "Définition diagonalisation", "Back": "Existe base de vecteurs propres"}],
                    "last_output": "Cartes générées avec succès.",
                    "plan_cours": "1. Définition\n2. Valeurs propres\n3. Sous-espaces propres",
                },
            }
            rendered_text = tpl.render(state=mock_state)
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
                font-family: monospace;
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
# BLOC 4 : VOLET DÉTAIL / INSPECTEUR DE CONFIGURATION (StepInspectorPanel)
# =====================================================================


class StepInspectorPanel(QFrame):
    """Volet droit d'inspection et de réglages fins de l'étape sélectionnée avec assistance Jinja2."""

    step_updated = Signal()
    test_step_requested = Signal(dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.step_data: Optional[Dict[str, Any]] = None
        self.step_order: int = 1
        self.total_steps: int = 1
        self.available_personas: List[PersonaModel] = []
        self.available_llms: List[LLMConfigModel] = []

        self.setObjectName("StepInspector")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            QFrame#StepInspector {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#StepInspector QLabel {{
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # ── 1. En-tête de l'Inspecteur ──────────────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.lbl_step_icon = QLabel()
        header_layout.addWidget(self.lbl_step_icon)

        self.edit_step_title = QLineEdit()
        self.edit_step_title.setPlaceholderText("Nom personnalisé de l'étape...")
        self.edit_step_title.setStyleSheet(f"""
            QLineEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_PRIMARY};
                font-weight: bold;
                font-size: 13px;
                padding: 4px 8px;
                border-radius: 4px;
            }}
        """)
        self.edit_step_title.textChanged.connect(self._on_title_changed)
        header_layout.addWidget(self.edit_step_title, 1)

        self.role_badge = Badge("LLM", variant="status")
        apply_pill_style(self.role_badge, "#8b5cf6")
        header_layout.addWidget(self.role_badge)

        self.btn_test_step = SecondaryButton("Tester l'étape")
        self.btn_test_step.setIcon(load_phosphor_icon("ph.flask", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test_step.clicked.connect(self._on_test_step_clicked)
        header_layout.addWidget(self.btn_test_step)

        layout.addLayout(header_layout)

        # ── 2. Onglets de Configuration ─────────────────────────────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background: {DesignTokens.BG_MAIN};
                border-radius: 6px;
                padding: 10px;
            }}
            QTabBar::tab {{
                background: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 6px 14px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }}
            QTabBar::tab:selected {{
                background: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Tab 1: Paramètres Métier (avec ScrollArea dédiée pour éliminer tout chevauchement)
        self.tab_params = QWidget()
        layout_tab_params = QVBoxLayout(self.tab_params)
        layout_tab_params.setContentsMargins(0, 0, 0, 0)
        layout_tab_params.setSpacing(0)

        self.params_scroll = QScrollArea()
        self.params_scroll.setWidgetResizable(True)
        self.params_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.params_scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ background: {DesignTokens.BG_INPUT}; width: 6px; border-radius: 3px; }}
            QScrollBar::handle:vertical {{ background: {DesignTokens.BORDER_COLOR}; border-radius: 3px; min-height: 20px; }}
        """)
        layout_tab_params.addWidget(self.params_scroll)
        self.tabs.addTab(self.tab_params, "⚙️ Paramètres & Prompt")

        # Tab 2: Branchements DAG
        self.tab_dag = QWidget()
        self.layout_dag = QGridLayout(self.tab_dag)
        self.layout_dag.setContentsMargins(12, 12, 12, 12)
        self.layout_dag.setHorizontalSpacing(12)
        self.layout_dag.setVerticalSpacing(10)
        self.tabs.addTab(self.tab_dag, "🔀 Transitions DAG & Erreurs")

        self._setup_dag_tab()

        layout.addWidget(self.tabs, 1)

    def _setup_dag_tab(self) -> None:
        """Construit le contenu de l'onglet Transitions DAG."""
        lbl_succ = QLabel("Transition de Succès :")
        lbl_succ.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.combo_succ = StyledComboBox()
        self.combo_succ.currentIndexChanged.connect(self._on_branching_changed)
        self.layout_dag.addWidget(lbl_succ, 0, 0)
        self.layout_dag.addWidget(self.combo_succ, 0, 1)

        lbl_fail_beh = QLabel("En cas d'Erreur :")
        lbl_fail_beh.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.combo_fail_beh = StyledComboBox()
        self.combo_fail_beh.addItem("🛑 Arrêter le pipeline (stop)", userData="stop")
        self.combo_fail_beh.addItem("⏭️ Continuer malgré l'erreur (continue)", userData="continue")
        self.combo_fail_beh.addItem("🔀 Sauter vers étape de secours", userData="goto_failure_step")
        self.combo_fail_beh.currentIndexChanged.connect(self._on_fail_beh_changed)
        self.layout_dag.addWidget(lbl_fail_beh, 1, 0)
        self.layout_dag.addWidget(self.combo_fail_beh, 1, 1)

        self.lbl_fail_target = QLabel("Étape de Secours :")
        self.lbl_fail_target.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.combo_fail_target = StyledComboBox()
        self.combo_fail_target.currentIndexChanged.connect(self._on_branching_changed)
        self.layout_dag.addWidget(self.lbl_fail_target, 2, 0)
        self.layout_dag.addWidget(self.combo_fail_target, 2, 1)

    def inspect_step(
        self,
        step_data: Dict[str, Any],
        step_order: int,
        total_steps: int,
        personas: List[PersonaModel],
        llms: List[LLMConfigModel],
    ) -> None:
        """Charge et affiche les données de l'étape sélectionnée."""
        self.step_data = step_data
        self.step_order = step_order
        self.total_steps = total_steps
        self.available_personas = personas
        self.available_llms = llms

        step_type = step_data.get("type", "LLM_PROMPT")
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])

        # En-tête
        self.lbl_step_icon.setPixmap(load_phosphor_icon(meta["icon"], color=meta["badge_color"]).pixmap(18, 18))
        persona = step_data.get("persona")
        custom_t = step_data.get("custom_title") or (persona.name if persona else meta["default_title"])
        self.edit_step_title.blockSignals(True)
        self.edit_step_title.setText(custom_t)
        self.edit_step_title.blockSignals(False)

        self.role_badge.setText(meta["badge"])
        apply_pill_style(self.role_badge, meta["badge_color"])

        # Reconstruire le formulaire dynamique des paramètres
        self._build_params_form(step_type)

        # Mettre à jour l'onglet DAG
        self._update_dag_controls()

    def _build_params_form(self, step_type: str) -> None:
        """Génère le formulaire spécifique au type d'étape avec assistance de chips Jinja2 et aperçu."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout_params = QVBoxLayout(container)
        layout_params.setContentsMargins(10, 10, 10, 10)
        layout_params.setSpacing(12)

        if not self.step_data:
            self.params_scroll.setWidget(container)
            return

        cfg = self.step_data.get("config", {})

        if step_type in ("LLM_PROMPT", "MAP_REDUCE"):
            # 1. Carte d'identité enrichie du Persona IA
            p_card = PersonaIdentityCard()
            cur_persona = self.step_data.get("persona")
            p_card.set_persona(cur_persona)

            def _handle_change_persona() -> None:
                cur_p = self.step_data.get("persona") if self.step_data else None
                dlg = PersonaSelectorDialog(personas=self.available_personas, current_persona=cur_p, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    new_p = dlg.selected_persona
                    self._on_param_changed("persona", new_p)
                    p_card.set_persona(new_p)
                    if new_p and self.step_data and not self.step_data.get("custom_title"):
                        self.edit_step_title.setText(str(new_p.name))

            p_card.change_persona_requested.connect(_handle_change_persona)
            layout_params.addWidget(p_card)

            # 2. Surcharge LLM
            row_llm = QHBoxLayout()
            lbl_m = QLabel("Modèle LLM dédié :")
            lbl_m.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            combo_llm = StyledComboBox()
            combo_llm.addItem("Modèle par défaut du profil", userData=None)
            sel_llm_idx = 0
            cur_llm_id = cfg.get("llm_config_id")
            for i, m in enumerate(self.available_llms, start=1):
                name = getattr(m, "display_name", None) or getattr(m, "model_id", "Modèle")
                pricing_tag = "Gratuit" if getattr(m, "is_free", False) else f"{getattr(m, 'prompt_pricing', 0):.1f}$/1M"
                combo_llm.addItem(f"{name} ({m.provider} · {pricing_tag})", userData=m.id)
                if cur_llm_id == m.id:
                    sel_llm_idx = i
            combo_llm.setCurrentIndex(sel_llm_idx)
            combo_llm.currentIndexChanged.connect(lambda: self._on_config_changed("llm_config_id", combo_llm.currentData()))
            row_llm.addWidget(lbl_m)
            row_llm.addWidget(combo_llm, 1)
            layout_params.addLayout(row_llm)

            # Si MAP_REDUCE, ajouter la taille des lots et le partitionnement
            if step_type == "MAP_REDUCE":
                row_mr = QHBoxLayout()
                lbl_batch = QLabel("Taille des lots :")
                lbl_batch.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
                spin_batch = QSpinBox()
                spin_batch.setRange(1, 10)
                spin_batch.setValue(int(cfg.get("batch_size", 3)))
                spin_batch.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR};")
                spin_batch.valueChanged.connect(lambda v: self._on_config_changed("batch_size", v))
                row_mr.addWidget(lbl_batch)
                row_mr.addWidget(spin_batch)

                lbl_mode = QLabel("Découpage :")
                lbl_mode.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-left: 10px;")
                combo_mode = StyledComboBox()
                combo_mode.addItem("📄 Par Page (PDF)", userData="page")
                combo_mode.addItem("📑 Par Section / Chapitre", userData="chapter")
                combo_mode.addItem("📦 Par Lots de Paragraphes", userData="paragraphs")
                combo_mode.currentIndexChanged.connect(lambda: self._on_config_changed("split_mode", combo_mode.currentData()))
                row_mr.addWidget(lbl_mode)
                row_mr.addWidget(combo_mode, 1)
                layout_params.addLayout(row_mr)

            # 3. Variables Entrée / Sortie & Format
            grid_vars = QGridLayout()
            lbl_in = QLabel("Variable d'entrée :")
            lbl_in.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            edit_in = QLineEdit(cfg.get("input_variable", "text_source"))
            edit_in.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 4px; border-radius: 4px;")
            edit_in.textChanged.connect(lambda t: self._on_config_changed("input_variable", t))

            lbl_out = QLabel("Variable de sortie :")
            lbl_out.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            edit_out = QLineEdit(cfg.get("output_variable", "generated_cards"))
            edit_out.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 4px; border-radius: 4px;")
            edit_out.textChanged.connect(lambda t: self._on_config_changed("output_variable", t))

            lbl_fmt = QLabel("Format de sortie :")
            lbl_fmt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            combo_fmt = StyledComboBox()
            combo_fmt.addItem("JSON Strict (Cartes)", userData="json")
            combo_fmt.addItem("Markdown / Texte", userData="text")
            cur_fmt = cfg.get("output_format", "json")
            combo_fmt.setCurrentIndex(0 if cur_fmt == "json" else 1)
            combo_fmt.currentIndexChanged.connect(lambda: self._on_config_changed("output_format", combo_fmt.currentData()))

            grid_vars.addWidget(lbl_in, 0, 0)
            grid_vars.addWidget(edit_in, 0, 1)
            grid_vars.addWidget(lbl_out, 0, 2)
            grid_vars.addWidget(edit_out, 0, 3)
            grid_vars.addWidget(lbl_fmt, 1, 0)
            grid_vars.addWidget(combo_fmt, 1, 1)
            layout_params.addLayout(grid_vars)

            # 4. Surcharge Prompt Jinja2 avec Palette de Chips d'insertion rapide
            row_prompt_header = QHBoxLayout()
            lbl_prompt = QLabel("Surcharge Prompt Système / Template Jinja2 :")
            lbl_prompt.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            row_prompt_header.addWidget(lbl_prompt)
            row_prompt_header.addStretch()

            btn_preview_prompt = SecondaryButton("Aperçu Prompt")
            btn_preview_prompt.setIcon(load_phosphor_icon("ph.eye", color=DesignTokens.TEXT_PRIMARY))
            btn_preview_prompt.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; font-size: 10px; padding: 2px 8px;")
            row_prompt_header.addWidget(btn_preview_prompt)
            layout_params.addLayout(row_prompt_header)

            edit_prompt = QTextEdit()
            edit_prompt.setPlaceholderText("Laisser vide pour utiliser le prompt par défaut du Persona...")
            edit_prompt.setText(cfg.get("prompt_override", ""))
            edit_prompt.setMinimumHeight(150)
            edit_prompt.setStyleSheet(f"""
                QTextEdit {{
                    background: {DesignTokens.BG_INPUT};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    color: {DesignTokens.TEXT_PRIMARY};
                    font-family: monospace;
                    font-size: 12px;
                    border-radius: 4px;
                    padding: 6px;
                }}
            """)
            edit_prompt.textChanged.connect(lambda: self._on_config_changed("prompt_override", edit_prompt.toPlainText()))

            btn_preview_prompt.clicked.connect(lambda: PromptPreviewDialog(edit_prompt.toPlainText(), parent=self).exec())

            # Palette de Chips Jinja2
            row_chips = QHBoxLayout()
            row_chips.setSpacing(4)
            lbl_chips = QLabel("Insérer :")
            lbl_chips.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
            row_chips.addWidget(lbl_chips)

            jinja_chips = [
                ("text_source", "{{ state.variables.text_source }}"),
                ("generated_cards", "{{ state.variables.generated_cards }}"),
                ("initial_prompt", "{{ state.initial_prompt }}"),
                ("last_output", "{{ state.variables.last_output }}"),
            ]

            for label, tag in jinja_chips:
                chip_btn = QPushButton(f"+ {label}")
                chip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                chip_btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {DesignTokens.BG_PANEL};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        color: {DesignTokens.ACCENT_PRIMARY};
                        font-size: 10px;
                        font-family: monospace;
                        border-radius: 3px;
                        padding: 2px 6px;
                    }}
                    QPushButton:hover {{
                        background-color: {DesignTokens.BG_HOVER};
                        border-color: {DesignTokens.ACCENT_PRIMARY};
                    }}
                """)

                def _make_insert(t: str) -> Any:
                    return lambda: (edit_prompt.textCursor().insertText(t), edit_prompt.setFocus())

                chip_btn.clicked.connect(_make_insert(tag))
                row_chips.addWidget(chip_btn)

            row_chips.addStretch()
            layout_params.addLayout(row_chips)
            layout_params.addWidget(edit_prompt)

        elif step_type == "RAG_RETRIEVAL":
            row_rag = QHBoxLayout()
            lbl_topk = QLabel("Nombre de fragments (Top-K) :")
            lbl_topk.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            spin_topk = QSpinBox()
            spin_topk.setRange(1, 20)
            spin_topk.setValue(int(cfg.get("top_k", 5)))
            spin_topk.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; color: {DesignTokens.TEXT_PRIMARY}; border: 1px solid {DesignTokens.BORDER_COLOR};")
            spin_topk.valueChanged.connect(lambda v: self._on_config_changed("top_k", v))
            row_rag.addWidget(lbl_topk)
            row_rag.addWidget(spin_topk)
            row_rag.addStretch()
            layout_params.addLayout(row_rag)

            lbl_query = QLabel("Template de Requête Sémantique (Jinja2) :")
            lbl_query.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
            layout_params.addWidget(lbl_query)

            edit_query = QLineEdit(cfg.get("rag_query_template", "{{ state.initial_prompt }}"))
            edit_query.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 6px; border-radius: 4px;")
            edit_query.textChanged.connect(lambda t: self._on_config_changed("rag_query_template", t))
            layout_params.addWidget(edit_query)
            layout_params.addStretch()

        elif step_type == "HUMAN_VALIDATION":
            lbl_ht = QLabel("Titre de l'Interruption Humaine :")
            lbl_ht.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            layout_params.addWidget(lbl_ht)

            edit_ht = QLineEdit(cfg.get("human_title", "Validation du Plan de Cours"))
            edit_ht.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 6px; border-radius: 4px;")
            edit_ht.textChanged.connect(lambda t: self._on_config_changed("human_title", t))
            layout_params.addWidget(edit_ht)

            lbl_hm = QLabel("Message d'Instructions :")
            lbl_hm.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
            layout_params.addWidget(lbl_hm)

            edit_hm = QTextEdit()
            edit_hm.setText(cfg.get("human_message", "Veuillez vérifier et ajuster les sections avant de forger les cartes."))
            edit_hm.setMinimumHeight(140)
            edit_hm.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; border-radius: 4px; padding: 6px;")
            edit_hm.textChanged.connect(lambda: self._on_config_changed("human_message", edit_hm.toPlainText()))
            layout_params.addWidget(edit_hm)

        elif step_type == "PYTHON_TOOL":
            row_sel = QHBoxLayout()
            lbl_tool = QLabel("Outil Python Déterministe :")
            lbl_tool.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
            row_sel.addWidget(lbl_tool)

            btn_new_tool = SecondaryButton("Nouvel Outil")
            btn_new_tool.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))
            btn_new_tool.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; font-size: 11px; padding: 3px 8px;")
            row_sel.addWidget(btn_new_tool)
            row_sel.addStretch()
            layout_params.addLayout(row_sel)

            combo_tool = StyledComboBox()
            tools_list = ToolService.list_tools()
            cur_tool_name = cfg.get("tool_name", "clean_html_latex")
            sel_tool_idx = 0
            for idx, t in enumerate(tools_list):
                tag = " (Natif)" if t.is_builtin else " (Custom)"
                combo_tool.addItem(f"{t.display_name}{tag}", userData=t.name)
                if t.name == cur_tool_name:
                    sel_tool_idx = idx
            combo_tool.setCurrentIndex(sel_tool_idx)
            combo_tool.currentIndexChanged.connect(lambda: self._on_config_changed("tool_name", combo_tool.currentData()))
            layout_params.addWidget(combo_tool)

            # Boutons d'édition et variables
            row_tool_actions = QHBoxLayout()
            btn_edit_code = SecondaryButton("Voir / Modifier le Script")
            btn_edit_code.setIcon(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.TEXT_PRIMARY))
            btn_edit_code.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; font-size: 11px; padding: 4px 10px;")

            def _open_editor() -> None:
                sel_name = combo_tool.currentData()
                tool_obj = ToolService.get_tool(sel_name)
                dlg = ToolEditorDialog(tool_obj, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._build_params_form("PYTHON_TOOL")

            def _create_new() -> None:
                dlg = ToolEditorDialog(None, parent=self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self._build_params_form("PYTHON_TOOL")

            btn_new_tool.clicked.connect(_create_new)
            btn_edit_code.clicked.connect(_open_editor)
            row_tool_actions.addWidget(btn_edit_code)
            row_tool_actions.addStretch()
            layout_params.addLayout(row_tool_actions)

            # Variable de sortie
            lbl_out = QLabel("Variable de sortie du résultat :")
            lbl_out.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
            layout_params.addWidget(lbl_out)

            edit_out = QLineEdit(cfg.get("output_variable", "tool_result"))
            edit_out.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 6px; border-radius: 4px;")
            edit_out.textChanged.connect(lambda t: self._on_config_changed("output_variable", t))
            layout_params.addWidget(edit_out)
            layout_params.addStretch()

        self.params_scroll.setWidget(container)

    def _update_dag_controls(self) -> None:
        """Met à jour les combos de transitions DAG."""
        if not self.step_data:
            return

        # Succès
        self.combo_succ.blockSignals(True)
        self.combo_succ.clear()
        self.combo_succ.addItem("➡️ Étape suivante par défaut (séquentiel)", userData=None)
        current_succ = self.step_data.get("on_success_order")
        sel_succ_idx = 0
        for num in range(1, self.total_steps + 1):
            if num != self.step_order:
                self.combo_succ.addItem(f"↳ Sauter vers Étape {num}", userData=num)
                if current_succ == num:
                    sel_succ_idx = self.combo_succ.count() - 1
        self.combo_succ.setCurrentIndex(sel_succ_idx)
        self.combo_succ.blockSignals(False)

        # Comportement d'échec
        self.combo_fail_beh.blockSignals(True)
        fail_beh = self.step_data.get("failure_behavior", "stop")
        if fail_beh == "continue":
            self.combo_fail_beh.setCurrentIndex(1)
        elif fail_beh == "goto_failure_step":
            self.combo_fail_beh.setCurrentIndex(2)
        else:
            self.combo_fail_beh.setCurrentIndex(0)
        self.combo_fail_beh.blockSignals(False)

        # Cible d'échec
        self.combo_fail_target.blockSignals(True)
        self.combo_fail_target.clear()
        self.combo_fail_target.addItem("Aucune étape de secours", userData=None)
        current_fail = self.step_data.get("on_failure_order")
        sel_fail_idx = 0
        for num in range(1, self.total_steps + 1):
            if num != self.step_order:
                self.combo_fail_target.addItem(f"↳ Sauter vers Étape {num}", userData=num)
                if current_fail == num:
                    sel_fail_idx = self.combo_fail_target.count() - 1
        self.combo_fail_target.setCurrentIndex(sel_fail_idx)
        self.combo_fail_target.blockSignals(False)

        self._on_fail_beh_changed()

    def _on_fail_beh_changed(self) -> None:
        beh = self.combo_fail_beh.currentData()
        show_target = beh == "goto_failure_step"
        self.lbl_fail_target.setVisible(show_target)
        self.combo_fail_target.setVisible(show_target)
        if self.step_data:
            self.step_data["failure_behavior"] = beh
            self.step_updated.emit()

    def _on_branching_changed(self) -> None:
        if not self.step_data:
            return
        self.step_data["on_success_order"] = self.combo_succ.currentData()
        self.step_data["on_failure_order"] = self.combo_fail_target.currentData()
        self.step_updated.emit()

    def _on_title_changed(self, text: str) -> None:
        if self.step_data:
            self.step_data["custom_title"] = text.strip()
            self.step_updated.emit()

    def _on_param_changed(self, key: str, value: Any) -> None:
        if self.step_data:
            self.step_data[key] = value
            self.step_updated.emit()

    def _on_config_changed(self, key: str, value: Any) -> None:
        if self.step_data:
            if "config" not in self.step_data:
                self.step_data["config"] = {}
            self.step_data["config"][key] = value
            self.step_updated.emit()

    def _on_test_step_clicked(self) -> None:
        if self.step_data:
            self.test_step_requested.emit(self.step_data)


# =====================================================================
# MODALES DE TEST : ÉTAPE ISOLÉE ET DAG COMPLET
# =====================================================================


class StepTestDialog(QDialog):
    """Dialogue modal pour tester l'exécution unitaire d'une étape spécifique."""

    def __init__(self, step_data: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.step_data = step_data
        step_type = step_data.get("type", "LLM_PROMPT")
        meta = STEP_TYPES_META.get(step_type, STEP_TYPES_META["LLM_PROMPT"])

        self.setWindowTitle(f"Test d'Étape : {step_data.get('custom_title', meta['default_title'])}")
        self.resize(650, 480)
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

        lbl_desc = QLabel("Simulation de l'étape sur un état en mémoire :")
        lbl_desc.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        layout.addWidget(lbl_desc)

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: #38bdf8; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.output_text, 1)

        h_btn = QHBoxLayout()
        btn_run = PrimaryButton("Lancer la simulation")
        btn_run.setIcon(load_phosphor_icon("ph.play", color="white"))
        btn_run.clicked.connect(self._run_simulation)
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        h_btn.addWidget(btn_run)
        h_btn.addStretch()
        h_btn.addWidget(btn_close)
        layout.addLayout(h_btn)

    def _run_simulation(self) -> None:
        self.output_text.clear()
        self.output_text.append("🧪 Démarrage de la simulation d'étape...")

        stype = self.step_data.get("type", "LLM_PROMPT")
        cfg = self.step_data.get("config", {})

        state = PipelineRunState(initial_prompt="Exemple de cours d'informatique.")
        state.set_variable("text_source", "La complexité temporelle du tri fusion est O(n log n).")
        state.set_variable("generated_cards", [{"Front": "Complexité du tri fusion ?", "Back": "O(n log n)"}])

        if stype == "LLM_PROMPT":
            persona = self.step_data.get("persona")
            prompt_override = cfg.get("prompt_override")
            raw_prompt = prompt_override or (persona.prompt_template if persona else "Extrais 3 flashcards du texte.")
            self.output_text.append(f"Prompt appliqué :\n{raw_prompt}\n")
            mock = MockProvider()
            res = mock.generate("Système", raw_prompt)
            self.output_text.append(f"Réponse simulée de l'IA :\n{res.content}")

        elif stype == "RAG_RETRIEVAL":
            self.output_text.append("Recherche RAG vectorielle (Top-K = %s)" % cfg.get("top_k", 5))
            self.output_text.append("Fragments trouvés : 3 chunks simulés depuis FAISS.")

        elif stype == "PYTHON_TOOL":
            tool_name = cfg.get("tool_name", "clean_html_latex")
            res = ToolService.execute_tool(tool_name, state)
            self.output_text.append(f"Exécution outil '{tool_name}' : {res}")

        elif stype == "HUMAN_VALIDATION":
            self.output_text.append("Interruption Copilote simulée : 'Plan validé par l'utilisateur'")


class PipelineRunDialog(QDialog):
    """Dialogue de test en direct du pipeline complet avec logs et suivi pas à pas."""

    def __init__(self, pipeline: PipelineModel, steps: List[Dict[str, Any]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.pipeline = pipeline
        self.steps = steps
        self.setWindowTitle(f"Test en direct : {pipeline.name}")
        self.resize(750, 520)
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

        lbl_top = QLabel(f"Exécution du pipeline DAG ({len(steps)} étapes) :")
        lbl_top.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        layout.addWidget(lbl_top)

        self.console = QPlainTextEdit()
        self.console.setReadOnly(True)
        self.console.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: #38bdf8; font-family: monospace; font-size: 12px;")
        layout.addWidget(self.console, 1)

        h_btn = QHBoxLayout()
        self.btn_start = PrimaryButton("Démarrer l'exécution")
        self.btn_start.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_start.clicked.connect(self._start_run)
        self.btn_close = SecondaryButton("Fermer")
        self.btn_close.clicked.connect(self.accept)
        h_btn.addWidget(self.btn_start)
        h_btn.addStretch()
        h_btn.addWidget(self.btn_close)
        layout.addLayout(h_btn)

    def _start_run(self) -> None:
        self.btn_start.setEnabled(False)
        self.console.appendPlainText("🚀 Initialisation du Moteur DAG...")

        state = PipelineRunState(initial_prompt="Introduction à l'algèbre linéaire.")
        state.set_variable("text_source", "Une matrice est un tableau rectangulaire de nombres réels ou complexes.")

        step_models: List[PipelineStepModel] = []
        for idx, s in enumerate(self.steps, start=1):
            cfg_json = json.dumps(s.get("config", {}))
            sm = PipelineStepModel(
                pipeline=self.pipeline,
                persona=s.get("persona"),
                step_type=s.get("type", "LLM_PROMPT"),
                step_order=idx,
                failure_behavior=s.get("failure_behavior", "stop"),
                config_data=cfg_json,
            )
            step_models.append(sm)

        self.orchestrator = PipelineOrchestrator(
            initial_state=state,
            steps=step_models,
        )
        self.orchestrator.signals.step_started.connect(self._on_step_started)
        self.orchestrator.signals.step_completed.connect(self._on_step_completed)
        self.orchestrator.signals.pipeline_finished.connect(self._on_finished)
        self.orchestrator.signals.error_occurred.connect(self._on_error)
        self.orchestrator.run()

    def _on_step_started(self, step_order: int, desc: str) -> None:
        self.console.appendPlainText(f"\n▶ [{step_order}] {desc}")

    def _on_step_completed(self, step_order: int, state: PipelineRunState) -> None:
        self.console.appendPlainText(f"  ✅ Étape {step_order} terminée avec succès.")

    def _on_finished(self, state: PipelineRunState) -> None:
        cards = state.get_variable("generated_cards", [])
        self.console.appendPlainText(f"\n🏁 Pipeline terminé avec succès ! ({len(cards)} cartes générées)")
        self.btn_start.setEnabled(True)

    def _on_error(self, err: str) -> None:
        self.console.appendPlainText(f"\n❌ Erreur : {err}")
        self.btn_start.setEnabled(True)


# =====================================================================
# VUE PRINCIPALE : PIPELINESVIEW (Architecture Maître-Détail JetBrains)
# =====================================================================


class PipelinesView(QWidget):
    """Vue Pipelines de Génération — Architecture Maître-Détail JetBrains."""

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_pipeline: Optional[PipelineModel] = None
        self.current_steps: List[Dict[str, Any]] = []
        self._step_widgets: List[StepItemWidget] = []
        self._cached_personas: List[PersonaModel] = []
        self._cached_llms: List[LLMConfigModel] = []
        self._selected_step_index: int = 0

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(0)

        # Panneau IdePanel
        self.pipeline_panel = IdePanel(detachable=True)
        self.pipeline_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.pipeline_panel, 1)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        # ── 1. Barre Supérieure Épurée : Gestion & Toolbar ────────────────────
        pipeline_sel_row = QHBoxLayout()
        pipeline_sel_row.setSpacing(10)

        # Titre et icône Phosphor
        lbl_pipe_icon = QLabel()
        lbl_pipe_icon.setPixmap(load_phosphor_icon("ph.git-branch", color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        pipeline_sel_row.addWidget(lbl_pipe_icon)

        lbl_pipe = QLabel("PIPELINE :")
        lbl_pipe.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; letter-spacing: 0.5px;")
        pipeline_sel_row.addWidget(lbl_pipe)

        self.pipeline_combo = StyledComboBox()
        self.pipeline_combo.setMinimumWidth(220)
        pipeline_sel_row.addWidget(self.pipeline_combo)

        self.lbl_pipeline_steps_badge = Badge("0 étapes", variant="neutral")
        apply_pill_style(self.lbl_pipeline_steps_badge, "#94a3b8")
        pipeline_sel_row.addWidget(self.lbl_pipeline_steps_badge)

        self.btn_rename_pipeline = IconButton("ph.pencil-simple", tooltip="Renommer le pipeline", size=16)
        pipeline_sel_row.addWidget(self.btn_rename_pipeline)

        pipeline_sel_row.addStretch()

        # Action Principale : Tester DAG
        self.btn_test_full = SecondaryButton("Tester le DAG")
        self.btn_test_full.setIcon(load_phosphor_icon("ph.play", color=DesignTokens.TEXT_PRIMARY))
        self.btn_test_full.clicked.connect(self._on_test_full_pipeline)
        pipeline_sel_row.addWidget(self.btn_test_full)

        # Action Secondaire : Sauvegarder
        self.btn_save_pipeline = PrimaryButton("Enregistrer")
        self.btn_save_pipeline.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        apply_shadow(self.btn_save_pipeline, blur=14, offset_y=0, color="rgba(99, 102, 241, 0.7)")
        pipeline_sel_row.addWidget(self.btn_save_pipeline)

        # Menu d'Actions Groupées (•••)
        self.btn_more_menu = SecondaryButton("")
        self.btn_more_menu.setIcon(load_phosphor_icon("ph.dots-three-vertical", color=DesignTokens.TEXT_PRIMARY))
        self.btn_more_menu.setToolTip("Options avancées (Nouveau, Dupliquer, Modèles, Export/Import, Supprimer)")
        self.btn_more_menu.clicked.connect(self._on_open_more_menu)
        pipeline_sel_row.addWidget(self.btn_more_menu)

        content_layout.addLayout(pipeline_sel_row)

        # ── 2. Aperçu Visuel du Graphe DAG Interactif ─────────────────────────
        self.flow_overview = DagFlowOverviewWidget()
        self.flow_overview.step_selected.connect(self._on_step_selected)
        content_layout.addWidget(self.flow_overview)

        # ── 3. Splitter Maître-Détail ──────────────────────────────────────────
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PANNEAU GAUCHE : LISTE DES ÉTAPES ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        steps_header = QHBoxLayout()
        lbl_steps_title = QLabel("ÉTAPES DU WORKFLOW :")
        lbl_steps_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        steps_header.addWidget(lbl_steps_title)
        steps_header.addStretch()

        self.lbl_step_count = QLabel("0 étape")
        self.lbl_step_count.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        steps_header.addWidget(self.lbl_step_count)
        left_layout.addLayout(steps_header)

        # Scroll Area pour la liste des étapes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")

        self.steps_inner = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_inner)
        self.steps_layout.setContentsMargins(8, 8, 8, 8)
        self.steps_layout.setSpacing(8)
        self.steps_layout.addStretch()
        scroll.setWidget(self.steps_inner)
        left_layout.addWidget(scroll, 1)

        # Bouton d'Ajout d'Étape (Palette / Catalogue Moderne)
        self.btn_add_step = PrimaryButton("Ajouter une étape à la fin du workflow")
        self.btn_add_step.clicked.connect(lambda: self._on_add_step_clicked(insert_at=None))
        left_layout.addWidget(self.btn_add_step)

        self.splitter.addWidget(left_widget)

        # --- PANNEAU DROIT : INSPECTEUR D'ÉTAPE ---
        self.inspector = StepInspectorPanel()
        self.inspector.step_updated.connect(self._on_inspector_step_updated)
        self.inspector.test_step_requested.connect(self._on_test_single_step)
        self.splitter.addWidget(self.inspector)

        # Proportions 40% gauche / 60% droite
        self.splitter.setSizes([380, 580])
        content_layout.addWidget(self.splitter, 1)

        self.pipeline_panel.add_tab("Éditeur de Pipelines DAG", content_widget, icon_name="ph.git-branch", closable=False)

    def _connect_signals(self) -> None:
        self.pipeline_combo.currentIndexChanged.connect(self._on_pipeline_changed)
        self.btn_rename_pipeline.clicked.connect(self._on_rename_pipeline)
        self.btn_save_pipeline.clicked.connect(self._on_save_pipeline)

    def _on_open_more_menu(self) -> None:
        """Affiche le menu contextuel élégant regroupant toutes les actions secondaires."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 6px 24px 6px 10px;
                border-radius: 4px;
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {DesignTokens.BORDER_COLOR};
                margin: 4px 0px;
            }}
        """)

        act_new = menu.addAction(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY), "Nouveau Pipeline...")
        act_clone = menu.addAction(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY), "Dupliquer le Pipeline")
        act_templates = menu.addAction(load_phosphor_icon("ph.puzzle-piece", color=DesignTokens.TEXT_PRIMARY), "Modèles Prédéfinis...")

        menu.addSeparator()

        act_export = menu.addAction(load_phosphor_icon("ph.export", color=DesignTokens.TEXT_PRIMARY), "Exporter en JSON...")
        act_import = menu.addAction(load_phosphor_icon("ph.download-simple", color=DesignTokens.TEXT_PRIMARY), "Importer un JSON...")

        menu.addSeparator()

        act_del = menu.addAction(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED), "Supprimer ce Pipeline")

        action = menu.exec(QCursor.pos())
        if action == act_new:
            self._on_new_pipeline()
        elif action == act_clone:
            self._on_clone_pipeline()
        elif action == act_templates:
            self._on_open_templates()
        elif action == act_export:
            self._on_export_json()
        elif action == act_import:
            self._on_import_json()
        elif action == act_del:
            self._on_delete_pipeline()

    def refresh_data(self) -> None:
        """Recharge les Personas, les modèles LLM et les pipelines depuis SQLite."""
        try:
            self._cached_personas = list(PersonaModel.select().order_by(PersonaModel.name.asc()))
            self._cached_llms = list(LLMConfigModel.select().order_by(LLMConfigModel.display_name.asc()))
        except Exception as e:
            logger.warning(f"Erreur refresh_data personas/llms: {e}")
            self._cached_personas = []
            self._cached_llms = []

        # Recharger les pipelines
        self.pipeline_combo.blockSignals(True)
        self.pipeline_combo.clear()

        try:
            pipelines = list(PipelineModel.select().order_by(PipelineModel.name.asc()))
            for p in pipelines:
                self.pipeline_combo.addItem(p.name, userData=p)
        except Exception as e:
            logger.warning(f"Erreur refresh_data pipelines: {e}")

        self.pipeline_combo.blockSignals(False)

        if self.pipeline_combo.count() > 0:
            self.pipeline_combo.setCurrentIndex(0)
            self._on_pipeline_changed()
        else:
            self._current_pipeline = None
            self.current_steps.clear()
            self._render_steps()

    @Slot()
    def _on_pipeline_changed(self) -> None:
        selected_pipe: Optional[PipelineModel] = self.pipeline_combo.currentData()
        if not selected_pipe:
            self._current_pipeline = None
            self.current_steps.clear()
            self._render_steps()
            return

        self._current_pipeline = selected_pipe
        self.current_steps.clear()

        try:
            steps_models = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == selected_pipe).order_by(PipelineStepModel.step_order.asc()))
        except Exception as e:
            logger.warning(f"Erreur chargement étapes : {e}")
            steps_models = []

        for s in steps_models:
            succ_order = s.on_success_step.step_order if s.on_success_step else None
            fail_order = s.on_failure_step.step_order if s.on_failure_step else None
            cfg = {}
            raw_cfg = getattr(s, "config_data", None)
            if raw_cfg:
                try:
                    cfg = json.loads(raw_cfg)
                except Exception:
                    cfg = {}

            self.current_steps.append(
                {
                    "persona": s.persona,
                    "type": s.step_type or "LLM_PROMPT",
                    "on_success_order": succ_order,
                    "on_failure_order": fail_order,
                    "failure_behavior": s.failure_behavior or "stop",
                    "config": cfg,
                }
            )

        self._selected_step_index = 0
        self._render_steps()

    def _render_steps(self) -> None:
        """Re-génère l'affichage de la liste des étapes et met à jour l'inspecteur."""
        while self.steps_layout.count() > 1:
            item = self.steps_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    w.deleteLater()

        self._step_widgets.clear()
        total = len(self.current_steps)
        self.lbl_step_count.setText(f"{total} étape{'s' if total > 1 else ''}")
        self.lbl_pipeline_steps_badge.setText(f"{total} étape{'s' if total > 1 else ''}")

        for idx, step_data in enumerate(self.current_steps, start=1):
            is_sel = (idx - 1) == self._selected_step_index
            widget = StepItemWidget(order=idx, step_data=step_data, is_selected=is_sel)
            widget.clicked.connect(self._on_step_selected)
            widget.btn_up.clicked.connect(lambda _, i=idx - 1: self._move_step_up(i))
            widget.btn_down.clicked.connect(lambda _, i=idx - 1: self._move_step_down(i))
            widget.btn_delete.clicked.connect(lambda _, i=idx - 1: self._delete_step(i))

            self._step_widgets.append(widget)
            self.steps_layout.insertWidget(self.steps_layout.count() - 1, widget)

            # Bouton d'insertion contextuelle entre les étapes (si ce n'est pas la dernière)
            if idx < total:
                inline_btn = InlineInsertButton(insert_index=idx)
                inline_btn.clicked.connect(lambda insert_at: self._on_add_step_clicked(insert_at=insert_at))
                self.steps_layout.insertWidget(self.steps_layout.count() - 1, inline_btn)

        # Mettre à jour l'inspecteur sur l'élément actif
        if total > 0 and 0 <= self._selected_step_index < total:
            self.inspector.inspect_step(
                step_data=self.current_steps[self._selected_step_index],
                step_order=self._selected_step_index + 1,
                total_steps=total,
                personas=self._cached_personas,
                llms=self._cached_llms,
            )
        else:
            self.inspector.inspect_step(
                step_data={},
                step_order=1,
                total_steps=0,
                personas=self._cached_personas,
                llms=self._cached_llms,
            )

        self.flow_overview.render_flow(self.current_steps, active_index=self._selected_step_index)

    def _on_step_selected(self, index: int) -> None:
        if 0 <= index < len(self.current_steps):
            self._selected_step_index = index
            self._render_steps()

    def _on_inspector_step_updated(self) -> None:
        self.flow_overview.render_flow(self.current_steps, active_index=self._selected_step_index)
        if 0 <= self._selected_step_index < len(self._step_widgets):
            cur = self.current_steps[self._selected_step_index]
            persona = cur.get("persona")
            meta = STEP_TYPES_META.get(cur.get("type", "LLM_PROMPT"), STEP_TYPES_META["LLM_PROMPT"])
            title = cur.get("custom_title") or (persona.name if persona else meta["default_title"])
            self._step_widgets[self._selected_step_index].title_lbl.setText(f"<b>{self._selected_step_index + 1}.</b> {title}")

    def _move_step_up(self, index: int) -> None:
        if index > 0:
            self.current_steps[index], self.current_steps[index - 1] = self.current_steps[index - 1], self.current_steps[index]
            self._selected_step_index = index - 1
            self._render_steps()

    def _move_step_down(self, index: int) -> None:
        if index < len(self.current_steps) - 1:
            self.current_steps[index], self.current_steps[index + 1] = self.current_steps[index + 1], self.current_steps[index]
            self._selected_step_index = index + 1
            self._render_steps()

    def _delete_step(self, index: int) -> None:
        if 0 <= index < len(self.current_steps):
            del self.current_steps[index]
            if self._selected_step_index >= len(self.current_steps):
                self._selected_step_index = max(0, len(self.current_steps) - 1)
            self._render_steps()

    def add_step(self, step_payload: Dict[str, Any], insert_at: Optional[int] = None) -> None:
        """Ajoute une étape (Agent IA ou Action Système) au workflow courant."""
        stype = step_payload.get("type", "LLM_PROMPT")
        persona = step_payload.get("persona")
        meta = STEP_TYPES_META.get(stype, STEP_TYPES_META["LLM_PROMPT"])

        new_step: Dict[str, Any] = {
            "type": stype,
            "persona": persona,
            "custom_title": persona.name if persona else meta["default_title"],
            "on_success_order": None,
            "on_failure_order": None,
            "failure_behavior": "stop",
            "config": {
                "input_variable": meta.get("default_input", "text_source"),
                "output_variable": meta.get("default_output", "generated_cards"),
            },
        }
        if "config" in step_payload:
            new_step["config"].update(step_payload["config"])

        if insert_at is not None and 0 <= insert_at <= len(self.current_steps):
            self.current_steps.insert(insert_at, new_step)
            self._selected_step_index = insert_at
        else:
            self.current_steps.append(new_step)
            self._selected_step_index = len(self.current_steps) - 1

        self._render_steps()
        show_toast(self, f"Étape '{new_step['custom_title']}' ajoutée", is_error=False)

    def _on_add_step_clicked(self, insert_at: Optional[int] = None) -> None:
        """Ouvre la palette/catalogue de composants modernes pour choisir l'étape."""
        dlg = StepPickerDialog(personas=self._cached_personas, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_step_data:
            self.add_step(dlg.selected_step_data, insert_at=insert_at)

    def _on_rename_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        new_name, ok = QInputDialog.getText(self, "Renommer le pipeline", "Nouveau nom :", text=str(self._current_pipeline.name))
        if ok and new_name.strip():
            self._current_pipeline.name = new_name.strip()
            self._current_pipeline.save()
            show_toast(self, "Pipeline renommé avec succès", is_error=False)
            self.refresh_data()

    def _on_new_pipeline(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau Pipeline", "Nom du pipeline :")
        if ok and name.strip():
            try:
                p = PipelineModel.create(name=name.strip(), description="Pipeline personnalisé")
                show_toast(self, f"Pipeline '{p.name}' créé !", is_error=False)
                self.refresh_data()
                # Sélectionner le nouveau pipeline
                for i in range(self.pipeline_combo.count()):
                    if self.pipeline_combo.itemText(i) == p.name:
                        self.pipeline_combo.setCurrentIndex(i)
                        break
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le pipeline : {e}")

    def _on_clone_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        clone_name = f"{self._current_pipeline.name} (Copie)"
        try:
            new_pipe = PipelineModel.create(name=clone_name, description=self._current_pipeline.description)
            created_steps: Dict[int, PipelineStepModel] = {}
            for idx, s in enumerate(self.current_steps, start=1):
                ps = PipelineStepModel.create(
                    pipeline=new_pipe,
                    persona=s.get("persona"),
                    step_type=s.get("type", "LLM_PROMPT"),
                    step_order=idx,
                    failure_behavior=s.get("failure_behavior", "stop"),
                    config_data=json.dumps(s.get("config", {})),
                )
                created_steps[idx] = ps

            for idx, s in enumerate(self.current_steps, start=1):
                succ_idx = s.get("on_success_order")
                fail_idx = s.get("on_failure_order")
                need_update = False
                ps = created_steps[idx]
                if succ_idx and succ_idx in created_steps:
                    ps.on_success_step = created_steps[succ_idx]
                    need_update = True
                if fail_idx and fail_idx in created_steps:
                    ps.on_failure_step = created_steps[fail_idx]
                    need_update = True
                if need_update:
                    ps.save()

            show_toast(self, f"Pipeline dupliqué sous le nom '{clone_name}' !", is_error=False)
            self.refresh_data()
            for i in range(self.pipeline_combo.count()):
                if self.pipeline_combo.itemText(i) == clone_name:
                    self.pipeline_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Échec du clonage : {e}")

    def _on_delete_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        reply = QMessageBox.question(
            self,
            "Supprimer le pipeline",
            f"Voulez-vous vraiment supprimer définitivement le pipeline '{self._current_pipeline.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._current_pipeline.delete_instance(recursive=True)
                show_toast(self, "Pipeline supprimé", is_error=False)
                self.refresh_data()
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Échec de suppression : {e}")

    def _on_save_pipeline(self) -> None:
        if not self._current_pipeline:
            return

        try:
            with db.atomic():
                PipelineStepModel.delete().where(PipelineStepModel.pipeline == self._current_pipeline).execute()

                created_steps: Dict[int, PipelineStepModel] = {}
                for idx, s in enumerate(self.current_steps, start=1):
                    cfg_json = json.dumps(s.get("config", {}))
                    ps = PipelineStepModel.create(
                        pipeline=self._current_pipeline,
                        persona=s.get("persona"),
                        step_order=idx,
                        step_type=s.get("type", "LLM_PROMPT"),
                        failure_behavior=s.get("failure_behavior", "stop"),
                        config_data=cfg_json,
                    )
                    created_steps[idx] = ps

                for idx, s in enumerate(self.current_steps, start=1):
                    succ_idx = s.get("on_success_order")
                    fail_idx = s.get("on_failure_order")
                    need_update = False
                    ps = created_steps[idx]
                    if succ_idx and succ_idx in created_steps:
                        ps.on_success_step = created_steps[succ_idx]
                        need_update = True
                    if fail_idx and fail_idx in created_steps:
                        ps.on_failure_step = created_steps[fail_idx]
                        need_update = True
                    if need_update:
                        ps.save()

            show_toast(self, f"Pipeline '{self._current_pipeline.name}' sauvegardé avec succès !", is_error=False)
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Échec : {e}")

    def _on_test_single_step(self, step_data: dict) -> None:
        dlg = StepTestDialog(step_data, parent=self)
        dlg.exec()

    def _on_test_full_pipeline(self) -> None:
        if not self._current_pipeline:
            return
        dlg = PipelineRunDialog(self._current_pipeline, self.current_steps, parent=self)
        dlg.exec()

    def _on_open_templates(self) -> None:
        """Affiche la bibliothèque de modèles prédéfinis pour charger un workflow en 1 clic."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Bibliothèque de Modèles Prédéfinis")
        dlg.resize(620, 420)
        dlg.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_PRIMARY};")

        dlg_layout = QVBoxLayout(dlg)
        dlg_layout.setContentsMargins(16, 16, 16, 16)
        dlg_layout.setSpacing(12)

        lbl = QLabel("Sélectionnez un modèle de workflow à instancier :")
        lbl.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        dlg_layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_w = QWidget()
        scroll_l = QVBoxLayout(scroll_w)
        scroll_l.setSpacing(10)

        for tpl in PRESET_TEMPLATES:
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: 6px;
                    padding: 10px;
                }}
                QFrame:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            c_l = QVBoxLayout(card)
            c_l.setSpacing(4)
            lbl_t = QLabel(f"<b>{tpl['name']}</b>")
            lbl_t.setStyleSheet(f"font-size: 13px; color: {DesignTokens.TEXT_PRIMARY};")
            lbl_d = QLabel(tpl["description"])
            lbl_d.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
            lbl_d.setWordWrap(True)

            btn_use = SecondaryButton("Instancier ce Modèle")
            btn_use.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))

            def _instantiate(t=tpl):
                self._apply_preset_template(t)
                dlg.accept()

            btn_use.clicked.connect(_instantiate)

            c_l.addWidget(lbl_t)
            c_l.addWidget(lbl_d)
            c_l.addWidget(btn_use, alignment=Qt.AlignmentFlag.AlignRight)
            scroll_l.addWidget(card)

        scroll_l.addStretch()
        scroll.setWidget(scroll_w)
        dlg_layout.addWidget(scroll, 1)

        dlg.exec()

    def _apply_preset_template(self, tpl: dict) -> None:
        """Applique un modèle prédéfini sous forme d'un nouveau pipeline."""
        pipe_name = f"{tpl['name']} (Instancié)"
        try:
            new_pipe = PipelineModel.create(name=pipe_name, description=tpl["description"])
            for idx, s in enumerate(tpl["steps"], start=1):
                p_obj = self._cached_personas[0] if self._cached_personas else None
                PipelineStepModel.create(
                    pipeline=new_pipe,
                    persona=p_obj if s["type"] in ("LLM_PROMPT", "MAP_REDUCE") else None,
                    step_type=s["type"],
                    step_order=idx,
                    config_data=json.dumps(s.get("config", {})),
                )
            show_toast(self, f"Modèle '{tpl['name']}' instancié !", is_error=False)
            self.refresh_data()
            for i in range(self.pipeline_combo.count()):
                if self.pipeline_combo.itemText(i) == pipe_name:
                    self.pipeline_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Impossible d'instancier le modèle : {e}")

    def _on_export_json(self) -> None:
        if not self._current_pipeline:
            return
        data = {
            "name": self._current_pipeline.name,
            "description": self._current_pipeline.description,
            "steps": [
                {
                    "type": s.get("type", "LLM_PROMPT"),
                    "persona_name": s["persona"].name if s.get("persona") else None,
                    "custom_title": s.get("custom_title"),
                    "on_success_order": s.get("on_success_order"),
                    "on_failure_order": s.get("on_failure_order"),
                    "failure_behavior": s.get("failure_behavior", "stop"),
                    "config": s.get("config", {}),
                }
                for s in self.current_steps
            ],
        }
        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter le Pipeline en JSON", f"{self._current_pipeline.name}.json", "Fichiers JSON (*.json)")
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                show_toast(self, "Pipeline exporté en JSON avec succès !", is_error=False)
            except Exception as e:
                QMessageBox.critical(self, "Erreur d'exportation", str(e))

    def _on_import_json(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Importer un Pipeline JSON", "", "Fichiers JSON (*.json)")
        if not file_path:
            return
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            name = data.get("name", "Pipeline Importé")
            # Assurer l'unicité
            base_name = name
            cnt = 1
            while PipelineModel.get_or_none(PipelineModel.name == name):
                name = f"{base_name} ({cnt})"
                cnt += 1

            new_pipe = PipelineModel.create(name=name, description=data.get("description", "Importé"))
            for idx, s in enumerate(data.get("steps", []), start=1):
                p_match = None
                p_name = s.get("persona_name")
                if p_name:
                    p_match = PersonaModel.get_or_none(PersonaModel.name == p_name)

                PipelineStepModel.create(
                    pipeline=new_pipe,
                    persona=p_match,
                    step_type=s.get("type", "LLM_PROMPT"),
                    step_order=idx,
                    failure_behavior=s.get("failure_behavior", "stop"),
                    config_data=json.dumps(s.get("config", {})),
                )

            show_toast(self, f"Pipeline '{name}' importé avec succès !", is_error=False)
            self.refresh_data()
            for i in range(self.pipeline_combo.count()):
                if self.pipeline_combo.itemText(i) == name:
                    self.pipeline_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            QMessageBox.critical(self, "Erreur d'importation", f"Fichier JSON invalide : {e}")
