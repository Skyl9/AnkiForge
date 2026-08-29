from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PersonaModel
from ankiforge.ui.components import Badge, GlowLineEdit
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.constants import apply_pill_style
from ankiforge.utils.icon_loader import load_phosphor_icon


class StepPickerCard(QFrame):
    """Carte cliquable pour un élément dans le sélecteur d'étape."""

    clicked = Signal(dict)

    def __init__(
        self,
        payload: dict[str, Any],
        icon_name: str,
        title: str,
        subtitle: str,
        badge_text: str,
        badge_color: str,
        parent: QWidget | None = None,
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

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(22, 22)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=badge_color).pixmap(18, 18))
        layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

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

        badge = Badge(badge_text, variant="status")
        apply_pill_style(badge, badge_color)
        badge.setFixedHeight(18)
        layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.payload)
        super().mousePressEvent(event)

    def click(self) -> None:
        self.clicked.emit(self.payload)


class StepPickerDialog(QDialog):
    """Catalogue & Palette de sélection en 2 colonnes (Prompts/Agents et Actions Système)."""

    def __init__(self, personas: list[PersonaModel], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.personas = personas
        self.selected_step_data: dict[str, Any] | None = None
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

        self.edit_search = GlowLineEdit()
        self.edit_search.setPlaceholderText("Rechercher un agent, un prompt ou une action système...")
        self.edit_search.setFixedHeight(34)
        self.edit_search.textChanged.connect(self._filter_items)
        layout_main.addWidget(self.edit_search)

        cols_layout = QHBoxLayout()
        cols_layout.setSpacing(14)

        self._cards: list[tuple[StepPickerCard, str]] = []

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

        pipeline_personas = [p for p in self.personas if getattr(p, "persona_type", "pipeline") in ("pipeline", "universal", None, "")]

        if not pipeline_personas:
            lbl_no_p = QLabel("Aucun persona de pipeline configuré. Créez des agents dans l'Atelier d'Agents.")
            lbl_no_p.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-style: italic; margin-left: 6px;")
            self.col1_cards_layout.addWidget(lbl_no_p)

        for p in pipeline_personas:
            p_desc = p.system_prompt.strip().replace("\n", " ") if p.system_prompt else "Agent IA spécialisé"
            if len(p_desc) > 85:
                p_desc = p_desc[:82] + "..."
            p_type = getattr(p, "persona_type", "pipeline")
            badge_txt = "UNIVERSEL" if p_type == "universal" else "LLM"
            badge_col = "#f59e0b" if p_type == "universal" else "#8b5cf6"

            card = StepPickerCard(
                payload={"type": "LLM_PROMPT", "persona": p},
                icon_name="ph.sparkle",
                title=f"Agent : {p.name}",
                subtitle=p_desc,
                badge_text=badge_txt,
                badge_color=badge_col,
            )
            card.clicked.connect(self._on_item_selected)
            self.col1_cards_layout.addWidget(card)
            self._cards.append((card, f"{p.name} {p_desc}".lower()))

        self.col1_cards_layout.addStretch()
        scroll1.setWidget(inner1)
        col1_layout.addWidget(scroll1, 1)
        cols_layout.addWidget(col1_widget, 1)

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

    def _on_item_selected(self, payload: dict[str, Any]) -> None:
        self.selected_step_data = payload
        self.accept()


class PersonaSelectorDialog(QDialog):
    """Dialogue compact pour sélectionner un Persona ou passer en Prompt Pur."""

    def __init__(self, personas: list[PersonaModel], current_persona: PersonaModel | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.personas = personas
        self.selected_persona: PersonaModel | None = None
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

    def _on_selected(self, payload: dict[str, Any]) -> None:
        self.selected_persona = payload.get("persona")
        self.accept()
