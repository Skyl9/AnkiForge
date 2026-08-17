"""
Vue Analyse & Audit IA (AnalysisView) - 100% Natif PySide6 / Qt & Peewee ORM.
Workflow conforme : Aucun paquet par défaut -> Choix du paquet -> Clic 'Analyser ce paquet'.
"""

import logging
from typing import Dict, Optional, Any, Union, cast

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import db, DocumentModel, DocumentChunkModel, NoteChunkLinkModel
from ankiforge.services.ai.linter import (
    TokenSrsFinancialService,
)
from ankiforge.services.workers.linter_worker import LinterWorker
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.duplicate_widgets import DuplicateMatrixTable, DuplicateMergeInspector
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.components.linter_widgets import (
    KatexLivePreviewWidget,
    RetentionCurveCanvas,
    WozniakCardItemWidget,
    WozniakKpiCard,
)
from ankiforge.ui.components.panels import IdePanel
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.ui.widgets.toast import show_toast

logger = logging.getLogger(__name__)


# =====================================================================================
# ONGLET 1 : AUDIT ERGONOMIQUE WOZNIAK (WORKFLOW À LA DEMANDE)
# =====================================================================================
class AIWozniakLinterTab(QWidget):
    """Onglet d'audit ergonomique Wozniak : Aucun paquet par défaut -> Choix -> Clic Analyser."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: Optional[int] = None
        self.selected_deck_name: Optional[str] = None
        self.active_category: str = "cat-atomicite"
        self._cached_deck_results: dict[int, list] = {}  # Cache par deck_id

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header Wozniak
        header = QFrame()
        header.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        lbl_title = QLabel("Audit Ergonomique Wozniak")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.btn_deck = SecondaryButton("Sélectionner un paquet...")
        self.btn_deck.setIcon(load_phosphor_icon("folder", color=DesignTokens.TEXT_PRIMARY))
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.btn_analyze = PrimaryButton("Analyser ce paquet")
        self.btn_analyze.setIcon(load_phosphor_icon("arrows-clockwise", color="#ffffff"))
        self.btn_analyze.clicked.connect(lambda checked=False: self.refresh_audit(force=True))

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher une carte...")
        self.search_input.setFixedWidth(180)
        self.search_input.textChanged.connect(self.filter_items_by_search)

        self.score_badge = QLabel("Score : -- / 100")
        self.score_badge.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.score_badge.setStyleSheet(
            f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 3px 8px;"
        )

        self.engine_combo = QComboBox()
        self.engine_combo.setFixedWidth(220)
        self.engine_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 4px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        # Remplissage du sélecteur
        from ankiforge.database.models import LLMConfigModel

        configs = list(LLMConfigModel.select())
        if not configs:
            LLMConfigModel.create(
                display_name="Ollama (Local)",
                provider="ollama",
                model_id="qwen2.5:7b",
                context_limit=32000,
            )
            configs = list(LLMConfigModel.select())

        for c in configs:
            display_name = getattr(c, "display_name", getattr(c, "name", str(c)))
            self.engine_combo.addItem(f"⚡ {display_name}", userData=c)

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(self.btn_deck)
        h_layout.addWidget(self.engine_combo)
        h_layout.addWidget(self.btn_analyze)
        h_layout.addStretch()
        h_layout.addWidget(self.search_input)
        h_layout.addWidget(self.score_badge)
        layout.addWidget(header)

        # 2. KPI Cards Bar (Catégories interactives)
        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(10)

        self.kpi_cards: Dict[str, WozniakKpiCard] = {
            "cat-atomicite": WozniakKpiCard("cat-atomicite", "Atomicité & Listes", 0, "Sélectionnez un paquet", "#f87171", "squares-four"),
            "cat-katex": WozniakKpiCard("cat-katex", "Formules & Clarté", 0, "Sélectionnez un paquet", "#c084fc", "function"),
            "cat-interference": WozniakKpiCard("cat-interference", "Non-Interférence", 0, "Sélectionnez un paquet", DesignTokens.COLOR_BLUE, "circles-three"),
            "cat-cloze": WozniakKpiCard("cat-cloze", "Questions Univoques Q/R", 0, "Sélectionnez un paquet", DesignTokens.COLOR_YELLOW, "question"),
        }

        for _cat_id, card in self.kpi_cards.items():
            card.clicked.connect(self.on_category_kpi_clicked)
            self.kpi_layout.addWidget(card)
        layout.addLayout(self.kpi_layout)

        # 3. Main Scroll Container for Dynamic Problem Items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_content)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(12)

        # Category 3 Banner with Cloze Toggle Switch
        self.cloze_banner = QFrame()
        self.cloze_banner.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px; }}")
        cb_layout = QHBoxLayout(self.cloze_banner)

        lbl_cb = QLabel("Catégorie 3 : Suppression du Cloze & Transformation en Questions Univoques Q/R")
        lbl_cb.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.toggle_cloze = QCheckBox("Audit Cloze : Activé (Recommandé)")
        self.toggle_cloze.setChecked(True)
        self.toggle_cloze.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-weight: bold;")
        self.toggle_cloze.stateChanged.connect(self.on_cloze_toggle_changed)

        cb_layout.addWidget(lbl_cb)
        cb_layout.addStretch()
        cb_layout.addWidget(self.toggle_cloze)
        self.items_layout.addWidget(self.cloze_banner)
        self.cloze_banner.setVisible(False)

        # Conteneur dynamique des cartes items
        self.items_container = QWidget()
        self.cards_layout = QVBoxLayout(self.items_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.items_layout.addWidget(self.items_container)

        self.items_layout.addStretch()
        self.scroll_area.setWidget(self.scroll_content)
        layout.addWidget(self.scroll_area)

        self.kpi_cards["cat-atomicite"].set_active(True)
        self.show_empty_state("Veuillez choisir un paquet ci-dessus et cliquer sur 'Analyser ce paquet' pour démarrer l'audit Wozniak.")

    def show_empty_state(self, message: str) -> None:
        """Affiche un état d'attente neutre dans le conteneur principal."""
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        empty_box = QFrame()
        empty_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px dashed {DesignTokens.BORDER_COLOR}; border-radius: 8px; padding: 40px; }}")
        eb_layout = QVBoxLayout(empty_box)
        eb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon("sparkle", color=DesignTokens.TEXT_MUTED).pixmap(32, 32))
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_text = QLabel(message)
        lbl_text.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        eb_layout.addWidget(lbl_icon)
        eb_layout.addWidget(lbl_text)
        self.cards_layout.addWidget(empty_box)

    def open_deck_select_dialog(self) -> None:
        """Ouvre un dialogue de sélection de paquet."""
        self._deck_window = DeckSelectWindow(parent=self)
        self._deck_window.deck_selected.connect(self._on_deck_selected)
        self._deck_window.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.selected_deck_id = deck_id
        self.selected_deck_name = deck_name
        self.btn_deck.setText(deck_name)
        logger.info(f"Paquet sélectionné pour audit : {deck_name}")

    def on_category_kpi_clicked(self, cat_id: str) -> None:
        """Bascule activement la catégorie affichée lors du clic sur une puce KPI."""
        self.active_category = cat_id
        for c_id, card in self.kpi_cards.items():
            card.set_active(c_id == cat_id)

        self.cloze_banner.setVisible(cat_id == "cat-cloze" and self.selected_deck_id is not None)
        if self.selected_deck_id is not None:
            self.refresh_audit(force=False)

    def on_cloze_toggle_changed(self, state: int) -> None:
        """Active/désactive dynamiquement l'audit de catégorie Cloze."""
        is_enabled = state == Qt.CheckState.Checked.value
        self.toggle_cloze.setText("Audit Cloze : Activé (Recommandé)" if is_enabled else "Audit Cloze : Désactivé (Conserver Cloze)")
        if self.selected_deck_id is not None:
            self.refresh_audit(force=False)

    def refresh_audit(self, force: bool = False) -> None:
        """Exécute l'audit via IA uniquement sur demande de l'utilisateur ou depuis le cache."""
        if self.selected_deck_id is None:
            self.show_empty_state("Veuillez d'abord choisir un paquet avec le bouton 'Sélectionner un paquet...'")
            return

        if not force and self.selected_deck_id in self._cached_deck_results:
            self._on_linter_finished(self._cached_deck_results[self.selected_deck_id])
            return

        from ankiforge.database.models import CardModel, NoteModel

        # Un Note n'a pas de deck direct, on passe par ses cartes
        note_ids = [n.id for n in NoteModel.select().join(CardModel).where(CardModel.deck == self.selected_deck_id).distinct()]
        if not note_ids:
            self.show_empty_state("Aucune carte trouvée dans ce paquet.")
            return

        mode_text = "Complet (Hard)" if force else "Incrémental (Soft)"
        self.show_empty_state(f"Analyse IA {mode_text} en cours (Linter Wozniak)...")
        self.btn_analyze.setEnabled(False)

        selected_config = self.engine_combo.currentData()
        config_id = selected_config.id if selected_config else None

        # Injection du paramètre force_recheck=force
        self.worker = LinterWorker(note_ids=note_ids, llm_config_id=config_id, force_recheck=force, parent=self)
        self.worker.progress_update.connect(lambda msg: self.show_empty_state(msg))
        self.worker.error_occurred.connect(self._on_linter_error)
        self.worker.finished_processing.connect(self._on_linter_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def _on_linter_error(self, err: str) -> None:
        self.btn_analyze.setEnabled(True)
        self.show_empty_state(f"Erreur lors de l'audit IA : {err}")

    def _on_linter_finished(self, results: list) -> None:
        self.btn_analyze.setEnabled(True)
        if self.selected_deck_id is not None:
            self._cached_deck_results[self.selected_deck_id] = results

        import json

        from ankiforge.database.models import NoteModel, NoteVersionModel

        # Mapping results to our categories
        cat_atomicite_items = []
        cat_katex_items = []
        cat_interference_items = []
        cat_cloze_items = []

        for res in results:
            if res.get("pass") or res.get("pass_"):
                continue

            nid = res.get("note_id")
            if not nid:
                continue

            note = NoteModel.get_or_none(NoteModel.id == nid)
            if not note:
                continue

            active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active)
            if not active_ver:
                continue

            try:
                content = json.loads(active_ver.content)
            except Exception:
                content = {"Text": str(active_ver.content)}

            recto = content.get("Recto", content.get("Text", ""))
            verso = content.get("Verso", "")

            rule = res.get("rule_broken", "Règle Inconnue")
            reason = res.get("reason", "Pas de raison fournie.")

            raw_sug = res.get("suggestion", {})

            # Si la suggestion est une chaîne de caractères (erreur de l'IA ou double sérialisation)
            if isinstance(raw_sug, str):
                import json

                try:
                    sug = json.loads(raw_sug)
                except Exception:
                    # Fallback de survie si l'IA a juste craché du texte brut au lieu d'un JSON
                    sug = {"Recto": raw_sug, "Verso": ""}
            else:
                sug = raw_sug

            # Sécurité finale : s'assurer que c'est bien un dictionnaire
            if not isinstance(sug, dict):
                sug = {}

            item = {
                "note_id": nid,
                "title": f"Note #{nid} - Problème d'atomicité",
                "badge": "Atomicité",
                "badge_color": "#f87171",
                "rule": f"{rule}: {reason}",
                "original": {"Recto": recto, "Verso": verso},
                "proposal": sug,
                "proposal_summary": "PROPOSITION IA (MCP) :",
            }

            rule_lower = rule.lower()
            if "atomic" in rule_lower or "list" in rule_lower:
                item["badge"] = "Atomicité"
                item["badge_color"] = "#f87171"
                cat_atomicite_items.append(item)
            elif "cloze" in rule_lower or "question" in rule_lower:
                item["badge"] = "Questions Univoques"
                item["badge_color"] = "#f59e0b"
                cat_cloze_items.append(item)
            elif "context" in rule_lower or "interf" in rule_lower:
                item["badge"] = "Interférence"
                item["badge_color"] = "#3b82f6"
                cat_interference_items.append(item)
            else:
                item["badge"] = "Formulation"
                item["badge_color"] = "#c084fc"
                cat_katex_items.append(item)

        # Update KPI score based on found issues (heuristic fallback to make UI look alive)
        score_atomicite = max(0, 100 - len(cat_atomicite_items) * 7)
        score_katex = max(0, 100 - len(cat_katex_items) * 5)
        score_cloze = max(0, 100 - len(cat_cloze_items) * 6)
        score_interference = max(0, 100 - len(cat_interference_items) * 4)

        score_global = int((score_atomicite + score_katex + score_cloze + score_interference) / 4)

        categories = {
            "cat-atomicite": {"score": score_atomicite, "items": cat_atomicite_items},
            "cat-katex": {"score": score_katex, "items": cat_katex_items},
            "cat-interference": {"score": score_interference, "items": cat_interference_items},
            "cat-cloze": {"score": score_cloze, "items": cat_cloze_items},
        }

        self.score_badge.setText(f"Score : {score_global} / 100")
        self.score_badge.setStyleSheet(f"background-color: rgba(245,158,11,0.12); color: {DesignTokens.COLOR_YELLOW}; border: 1px solid rgba(245,158,11,0.3); border-radius: 4px; padding: 3px 8px;")

        # Mise à jour des KPI cards
        for cat_id, cat_data in categories.items():
            if cat_id in self.kpi_cards:
                kpi = self.kpi_cards[cat_id]
                kpi.lbl_pct.setText(f"{cat_data['score']}%")

        # Vider les cartes précédentes
        while self.cards_layout.count():
            item_widget = self.cards_layout.takeAt(0)
            widget = item_widget.widget() if item_widget is not None else None
            if widget is not None:
                widget.deleteLater()

        # Remplir dynamiquement la catégorie active
        current_cat_data = categories.get(self.active_category, {})
        from typing import Any, Dict, List

        items = cast(List[Dict[str, Any]], current_cat_data.get("items", []))

        for item_data in items:
            card_widget = WozniakCardItemWidget(item_data)
            card_widget.applied.connect(lambda nid, prop, w=card_widget: self._on_card_applied(nid, prop, w))

            if hasattr(card_widget, "ignored"):
                card_widget.ignored.connect(lambda nid, w=card_widget: self._on_card_ignored(nid, w))

            self.cards_layout.addWidget(card_widget)

            if self.active_category == "cat-katex" and "formula" in item_data:
                preview = KatexLivePreviewWidget(initial_formula=item_data["formula"])
                self.cards_layout.addWidget(preview)

    @Slot(int, dict, QWidget)
    def _on_card_applied(self, note_id: int, proposal: dict, widget_to_remove: QWidget) -> None:
        """Applique la proposition de l'IA, valide l'audit en BDD et supprime le widget."""
        import json

        from ankiforge.database.models import AuditRecordModel, NoteModel, NoteVersionModel

        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                return

            active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712

            if not active_ver:
                return

            with db.atomic():
                try:
                    content = json.loads(active_ver.content)
                except Exception:
                    content = {}

                if "Front" in proposal and "Recto" not in proposal:
                    proposal["Recto"] = proposal.pop("Front")
                if "Back" in proposal and "Verso" not in proposal:
                    proposal["Verso"] = proposal.pop("Back")

                for k, v in proposal.items():
                    content[k] = v

                # 1. Création de la nouvelle version
                new_version = note.add_version(new_content_dict=content, source="Linter AI")

                # 2. Nettoyage de l'ancien audit et validation du nouveau
                AuditRecordModel.delete().where(AuditRecordModel.note == note).execute()
                AuditRecordModel.create(note=note, note_version=new_version, is_compliant=True, rule_broken=None, reason="Corrigé manuellement via Linter")

            logger.info(f"Proposition appliquée avec succès pour la note #{note_id}")

            # 3. Disparition de l'interface
            widget_to_remove.deleteLater()

        except Exception as e:
            logger.error(f"Erreur lors de l'application de la proposition pour la note #{note_id}: {e}")

    @Slot(int, QWidget)
    def _on_card_ignored(self, note_id: int, widget_to_remove: QWidget) -> None:
        """Marque la carte comme conforme (faux positif) pour qu'elle soit ignorée au prochain Soft Analysis."""
        from ankiforge.database.models import AuditRecordModel, NoteModel, NoteVersionModel

        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                return
            active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
            if not active_ver:
                return

            with db.atomic():
                # On efface l'ancien record d'échec
                AuditRecordModel.delete().where(AuditRecordModel.note == note, AuditRecordModel.note_version == active_ver).execute()

                # On crée un record de succès
                AuditRecordModel.create(note=note, note_version=active_ver, is_compliant=True, reason="Ignoré par l'utilisateur (Faux positif)")

            widget_to_remove.deleteLater()
            logger.info(f"Note #{note_id} ignorée et marquée comme conforme.")

        except Exception as e:
            logger.error(f"Erreur lors de l'ignorance de la note #{note_id}: {e}")

    def filter_items_by_search(self, query: str) -> None:
        """Filtre dynamiquement les cartes affichées selon le texte de recherche."""
        q = query.lower().strip()
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w:
                if not q:
                    w.setVisible(True)
                else:
                    text = w.findChildren(QLabel)[0].text().lower() if w.findChildren(QLabel) else ""
                    w.setVisible(q in text)


