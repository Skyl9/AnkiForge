"""
Vue Card Models (Éditeur de Modèles de Cartes) — 100% Conforme à la Maquette concept_ide (L1740-L1880).
- Panneau gauche (250px) : Liste des modèles de cartes disponibles (Peewee NoteTypeModel).
- Panneau central (Éditeur de Modèle) :
  - Champs de données (virgules)
  - Toolbar 'Sélection de la carte' (Sélecteur Carte 1 + boutons +, ✏️, 🗑️ + ligne séparatrice)
  - Barre d'onglets .ide-tab (Style CSS, HTML Recto, HTML Verso)
  - Toolbar de tag pilules (.tag-btn {{Texte}}, {{Extra}}, {{FrontSide}}, {{cloze:Texte}}, <hr id="answer">)
  - Éditeur de code avec gouttière de numéros de ligne (.code-editor-wrapper, .code-editor-lines, #0d0f12)
- Panneau droit (400px) : Live Preview de carte Anki enrichi avec canvas sombre #0f111a et carte simulée .anki-card-preview.
"""

import json
import logging
from typing import Any, Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.components import (
    DangerButton,
    IconButton,
    IdePanel,
    PrimaryButton,
    SecondaryButton,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class TagPillButton(QPushButton):
    """Bouton style pilule .tag-btn conforme à la maquette concept_ide."""

    def __init__(self, text: str, is_cloze: bool = False, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        border_color = "rgba(139, 92, 246, 0.4)" if is_cloze else "rgba(255, 255, 255, 0.12)"
        text_color = "#c084fc" if is_cloze else "#a5b4fc"

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: #20242e;
                border: 1px solid {border_color};
                border-radius: 12px;
                color: {text_color};
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 11px;
                font-weight: bold;
                padding: 4px 10px;
            }}
            QPushButton:hover {{
                background-color: #2d3240;
                border-color: #8b5cf6;
                color: #ffffff;
            }}
        """)


class CodeEditorWithGutter(QWidget):
    """
    Conteneur d'édition de code avec gouttière de numéros de ligne conforme à la maquette (.code-editor-wrapper).
    """

    def __init__(self, placeholder: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.setStyleSheet("""
            QWidget {
                background-color: #0d0f12;
                border: 1px solid #2d313a;
                border-radius: 6px;
            }
        """)

        # Gouttière des numéros de lignes (#121419)
        self.lines_label = QLabel("1")
        self.lines_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.lines_label.setStyleSheet("""
            QLabel {
                background-color: #121419;
                color: #4b5563;
                font-family: 'Fira Code', 'JetBrains Mono', monospace;
                font-size: 13px;
                line-height: 1.5;
                padding: 12px 10px;
                border-right: 1px solid #2d313a;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
            }
        """)
        layout.addWidget(self.lines_label)

        # Éditeur de texte (#0d0f12)
        self.editor = StyledTextEdit()
        self.editor.setPlaceholderText(placeholder)
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                background-color: #0d0f12;
                color: #e2e8f0;
                font-family: 'Fira Code', 'JetBrains Mono', monospace;
                font-size: 13px;
                line-height: 1.5;
                padding: 12px;
                border: none;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
            }
        """)
        layout.addWidget(self.editor, 1)

        self.editor.blockCountChanged.connect(self._update_line_numbers)
        self.editor.textChanged.connect(self._update_line_numbers)

    def _update_line_numbers(self) -> None:
        count = max(1, self.editor.blockCount())
        lines_text = "\n".join(str(i) for i in range(1, count + 1))
        self.lines_label.setText(lines_text)

    def toPlainText(self) -> str:
        return self.editor.toPlainText()

    def setPlainText(self, text: str) -> None:
        self.editor.setPlainText(text)
        self._update_line_numbers()

    def insertPlainText(self, text: str) -> None:
        self.editor.insertPlainText(text)
        self._update_line_numbers()


