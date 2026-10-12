"""Modal pédagogique expliquant le rôle et la valeur du moteur de pipelines DAG.

Répond à une question d'affordance : « à quoi sert le DAG, et à quoi sert de le tester ? ».
Le contenu est volontairement court, en `tr()` (ADR 0013) et adossé au comportement réel du
`PipelineOrchestrator` (branchements, garde-fous, reprise) pour ne jamais décrire un
comportement que le code n'a pas.

Les libellés sont des littéraux passés directement à ``self.tr()`` afin d'être captés par
``pyside6-lupdate`` : aucune chaîne affichée n'est assemblée à l'avance.
"""

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import Badge, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.pipelines_view.constants import STEP_TYPES_META
from ankiforge.utils.icon_loader import load_phosphor_icon

#: Clés des sections pédagogiques, dans l'ordre d'affichage. Exposées pour les tests.
DAG_HELP_SECTION_KEYS: tuple[str, ...] = (
    "purpose",
    "branching",
    "guardrails",
    "resume",
    "testing",
)


class DagHelpDialog(QDialog):
    """Modal d'aide expliquant le rôle du DAG et la valeur de son test/exécution."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.section_cards: list[QFrame] = []
        self.section_keys: list[str] = []
        self.step_type_badges: list[Badge] = []
        self.setWindowTitle(self.tr("À quoi sert le moteur de pipelines DAG ?"))
        self.resize(680, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QDialog QLabel {{
                background: transparent;
            }}
        """)
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # ── En-tête ───────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(10)

        lbl_icon = QLabel()
        lbl_icon.setFixedSize(24, 24)
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setPixmap(load_phosphor_icon("ph.git-branch", color=DesignTokens.ACCENT_PRIMARY).pixmap(22, 22))
        header_row.addWidget(lbl_icon, alignment=Qt.AlignmentFlag.AlignVCenter)

        lbl_title = QLabel(self.tr("À quoi sert le moteur de pipelines DAG ?"))
        lbl_title.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        header_row.addWidget(lbl_title, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_row.addStretch()
        main_layout.addLayout(header_row)

        lbl_intro = QLabel(
            self.tr(
                "Un pipeline DAG enchaîne des étapes d'IA et de traitement documentaire en un "
                "workflow reproductible. Voici ce que le moteur apporte — et pourquoi le tester "
                "avant de le lancer est payant."
            )
        )
        lbl_intro.setWordWrap(True)
        lbl_intro.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px;")
        main_layout.addWidget(lbl_intro)

        # ── Les 6 types d'étapes (matière adossée à STEP_TYPES_META) ──────────
        types_row = QHBoxLayout()
        types_row.setSpacing(8)
        lbl_types = QLabel(self.tr("Types d'étapes :"))
        lbl_types.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        types_row.addWidget(lbl_types, alignment=Qt.AlignmentFlag.AlignVCenter)

        for meta in STEP_TYPES_META.values():
            badge = Badge(meta["label"], variant=meta["badge_variant"])
            badge.setToolTip(meta["default_title"])
            self.step_type_badges.append(badge)
            types_row.addWidget(badge, alignment=Qt.AlignmentFlag.AlignVCenter)
        types_row.addStretch()
        main_layout.addLayout(types_row)

        # ── Sections pédagogiques ─────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

        cards_container = QWidget()
        cards_container.setStyleSheet("background: transparent;")
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(10)

        for section in self._build_sections():
            card = self._build_section_card(section)
            self.section_cards.append(card)
            self.section_keys.append(section["key"])
            cards_layout.addWidget(card)
        cards_layout.addStretch()
        scroll.setWidget(cards_container)
        main_layout.addWidget(scroll, 1)

        # ── Pied de page ──────────────────────────────────────────────────────
        footer_row = QHBoxLayout()
        footer_row.addStretch()
        btn_close = SecondaryButton(self.tr("Fermer"))
        btn_close.clicked.connect(self.accept)
        footer_row.addWidget(btn_close)
        main_layout.addLayout(footer_row)

    def _build_sections(self) -> list[dict[str, Any]]:
        """Matière pédagogique : chaque libellé est un littéral soumis à ``self.tr()``."""
        return [
            {
                "key": "purpose",
                "icon": "ph.git-branch",
                "title": self.tr("Un pipeline est une chaîne d'étapes"),
                "points": [
                    self.tr("Chaque étape reçoit des variables produites en amont et en produit de nouvelles pour la suivante."),
                    self.tr("Le graphe est orienté acyclique : l'ordre d'exécution reste déterministe et reproductible."),
                    self.tr("Six types d'étapes composent le workflow : agent IA, recherche RAG, génération parallèle, pause humaine, outil Python et synthèse audio."),
                ],
            },
            {
                "key": "branching",
                "icon": "ph.arrows-split",
                "title": self.tr("Des branchements conditionnels"),
                "points": [
                    self.tr("Une étape peut sauter vers une autre selon son succès (on_success_step)."),
                    self.tr("En cas d'échec, on choisit le comportement : arrêter le pipeline (défaut), continuer malgré l'erreur, ou router vers une étape de secours (on_failure_step)."),
                ],
            },
            {
                "key": "guardrails",
                "icon": "ph.shield-check",
                "title": self.tr("Des garde-fous anti-dérapage"),
                "points": [
                    self.tr("Limite d'exécutions par étape : une boucle qui se répète est détectée puis arrêtée par le moteur."),
                    self.tr("Budget de tokens : lorsqu'un plafond est configuré, l'exécution est interrompue si le volume de tokens est dépassé."),
                    self.tr("Linter du graphe : le badge de santé du flux signale en amont une variable d'entrée jamais produite."),
                ],
            },
            {
                "key": "resume",
                "icon": "ph.clock-counter-clockwise",
                "title": self.tr("Une reprise après interruption"),
                "points": [
                    self.tr("Chaque exécution est persistée : l'état des variables et l'étape courante sont conservés même après une fermeture ou un plantage."),
                    self.tr("La reprise (resume_run) repart de l'étape courante enregistrée, sans rejouer les étapes déjà terminées."),
                ],
            },
            {
                "key": "testing",
                "icon": "ph.flask",
                "title": self.tr("Pourquoi tester avant de lancer pour de vrai"),
                "points": [
                    self.tr(
                        "Tester une étape (fournisseur factice) prévisualise le prompt résolu et une réponse simulée, sans aucun appel réel : idéal pour déboguer un gabarit avant de payer des tokens."
                    ),
                    self.tr("Tester le DAG exécute réellement le pipeline sur un texte d'exemple et journalise chaque étape : on localise l'étape fautive avant de le lancer sur un vrai document."),
                    self.tr("Le badge de santé du flux (DAG Valide / alertes) contrôle en amont les variables et les branchements, avant même d'exécuter."),
                ],
            },
        ]

    def _build_section_card(self, section: dict[str, Any]) -> QFrame:
        card = QFrame()
        card.setObjectName("DagHelpSection")
        card.setStyleSheet(f"""
            QFrame#DagHelpSection {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#DagHelpSection QLabel {{
                background: transparent;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        head_row = QHBoxLayout()
        head_row.setSpacing(8)

        lbl_ico = QLabel()
        lbl_ico.setFixedSize(20, 20)
        lbl_ico.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ico.setPixmap(load_phosphor_icon(section["icon"], color=DesignTokens.ACCENT_PRIMARY).pixmap(18, 18))
        head_row.addWidget(lbl_ico, alignment=Qt.AlignmentFlag.AlignVCenter)

        lbl_title = QLabel(section["title"])
        lbl_title.setStyleSheet(f"font-size: 12.5px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        head_row.addWidget(lbl_title, alignment=Qt.AlignmentFlag.AlignVCenter)
        head_row.addStretch()
        card_layout.addLayout(head_row)

        for point in section["points"]:
            point_row = QHBoxLayout()
            point_row.setSpacing(8)

            lbl_bullet = QLabel()
            lbl_bullet.setFixedSize(12, 12)
            lbl_bullet.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            lbl_bullet.setPixmap(load_phosphor_icon("ph.circle", color=DesignTokens.ACCENT_PRIMARY).pixmap(7, 7))
            point_row.addWidget(lbl_bullet, alignment=Qt.AlignmentFlag.AlignTop)

            lbl_point = QLabel(point)
            lbl_point.setWordWrap(True)
            lbl_point.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px;")
            point_row.addWidget(lbl_point, 1)
            card_layout.addLayout(point_row)

        return card


__all__ = ["DagHelpDialog", "DAG_HELP_SECTION_KEYS"]