# =====================================================================================
# ONGLET 2 : DIAGNOSTIC & COUVERTURE COGNITIVE (SMART COVERAGE)
# =====================================================================================


class ClickableChunkWidget(QFrame):
    """Un paragraphe du document, cliquable, avec un indicateur visuel de couverture."""

    clicked = Signal(int)  # Renvoie l'ID du Chunk

    def __init__(self, chunk_id: int, text: str, status: str = "unprofiled", parent=None):
        super().__init__(parent)
        self.chunk_id = chunk_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Statut visuel (Bordure gauche)
        color_map = {
            "unprofiled": "transparent",
            "gap": DesignTokens.COLOR_YELLOW,  # Des facettes manquent
            "covered": DesignTokens.COLOR_GREEN,  # Toutes les facettes sont couvertes
            "hallucination": DesignTokens.COLOR_RED,
        }
        border_color = color_map.get(status, "transparent")

        self.setStyleSheet(f"""
            ClickableChunkWidget {{
                background-color: {DesignTokens.BG_MAIN};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-left: 3px solid {border_color};
                border-radius: 4px;
                margin-bottom: 4px;
            }}
            ClickableChunkWidget:hover {{
                background-color: {DesignTokens.BG_HOVER};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_text = QLabel(text)
        self.lbl_text.setWordWrap(True)
        self.lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; line-height: 1.4;")
        layout.addWidget(self.lbl_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chunk_id)
        super().mousePressEvent(event)


class DocumentInspectorPanel(QWidget):
    """Panneau pour inspecter l'audit et la couverture détaillée d'un document."""

    back_requested = Signal()
    request_navigation = Signal(str, object)

    def __init__(self, doc_or_id: Union[int, DocumentModel], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        if isinstance(doc_or_id, DocumentModel):
            self.doc = doc_or_id
            self.doc_id = doc_or_id.id
        else:
            self.doc_id = doc_or_id
            self.doc = DocumentModel.get_or_none(DocumentModel.id == doc_or_id)

        if not self.doc:
            return

        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header du Document
        header_layout = QHBoxLayout()
        btn_back = SecondaryButton("← Retour aux documents")
        btn_back.clicked.connect(self.back_requested.emit)

        title_to_display = self.doc.original_media.original_name if self.doc.original_media else self.doc.title
        header_lbl = QLabel(f"📄 Audit Document : {title_to_display}")
        header_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        header_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.lbl_doc_summary = QLabel("📊 Couverture : 0%")
        self.lbl_doc_summary.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_doc_summary.setStyleSheet(f"background-color: rgba(16,185,129,0.12); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 4px 8px;")

        self.btn_fill_orphans = PrimaryButton("⚡ Combler toutes les sections orphelines")
        self.btn_fill_orphans.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
        self.btn_fill_orphans.clicked.connect(self._on_fill_all_orphans)

        self.btn_reindex = SecondaryButton("🔄 Ré-indexer FAISS")
        self.btn_reindex.clicked.connect(self._on_reindex_faiss)

        header_layout.addWidget(btn_back)
        header_layout.addSpacing(10)
        header_layout.addWidget(header_lbl)
        header_layout.addWidget(self.lbl_doc_summary)
        header_layout.addStretch()
        header_layout.addWidget(self.btn_fill_orphans)
        header_layout.addWidget(self.btn_reindex)

        layout.addLayout(header_layout)

        # 2. Splitter 2 Volets
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- VOLET GAUCHE : Sommaire & Visualiseur du Texte ---
        left_panel = QFrame()
        left_panel.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl_toc = QLabel("📑 Sommaire & Sections du Document")
        lbl_toc.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_toc.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 6px;")
        left_layout.addWidget(lbl_toc)

        self.chapters_list = QListWidget()
        self.chapters_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self.chapters_list.itemClicked.connect(self._on_chapter_item_clicked)
        left_layout.addWidget(self.chapters_list, 1)

        lbl_text_title = QLabel("📖 Extrait de la Section Sélectionnée")
        lbl_text_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        lbl_text_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; padding-top: 4px;")
        left_layout.addWidget(lbl_text_title)

        self.text_preview = QTextBrowser()
        self.text_preview.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
                padding: 10px;
                font-size: 13px;
                line-height: 1.5;
            }}
        """)
        left_layout.addWidget(self.text_preview, 1)

        # --- VOLET DROIT : Inspecteur de Cartes Anki ---
        right_panel = QFrame()
        right_panel.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(8)

        lbl_cards_title = QLabel("🔍 Cartes Anki Liées & Action de Forge")
        lbl_cards_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        lbl_cards_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 6px;")
        right_layout.addWidget(lbl_cards_title)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setStyleSheet("background: transparent;")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.cards_scroll.setWidget(self.cards_container)
        right_layout.addWidget(self.cards_scroll, 1)

        self.splitter.addWidget(left_panel)
        self.splitter.addWidget(right_panel)
        self.splitter.setStretchFactor(0, 5)
        self.splitter.setStretchFactor(1, 5)
        layout.addWidget(self.splitter, 1)

        self.load_chunks()

    def load_chunks(self) -> None:
        self.chapters_list.clear()
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))

        if not chunks:
            self.lbl_doc_summary.setText("⚪ Non indexé (0 section)")
            self.text_preview.setHtml("<p style='color: #9ca3af;'>Ce document n'a pas encore été fragmenté. Cliquez sur 'Ré-indexer FAISS'.</p>")
            return

        covered_count = 0
        for chunk in chunks:
            card_count = NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk).count()
            is_covered = card_count > 0
            if is_covered:
                covered_count += 1
                badge = "🟢"
                status_text = f"✅ {card_count} carte(s)"
            else:
                badge = "⚠️"
                status_text = "0 carte (Trou)"

            title_str = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
            item_text = f"{badge} {title_str}  ·  {status_text}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, chunk.id)
            self.chapters_list.addItem(item)

        total_chunks = len(chunks)
        percent = (covered_count / total_chunks * 100) if total_chunks > 0 else 0
        orphans = total_chunks - covered_count
        total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == self.doc).count()

        self.lbl_doc_summary.setText(f"📊 Couverture : {percent:.0f}% ({covered_count}/{total_chunks} sections) · {total_cards} cartes · {orphans} trou(s)")

        if self.chapters_list.count() > 0:
            self.chapters_list.setCurrentRow(0)
            first_id = self.chapters_list.item(0).data(Qt.ItemDataRole.UserRole)
            self.inspect_chunk(first_id)

    def _on_chapter_item_clicked(self, item: QListWidgetItem) -> None:
        chunk_id = item.data(Qt.ItemDataRole.UserRole)
        if chunk_id:
            self.inspect_chunk(chunk_id)

    def inspect_chunk(self, chunk_id: int) -> None:
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return

        header_title = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
        safe_content = chunk.content.replace("\n", "<br>")
        self.text_preview.setHtml(f"<h4>📌 {header_title}</h4><hr style='border: 1px solid {DesignTokens.BORDER_COLOR};'/><p>{safe_content}</p>")

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        links = list(NoteChunkLinkModel.select().where(NoteChunkLinkModel.chunk == chunk))

        if not links:
            box = QFrame()
            box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 6px; border: 1px dashed {DesignTokens.COLOR_YELLOW}; padding: 16px; }}")
            b_layout = QVBoxLayout(box)
            b_layout.setSpacing(10)

            lbl_warn = QLabel("⚠️ Trou de cours détecté : Aucune flashcard n'a encore été générée pour cette section.")
            lbl_warn.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-weight: bold;")
            lbl_warn.setWordWrap(True)
            b_layout.addWidget(lbl_warn)

            lbl_desc = QLabel("Forgez des cartes ciblées pour combler ce manque et garantir la complétion de votre apprentissage.")
            lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
            lbl_desc.setWordWrap(True)
            b_layout.addWidget(lbl_desc)

            btn_gen = PrimaryButton("⚡ Forger cette section maintenant")
            btn_gen.setIcon(load_phosphor_icon("ph.sparkle", color="white"))
            btn_gen.clicked.connect(lambda: self._on_forge_chunk(chunk.id))
            b_layout.addWidget(btn_gen)

            self.cards_layout.addWidget(box)
        else:
            lbl_cnt = QLabel(f"✅ {len(links)} carte(s) Anki forgée(s) depuis cette section :")
            lbl_cnt.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-weight: bold; margin-bottom: 4px;")
            self.cards_layout.addWidget(lbl_cnt)

            for link in links:
                note = link.note
                card_box = QFrame()
                card_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_INPUT}; border-radius: 6px; border: 1px solid {DesignTokens.BORDER_COLOR}; padding: 10px; }}")
                c_layout = QVBoxLayout(card_box)
                c_layout.setContentsMargins(8, 8, 8, 8)
                c_layout.setSpacing(6)

                import json
                from ankiforge.database.models import CardModel, NoteVersionModel

                fields = {}
                if note:
                    active_ver = NoteVersionModel.get_or_none(
                        NoteVersionModel.note == note,
                        NoteVersionModel.is_active == True,  # noqa: E712
                    )
                    if active_ver and active_ver.content:
                        try:
                            fields = json.loads(active_ver.content)
                        except Exception as e:
                            logger.debug("Erreur parsing active_ver content: %s", e)

                    if not fields and hasattr(note, "fields_data") and getattr(note, "fields_data", None):
                        try:
                            fields = json.loads(note.fields_data)
                        except Exception as e:
                            logger.debug("Erreur parsing fields_data: %s", e)

                front = fields.get("Front") or fields.get("Recto") or fields.get("Question") or "Carte Anki"
                back = fields.get("Back") or fields.get("Verso") or fields.get("Answer") or ""

                deck_name = "Général"
                if note:
                    card = CardModel.get_or_none(CardModel.note == note)
                    if card and card.deck:
                        deck_name = card.deck.name
                    elif hasattr(note, "deck") and getattr(note, "deck", None):
                        deck_name = getattr(note.deck, "name", "Général")

                top_row = QHBoxLayout()
                lbl_deck = QLabel(f"📁 {deck_name}")
                lbl_deck.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
                top_row.addWidget(lbl_deck)
                top_row.addStretch()
                c_layout.addLayout(top_row)

                lbl_front = QLabel(f"Q : {front}")
                lbl_front.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
                lbl_front.setWordWrap(True)
                c_layout.addWidget(lbl_front)

                if back:
                    lbl_back = QLabel(f"R : {back}")
                    lbl_back.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
                    lbl_back.setWordWrap(True)
                    c_layout.addWidget(lbl_back)

                if link.is_hallucinating:
                    lbl_bad = QLabel("🔴 Alerte : Incohérence sémantique détectée face au document source")
                    lbl_bad.setStyleSheet(f"color: {DesignTokens.COLOR_RED}; font-size: 10px; font-weight: bold;")
                    c_layout.addWidget(lbl_bad)

                self.cards_layout.addWidget(card_box)

            btn_more = SecondaryButton("+ Générer plus de cartes pour ce chapitre")
            btn_more.clicked.connect(lambda: self._on_forge_chunk(chunk.id))
            self.cards_layout.addWidget(btn_more)

    def _on_forge_chunk(self, chunk_id: int) -> None:
        chunk = DocumentChunkModel.get_or_none(DocumentChunkModel.id == chunk_id)
        if not chunk:
            return
        doc_title = self.doc.title if self.doc else "Document"
        section_name = chunk.heading_path or (f"Page {chunk.page_number}" if chunk.page_number else f"Section #{chunk.chunk_index + 1}")
        self.request_navigation.emit(
            "creation",
            {
                "text_source": chunk.content,
                "source_title": f"{doc_title} - {section_name}",
                "chunk_id": chunk.id,
            },
        )

    def _on_fill_all_orphans(self) -> None:
        """Trouve la première section orpheline pour la forger dans l'Usine de Création."""
        chunks = list(DocumentChunkModel.select().where(DocumentChunkModel.document == self.doc).order_by(DocumentChunkModel.chunk_index))
        linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == self.doc)}

        orphan = next((c for c in chunks if c.id not in linked_chunk_ids), None)
        if orphan:
            self._on_forge_chunk(orphan.id)
        else:
            show_toast(self, "Toutes les sections de ce cours sont déjà couvertes !")

    def _on_reindex_faiss(self) -> None:
        from ankiforge.services.workers.coverage_worker import CoverageWorker

        show_toast(self, "Indexation FAISS et structuration en cours...")
        self._coverage_worker = CoverageWorker(self.doc.id)
        self._coverage_worker.finished_processing.connect(self._on_coverage_finished)
        self._coverage_worker.start()

    def _on_coverage_finished(self) -> None:
        show_toast(self, "Indexation FAISS terminée avec succès !")
        self.load_chunks()