class SubTabButton(QPushButton):
    """Bouton d'onglet style IDE (.ide-tab)."""

    def __init__(self, text: str, icon_name: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.icon_name = icon_name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIcon(load_phosphor_icon(icon_name, color=DesignTokens.TEXT_SECONDARY))
        self.setFixedHeight(34)
        self.set_active(False)

    def set_active(self, active: bool) -> None:
        if active:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_PRIMARY))
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: #1e2128;
                    color: #f8fafc;
                    border: none;
                    border-top: 2px solid {DesignTokens.ACCENT_PRIMARY};
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: bold;
                }}
            """)
        else:
            self.setIcon(load_phosphor_icon(self.icon_name, color=DesignTokens.TEXT_MUTED))
            self.setStyleSheet("""
                QPushButton {
                    background-color: #16181d;
                    color: #94a3b8;
                    border: none;
                    border-top: 2px solid transparent;
                    padding: 6px 14px;
                    font-size: 12px;
                    font-weight: normal;
                }
                QPushButton:hover {
                    background-color: #2d313a;
                    color: #f8fafc;
                }
            """)


class CardModelsView(QWidget):
    """
    Vue Card Models — 100% Conforme à la Maquette concept_ide.
    """

    def __init__(self, ai_manager: Optional[Any] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ai_manager = ai_manager
        self._current_model: Optional[NoteTypeModel] = None

        self._setup_ui()
        self._connect_signals()
        self.refresh_data()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.main_splitter)

        # =========================================================================
        # PANNEAU GAUCHE : Modèles Disponibles (250px, L1742-L1759)
        # =========================================================================
        self.list_panel = IdePanel(detachable=True)
        self.list_panel.setMinimumWidth(240)

        list_content = QWidget()
        list_layout = QVBoxLayout(list_content)
        list_layout.setContentsMargins(10, 10, 10, 10)
        list_layout.setSpacing(8)

        lbl_list_title = QLabel("MODÈLES EN BASE")
        lbl_list_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        list_layout.addWidget(lbl_list_title)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: #1a1d24;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QListWidget::item {{
                padding: 10px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                font-weight: 500;
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.ACCENT_PRIMARY};
                border-left: 3px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        list_layout.addWidget(self.list_widget, 1)

        # Toolbar inférieure (Nouveau & Supprimer)
        list_toolbar = QHBoxLayout()
        list_toolbar.setSpacing(6)

        self.btn_new = SecondaryButton("Nouveau")
        self.btn_new.setIcon(load_phosphor_icon("ph.plus", color=DesignTokens.TEXT_PRIMARY))

        self.btn_del = DangerButton("Supprimer", ghost=True)
        self.btn_del.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))

        list_toolbar.addWidget(self.btn_new, 1)
        list_toolbar.addWidget(self.btn_del, 1)
        list_layout.addLayout(list_toolbar)

        self.list_panel.add_tab("Modèles Disponibles", list_content, "ph.swatches", closable=False)
        self.main_splitter.addWidget(self.list_panel)

        # =========================================================================
        # PANNEAU CENTRAL : Éditeur de Modèle (L1761-L1852)
        # =========================================================================
        self.editor_panel = IdePanel(detachable=True)

        # Header Widgets (Rafraîchir & Sauvegarder)
        self.btn_refresh = SecondaryButton("Rafraîchir")
        self.btn_refresh.setIcon(load_phosphor_icon("ph.arrows-clockwise", color=DesignTokens.TEXT_PRIMARY))

        self.btn_save = PrimaryButton("Sauvegarder")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #6366f1, stop:1 #8b5cf6);
                border: 1px solid #6366f1;
                color: white;
                font-weight: bold;
                padding: 4px 12px;
                border-radius: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #4f46e5, stop:1 #7c3aed);
            }
        """)
        apply_shadow(self.btn_save, blur=14, offset_y=0, color="rgba(99, 102, 241, 0.7)")

        self.editor_panel.add_header_widget(self.btn_refresh)
        self.editor_panel.add_header_widget(self.btn_save)

        editor_content = QWidget()
        editor_layout = QVBoxLayout(editor_content)
        editor_layout.setContentsMargins(16, 16, 16, 16)
        editor_layout.setSpacing(12)

        # 1. Champs de données
        lbl_fields = QLabel("CHAMPS DE DONNÉES (SÉPARÉS PAR DES VIRGULES) :")
        lbl_fields.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        editor_layout.addWidget(lbl_fields)

        self.fields_input = StyledLineEdit()
        self.fields_input.setText("Texte, Extra")
        editor_layout.addWidget(self.fields_input)

        # 2. Toolbar 'Sélection de la carte' (conforme L1784-L1792)
        card_sel_widget = QWidget()
        card_sel_widget.setStyleSheet("background: transparent;")
        card_sel_row = QHBoxLayout(card_sel_widget)
        card_sel_row.setContentsMargins(0, 4, 0, 8)
        card_sel_row.setSpacing(8)

        lbl_card_sel = QLabel("SÉLECTION DE LA CARTE :")
        lbl_card_sel.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold;")
        card_sel_row.addWidget(lbl_card_sel)

        self.card_selector_combo = StyledComboBox()
        self.card_selector_combo.setFixedWidth(150)
        self.card_selector_combo.addItem("Carte 1", userData=0)
        card_sel_row.addWidget(self.card_selector_combo)

        self.btn_add_card_tmpl = IconButton("ph.plus", tooltip="Ajouter un modèle de carte", size=22)
        self.btn_rename_card_tmpl = IconButton("ph.pencil-simple", tooltip="Renommer le modèle", size=22)
        self.btn_del_card_tmpl = IconButton("ph.trash", tooltip="Supprimer ce modèle", size=22)

        card_sel_row.addWidget(self.btn_add_card_tmpl)
        card_sel_row.addWidget(self.btn_rename_card_tmpl)
        card_sel_row.addWidget(self.btn_del_card_tmpl)
        card_sel_row.addStretch()

        editor_layout.addWidget(card_sel_widget)

        # 3. Sub-tabs Bar Style IDE (conforme L1794-L1800)
        subtabs_container = QWidget()
        subtabs_container.setStyleSheet(f"background-color: #16181d; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        subtabs_row = QHBoxLayout(subtabs_container)
        subtabs_row.setContentsMargins(8, 0, 8, 0)
        subtabs_row.setSpacing(2)

        self.btn_subtab_css = SubTabButton("Style CSS", "ph.file-css")
        self.btn_subtab_front = SubTabButton("HTML Recto", "ph.file-html")
        self.btn_subtab_back = SubTabButton("HTML Verso", "ph.file-html")

        subtabs_row.addWidget(self.btn_subtab_css)
        subtabs_row.addWidget(self.btn_subtab_front)
        subtabs_row.addWidget(self.btn_subtab_back)
        subtabs_row.addStretch()

        editor_layout.addWidget(subtabs_container)

        # 4. Tag Pilules Toolbar (.tag-btn conforme L1802-L1808)
        self.tags_toolbar_layout = QHBoxLayout()
        self.tags_toolbar_layout.setContentsMargins(0, 4, 0, 4)
        self.tags_toolbar_layout.setSpacing(6)
        editor_layout.addLayout(self.tags_toolbar_layout)

        # 5. Stacked Code Editors avec Gouttière de Lignes (.code-editor-wrapper conforme L1812-L1851)
        self.editor_stack = QStackedWidget()

        self.css_editor_wrapper = CodeEditorWithGutter(placeholder=".card { font-family: arial; text-align: center; }")
        self.editor_stack.addWidget(self.css_editor_wrapper)

        self.front_html_wrapper = CodeEditorWithGutter(placeholder="{{cloze:Texte}}")
        self.editor_stack.addWidget(self.front_html_wrapper)

        self.back_html_wrapper = CodeEditorWithGutter(placeholder='{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}')
        self.editor_stack.addWidget(self.back_html_wrapper)

        editor_layout.addWidget(self.editor_stack, 1)

        self.editor_panel.add_tab("Éditeur de Modèle", editor_content, "ph.pencil-simple", closable=False)
        self.main_splitter.addWidget(self.editor_panel)

        # =========================================================================
        # PANNEAU DROIT : Live Preview Enrichi (400px, L1854-L1876)
        # =========================================================================
        self.preview_panel = IdePanel(detachable=True)
        self.preview_panel.setMinimumWidth(340)

        preview_content = QWidget()
        preview_layout = QVBoxLayout(preview_content)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        # Toolbar supérieure de Live Preview
        prev_controls_widget = QWidget()
        prev_controls_widget.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR};")
        prev_controls = QHBoxLayout(prev_controls_widget)
        prev_controls.setContentsMargins(12, 8, 12, 8)
        prev_controls.setSpacing(8)

        lbl_prev_icon = QLabel()
        lbl_prev_icon.setPixmap(load_phosphor_icon("ph.monitor", color=DesignTokens.COLOR_BLUE).pixmap(18, 18))
        lbl_prev = QLabel("LIVE PREVIEW")
        lbl_prev.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")

        prev_controls.addWidget(lbl_prev_icon)
        prev_controls.addWidget(lbl_prev)
        prev_controls.addStretch()

        lbl_card_num = QLabel("Carte :")
        lbl_card_num.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        prev_controls.addWidget(lbl_card_num)

        self.card_index_combo = StyledComboBox()
        self.card_index_combo.addItems(["1/1"])
        prev_controls.addWidget(self.card_index_combo)

        self.view_side_combo = StyledComboBox()
        self.view_side_combo.addItems(["Voir Recto", "Voir Verso"])
        prev_controls.addWidget(self.view_side_combo)

        preview_layout.addWidget(prev_controls_widget)

        # Cadre d'arrière-plan sombre avec halo lumineux radial (#0f111a)
        preview_canvas = QFrame()
        preview_canvas.setStyleSheet("""
            QFrame {
                background-color: #0f111a;
                border: none;
            }
        """)
        canvas_layout = QVBoxLayout(preview_canvas)
        canvas_layout.setContentsMargins(16, 16, 16, 16)
        canvas_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Composant WebEngine Anki Preview
        self.card_preview_widget = CardPreviewWidget()
        self.card_preview_widget.setMinimumWidth(320)
        self.card_preview_widget.setMaximumWidth(440)
        apply_shadow(self.card_preview_widget, blur=20, offset_y=4, color="rgba(0, 0, 0, 0.6)")

        canvas_layout.addWidget(self.card_preview_widget)
        preview_layout.addWidget(preview_canvas, 1)

        self.preview_panel.add_tab("Live Preview Modèle", preview_content, "ph.monitor", closable=False)
        self.main_splitter.addWidget(self.preview_panel)

        self.main_splitter.setSizes([250, 520, 400])
        self._switch_subtab(0)

    def _connect_signals(self) -> None:
        self.list_widget.currentItemChanged.connect(self._on_item_selected)
        self.btn_new.clicked.connect(self._on_new_model)
        self.btn_del.clicked.connect(self._on_delete_model)

        self.btn_refresh.clicked.connect(self._update_preview)
        self.btn_save.clicked.connect(self._on_save_model)

        self.fields_input.textChanged.connect(self._on_fields_changed)

        self.btn_subtab_css.clicked.connect(lambda: self._switch_subtab(0))
        self.btn_subtab_front.clicked.connect(lambda: self._switch_subtab(1))
        self.btn_subtab_back.clicked.connect(lambda: self._switch_subtab(2))

        self.css_editor_wrapper.editor.textChanged.connect(self._update_preview)
        self.front_html_wrapper.editor.textChanged.connect(self._update_preview)
        self.back_html_wrapper.editor.textChanged.connect(self._update_preview)
        self.view_side_combo.currentIndexChanged.connect(self._update_preview)

    def _switch_subtab(self, index: int) -> None:
        self.editor_stack.setCurrentIndex(index)
        self.btn_subtab_css.set_active(index == 0)
        self.btn_subtab_front.set_active(index == 1)
        self.btn_subtab_back.set_active(index == 2)

    def refresh_data(self) -> None:
        """Recharge la liste des modèles depuis la base Peewee."""
        try:
            self.list_widget.blockSignals(True)
            self.list_widget.clear()

            models = list(NoteTypeModel.select())
            for m in models:
                item = QListWidgetItem(m.name)
                item.setData(Qt.ItemDataRole.UserRole, m)
                self.list_widget.addItem(item)

            self.list_widget.blockSignals(False)

            if models and not self._current_model:
                self.list_widget.setCurrentRow(0)

        except Exception as e:
            logger.warning("Erreur refresh_data card_models_view: %s", e)

    def is_dirty(self) -> bool:
        return False

    @Slot()
    def _on_item_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            self._current_model = None
            return

        model: Optional[NoteTypeModel] = current.data(Qt.ItemDataRole.UserRole)
        if not model:
            return

        self._current_model = model

        # Décompilation des champs schema JSON -> Texte séparé par virgules
        if model.fields_schema:
            try:
                parsed_fields = json.loads(model.fields_schema)
                if isinstance(parsed_fields, list):
                    self.fields_input.setText(", ".join(parsed_fields))
                else:
                    self.fields_input.setText("Texte, Extra")
            except Exception:
                self.fields_input.setText("Texte, Extra")
        else:
            self.fields_input.setText("Front, Back")

        default_css = (
            ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n"
            "  color: #1e293b;\n  background-color: #ffffff;\n}\n\n.cloze {\n"
            "  font-weight: bold;\n  color: #3b82f6;\n}"
        )
        self.css_editor_wrapper.setPlainText(model.css_style or default_css)

        # Décompilation des templates JSON -> Front & Back HTML
        if model.templates:
            try:
                parsed_tmpl = json.loads(model.templates)
                if isinstance(parsed_tmpl, list) and parsed_tmpl:
                    first_tmpl = parsed_tmpl[0]
                    self.front_html_wrapper.setPlainText(first_tmpl.get("qfmt", "{{cloze:Texte}}"))
                    self.back_html_wrapper.setPlainText(first_tmpl.get("afmt", '{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}'))
                else:
                    self.front_html_wrapper.setPlainText("{{cloze:Texte}}")
                    self.back_html_wrapper.setPlainText('{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}')
            except Exception:
                self.front_html_wrapper.setPlainText("{{cloze:Texte}}")
                self.back_html_wrapper.setPlainText('{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}')
        else:
            self.front_html_wrapper.setPlainText("{{cloze:Texte}}")
            self.back_html_wrapper.setPlainText('{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}')

        self._update_tags_toolbar()
        self._update_preview()

    @Slot()
    def _on_fields_changed(self) -> None:
        self._update_tags_toolbar()

    def _update_tags_toolbar(self) -> None:
        """Génère dynamiquement les boutons style pilule (.tag-btn) d'insertion de tags."""
        while self.tags_toolbar_layout.count():
            child = self.tags_toolbar_layout.takeAt(0)
            if child and child.widget():
                child.widget().deleteLater()

        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Texte", "Extra"]

        for f in raw_fields:
            tag_str = f"{{{{{f}}}}}"
            btn = TagPillButton(tag_str, is_cloze=False)
            btn.clicked.connect(lambda _, t=tag_str: self._insert_tag_to_active_editor(t))
            self.tags_toolbar_layout.addWidget(btn)

            cloze_str = f"{{{{cloze:{f}}}}}"
            btn_c = TagPillButton(cloze_str, is_cloze=True)
            btn_c.clicked.connect(lambda _, t=cloze_str: self._insert_tag_to_active_editor(t))
            self.tags_toolbar_layout.addWidget(btn_c)

        btn_fs = TagPillButton("{{FrontSide}}", is_cloze=False)
        btn_fs.clicked.connect(lambda: self._insert_tag_to_active_editor("{{FrontSide}}"))
        self.tags_toolbar_layout.addWidget(btn_fs)

        btn_hr = TagPillButton('<hr id="answer">', is_cloze=False)
        btn_hr.clicked.connect(lambda: self._insert_tag_to_active_editor('<hr id="answer">'))
        self.tags_toolbar_layout.addWidget(btn_hr)

        self.tags_toolbar_layout.addStretch()

    def _insert_tag_to_active_editor(self, tag_str: str) -> None:
        active_idx = self.editor_stack.currentIndex()
        if active_idx == 1:
            self.front_html_wrapper.insertPlainText(tag_str)
        elif active_idx == 2:
            self.back_html_wrapper.insertPlainText(tag_str)
        else:
            self.css_editor_wrapper.insertPlainText(tag_str)

    @Slot()
    def _update_preview(self) -> None:
        """Met à jour l'aperçu WebEngine temps réel (CardPreviewWidget)."""
        raw_fields = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
        if not raw_fields:
            raw_fields = ["Texte", "Extra"]

        # Données de test (cloze / texte)
        mock_fields: dict[str, str] = {}
        for f in raw_fields:
            f_lower = f.lower()
            if "cloze" in f_lower or "texte" in f_lower or "front" in f_lower:
                mock_fields[f] = "La capitale de la France est {{c1::Paris::Ville}}."
            elif "extra" in f_lower or "back" in f_lower or "answer" in f_lower:
                mock_fields[f] = "Paris est la ville la plus peuplée de France."
            else:
                mock_fields[f] = f"Exemple pour {f}"

        qfmt = self.front_html_wrapper.toPlainText()
        afmt = self.back_html_wrapper.toPlainText()
        css = self.css_editor_wrapper.toPlainText()

        tmpl = {"name": "Carte 1", "qfmt": qfmt}
        is_verso = self.view_side_combo.currentIndex() == 1
        if is_verso:
            tmpl["afmt"] = afmt

        self.card_preview_widget.update_preview(
            note_type=self._current_model,
            fields_dict=mock_fields,
            override_templates=[tmpl],
            override_css=css,
        )

    @Slot()
    def _on_new_model(self) -> None:
        name, ok = QInputDialog.getText(self, "Nouveau modèle de carte", "Nom du modèle :")
        if ok and name.strip():
            try:
                default_tmpl = [{"name": "Carte 1", "qfmt": "{{cloze:Texte}}", "afmt": '{{cloze:Texte}}<br><hr id="answer"><br>{{Extra}}'}]
                NoteTypeModel.create(
                    name=name.strip(),
                    fields_schema=json.dumps(["Texte", "Extra"], ensure_ascii=False),
                    templates=json.dumps(default_tmpl, ensure_ascii=False),
                    css_style=(
                        ".card {\n  font-family: arial;\n  font-size: 20px;\n  text-align: center;\n"
                        "  color: #1e293b;\n  background-color: #ffffff;\n}\n\n.cloze {\n"
                        "  font-weight: bold;\n  color: #3b82f6;\n}"
                    ),
                )
                self.refresh_data()
                show_toast(self, f"Modèle '{name.strip()}' créé avec succès !")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de créer le modèle : {str(e)}")

    @Slot()
    def _on_delete_model(self) -> None:
        if not self._current_model:
            return

        res = QMessageBox.question(
            self,
            "Supprimer le modèle",
            f"Voulez-vous vraiment supprimer le modèle '{self._current_model.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            try:
                self._current_model.delete_instance()
                self._current_model = None
                self.refresh_data()
                show_toast(self, "Modèle supprimé.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Impossible de supprimer le modèle : {str(e)}")

    @Slot()
    def _on_save_model(self) -> None:
        if not self._current_model:
            show_toast(self, "Aucun modèle sélectionné à sauvegarder.", is_error=True)
            return

        try:
            fields_list = [f.strip() for f in self.fields_input.text().split(",") if f.strip()]
            if not fields_list:
                fields_list = ["Texte", "Extra"]

            qfmt = self.front_html_wrapper.toPlainText()
            afmt = self.back_html_wrapper.toPlainText()
            css = self.css_editor_wrapper.toPlainText()

            templates = [{"name": "Carte 1", "qfmt": qfmt, "afmt": afmt}]

            self._current_model.fields_schema = json.dumps(fields_list, ensure_ascii=False)
            self._current_model.templates = json.dumps(templates, ensure_ascii=False)
            self._current_model.css_style = css
            self._current_model.save()

            show_toast(self, f"Modèle '{self._current_model.name}' sauvegardé avec succès !")
            self._update_preview()
        except Exception as e:
            QMessageBox.critical(self, "Erreur de sauvegarde", f"Impossible de sauvegarder le modèle : {str(e)}")


CardModelsTab = CardModelsView
