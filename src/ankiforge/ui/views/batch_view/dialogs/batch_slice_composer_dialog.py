"""Modale fusionnée de composition d'un lot : document → mode de découpage → parties → insertion (BatchSliceComposerDialog)."""

from __future__ import annotations

import html
import logging
from collections.abc import Callable
from typing import Any

import markdown
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import DocumentModel
from ankiforge.services.batch.slicing_service import SliceUnit
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.components.document_picker_button import DocumentPickerButton
from ankiforge.ui.dialogs.document_scope_dialog import DocumentScopeWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.views.batch_view.widgets import AutoSliceWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon

logger = logging.getLogger(__name__)


class _ModeCard(QFrame):
    """Carte cliquable de choix du mode de découpage (style page d'accueil du Studio de Création)."""

    clicked = Signal()

    def __init__(self, title: str, subtitle: str, icon_name: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modeCard")
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(240)
        self._apply_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon(icon_name, color=color).pixmap(24, 24))
        icon_lbl.setStyleSheet("background: transparent; border: none;")
        header.addWidget(icon_lbl)
        self.badge = QLabel("✓ Sélectionné")
        self.badge.setStyleSheet(f"""
            QLabel {{
                background-color: {DesignTokens.ACCENT_BG};
                color: {DesignTokens.ACCENT_PRIMARY};
                font-size: 10px;
                font-weight: bold;
                border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 1px 7px;
            }}
        """)
        self.badge.hide()
        header.addWidget(self.badge)
        header.addStretch()
        layout.addLayout(header)

        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 13px; background: transparent; border: none;")
        layout.addWidget(self.title_lbl)

        self.desc_lbl = QLabel(subtitle)
        self.desc_lbl.setWordWrap(True)
        self.desc_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")
        layout.addWidget(self.desc_lbl)

        layout.addStretch()

    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QFrame#modeCard {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
            QFrame#modeCard:hover {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QFrame#modeCard[selected="true"] {{
                background-color: {DesignTokens.ACCENT_BG};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.badge.setVisible(selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _markdown_to_html(text: str) -> str:
    """Rend du Markdown en HTML stylé pour la prévisualisation « Formaté » du récapitulatif."""
    try:
        body = markdown.markdown(text or "", extensions=["fenced_code", "tables"])
    except Exception as err:
        logger.warning("Rendu Markdown du récapitulatif incomplet : %s", err)
        body = f"<pre>{html.escape(text or '')}</pre>"
    return (
        "<html><head><style>"
        f"body {{ color: {DesignTokens.TEXT_PRIMARY}; font-family: {DesignTokens.FONT_MAIN}; font-size: 12px; line-height: 1.55; }}"
        f"h1, h2, h3, h4 {{ color: {DesignTokens.ACCENT_PRIMARY}; }}"
        f"code {{ font-family: {DesignTokens.FONT_CODE}; background-color: {DesignTokens.BG_MAIN}; padding: 1px 4px; border-radius: 3px; }}"
        f"pre {{ background-color: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px; padding: 10px; }}"
        "a { color: #60a5fa; }"
        "</style></head>"
        f"<body>{body}</body></html>"
    )


class _RecapTaskCard(QFrame):
    """Carte du récapitulatif : libellé + statistiques de la tâche et données du lot en double vue.

    Les onglets « Formaté » (Markdown rendu) et « Source » (données brutes) permettent de vérifier
    ce qui sera réellement expédié au moteur, plutôt que de s'appuyer sur les seuls titres de sections.
    """

    def __init__(self, label: str, stats: str, content: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("recapTaskCard")
        self.setStyleSheet(f"""
            QFrame#recapTaskCard {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        self.lbl_title = QLabel(label)
        self.lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold; font-size: 12px; background: transparent; border: none;")
        self.lbl_stats = QLabel(stats)
        self.lbl_stats.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-family: {DesignTokens.FONT_CODE}; background: transparent; border: none;")
        header.addWidget(self.lbl_title)
        header.addWidget(self.lbl_stats)
        header.addStretch()
        layout.addLayout(header)

        self.btn_formatted = QPushButton("Formaté")
        self.btn_source = QPushButton("Source")
        self.btn_formatted.setCheckable(True)
        self.btn_source.setCheckable(True)
        for btn in (self.btn_formatted, self.btn_source):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_group = QButtonGroup(self)
        self._view_group.addButton(self.btn_formatted)
        self._view_group.addButton(self.btn_source)
        self.btn_formatted.setChecked(True)
        self._apply_toggle_styles()
        self.btn_formatted.clicked.connect(lambda: self._set_view("formatted"))
        self.btn_source.clicked.connect(lambda: self._set_view("source"))
        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(6)
        toggle_row.addWidget(self.btn_formatted)
        toggle_row.addWidget(self.btn_source)
        toggle_row.addStretch()
        layout.addLayout(toggle_row)

        self.preview_stack = QStackedWidget()
        self.browser_formatted = QTextBrowser()
        self.browser_source = QTextBrowser()
        for browser in (self.browser_formatted, self.browser_source):
            browser.setStyleSheet(
                f"QTextBrowser {{ background-color: {DesignTokens.BG_PANEL}; color: {DesignTokens.TEXT_PRIMARY}; "
                f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px; font-size: 12px; }}"
            )
        self.browser_formatted.setHtml(_markdown_to_html(content))
        self.browser_source.setPlainText(content)
        self.preview_stack.addWidget(self.browser_formatted)
        self.preview_stack.addWidget(self.browser_source)
        layout.addWidget(self.preview_stack, 1)

    def _apply_toggle_styles(self) -> None:
        for btn in (self.btn_formatted, self.btn_source):
            checked = btn.isChecked()
            bg = DesignTokens.ACCENT_PRIMARY if checked else DesignTokens.BG_MAIN
            color = DesignTokens.TEXT_ON_ACCENT if checked else DesignTokens.TEXT_SECONDARY
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {bg}; color: {color}; font-size: 11px; font-weight: bold; "
                f"border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_SM}px; padding: 3px 12px; }}"
            )

    def _set_view(self, view: str) -> None:
        self.preview_stack.setCurrentIndex(0 if view == "formatted" else 1)
        self._apply_toggle_styles()


class BatchSliceComposerDialog(QDialog):
    """Parcours unique : document → mode de découpage → parties → ajout à la Queue.

    - Le document est déjà découpé/délimité dans l'onglet document : il ne reste qu'à choisir
      le mode (Direct ou Auto), puis les parties à insérer.
    - Étape 1 « Document & découpage » : picker + deux cartes descriptives côte à côte
      (Direct / Auto) ; en Auto, la règle de découpage (AutoSliceWidget) s'affiche ici.
    - Étape 2 « Choix des parties » : Direct → DocumentScopeWidget (1 partie cochée = 1 tâche),
      Auto → liste à cocher des tranches générées.
    """

    STEP_LABELS = ("1. Document && découpage", "2. Choix des parties", "3. Récapitulatif")

    def __init__(
        self,
        doc: DocumentModel | None = None,
        resolve_chunks: Callable[[DocumentModel], list[dict[str, Any]]] | None = None,
        scope_memory: Callable[[DocumentModel], dict[str, Any] | None] | None = None,
        task_from_chunk: Callable[[DocumentModel, dict[str, Any]], dict[str, Any] | None] | None = None,
        task_from_slice: Callable[[DocumentModel, SliceUnit], dict[str, Any] | None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._has_custom_resolver = resolve_chunks is not None
        self._resolve_chunks = resolve_chunks or (lambda d: [])
        self._scope_memory = scope_memory or (lambda d: None)
        self._task_from_chunk = task_from_chunk or (lambda d, c: None)
        self._task_from_slice = task_from_slice or (lambda d, s: None)

        self.doc: DocumentModel | None = None
        self.scope_result: dict[str, Any] = {}
        self._tasks: list[dict[str, Any]] = []
        self._slice_items: list[SliceUnit] = []
        self._building_slices = False
        self._current_step = 0
        self._mode = "direct"

        self.setWindowTitle("Composer le lot : document, découpage & parties")
        self.resize(1180, 760)
        self.setMinimumSize(960, 620)
        self._setup_ui()
        self._load_document(doc)
        self.select_mode("direct")

    # ── Construction de l'UI ─────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._build_nav_chips(layout)

        self.body_stack = QStackedWidget()
        self.body_stack.addWidget(self._build_step_document())
        self.body_stack.addWidget(self._build_step_parties())
        self.body_stack.addWidget(self._build_step_recap())
        layout.addWidget(self.body_stack, 1)

        footer = QHBoxLayout()
        footer.setSpacing(10)
        self.btn_back = SecondaryButton("Précédent")
        self.btn_back.clicked.connect(self._on_back)
        self.btn_next = PrimaryButton("Suivant")
        self.btn_next.clicked.connect(self._on_next)
        footer.addWidget(self.btn_back)
        footer.addStretch()
        footer.addWidget(self.btn_next)
        layout.addLayout(footer)

    def _build_nav_chips(self, layout: QVBoxLayout) -> None:
        nav = QHBoxLayout()
        nav.setSpacing(8)
        self._chips: list[QPushButton] = []
        for i, label in enumerate(self.STEP_LABELS):
            btn = QPushButton(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, idx=i: self._on_step_chip_clicked(idx))
            self._chips.append(btn)
            nav.addWidget(btn, 1)
        layout.addLayout(nav)

    def _build_step_document(self) -> QWidget:
        page = QWidget()
        p_layout = QVBoxLayout(page)
        p_layout.setContentsMargins(0, 8, 0, 0)
        p_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.doc_picker = DocumentPickerButton()
        self.doc_picker.document_changed.connect(self._on_document_changed)
        top_row.addWidget(self.doc_picker, 1)
        p_layout.addLayout(top_row)

        self.lbl_doc_hint = QLabel("Aucun document sélectionné — choisissez un document pour continuer.")
        self.lbl_doc_hint.setWordWrap(True)
        self.lbl_doc_hint.setStyleSheet(
            f"background-color: {DesignTokens.COLOR_YELLOW_BG}; color: {DesignTokens.COLOR_YELLOW_TEXT}; "
            f"border: 1px solid {DesignTokens.COLOR_YELLOW_BORDER}; border-radius: {DesignTokens.RADIUS_SM}px; "
            "padding: 6px 10px; font-size: 11px;"
        )
        self.lbl_doc_hint.hide()
        p_layout.addWidget(self.lbl_doc_hint)

        mode_title = QLabel("MODE DE DÉCOUPAGE")
        mode_title.setStyleSheet(f"font-size: 10px; font-weight: bold; color: {DesignTokens.TEXT_MUTED}; letter-spacing: 0.5px;")
        p_layout.addWidget(mode_title)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(14)
        self.card_direct = _ModeCard(
            "Découpage direct",
            "Chaque partie cochée du document devient une tâche (1 partie = 1 tâche). Le choix manuel le plus fiable.",
            "ph.list-checks",
            DesignTokens.COLOR_BLUE,
        )
        self.card_direct.clicked.connect(lambda: self.select_mode("direct"))
        cards_row.addWidget(self.card_direct, 1)

        self.card_auto = _ModeCard(
            "Découpage automatique",
            "Découpage selon des règles : chapitres/titres, blocs de tokens ou tranches de pages.",
            "ph.magic-wand",
            DesignTokens.COLOR_GREEN,
        )
        self.card_auto.clicked.connect(lambda: self.select_mode("auto"))
        cards_row.addWidget(self.card_auto, 1)
        p_layout.addLayout(cards_row)

        self.decoupage_stack = QStackedWidget()

        direct_page = QWidget()
        d_layout = QVBoxLayout(direct_page)
        d_layout.setContentsMargins(0, 8, 0, 0)
        d_hint = QLabel("Le document est déjà découpé dans l'onglet document. À l'étape suivante, cochez directement les parties à insérer : chaque partie deviendra une tâche.")
        d_hint.setWordWrap(True)
        d_hint.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        d_layout.addWidget(d_hint)
        self.decoupage_stack.addWidget(direct_page)

        auto_page = QWidget()
        a_layout = QVBoxLayout(auto_page)
        a_layout.setContentsMargins(0, 8, 0, 0)
        self.auto_widget = AutoSliceWidget()
        self.auto_widget.slices_changed.connect(lambda _: self._refresh_auto_checklist())
        a_layout.addWidget(self.auto_widget)
        self.decoupage_stack.addWidget(auto_page)

        p_layout.addWidget(self.decoupage_stack, 1)
        return page

    def _build_step_parties(self) -> QWidget:
        page = QWidget()
        p_layout = QVBoxLayout(page)
        p_layout.setContentsMargins(0, 8, 0, 0)
        p_layout.setSpacing(10)
        p_layout.addWidget(self._build_parties_rules_row())

        self.parties_stack = QStackedWidget()

        direct_page = QWidget()
        d_layout = QVBoxLayout(direct_page)
        d_layout.setContentsMargins(0, 0, 0, 0)
        d_layout.setSpacing(8)
        d_hint = QLabel("Cochez les parties du document à insérer. Chaque modification met à jour le nombre de tâches en direct.")
        d_hint.setWordWrap(True)
        d_hint.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        d_layout.addWidget(d_hint)
        self.scope_container = QWidget()
        self.scope_layout = QVBoxLayout(self.scope_container)
        self.scope_layout.setContentsMargins(0, 0, 0, 0)
        d_layout.addWidget(self.scope_container, 1)
        self.parties_stack.addWidget(direct_page)

        auto_page = QWidget()
        a_layout = QVBoxLayout(auto_page)
        a_layout.setContentsMargins(0, 0, 0, 0)
        a_layout.setSpacing(8)
        a_hint = QLabel("Les tranches générées par la règle sont toutes cochées. Décochez celles à exclure du lot.")
        a_hint.setWordWrap(True)
        a_hint.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        a_layout.addWidget(a_hint)
        self.lst_slices = QListWidget()
        self.lst_slices.itemChanged.connect(lambda _: self._on_slice_item_changed())
        a_layout.addWidget(self.lst_slices, 1)
        self.parties_stack.addWidget(auto_page)

        p_layout.addWidget(self.parties_stack, 1)

        self.lbl_parties_count = QLabel("0 partie(s) sélectionnée(s)")
        self.lbl_parties_count.setStyleSheet(f"color: {DesignTokens.ACCENT_PRIMARY}; font-weight: bold; font-size: 11px;")
        p_layout.addWidget(self.lbl_parties_count)
        return page

    def _build_parties_rules_row(self) -> QWidget:
        row = QWidget()
        r_layout = QHBoxLayout(row)
        r_layout.setContentsMargins(0, 0, 0, 0)
        r_layout.setSpacing(8)
        self.lbl_mode_caption = QLabel("")
        self.lbl_mode_caption.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px;")
        r_layout.addWidget(self.lbl_mode_caption)
        r_layout.addStretch()
        return row

    def _build_step_recap(self) -> QWidget:
        page = QWidget()
        p_layout = QVBoxLayout(page)
        p_layout.setContentsMargins(0, 8, 0, 0)
        p_layout.setSpacing(10)

        recap_card = QFrame()
        recap_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 14px;
            }}
        """)
        r_layout = QVBoxLayout(recap_card)
        r_layout.setSpacing(6)
        self.lbl_recap_title = QLabel("Aucune tâche à générer.")
        self.lbl_recap_title.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        self.lbl_recap_stats = QLabel("")
        self.lbl_recap_stats.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY}; font-family: {DesignTokens.FONT_CODE};")
        r_layout.addWidget(self.lbl_recap_title)
        r_layout.addWidget(self.lbl_recap_stats)
        p_layout.addWidget(recap_card)

        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tasks_container = QWidget()
        self.tasks_layout = QVBoxLayout(self.tasks_container)
        self.tasks_layout.setContentsMargins(0, 0, 0, 0)
        self.tasks_layout.setSpacing(8)
        self.tasks_scroll.setWidget(self.tasks_container)
        p_layout.addWidget(self.tasks_scroll, 1)
        return page

    # ── Gestion du document / des parties ────────────────────────────────────────────────────

    def _on_document_changed(self, doc: DocumentModel | None) -> None:
        if doc is not None and getattr(doc, "id", None):
            try:
                doc = DocumentModel.get_by_id(doc.id) or doc
            except Exception as err:
                logger.debug("Rechargement du document du composer ignoré : %s", err)
        self._load_document(doc)

    def _load_document(self, doc: DocumentModel | None) -> None:
        self.doc = doc
        if hasattr(self, "doc_picker") and self.doc_picker.get_document() != doc:
            self.doc_picker.set_document(doc, emit_signal=False)
        self.scope_result = {}
        self._tasks = []
        self._slice_items = []
        self._update_doc_hint()
        if self.hasattr_scope_widget():
            old = getattr(self, "scope_widget", None)
            if old is not None:
                self.scope_layout.removeWidget(old)
                old.deleteLater()
            self.__dict__.pop("scope_widget", None)
            self.__dict__.pop("_scope_live_wired", None)

        if doc is None:
            self.lbl_parties_count.setText("0 partie(s) sélectionnée(s)")
            self._update_parties_caption()
            self._recompute_tasks()
            self._update_step_view()
            return

        scope_widget = DocumentScopeWidget(
            doc,
            initial_scope_str="",
            initial_scope_result=self._scope_memory(doc),
            parent=self.scope_container,
        )
        self.scope_widget = scope_widget
        self.scope_layout.addWidget(scope_widget)
        self._wire_scope_live()
        scope_widget.notify_changed()
        self._update_parties_caption()
        if self._mode == "auto":
            self._ensure_auto_content()
        self._recompute_tasks()
        self._update_step_view()

    def _update_doc_hint(self) -> None:
        """Alerte visuelle et blocage de navigation tant qu'aucun document n'est sélectionné."""
        self.lbl_doc_hint.setVisible(self.doc is None)

    def hasattr_scope_widget(self) -> bool:
        return "scope_widget" in self.__dict__

    def _wire_scope_live(self) -> None:
        """Branche tous les signaux de sélection du DocumentScopeWidget vers le recalcul live."""
        if not self.hasattr_scope_widget() or self.__dict__.get("_scope_live_wired", False):
            return
        scope = self.scope_widget
        scope.scope_changed.connect(self._on_scope_changed)

        def notify() -> None:
            scope.notify_changed()

        sections_tree = getattr(scope, "tree_widget", None) or getattr(scope, "sections_list", None) or getattr(scope, "sections_tree", None)
        if sections_tree is not None:
            sections_tree.itemChanged.connect(lambda *_: notify())
        for attr in ("btn_mode_all", "btn_mode_range", "btn_mode_structure", "btn_mode_sections"):
            if hasattr(scope, attr):
                getattr(scope, attr).clicked.connect(notify)
        for attr in ("spin_p_start", "spin_p_end"):
            if hasattr(scope, attr):
                getattr(scope, attr).valueChanged.connect(lambda _: notify())
        if hasattr(scope, "slide_selector_bar"):
            bar = scope.slide_selector_bar
            for sig in (bar.page_toggled, bar.all_selected, bar.none_selected, bar.inverted):
                sig.connect(notify)
        if hasattr(scope, "range_segments_widget"):
            seg = scope.range_segments_widget
            seg.segment_removed.connect(notify)
            seg.range_added.connect(notify)
        for card in getattr(scope, "_chapter_cards", []):
            card.toggled.connect(notify)
        self.__dict__["_scope_live_wired"] = True

    def _on_scope_changed(self, result: dict[str, Any]) -> None:
        if not hasattr(self, "scope_widget") or self.doc is None:
            return
        self.scope_result = result
        self._recompute_tasks()

    # ── Modes de découpage & tâches ──────────────────────────────────────────────────────────

    def select_mode(self, mode: str) -> None:
        """Sélectionne le mode de découpage (cartes) et met à jour la vue associée."""
        self._mode = mode
        self.card_direct.set_selected(mode == "direct")
        self.card_auto.set_selected(mode == "auto")
        self.decoupage_stack.setCurrentIndex(0 if mode == "direct" else 1)
        self.parties_stack.setCurrentIndex(0 if mode == "direct" else 1)
        self._update_parties_caption()
        if mode == "auto":
            self._ensure_auto_content()
        self._recompute_tasks()

    def _update_parties_caption(self) -> None:
        if self._mode == "auto":
            self.lbl_mode_caption.setText("Règle de découpage automatique — les tranches générées deviennent les parties du lot.")
        else:
            self.lbl_mode_caption.setText("Direct — chaque partie cochée du document devient une tâche (1 partie = 1 tâche).")

    def _document_text(self) -> str:
        if self.doc is None:
            return ""
        if self._has_custom_resolver:
            chunks = self._resolve_chunks(self.doc) or []
            return "\n\n".join(str(c.get("content", "")).strip() for c in chunks if str(c.get("content", "")).strip())
        chunks = self._resolve_chunks(self.doc) or []
        if chunks:
            text = "\n\n".join(str(c.get("content", "")).strip() for c in chunks if str(c.get("content", "")).strip())
            if text:
                return text
        return getattr(self.doc, "content", "") or ""

    def _ensure_auto_content(self) -> None:
        self.auto_widget.set_content(self._document_text())

    def _refresh_auto_checklist(self) -> None:
        self.lst_slices.clear()
        self._slice_items = list(self.auto_widget.get_slices())
        self._building_slices = True
        try:
            for sl in self._slice_items:
                path_str = f" ({sl.heading_path})" if sl.heading_path and sl.heading_path != sl.title else ""
                item = QListWidgetItem(f"{sl.title}{path_str}  •  ~{sl.tokens_estimate or 0} tokens  •  ~{sl.words_estimate or 0} mots")
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                self.lst_slices.addItem(item)
        finally:
            self._building_slices = False
        self._recompute_tasks()

    def _on_slice_item_changed(self) -> None:
        if not self._building_slices:
            self._recompute_tasks()

    def _checked_slices(self) -> list[SliceUnit]:
        return [sl for index, sl in enumerate(self._slice_items) if index < self.lst_slices.count() and self.lst_slices.item(index).checkState() == Qt.CheckState.Checked]

    def _direct_parts(self) -> list[dict[str, Any]]:
        """Retourne les parties actuelles en mode Direct avec repli sur les fragments (scopes mémorisés sans clé 'parts')."""
        parts = self.scope_result.get("parts")
        if not parts:
            parts = self.scope_result.get("chunks") or []
        return list(parts)

    def _recompute_tasks(self) -> None:
        if self.doc is None:
            self._tasks = []
        elif self._mode == "direct":
            self._tasks = [t for p in self._direct_parts() if (t := self._task_from_chunk(self.doc, p)) is not None]
        else:
            self._tasks = [t for s in self._checked_slices() if (t := self._task_from_slice(self.doc, s)) is not None]
        self._update_parties_count()
        self._render_task_lists()
        self._update_step_view()

    def _update_parties_count(self) -> None:
        if self._mode == "auto":
            checked = len(self._checked_slices())
            total = len(self._slice_items)
            self.lbl_parties_count.setText(f"{checked} tranche(s) sélectionnée(s) sur {total}")
        else:
            self.lbl_parties_count.setText(f"{len(self._direct_parts())} partie(s) sélectionnée(s)")

    def _render_task_lists(self) -> None:
        tasks = self._tasks
        while self.tasks_layout.count():
            item = self.tasks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for task in tasks:
            label = str(task.get("chunk_label") or task.get("doc_title") or "Tâche")
            tokens = int(task.get("tokens_est", 0) or 0)
            content = str(task.get("doc_content") or "").strip()
            self.tasks_layout.addWidget(_RecapTaskCard(label, f"~{tokens} tokens", content))
        total_tokens = sum(int(t.get("tokens_est", 0) or 0) for t in tasks)
        self.lbl_recap_title.setText(f"{len(tasks)} tâche(s) à ajouter à la Queue")
        self.lbl_recap_stats.setText(f"~{total_tokens:,} tokens au total".replace(",", " "))

    # ── Navigation par étapes ────────────────────────────────────────────────────────────────

    def _on_step_chip_clicked(self, step_idx: int) -> None:
        """Permet de naviguer directement vers une étape en cliquant sur sa puce en haut."""
        if step_idx == self._current_step:
            return
        if step_idx > 0 and self.doc is None:
            show_toast(self, "Veuillez sélectionner un document avant de continuer.", is_error=True)
            return
        self._current_step = step_idx
        if self._current_step == 1 and self._mode == "auto":
            self._refresh_auto_checklist()
        self._update_step_view()

    def _update_step_view(self) -> None:
        self.body_stack.setCurrentIndex(self._current_step)
        for i, chip in enumerate(self._chips):
            active = i == self._current_step
            bg = DesignTokens.ACCENT_PRIMARY if active else DesignTokens.BG_INPUT
            color = DesignTokens.TEXT_ON_ACCENT if active else DesignTokens.TEXT_SECONDARY
            chip.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg};
                    color: {color};
                    font-weight: bold;
                    font-size: 11px;
                    padding: 6px 12px;
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                }}
                QPushButton:hover {{
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.TEXT_PRIMARY if not active else DesignTokens.TEXT_ON_ACCENT};
                }}
            """)
        self.btn_back.setEnabled(self._current_step > 0)
        if self._current_step == len(self.STEP_LABELS) - 1:
            self.btn_next.setText(f"Ajouter à la Queue ({len(self._tasks)})")
            self.btn_next.setIcon(load_on_accent_icon("ph.check"))
            self.btn_next.setEnabled(bool(self._tasks))
        else:
            self.btn_next.setText("Suivant")
            self.btn_next.setIcon(load_on_accent_icon("ph.caret-right"))
            self.btn_next.setEnabled(self._current_step > 0 or self.doc is not None)

    def _on_back(self) -> None:
        if self._current_step > 0:
            self._current_step -= 1
            if self._current_step == 1 and self._mode == "auto":
                self._refresh_auto_checklist()
            self._update_step_view()

    def _on_next(self) -> None:
        if self._current_step == 0 and self.doc is None:
            show_toast(self, "Veuillez sélectionner un document avant de continuer.", is_error=True)
            return
        if self._current_step < len(self.STEP_LABELS) - 1:
            self._current_step += 1
            if self._current_step == 1 and self._mode == "auto":
                self._refresh_auto_checklist()
            self._update_step_view()
        else:
            self.accept()

    def get_result(self) -> dict[str, Any]:
        """Retourne les tâches à ajouter et la portée validée pour le document (mode Direct)."""
        return {
            "tasks": self._tasks,
            "scope_result": self.scope_result,
            "doc": self.doc,
        }
