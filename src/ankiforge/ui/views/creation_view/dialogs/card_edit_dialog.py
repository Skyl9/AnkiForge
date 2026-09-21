from typing import Any

from PySide6.QtCore import QKeyCombination, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.components import (
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.note_editor_widget import NoteKaTeXHighlighter
from ankiforge.utils.anki_renderer import get_max_cloze_index
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon


class CardEditDialog(QDialog):
    """
    Dialogue d'édition complet d'une carte générée avant son enregistrement en BDD :
    - Filtrage strict des champs selon le schéma du modèle (zéro champ fantôme).
    - Barre d'outils de mise en forme riche (HTML, LaTeX KaTeX, Clozes).
    - Coloration syntaxique temps réel (NoteKaTeXHighlighter).
    - Aperçu en direct intégré (CardPreviewWidget avec moteur WebEngine/MathJax).
    """

    METADATA_KEYS: set[str] = {
        "model",
        "note_type",
        "status",
        "chunk_id",
        "source_doc_id",
        "tags",
        "section",
        "heading_path",
        "page_number",
        "_source_chunk_id",
        "_source_heading_path",
        "_source_page_number",
        "_source_chunk_hash",
        "_documentation_enabled",
        "guid",
        "id",
        "source",
    }

    def __init__(
        self,
        front: str = "",
        back: str = "",
        card_data: dict[str, Any] | None = None,
        field_names: list[str] | None = None,
        note_type: NoteTypeModel | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Éditer la carte")
        self.setMinimumSize(680, 520)
        self.resize(1020, 640)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        self.note_type = note_type
        self.card_data: dict[str, Any] = dict(card_data) if card_data is not None else {}
        if not self.card_data and (front or back):
            self.card_data = {"Front": front, "Back": back}

        # 1. Résolution stricte des champs du modèle
        ordered_fields: list[str] = []
        if field_names:
            for f in field_names:
                if f not in self.METADATA_KEYS and not f.startswith("_") and f not in ordered_fields:
                    ordered_fields.append(f)
        else:
            # Repli uniquement si aucun schéma de champs n'est spécifié
            for k in self.card_data:
                if k not in self.METADATA_KEYS and not k.startswith("_") and k not in ordered_fields:
                    ordered_fields.append(k)

        if not ordered_fields:
            ordered_fields = ["Front", "Back"]

        self.ordered_fields = ordered_fields
        self.field_edits: dict[str, StyledTextEdit] = {}
        self.highlighters: list[NoteKaTeXHighlighter] = []
        self._last_focused_field: str | None = None

        self._setup_ui()
        self._setup_shortcuts()

        # Minuteur anti-rebond pour l'aperçu en direct
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(120)
        self._preview_timer.timeout.connect(self._update_live_preview)

        # Rendu initial différé
        QTimer.singleShot(50, self._update_live_preview)

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # En-tête : Modèle, Titre et bouton bascule d'aperçu
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(load_phosphor_icon("ph.pencil-simple", color=DesignTokens.ACCENT_PRIMARY).pixmap(20, 20))
        header_layout.addWidget(ico)

        model_name = (self.note_type.name if self.note_type else None) or self.card_data.get("model") or self.card_data.get("note_type") or "Carte"
        title_lbl = QLabel(f"Éditer la carte — {model_name}")
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 15px; font-weight: 700; border: none; background: transparent;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        self.btn_toggle_preview = IconButton("ph.eye", "Masquer/Afficher l'aperçu en direct", 22)
        self.btn_toggle_preview.clicked.connect(self._toggle_preview_panel)
        header_layout.addWidget(self.btn_toggle_preview)

        main_layout.addLayout(header_layout)

        # Splitter principal : Gauche (Édition) / Droite (Aperçu Live)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {DesignTokens.BORDER_COLOR};
                width: 2px;
            }}
        """)

        # ── PANNEAU GAUCHE : ÉDITEUR DES CHAMPS ET OUTILS ──
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        # Barre d'outils de formatage
        toolbar = self._create_formatting_toolbar()
        left_layout.addWidget(toolbar)

        # Zone scrollable hébergeant les champs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        fields_layout = QVBoxLayout(scroll_content)
        fields_layout.setContentsMargins(0, 0, 6, 0)
        fields_layout.setSpacing(12)

        for i, field_name in enumerate(self.ordered_fields):
            lbl = QLabel(f"{field_name} :")
            lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px; border: none; background: transparent;")
            fields_layout.addWidget(lbl)

            edit = StyledTextEdit()
            raw_val = self._resolve_initial_field_value(field_name)
            edit.setPlainText(str(raw_val) if raw_val is not None else "")
            edit.setMinimumHeight(75)

            # Coloration syntaxique HTML/KaTeX/Cloze
            highlighter = NoteKaTeXHighlighter(edit.document())
            self.highlighters.append(highlighter)

            # Détection du focus et saisie
            edit.textChanged.connect(self._on_field_text_changed)
            edit.cursorPositionChanged.connect(lambda f=field_name: self._set_last_focused(f))

            self.field_edits[field_name] = edit
            fields_layout.addWidget(edit, 1 if len(self.ordered_fields) <= 3 else 0)

            # Rétrocompatibilité edit_front et edit_back
            if i == 0:
                self.edit_front = edit
            elif i == 1:
                self.edit_back = edit

        if "Front" not in self.field_edits and not hasattr(self, "edit_front"):
            self.edit_front = list(self.field_edits.values())[0] if self.field_edits else StyledTextEdit()
        if "Back" not in self.field_edits and not hasattr(self, "edit_back"):
            self.edit_back = list(self.field_edits.values())[1] if len(self.field_edits) > 1 else self.edit_front

        scroll.setWidget(scroll_content)
        left_layout.addWidget(scroll, 1)

        self.splitter.addWidget(left_panel)

        # ── PANNEAU DROIT : APERÇU EN DIRECT ──
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_layout.setSpacing(6)

        prev_header = QHBoxLayout()
        prev_lbl = QLabel("Aperçu en direct (Recto / Verso)")
        prev_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: 600; text-transform: uppercase;")
        prev_header.addWidget(prev_lbl)
        prev_header.addStretch()
        right_layout.addLayout(prev_header)

        self.preview_widget = CardPreviewWidget(show_header=False)
        self.preview_widget.setMinimumWidth(320)
        right_layout.addWidget(self.preview_widget, 1)

        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([540, 440])

        main_layout.addWidget(self.splitter, 1)

        # Barre inférieure d'actions
        btn_box = QHBoxLayout()
        btn_box.setContentsMargins(0, 4, 0, 0)
        btn_box.addStretch()

        btn_cancel = SecondaryButton("Annuler")
        btn_cancel.clicked.connect(self.reject)

        btn_save = PrimaryButton("Enregistrer les modifications")
        btn_save.setIcon(load_on_accent_icon("ph.check"))
        btn_save.clicked.connect(self.accept)

        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)

        main_layout.addLayout(btn_box)

    def _create_formatting_toolbar(self) -> QWidget:
        """Barre d'outils compacte pour insérer rapidement des balises HTML, Math et Cloze."""
        bar = QWidget()
        bar.setStyleSheet(f"""
            QWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        def make_tool_btn(icon_name: str, tooltip: str, on_click: Any) -> QToolButton:
            btn = QToolButton()
            btn.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_PRIMARY))
            btn.setIconSize(QSize(16, 16))
            btn.setToolTip(tooltip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QToolButton {{
                    background-color: transparent;
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 3px;
                }}
                QToolButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                }}
            """)
            btn.clicked.connect(on_click)
            return btn

        btn_bold = make_tool_btn("ph.text-b", "Gras (Ctrl+B)", lambda: self._wrap_selection("<b>", "</b>"))
        btn_italic = make_tool_btn("ph.text-italic", "Italique (Ctrl+I)", lambda: self._wrap_selection("<i>", "</i>"))
        btn_underline = make_tool_btn("ph.text-underline", "Souligné (Ctrl+U)", lambda: self._wrap_selection("<u>", "</u>"))
        btn_code = make_tool_btn("ph.code", "Code en ligne (Ctrl+K)", lambda: self._wrap_selection("<code>", "</code>"))

        btn_math_inline = make_tool_btn("ph.function", "Formule LaTeX inline \\( ... \\) (Ctrl+M)", lambda: self._wrap_selection(r"\( ", r" \)"))
        btn_math_block = make_tool_btn("ph.sigma", "Formule LaTeX bloc \\[ ... \\]", lambda: self._wrap_selection(r"\[ ", r" \]"))
        btn_cloze = make_tool_btn("ph.brackets-curly", "Trou Cloze {{c1::...}} (Ctrl+Shift+C)", self._insert_cloze)
        btn_br = make_tool_btn("ph.arrow-down-left", "Saut de ligne HTML <br>", lambda: self._insert_text("<br>\n"))
        btn_list = make_tool_btn("ph.list-bullets", "Liste à puces <ul><li>...</li></ul>", lambda: self._wrap_selection("<ul>\n  <li>", "</li>\n</ul>"))

        layout.addWidget(btn_bold)
        layout.addWidget(btn_italic)
        layout.addWidget(btn_underline)
        layout.addWidget(btn_code)
        layout.addSpacing(6)
        layout.addWidget(btn_math_inline)
        layout.addWidget(btn_math_block)
        layout.addWidget(btn_cloze)
        layout.addSpacing(6)
        layout.addWidget(btn_br)
        layout.addWidget(btn_list)
        layout.addStretch()

        return bar

    def _setup_shortcuts(self) -> None:
        """Enregistre les raccourcis de formatage standard."""
        sc_bold = QShortcut(QKeySequence("Ctrl+B"), self)
        sc_bold.activated.connect(lambda: self._wrap_selection("<b>", "</b>"))

        sc_italic = QShortcut(QKeySequence("Ctrl+I"), self)
        sc_italic.activated.connect(lambda: self._wrap_selection("<i>", "</i>"))

        sc_underline = QShortcut(QKeySequence("Ctrl+U"), self)
        sc_underline.activated.connect(lambda: self._wrap_selection("<u>", "</u>"))

        sc_code = QShortcut(QKeySequence("Ctrl+K"), self)
        sc_code.activated.connect(lambda: self._wrap_selection("<code>", "</code>"))

        sc_math = QShortcut(QKeySequence("Ctrl+M"), self)
        sc_math.activated.connect(lambda: self._wrap_selection(r"\( ", r" \)"))

        sc_cloze = QShortcut(QKeyCombination(Qt.Modifier.CTRL | Qt.Modifier.SHIFT, Qt.Key.Key_C), self)
        sc_cloze.activated.connect(self._insert_cloze)

        sc_save = QShortcut(QKeySequence("Ctrl+Return"), self)
        sc_save.activated.connect(self.accept)

    def _resolve_initial_field_value(self, field_name: str) -> str:
        """Résout la valeur initiale d'un champ avec repli gracieux sur les synonymes courants."""
        if field_name in self.card_data:
            return str(self.card_data[field_name])

        f_lower = field_name.lower().strip()
        lower_data = {str(k).lower().strip(): v for k, v in self.card_data.items()}

        if f_lower in lower_data:
            return str(lower_data[f_lower])

        if f_lower in ("front", "recto"):
            for alias in ("front", "recto", "texte"):
                if alias in lower_data:
                    return str(lower_data[alias])
        elif f_lower in ("back", "verso"):
            for alias in ("back", "verso", "remarques extra", "extra"):
                if alias in lower_data:
                    return str(lower_data[alias])
        elif f_lower in ("texte",):
            for alias in ("texte", "front", "recto"):
                if alias in lower_data:
                    return str(lower_data[alias])
        elif f_lower in ("remarques extra", "remarques", "extra"):
            for alias in ("remarques extra", "remarques", "extra", "back", "verso"):
                if alias in lower_data:
                    return str(lower_data[alias])

        return ""

    def _set_last_focused(self, field_name: str) -> None:
        self._last_focused_field = field_name

    def _get_active_editor(self) -> StyledTextEdit | None:
        if self._last_focused_field and self._last_focused_field in self.field_edits:
            return self.field_edits[self._last_focused_field]
        for edit in self.field_edits.values():
            if edit.hasFocus():
                return edit
        return list(self.field_edits.values())[0] if self.field_edits else None

    def _wrap_selection(self, prefix: str, suffix: str) -> None:
        edit = self._get_active_editor()
        if not edit:
            return
        cursor = edit.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            cursor.insertText(f"{prefix}{selected}{suffix}")
        else:
            pos = cursor.position()
            cursor.insertText(f"{prefix}{suffix}")
            cursor.setPosition(pos + len(prefix))
            edit.setTextCursor(cursor)
        edit.setFocus()

    def _insert_text(self, text: str) -> None:
        edit = self._get_active_editor()
        if not edit:
            return
        cursor = edit.textCursor()
        cursor.insertText(text)
        edit.setFocus()

    def _insert_cloze(self) -> None:
        all_text = " ".join(edit.toPlainText() for edit in self.field_edits.values())
        max_idx = get_max_cloze_index({"_all": all_text})
        next_idx = max(1, max_idx + 1)
        self._wrap_selection(f"{{{{c{next_idx}::", "}}")

    def _toggle_preview_panel(self) -> None:
        visible = not self.right_panel.isVisible()
        self.right_panel.setVisible(visible)
        self.btn_toggle_preview.setIcon(load_phosphor_icon("ph.eye" if visible else "ph.eye-slash", color=DesignTokens.TEXT_PRIMARY))

    def _on_field_text_changed(self) -> None:
        self._preview_timer.start()

    def _update_live_preview(self) -> None:
        if not hasattr(self, "preview_widget") or not self.preview_widget.isVisible():
            return
        fields = self.get_fields()
        self.preview_widget.update_preview(
            note_type=self.note_type,
            fields_dict=fields,
            override_templates=None,
        )

    def get_fields(self) -> dict[str, str]:
        """Retourne l'ensemble des champs modifiés sous forme de dictionnaire."""
        return {f_name: edit.toPlainText().strip() for f_name, edit in self.field_edits.items()}

    def get_data(self) -> tuple[str, str]:
        """Méthode rétrocompatible retournant le premier et le second champ."""
        vals = list(self.get_fields().values())
        return (vals[0] if len(vals) > 0 else "", vals[1] if len(vals) > 1 else "")

    def cleanup(self) -> None:
        """Libère les ressources WebEngine de l'aperçu en direct."""
        if hasattr(self, "preview_widget"):
            self.preview_widget.cleanup()

    def closeEvent(self, event: Any) -> None:
        self.cleanup()
        super().closeEvent(event)

    def reject(self) -> None:
        self.cleanup()
        super().reject()

    def accept(self) -> None:
        self.cleanup()
        super().accept()