class AISourcesDiagnosticTab(QWidget):
    """Onglet de diagnostic et santé des documents : synthèse globale et inspection détaillée."""

    request_navigation = Signal(str, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QStackedWidget

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # PAGE 0 : Grille des Documents
        self.page_grid = QWidget()
        grid_page_layout = QVBoxLayout(self.page_grid)
        grid_page_layout.setContentsMargins(12, 12, 12, 12)
        grid_page_layout.setSpacing(10)
        self.stack.addWidget(self.page_grid)

        # PAGE 1 : Inspecteur de Document
        self.page_inspector = QWidget()
        inspector_layout = QVBoxLayout(self.page_inspector)
        inspector_layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.page_inspector)

        # 1. Barre de KPIs globaux de la Forge
        kpi_header = QFrame()
        kpi_header.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        kpi_layout = QHBoxLayout(kpi_header)
        kpi_layout.setContentsMargins(12, 10, 12, 10)
        kpi_layout.setSpacing(16)

        self.lbl_kpi_docs = QLabel("📚 Documents : 0")
        self.lbl_kpi_docs.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.lbl_kpi_docs.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")

        self.lbl_kpi_coverage = QLabel("🎯 Couverture Moyenne : 0%")
        self.lbl_kpi_coverage.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.lbl_kpi_coverage.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN};")

        self.lbl_kpi_orphans = QLabel("⚠️ Sections Orphelines : 0")
        self.lbl_kpi_orphans.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.lbl_kpi_orphans.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW};")

        self.lbl_kpi_cards = QLabel("⚡ Cartes Forgées : 0")
        self.lbl_kpi_cards.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.lbl_kpi_cards.setStyleSheet(f"color: {DesignTokens.COLOR_PURPLE};")

        kpi_layout.addWidget(self.lbl_kpi_docs)
        kpi_layout.addWidget(self.lbl_kpi_coverage)
        kpi_layout.addWidget(self.lbl_kpi_orphans)
        kpi_layout.addWidget(self.lbl_kpi_cards)
        kpi_layout.addStretch()

        grid_page_layout.addWidget(kpi_header)

        # 2. Barre de Filtres et Recherche
        filter_bar = QFrame()
        filter_bar.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        f_layout = QHBoxLayout(filter_bar)
        f_layout.setContentsMargins(12, 6, 12, 6)
        f_layout.setSpacing(8)

        # Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher un document...")
        self.search_input.setFixedWidth(200)
        self.search_input.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 4px 8px; border-radius: 4px;"
        )
        self.search_input.textChanged.connect(self.refresh_data)
        f_layout.addWidget(self.search_input)

        lbl_filter = QLabel("Format :")
        lbl_filter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-weight: bold; font-size: 11px;")
        f_layout.addWidget(lbl_filter)

        self.btn_filter_all = SecondaryButton("Tous")
        self.btn_filter_pdf = SecondaryButton(".PDF")
        self.btn_filter_md = SecondaryButton(".MD")
        self.btn_filter_web = SecondaryButton("Web")
        self.current_format_filter = "all"

        for b, fmt in [(self.btn_filter_all, "all"), (self.btn_filter_pdf, "pdf"), (self.btn_filter_md, "md"), (self.btn_filter_web, "web")]:
            b.setFixedHeight(24)
            b.clicked.connect(lambda _, f=fmt: self._set_format_filter(f))
            f_layout.addWidget(b)

        f_layout.addSpacing(8)
        lbl_status = QLabel("Statut :")
        lbl_status.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-weight: bold; font-size: 11px;")
        f_layout.addWidget(lbl_status)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Tous les statuts", "🟢 Couverts à 100%", "⚠️ Trous à forger (<100%)", "⚪ Non indexés"])
        self.status_combo.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 3px 6px; border-radius: 4px;"
        )
        self.status_combo.currentIndexChanged.connect(self.refresh_data)
        f_layout.addWidget(self.status_combo)

        f_layout.addStretch()

        lbl_sort = QLabel("Trier par :")
        lbl_sort.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-weight: bold; font-size: 11px;")
        f_layout.addWidget(lbl_sort)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(
            [
                "Taux de couverture ↓",
                "Taux de couverture ↑",
                "Nombre de cartes ↓",
                "Sections orphelines ↓",
                "Nom du fichier (A-Z)",
                "Date d'importation ↓",
            ]
        )
        self.sort_combo.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 3px 6px; border-radius: 4px;"
        )
        self.sort_combo.currentIndexChanged.connect(self.refresh_data)
        f_layout.addWidget(self.sort_combo)

        grid_page_layout.addWidget(filter_bar)

        # 3. Grille des Cartes de Documents
        from PySide6.QtWidgets import QScrollArea, QGridLayout

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setStyleSheet("background: transparent;")

        self.grid_content = QWidget()
        self.grid_content.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_content)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.grid_content)
        grid_page_layout.addWidget(self.scroll_area, 1)

        self.refresh_data()

    def _set_format_filter(self, fmt: str) -> None:
        self.current_format_filter = fmt
        self.refresh_data()

    def refresh_data(self) -> None:
        from ankiforge.ui.components.linter_widgets import SourceDiagnosticCardWidget

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        docs = list(DocumentModel.select())
        search_text = self.search_input.text().strip().lower()

        docs_data = []
        total_forge_chunks = 0
        total_forge_covered = 0
        total_forge_orphans = 0
        total_forge_cards = 0

        for doc in docs:
            ext = (doc.file_type or "md").lower()
            title = doc.original_media.original_name if doc.original_media else doc.title

            chunks = list(doc.chunks)
            total_chunks = len(chunks)
            linked_chunk_ids = {link.chunk_id for link in NoteChunkLinkModel.select(NoteChunkLinkModel.chunk_id).join(DocumentChunkModel).where(DocumentChunkModel.document == doc)}
            covered_chunks = len(linked_chunk_ids)
            orphan_chunks = max(0, total_chunks - covered_chunks)
            total_cards = NoteChunkLinkModel.select().join(DocumentChunkModel).where(DocumentChunkModel.document == doc).count()
            coverage_pct = (covered_chunks / total_chunks * 100) if total_chunks > 0 else 0.0
            density = (total_cards / total_chunks) if total_chunks > 0 else 0.0
            is_indexed = total_chunks > 0
            word_count = getattr(doc, "word_count", None) or (len(doc.content.split()) if doc.content else 0)

            total_forge_chunks += total_chunks
            total_forge_covered += covered_chunks
            total_forge_orphans += orphan_chunks
            total_forge_cards += total_cards

            if self.current_format_filter != "all":
                if self.current_format_filter == "pdf" and ext != "pdf":
                    continue
                if self.current_format_filter == "md" and ext not in ("md", "markdown"):
                    continue
                if self.current_format_filter == "web" and ext not in ("web", "yt", "youtube"):
                    continue

            if search_text and search_text not in title.lower():
                continue

            status_idx = self.status_combo.currentIndex()
            if status_idx == 1 and (not is_indexed or coverage_pct < 100):
                continue
            elif status_idx == 2 and (not is_indexed or orphan_chunks == 0):
                continue
            elif status_idx == 3 and is_indexed:
                continue

            docs_data.append(
                {
                    "doc_id": doc.id,
                    "extension": ext,
                    "title": title,
                    "coverage_pct": coverage_pct,
                    "is_indexed": is_indexed,
                    "total_chunks": total_chunks,
                    "covered_chunks": covered_chunks,
                    "orphan_chunks": orphan_chunks,
                    "total_cards": total_cards,
                    "density": density,
                    "word_count": word_count,
                    "created_at": getattr(doc, "created_at", None),
                }
            )

        self.lbl_kpi_docs.setText(f"📚 Documents : {len(docs)}")
        avg_cov = (total_forge_covered / total_forge_chunks * 100) if total_forge_chunks > 0 else 0.0
        self.lbl_kpi_coverage.setText(f"🎯 Couverture Moyenne : {avg_cov:.0f}%")
        self.lbl_kpi_orphans.setText(f"⚠️ Sections Orphelines : {total_forge_orphans}")
        self.lbl_kpi_cards.setText(f"⚡ Cartes Forgées : {total_forge_cards}")

        sort_idx = self.sort_combo.currentIndex()
        if sort_idx == 0:
            docs_data.sort(key=lambda d: d["coverage_pct"], reverse=True)
        elif sort_idx == 1:
            docs_data.sort(key=lambda d: d["coverage_pct"])
        elif sort_idx == 2:
            docs_data.sort(key=lambda d: d["total_cards"], reverse=True)
        elif sort_idx == 3:
            docs_data.sort(key=lambda d: d["orphan_chunks"], reverse=True)
        elif sort_idx == 4:
            docs_data.sort(key=lambda d: d["title"].lower())
        elif sort_idx == 5:
            docs_data.sort(key=lambda d: str(d["created_at"]), reverse=True)

        row = 0
        col = 0
        for data in docs_data:
            card = SourceDiagnosticCardWidget(data)
            card.inspect_requested.connect(self.show_inspector)
            self.grid_layout.addWidget(card, row, col)
            col += 1
            if col > 2:
                col = 0
                row += 1

    def show_inspector(self, doc_id: int) -> None:
        while self.page_inspector.layout().count():
            item = self.page_inspector.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        panel = DocumentInspectorPanel(doc_id, self)
        panel.back_requested.connect(lambda: self.stack.setCurrentIndex(0))
        panel.request_navigation.connect(self.request_navigation)
        self.page_inspector.layout().addWidget(panel)
        self.stack.setCurrentIndex(1)


