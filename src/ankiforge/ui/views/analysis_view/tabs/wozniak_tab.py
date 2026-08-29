import json
import logging
from typing import Any, Dict, List, Optional, cast

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    AuditRecordModel,
    LLMConfigModel,
    LinterRuleModel,
    NoteModel,
    NoteVersionModel,
    db,
    seed_default_linter_rules,
)
from ankiforge.services.ai.linter import normalize_linter_suggestion
from ankiforge.services.workers.linter_worker import LinterWorker
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.components.linter_rules_dialog import LinterRulesManagerDialog
from ankiforge.ui.components.linter_widgets import (
    KatexLivePreviewWidget,
    WozniakCardItemWidget,
    WozniakHubWidget,
    WozniakKpiCard,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class AIWozniakLinterTab(QWidget):
    """Onglet d'audit ergonomique Wozniak avec support complet des catégories dynamiques et gestion des règles."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.selected_deck_id: Optional[int] = None
        self.selected_deck_name: Optional[str] = None
        self.active_category: str = "cat-atomicite"
        self._cached_deck_results: dict[int, list] = {}
        self._cached_categories_data: dict[str, dict] = {}
        self.kpi_cards: Dict[str, WozniakKpiCard] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header Wozniak (2 Lignes aérées et responsives)
        header = QFrame()
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        h_outer_layout = QVBoxLayout(header)
        h_outer_layout.setContentsMargins(12, 10, 12, 10)
        h_outer_layout.setSpacing(8)

        # Ligne 1 : Titre + Sélecteur de Paquet + Moteur IA + Boutons Action + Score
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        lbl_ico = QLabel()
        lbl_ico.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_BLUE, weight="fill").pixmap(18, 18))
        lbl_ico.setStyleSheet("border: none; background: transparent;")

        lbl_title = QLabel("Audit Wozniak")
        lbl_title.setFont(QFont(DesignTokens.FONT_MAIN, 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        self.btn_deck = SecondaryButton("Choisir un paquet...")
        self.btn_deck.setIcon(load_phosphor_icon("ph.folder-open", color=DesignTokens.TEXT_PRIMARY))
        self.btn_deck.clicked.connect(self.open_deck_select_dialog)

        self.engine_combo = QComboBox()
        self.engine_combo.setMinimumWidth(150)
        self.engine_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.engine_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 8px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

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
            self.engine_combo.addItem(f"{display_name}", userData=c)

        self.btn_rules = SecondaryButton("Règles")
        self.btn_rules.setIcon(load_phosphor_icon("ph.sliders", color=DesignTokens.TEXT_PRIMARY))
        self.btn_rules.clicked.connect(self.open_rules_dialog)

        self.btn_analyze = PrimaryButton("Lancer l'audit")
        self.btn_analyze.setIcon(load_phosphor_icon("ph.arrows-clockwise", color="#ffffff"))
        self.btn_analyze.clicked.connect(lambda checked=False: self.refresh_audit(force=True))

        self.score_badge = QLabel("Score : --")
        self.score_badge.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        self.score_badge.setStyleSheet(
            f"background-color: {DesignTokens.BG_MAIN}; color: {DesignTokens.TEXT_MUTED}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 9999px; padding: 4px 12px;"
        )

        row1.addWidget(lbl_ico)
        row1.addWidget(lbl_title)
        row1.addSpacing(4)
        row1.addWidget(self.btn_deck)
        row1.addWidget(self.engine_combo)
        row1.addStretch()
        row1.addWidget(self.btn_rules)
        row1.addWidget(self.btn_analyze)
        row1.addWidget(self.score_badge)
        h_outer_layout.addLayout(row1)

        # Ligne 2 : Recherche & Statistiques
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.search_input = GlowLineEdit()
        self.search_input.setPlaceholderText("Rechercher une carte, un mot-clé ou une anomalie...")
        self.search_input.setMinimumWidth(260)
        self.search_input.textChanged.connect(self.filter_items_by_search)

        self.lbl_status_summary = QLabel("Aucun paquet analysé")
        self.lbl_status_summary.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")

        row2.addWidget(self.search_input)
        row2.addStretch()
        row2.addWidget(self.lbl_status_summary)
        h_outer_layout.addLayout(row2)

        layout.addWidget(header)

        # 2. KPI Cards Bar
        self.kpi_layout = QHBoxLayout()
        self.kpi_layout.setSpacing(10)
        layout.addLayout(self.kpi_layout)
        self.load_categories()

        # 3. Main Scroll Container for Dynamic Problem Items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content = QWidget()
        self.items_layout = QVBoxLayout(self.scroll_content)
        self.items_layout.setContentsMargins(0, 0, 0, 0)
        self.items_layout.setSpacing(12)

        # Category Banner with Cloze Toggle Switch
        self.cloze_banner = QFrame()
        self.cloze_banner.setStyleSheet(f".QFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px; }}")
        cb_layout = QHBoxLayout(self.cloze_banner)

        lbl_cb = QLabel("Catégorie Cloze : Conversion en Questions Univoques Q/R")
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

        self.show_empty_state()

    def load_categories(self) -> None:
        """Charge dynamiquement les catégories actives depuis la base de données LinterRuleModel."""
        seed_default_linter_rules()

        while self.kpi_layout.count():
            item = self.kpi_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()

        self.kpi_cards.clear()
        rules = list(LinterRuleModel.select().order_by(LinterRuleModel.category, LinterRuleModel.name))
        if not rules:
            seed_default_linter_rules()
            rules = list(LinterRuleModel.select().order_by(LinterRuleModel.category, LinterRuleModel.name))

        short_titles = {
            "cat-atomicite": "Atomicité",
            "cat-cloze": "Cloze & Univoque",
            "cat-univoque": "Questions Univoques",
            "cat-interference": "Désambiguïsation",
            "cat-katex": "Formules KaTeX",
        }

        seen_cats = set()
        for r in rules:
            cat_id = r.category or "cat-atomicite"
            if cat_id in seen_cats:
                continue
            seen_cats.add(cat_id)
            title = short_titles.get(cat_id, r.category_label or r.name)
            card = WozniakKpiCard(
                cat_id=cat_id,
                title=title,
                pct=100,
                subtitle="En attente",
                color=r.color or DesignTokens.COLOR_RED,
                icon_name=r.icon_name or "ph.squares-four",
                is_pending=True,
            )
            card.clicked.connect(self.on_category_kpi_clicked)
            self.kpi_cards[cat_id] = card
            self.kpi_layout.addWidget(card)

        if self.active_category not in self.kpi_cards and self.kpi_cards:
            self.active_category = next(iter(self.kpi_cards.keys()))

        if self.active_category in self.kpi_cards:
            self.kpi_cards[self.active_category].set_active(True)

    def open_rules_dialog(self) -> None:
        dialog = LinterRulesManagerDialog(parent=self)
        dialog.rules_updated.connect(self._on_rules_config_updated)
        dialog.exec()

    def _on_rules_config_updated(self) -> None:
        self.load_categories()
        if self.selected_deck_id is not None:
            self.refresh_audit(force=False)

    def show_empty_state(self, message: str = "") -> None:
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        if self.selected_deck_id is None and not message:
            hub = WozniakHubWidget(parent=self)
            hub.select_deck_requested.connect(self.open_deck_select_dialog)
            self.cards_layout.addWidget(hub)
            return

        empty_box = QFrame()
        empty_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px dashed {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 30px;
            }}
        """)
        eb_layout = QVBoxLayout(empty_box)
        eb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        eb_layout.setSpacing(8)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.COLOR_BLUE).pixmap(32, 32))
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setStyleSheet("border: none; background: transparent;")

        lbl_text = QLabel(message or "Veuillez choisir un paquet ci-dessus et cliquer sur 'Analyser ce paquet' pour démarrer l'audit Wozniak.")
        lbl_text.setFont(QFont(DesignTokens.FONT_MAIN, 11))
        lbl_text.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; border: none; background: transparent;")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        eb_layout.addWidget(lbl_icon)
        eb_layout.addWidget(lbl_text)
        self.cards_layout.addWidget(empty_box)

    def open_deck_select_dialog(self) -> None:
        self._deck_window = DeckSelectWindow(parent=self)
        self._deck_window.deck_selected.connect(self._on_deck_selected)
        self._deck_window.show()

    def _on_deck_selected(self, deck_id: int, deck_name: str) -> None:
        self.selected_deck_id = deck_id
        self.selected_deck_name = deck_name
        self.btn_deck.setText(deck_name)
        self.lbl_status_summary.setText(f"Paquet actif : {deck_name} • Prêt pour l'audit")
        logger.info("Paquet sélectionné pour audit : %s", deck_name)
        self.show_empty_state(f"Paquet '{deck_name}' sélectionné. Cliquez sur 'Analyser ce paquet' pour lancer le linter Wozniak.")

    def on_category_kpi_clicked(self, cat_id: str) -> None:
        self.active_category = cat_id
        for c_id, card in self.kpi_cards.items():
            card.set_active(c_id == cat_id)

        self.cloze_banner.setVisible(cat_id == "cat-cloze" and self.selected_deck_id is not None)
        if self.selected_deck_id is not None:
            self._render_active_category_items()

    def on_cloze_toggle_changed(self, state: int) -> None:
        is_enabled = state == Qt.CheckState.Checked.value
        self.toggle_cloze.setText("Audit Cloze : Activé (Recommandé)" if is_enabled else "Audit Cloze : Désactivé (Conserver Cloze)")
        if self.selected_deck_id is not None:
            self.refresh_audit(force=False)

    def refresh_audit(self, force: bool = False) -> None:
        if self.selected_deck_id is None:
            self.show_empty_state("Veuillez d'abord choisir un paquet avec le bouton 'Sélectionner un paquet...'")
            return

        if not force and self.selected_deck_id in self._cached_deck_results:
            self._on_linter_finished(self._cached_deck_results[self.selected_deck_id])
            return

        from ankiforge.database.models import CardModel, NoteModel

        note_ids = [n.id for n in NoteModel.select().join(CardModel).where(CardModel.deck == self.selected_deck_id).distinct()]
        if not note_ids:
            self.show_empty_state("Aucune carte trouvée dans ce paquet.")
            return

        mode_text = "Complet (Hard)" if force else "Incrémental (Soft)"
        self.show_empty_state(f"Analyse IA {mode_text} en cours (Linter Wozniak)...")
        self.btn_analyze.setEnabled(False)

        selected_config = self.engine_combo.currentData()
        config_id = selected_config.id if selected_config else None

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

        categories_dict: Dict[str, Dict[str, Any]] = {cat_id: {"score": 100, "items": []} for cat_id in self.kpi_cards}
        rules_map = {r.name.lower(): r for r in LinterRuleModel.select()}

        for res in results:
            if res.get("pass") or res.get("pass_"):
                continue

            nid = res.get("note_id")
            if not nid:
                continue

            note = NoteModel.get_or_none(NoteModel.id == nid)
            if not note:
                continue

            active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
            if not active_ver:
                continue

            content = {}
            try:
                content = json.loads(active_ver.content)
            except Exception:
                content = {"Recto": str(active_ver.content), "Verso": ""}

            recto = content.get("Recto") or content.get("Front") or content.get("Texte") or content.get("Text") or ""
            verso = content.get("Verso") or content.get("Back") or ""
            extra = content.get("Champ Annexe Extra") or content.get("Extra") or content.get("Remarques extra") or ""

            rule_name = res.get("rule_broken", "Règle Wozniak")
            reason = res.get("reason", "Problème ergonomique détecté.")

            normalized_sug = normalize_linter_suggestion(res.get("suggestion"), original_content=content, rule_name=rule_name)

            cat_id = res.get("category")
            if not cat_id or cat_id not in categories_dict:
                matched = rules_map.get(rule_name.lower())
                if matched and matched.category in categories_dict:
                    cat_id = matched.category
                else:
                    rl = rule_name.lower()
                    if "atomic" in rl or "list" in rl:
                        cat_id = "cat-atomicite"
                    elif "katex" in rl or "formule" in rl or "math" in rl:
                        cat_id = "cat-katex"
                    elif "cloze" in rl or "trou" in rl or "question" in rl:
                        cat_id = "cat-cloze"
                    elif "interf" in rl or "contexte" in rl:
                        cat_id = "cat-interference"
                    else:
                        cat_id = next(iter(categories_dict.keys())) if categories_dict else "cat-atomicite"

            if cat_id not in categories_dict:
                categories_dict[cat_id] = {"score": 100, "items": []}

            item = {
                "note_id": nid,
                "title": f"Note #{nid} · {recto[:35]}...",
                "badge": rule_name,
                "badge_color": self.kpi_cards[cat_id].color if cat_id in self.kpi_cards else "#f87171",
                "rule": f"{rule_name}: {reason}",
                "original": {"NoteType": note.note_type.name if note.note_type else "AnkiForge-Basic", "Recto": recto, "Verso": verso, "Champ Annexe Extra": extra, "Tags": note.tags or "#general"},
                "proposal": normalized_sug,
                "proposal_summary": "PROPOSITION MUTÉE IA MCP :",
            }
            categories_dict[cat_id]["items"].append(item)

        total_score = 0
        cat_count = max(1, len(categories_dict))
        for cat_id, cat_data in categories_dict.items():
            items_count = len(cat_data["items"])
            cat_score = max(0, 100 - items_count * 7)
            cat_data["score"] = cat_score
            total_score += cat_score

            if cat_id in self.kpi_cards:
                kpi = self.kpi_cards[cat_id]
                sub_text = f"{items_count} problème(s)" if items_count > 0 else "Conforme"
                kpi.update_pct(cat_score, sub_text)

        score_global = int(total_score / cat_count)
        self.score_badge.setText(f"Score : {score_global} / 100")
        self.score_badge.setStyleSheet(
            f"background-color: rgba(245,158,11,0.12); color: {DesignTokens.COLOR_YELLOW}; border: 1px solid rgba(245,158,11,0.3); border-radius: 9999px; padding: 4px 14px;"
        )

        self._cached_categories_data = categories_dict
        self._render_active_category_items()

    def _render_active_category_items(self) -> None:
        while self.cards_layout.count():
            item_widget = self.cards_layout.takeAt(0)
            widget = item_widget.widget() if item_widget is not None else None
            if widget is not None:
                widget.deleteLater()

        current_cat_data = self._cached_categories_data.get(self.active_category, {})
        items = cast(List[Dict[str, Any]], current_cat_data.get("items", []))

        if not items:
            self.show_empty_state("Aucune anomalie détectée dans cette catégorie ! Toutes les cartes sont conformes.")
            return

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

                safe_prop = normalize_linter_suggestion(proposal, original_content=content)
                for k, v in safe_prop.items():
                    content[k] = v

                new_version = note.add_version(new_content_dict=content, source="Linter AI")

                AuditRecordModel.delete().where(AuditRecordModel.note == note).execute()
                AuditRecordModel.create(note=note, note_version=new_version, is_compliant=True, rule_broken=None, reason="Corrigé manuellement via Linter")

            logger.info("Proposition appliquée avec succès pour la note #%d", note_id)
            show_toast(self, f"Note #{note_id} mise à jour avec succès !")
            widget_to_remove.deleteLater()

        except Exception as e:
            logger.error("Erreur lors de l'application de la proposition pour la note #%d : %s", note_id, e)

    @Slot(int, QWidget)
    def _on_card_ignored(self, note_id: int, widget_to_remove: QWidget) -> None:
        try:
            note = NoteModel.get_or_none(NoteModel.id == note_id)
            if not note:
                return
            active_ver = NoteVersionModel.get_or_none(NoteVersionModel.note == note, NoteVersionModel.is_active == True)  # noqa: E712
            if not active_ver:
                return

            with db.atomic():
                AuditRecordModel.delete().where(AuditRecordModel.note == note, AuditRecordModel.note_version == active_ver).execute()
                AuditRecordModel.create(note=note, note_version=active_ver, is_compliant=True, reason="Ignoré par l'utilisateur (Faux positif)")

            widget_to_remove.deleteLater()
            logger.info("Note #%d ignorée et marquée comme conforme.", note_id)
            show_toast(self, f"Note #{note_id} marquée comme conforme.")

        except Exception as e:
            logger.error("Erreur lors de l'ignorance de la note #%d : %s", note_id, e)

    def filter_items_by_search(self, query: str) -> None:
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
