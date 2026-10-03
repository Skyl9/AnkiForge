"""
Bandeau de traçabilité documentaire pour la vue d'Édition (DocumentSourceBadge).
Fournit un affichage responsive et résistant au rétrécissement liant une carte à son document source.
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components.elided_label import ElidedLabel
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class DocumentSourceBadge(QFrame):
    """Bandeau responsive de traçabilité liant la carte éditée à son document source.

    Structure responsive sur deux niveaux :
    - Ligne 1 : Icône document + titre de la source avec élision dynamique (`ElidedLabel`)
      et bouton d'action « Voir le cours ➔ » ancré à droite avec taille minimale garantie.
    - Ligne 2 : Icône flèche coudée + fil d'Ariane / section / page (`ElidedLabel`),
      laissant respirer les longs intitulés sans jamais expulser le bouton d'action.
    """

    request_navigation = Signal(str, object)

    def __init__(
        self,
        doc_id: int | Any,
        doc_title: str,
        heading: str | None = None,
        resolution: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.doc_id = doc_id
        self.doc_title = doc_title or "Document"
        self.heading = heading or ""
        self.resolution = resolution

        self.setObjectName("documentSourceBadge")
        self._init_ui()

    def _init_ui(self) -> None:
        self.setStyleSheet(f"""
            QFrame#documentSourceBadge {{
                background-color: {DesignTokens.COLOR_BLUE_BG};
                border: 1px solid {DesignTokens.COLOR_BLUE_BORDER};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                margin-bottom: 6px;
            }}
        """)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 3, 4, 3)
        root_layout.setSpacing(2)

        # Ligne 1 : Icône, Titre source élidé et Bouton de navigation
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        self.ico_doc = QLabel()
        self.ico_doc.setPixmap(load_phosphor_icon("ph.file-text", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        self.ico_doc.setStyleSheet("border: none; background: transparent;")
        self.ico_doc.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        header_layout.addWidget(self.ico_doc)

        self.lbl_title = ElidedLabel(f"Source : {self.doc_title}")
        self.lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE_TEXT}; border: none; background: transparent;")

        tooltip_parts = [f"Document source : {self.doc_title}"]
        if self.heading:
            tooltip_parts.append(f"Emplacement : {self.heading}")
        if self.resolution:
            tooltip_parts.append(f"Résolution : {self.resolution}")
        full_tooltip = "\n".join(tooltip_parts)
        self.lbl_title.setToolTip(full_tooltip)
        header_layout.addWidget(self.lbl_title, 1)

        self.btn_go_doc = QPushButton("Voir le cours ➔")
        self.btn_go_doc.setObjectName("sourceBadgeNavBtn")
        self.btn_go_doc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_go_doc.setAccessibleName("Voir le document source")
        self.btn_go_doc.setAccessibleDescription(f"Ouvrir le cours '{self.doc_title}' dans la vue Documents")
        self.btn_go_doc.setToolTip(f"Ouvrir '{self.doc_title}' dans la vue Documents")

        # Taille minimale garantie pour empêcher toute expulsion ou tronquage hors champ
        fm = self.btn_go_doc.fontMetrics()
        btn_text_w = fm.horizontalAdvance("Voir le cours ➔")
        min_btn_w = max(110, btn_text_w + 14)
        self.btn_go_doc.setMinimumWidth(min_btn_w)
        self.btn_go_doc.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self.btn_go_doc.setStyleSheet(f"""
            QPushButton#sourceBadgeNavBtn {{
                background-color: transparent;
                color: {DesignTokens.COLOR_BLUE};
                font-family: {DesignTokens.FONT_MAIN};
                font-size: 10px;
                font-weight: bold;
                border: none;
                text-decoration: underline;
                padding: 0px 4px;
            }}
            QPushButton#sourceBadgeNavBtn:hover {{
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QPushButton#sourceBadgeNavBtn:focus {{
                outline: none;
                color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.btn_go_doc.clicked.connect(self._on_navigate_clicked)
        header_layout.addWidget(self.btn_go_doc)

        root_layout.addLayout(header_layout)

        # Ligne 2 : Fil d'Ariane / Section / Page (si disponible)
        if self.heading:
            breadcrumb_layout = QHBoxLayout()
            # Décalage de 20px pour aligner le fil d'Ariane verticalement sous le titre (après icône 14px + espacement 6px)
            breadcrumb_layout.setContentsMargins(20, 0, 0, 0)
            breadcrumb_layout.setSpacing(4)

            self.ico_sub: QLabel | None = QLabel()
            self.ico_sub.setPixmap(load_phosphor_icon("ph.arrow-elbow-down-right", color=DesignTokens.COLOR_BLUE).pixmap(12, 12))
            self.ico_sub.setStyleSheet("border: none; background: transparent;")
            self.ico_sub.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            breadcrumb_layout.addWidget(self.ico_sub)

            self.lbl_heading: ElidedLabel | None = ElidedLabel(self.heading)
            self.lbl_heading.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            self.lbl_heading.setStyleSheet(f"color: {DesignTokens.COLOR_BLUE_TEXT}; border: none; background: transparent;")
            self.lbl_heading.setToolTip(f"Section : {self.heading}")
            breadcrumb_layout.addWidget(self.lbl_heading, 1)

            root_layout.addLayout(breadcrumb_layout)
        else:
            self.ico_sub = None
            self.lbl_heading = None

    def _on_navigate_clicked(self) -> None:
        """Émet le signal de navigation vers la vue Documents avec l'ID du document."""
        logger.debug("Navigation vers le document source ID=%s demandée depuis DocumentSourceBadge", self.doc_id)
        self.request_navigation.emit("documents", {"doc_id": self.doc_id})

    @property
    def lbl_src(self) -> ElidedLabel:
        """Alias rétrocompatible pour le label de titre."""
        return self.lbl_title

    @property
    def ico_src(self) -> QLabel:
        """Alias rétrocompatible pour l'icône de document."""
        return self.ico_doc