# =====================================================================================
# ONGLET 3 : SUIVI FINANCIER JETONS IA & SRS (FSRS-4.5)
# =====================================================================================
class AITokensSrsTab(QWidget):
    """Onglet de suivi financier des jetons et de santé d'apprentissage FSRS-4.5."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.current_deck_id: Optional[int] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header (Bouton Analyser placé à droite)
        header = QFrame()
        header.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; }}")
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(12, 8, 12, 8)

        lbl_title = QLabel("Suivi Financier Jetons IA & Rétention SRS (FSRS-4.5)")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.btn_deck = SecondaryButton("L'ensemble des paquets")
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.lbl_spent = QLabel("Dépenses Cumulées : 0.000 $")
        self.lbl_spent.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        self.lbl_spent.setStyleSheet(f"background-color: rgba(16,185,129,0.12); color: {DesignTokens.COLOR_GREEN}; border: 1px solid rgba(16,185,129,0.3); border-radius: 4px; padding: 3px 8px;")

        self.lbl_cost = QLabel("Coût moyen / carte : 0.00000 $")
        self.lbl_cost.setFont(QFont(DesignTokens.FONT_MAIN, 10))
        self.lbl_cost.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

        btn_analyze = PrimaryButton("Analyser ce paquet")
        btn_analyze.setStyleSheet(f"background-color: {DesignTokens.COLOR_GREEN}; border: none; border-radius: 4px;")
        btn_analyze.clicked.connect(self.refresh_stats)

        h_layout.addWidget(lbl_title)
        h_layout.addWidget(self.btn_deck)
        h_layout.addWidget(self.lbl_spent)
        h_layout.addStretch()
        h_layout.addWidget(self.lbl_cost)
        h_layout.addWidget(btn_analyze)
        layout.addWidget(header)

        # 2. 4 KPI Summary Cards
        self.kpi_grid = QHBoxLayout()
        self.kpi_grid.setSpacing(10)
        layout.addLayout(self.kpi_grid)

        # 3. Main 2-Column Grid (Expenses vs SRS Curve)
        main_grid = QHBoxLayout()
        main_grid.setSpacing(10)

        # Left Column : AI Provider Expenses
        self.left_col = QFrame()
        self.left_col.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px; }}")
        self.l_layout = QVBoxLayout(self.left_col)
        self.l_layout.setSpacing(8)

        l_title = QLabel("Dépenses par Fournisseur IA & Modèle")
        l_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        l_title.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px; border-top: none; border-left: none; border-right: none; background: transparent;"  # noqa: E501
        )
        self.l_layout.addWidget(l_title)

        main_grid.addWidget(self.left_col)

        # Right Column : SRS FSRS-4.5 & Curve Canvas
        right_col = QFrame()
        right_col.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px; }}")
        r_layout = QVBoxLayout(right_col)
        r_layout.setSpacing(8)

        # Equilibre box
        eq_box = QFrame()
        eq_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px; }}")
        eq_layout = QVBoxLayout(eq_box)
        eq_layout.setSpacing(8)

        eq_title = QLabel("Équilibre & Maturité SRS (FSRS-4.5)")
        eq_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        eq_title.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px; border-top: none; border-left: none; border-right: none; background: transparent;"  # noqa: E501
        )
        eq_layout.addWidget(eq_title)

        self.eq_grid = QHBoxLayout()
        self.eq_grid.setSpacing(8)
        eq_layout.addLayout(self.eq_grid)
        r_layout.addWidget(eq_box)

        r_title = QLabel("Courbe Théorique de la Rétention (Forgetting Curve FSRS-4.5)")
        r_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        r_title.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px; border-top: none; border-left: none; border-right: none; background: transparent;"  # noqa: E501
        )
        r_layout.addWidget(r_title)

        canvas = RetentionCurveCanvas()
        r_layout.addWidget(canvas)

        btn_opt = PrimaryButton("Optimiser FSRS-4.5 (ML Local)")
        r_layout.addWidget(btn_opt)

        r_layout.addStretch()
        main_grid.addWidget(right_col)

        layout.addLayout(main_grid)
        self.refresh_stats()

    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                elif item.layout() is not None:
                    self._clear_layout(item.layout())

    def refresh_stats(self):
        summary = TokenSrsFinancialService.get_financial_summary(self.current_deck_id)

        self.lbl_spent.setText(f"Dépenses Cumulées : {summary['total_spent_usd']:.4f} $")
        avg_cost = summary["total_spent_usd"] / max(summary["total_cards"], 1)
        self.lbl_cost.setText(f"Coût moyen / carte : {avg_cost:.5f} $")

        self._clear_layout(self.kpi_grid)
        self._clear_layout(self.eq_grid)

        eq_data = []
        tot = summary["total_cards"]
        if tot > 0:
            eq_data.append(("NOUVELLES", str(summary["maturity_distribution"]["new"]), f"{summary['maturity_distribution']['new'] / tot * 100:.1f}% du paquet", DesignTokens.COLOR_BLUE))
            eq_data.append(
                ("APPRENTISSAGE", str(summary["maturity_distribution"]["learning"]), f"{summary['maturity_distribution']['learning'] / tot * 100:.1f}% du paquet", DesignTokens.COLOR_YELLOW)
            )
            eq_data.append(("MÛRES (>21j)", str(summary["maturity_distribution"]["maturing"]), f"{summary['maturity_distribution']['maturing'] / tot * 100:.1f}% (Ancrées)", "#c084fc"))
        else:
            eq_data = [("NOUVELLES", "0", "0% du paquet", DesignTokens.COLOR_BLUE), ("APPRENTISSAGE", "0", "0% du paquet", DesignTokens.COLOR_YELLOW), ("MÛRES (>21j)", "0", "0% (Ancrées)", "#c084fc")]

        for lbl, val, sub, col in eq_data:
            bx = QFrame()
            bx.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px; }}")
            b_ly = QVBoxLayout(bx)
            b_ly.setAlignment(Qt.AlignmentFlag.AlignCenter)
            t = QLabel(lbl)
            t.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            t.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            v = QLabel(val)
            v.setFont(QFont(DesignTokens.FONT_MAIN, 14, QFont.Weight.Bold))
            v.setStyleSheet(f"color: {col}; border: none; background: transparent;")
            s = QLabel(sub)
            s.setFont(QFont(DesignTokens.FONT_MAIN, 8))
            s.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
            b_ly.addWidget(t, 0, Qt.AlignmentFlag.AlignCenter)
            b_ly.addWidget(v, 0, Qt.AlignmentFlag.AlignCenter)
            b_ly.addWidget(s, 0, Qt.AlignmentFlag.AlignCenter)
            self.eq_grid.addWidget(bx)
        mat_pct = "0%" if summary["total_cards"] == 0 else f"{summary['maturing_cards'] / summary['total_cards'] * 100:.1f}%"
        cards_data = [
            ("Budget Jetons Consommé", f"{summary['total_spent_usd']:.4f} $", f"{summary['tokens_consumed']} jetons consommés", "Optimal", DesignTokens.COLOR_GREEN),
            (
                "Rétention Théorique FSRS",
                f"{summary['fsrs_retention_pct']}%",
                f"Cible paramétrée : {summary['target_retention_pct']}%",
                f"+{float(summary['fsrs_retention_pct']) - float(summary['target_retention_pct']):.1f}%",
                DesignTokens.ACCENT_PRIMARY,
            ),
            ("Cartes Mûres (>21j)", f"{summary['maturing_cards']} / {summary['total_cards']}", f"{mat_pct} de la collection", "Ancrage Fort", "#c084fc"),
            ("Charge Révisions Estimée", f"{summary['daily_workload_cards']} cartes / jour", f"Temps estimé : ~{summary['daily_workload_minutes']} min", "Très Léger", DesignTokens.COLOR_BLUE),
        ]

        for title, val, sub_left, sub_right, color in cards_data:
            box = QFrame()
            box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px; }}")
            b_layout = QVBoxLayout(box)
            b_layout.setSpacing(4)

            t_lbl = QLabel(title)
            t_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            t_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")

            v_lbl = QLabel(val)
            v_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 16, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {color}; border: none; background: transparent;")

            s_layout = QHBoxLayout()
            s_layout.setContentsMargins(0, 0, 0, 0)

            s_left = QLabel(sub_left)
            s_left.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            s_left.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")

            s_right = QLabel(sub_right)
            s_right.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            s_right.setStyleSheet(f"color: {color}; border: none; background: transparent;")

            s_layout.addWidget(s_left)
            s_layout.addStretch()
            s_layout.addWidget(s_right)

            b_layout.addWidget(t_lbl)
            b_layout.addWidget(v_lbl)
            b_layout.addLayout(s_layout)
            self.kpi_grid.addWidget(box)

        # Refresh models
        while self.l_layout.count() > 1:  # Keep title
            item = self.l_layout.takeAt(1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

        for m in summary["models"]:
            m_box = QFrame()
            m_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px; }}")
            mb_layout = QVBoxLayout(m_box)
            mb_layout.setSpacing(2)

            r1 = QHBoxLayout()
            name = QLabel(m["name"])
            name.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            name.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")
            cost = QLabel(f"{m['cost_usd']:.4f} $")
            cost.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
            cost.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")
            r1.addWidget(name)
            r1.addStretch()
            r1.addWidget(cost)
            mb_layout.addLayout(r1)

            det = QLabel(f"Volume : {m['tokens']} jetons ({m['pct']:.1f}% des appels)")
            det.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            det.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; border: none; background: transparent;")
            mb_layout.addWidget(det)
            self.l_layout.insertWidget(self.l_layout.count(), m_box)

        # Ajouter "Répartition par Type de Tâche IA"
        task_box = QFrame()
        task_box.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px; }}")
        tb_layout = QVBoxLayout(task_box)
        tb_layout.setSpacing(10)

        tb_title = QLabel("Répartition par Type de Tâche IA")
        tb_title.setFont(QFont(DesignTokens.FONT_MAIN, 10, QFont.Weight.Bold))
        tb_title.setStyleSheet(
            f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 6px; border-top: none; border-left: none; border-right: none; background: transparent;"  # noqa: E501
        )
        tb_layout.addWidget(tb_title)

        tasks = []
        for t in summary.get("tasks_breakdown", []):
            tasks.append((t["task"], f"{t['cost_usd']:.4f} $ ({t['pct']:.1f}%)", t["pct"], t.get("color", DesignTokens.COLOR_BLUE)))

        for t_name, t_val, t_pct, t_col in tasks:
            t_row = QFrame()
            t_row.setStyleSheet("border: none; background: transparent;")
            t_r_layout = QVBoxLayout(t_row)
            t_r_layout.setContentsMargins(0, 0, 0, 0)
            t_r_layout.setSpacing(3)

            lbl_row = QHBoxLayout()
            lbl_row.setContentsMargins(0, 0, 0, 0)
            n_lbl = QLabel(t_name)
            n_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9))
            n_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
            v_lbl = QLabel(t_val)
            v_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 9, QFont.Weight.Bold))
            v_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; border: none; background: transparent;")
            lbl_row.addWidget(n_lbl)
            lbl_row.addStretch()
            lbl_row.addWidget(v_lbl)

            t_r_layout.addLayout(lbl_row)

            p_bg = QFrame()
            p_bg.setFixedHeight(4)
            p_bg.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_MAIN}; border-radius: 2px; }}")
            p_ly = QHBoxLayout(p_bg)
            p_ly.setContentsMargins(0, 0, 0, 0)
            p_ly.setSpacing(0)
            p_fg = QFrame()
            p_fg.setStyleSheet(f".QFrame {{ background-color: {t_col}; border-radius: 2px; }}")
            p_ly.addWidget(p_fg, stretch=t_pct)
            p_ly.addStretch(100 - t_pct)

            t_r_layout.addWidget(p_bg)
            tb_layout.addWidget(t_row)

        self.l_layout.insertWidget(self.l_layout.count(), task_box)

        self.l_layout.addStretch()

    def open_deck_select_dialog(self) -> None:
        from ankiforge.ui.components.deck_select_window import DeckSelectWindow

        self._deck_modal = DeckSelectWindow(parent=self)
        self._deck_modal.deck_selected.connect(self._on_deck_selected)
        self._deck_modal.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.current_deck_id = deck_id
        self.btn_deck.setText(deck_name)
        self.refresh_stats()


# =====================================================================================
# ONGLET 5 : FUSIONS & DOUBLONS
# =====================================================================================
class AIDuplicatesMergeTab(QWidget):
    """Onglet de gestion des fusions et faux doublons."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: Optional[int] = None
        self.conflicts: list = []
        from ankiforge.services.workers.duplicate_worker import DuplicateWorker

        self.worker: Optional[DuplicateWorker] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        # 1. Matrice des doublons (Upper)
        self.matrix_table = DuplicateMatrixTable()
        layout.addWidget(self.matrix_table, stretch=1)

        # 2. Inspecteur de fusion (Bottom)
        self.merge_inspector = DuplicateMergeInspector()
        self.merge_inspector.hide()
        layout.addWidget(self.merge_inspector, stretch=1)

        # Connexions
        self.matrix_table.btn_deck.clicked.connect(self.open_deck_select_dialog)
        self.matrix_table.btn_reanalyze.clicked.connect(self.run_duplicate_scan)
        self.matrix_table.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        self.merge_inspector.merge_requested.connect(self.on_merge_requested)
        self.merge_inspector.ignore_requested.connect(self.on_ignore_requested)

    def open_deck_select_dialog(self) -> None:
        from ankiforge.ui.components.deck_select_window import DeckSelectWindow

        self._deck_dialog = DeckSelectWindow(parent=self)
        self._deck_dialog.deck_selected.connect(self._on_deck_selected)
        self._deck_dialog.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.selected_deck_id = deck_id
        self.matrix_table.btn_deck.setText(deck_name)
        self.run_duplicate_scan()
        if hasattr(self, "_deck_dialog") and self._deck_dialog:
            self._deck_dialog.close()

    def run_duplicate_scan(self) -> None:
        if self.selected_deck_id is None:
            return

        self.matrix_table.btn_reanalyze.setEnabled(False)
        self.matrix_table.btn_reanalyze.setText("Recherche...")
        self.matrix_table.table.setRowCount(0)

        from ankiforge.services.workers.duplicate_worker import DuplicateWorker

        self.worker = DuplicateWorker(deck_id=self.selected_deck_id, parent=self)
        self.worker.finished_processing.connect(self.on_scan_finished)
        self.worker.error_occurred.connect(self.on_scan_error)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()

    def on_scan_finished(self, conflicts: list) -> None:
        self.matrix_table.btn_reanalyze.setEnabled(True)
        self.matrix_table.btn_reanalyze.setText("Relancer l'analyse")
        self.conflicts = conflicts

        # Update badge
        from PySide6.QtWidgets import QLabel

        for child in self.matrix_table.findChildren(QLabel):
            if "paires à examiner" in child.text() or "0" in child.text():
                child.setText(f"{len(conflicts)} paires à examiner")

        self.matrix_table.table.setRowCount(0)
        for idx, (note_a, content_a, note_b, content_b, sim) in enumerate(conflicts):
            row_data = {
                "idx": idx,
                "note_a": note_a,
                "content_a": content_a,
                "note_b": note_b,
                "content_b": content_b,
                "sim": sim,
            }
            self.matrix_table.add_row(note_a, content_a, note_b, content_b, sim, row_data)

    def on_scan_error(self, err: str) -> None:
        self.matrix_table.btn_reanalyze.setEnabled(True)
        self.matrix_table.btn_reanalyze.setText("Relancer l'analyse")
        logger.error(f"Duplicate scan error: {err}")

    def on_table_selection_changed(self) -> None:
        selected = self.matrix_table.table.selectedItems()
        if not selected:
            self.merge_inspector.hide()
            return

        row = selected[0].row()
        item = self.matrix_table.table.item(row, 2)
        if not item:
            self.merge_inspector.hide()
            return

        row_data = item.data(Qt.ItemDataRole.UserRole)
        if not row_data:
            self.merge_inspector.hide()
            return

        self.merge_inspector.load_conflict(row_data)
        self.merge_inspector.show()

    def on_merge_requested(self, note_keep, note_del, merged_content) -> None:
        # Business logic for merging
        # 1. Update note_keep's active version content
        # 2. Delete note_del
        import json

        from ankiforge.database.models import NoteVersionModel

        try:
            with db.atomic():
                # Créer une nouvelle version pour note_keep
                active_ver = NoteVersionModel.get_or_none(note=note_keep, is_active=True)
                if active_ver:
                    active_ver.is_active = False
                    active_ver.save()
                    NoteVersionModel.create(
                        note=note_keep, version_number=active_ver.version_number + 1, content=json.dumps(merged_content), is_active=True, change_reason="Fusion avec doublon", author_type="human"
                    )
                # Supprimer la note dupliquée (note_del)
                note_del.delete_instance(recursive=True)

            # Remove row from table
            self.remove_current_conflict()
        except Exception as e:
            logger.error(f"Erreur fusion: {e}", exc_info=True)

    def on_ignore_requested(self, note_a, note_b) -> None:
        from ankiforge.database.models import IgnoredDuplicateModel

        try:
            id_1, id_2 = min(note_a.id, note_b.id), max(note_a.id, note_b.id)
            IgnoredDuplicateModel.get_or_create(note_a_id=id_1, note_b_id=id_2)
            self.remove_current_conflict()
        except Exception as e:
            logger.error(f"Erreur ignore: {e}", exc_info=True)

    def remove_current_conflict(self):
        selected = self.matrix_table.table.selectedItems()
        if selected:
            row = selected[0].row()
            self.matrix_table.table.removeRow(row)
            self.merge_inspector.current_conflict = None
            self.merge_inspector.lbl_title_a.setText("CARTE #1")
            self.merge_inspector.lbl_title_b.setText("CARTE #2")
            self.merge_inspector.lbl_content_a.setText("...")
            self.merge_inspector.lbl_content_b.setText("...")
            self.merge_inspector.lbl_merged.setText("...")

            # Update badge
            from PySide6.QtWidgets import QLabel

            for child in self.matrix_table.findChildren(QLabel):
                if "paires à examiner" in child.text() or "0" in child.text():
                    child.setText(f"{self.matrix_table.table.rowCount()} paires à examiner")


# =====================================================================================
# VUE PRINCIPALE : ANALYSISVIEW (CONTENEUR AVEC TAB BAR ET STACKED WIDGET)
# =====================================================================================
class AnalysisView(QWidget):
    """Vue Principale Analyse & Audit IA avec barre d'onglets JetBrains-style."""

    request_navigation = Signal(str, object)

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Utilisation de IdePanel (Onglets et StackedWidget intégrés)
        self.main_panel = IdePanel(detachable=True, parent=self)

        self.tab_wozniak = AIWozniakLinterTab()
        self.tab_sources = AISourcesDiagnosticTab()
        self.tab_tokens = AITokensSrsTab()
        self.tab_duplicates = AIDuplicatesMergeTab()

        self.tab_sources.request_navigation.connect(self.request_navigation)

        self.main_panel.add_tab("Audit && Linter Wozniak", self.tab_wozniak, icon_name="sparkle")
        self.main_panel.add_tab("Documents", self.tab_sources, icon_name="file-text")
        self.main_panel.add_tab("Jetons && SRS", self.tab_tokens, icon_name="currency-dollar")
        self.main_panel.add_tab("Fusions && Doublons", self.tab_duplicates, icon_name="git-merge")

        # Bouton de paramètres ajouté au header
        btn_settings = IconButton("gear", "Paramètres de l'Analyse", 24)
        btn_settings.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #2d313a;
            }
        """)
        self.main_panel.add_header_widget(btn_settings)

        layout.addWidget(self.main_panel)
