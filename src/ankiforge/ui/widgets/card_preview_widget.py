import json
from typing import Any, cast

from PySide6.QtCore import QUrl, Slot
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox

from ankiforge.database.models import NoteTypeModel
from ankiforge.ui.theme import is_dark_mode
from ankiforge.ui.widgets.cloze_manager import sync_preview_card_selector, get_preview_template
from ankiforge.ui.widgets.safe_web_preview import SafeWebEngineView
from ankiforge.utils.anki_renderer import render_anki_card, AnkiFields
from ankiforge.utils.paths import get_app_data_dir


class CardPreviewWidget(QWidget):
    """
    Composant réutilisable encapsulant la prévisualisation d'une carte Anki.
    Gère de manière autonome la bascule Recto/Verso, la sélection du template
    et le rendu HTML/MathJax via SafeWebEngineView.
    """

    def __init__(self, parent=None, show_header=True):
        super().__init__(parent)
        self.current_fields: dict[str, str] = {}
        self.current_templates: list[dict[str, Any]] = []
        self.current_css: str = ""

        self._setup_ui(show_header)
        self._connect_signals()

    def _setup_ui(self, show_header: bool) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.controls_layout = QHBoxLayout()

        if show_header:
            lbl_preview = QLabel("PRÉVISUALISATION :")
            lbl_preview.setStyleSheet("font-weight: bold; color: palette(placeholder-text); font-size: 11px; text-transform: uppercase; letter-spacing: 1px;")
            self.controls_layout.addWidget(lbl_preview)

        self.card_selector = QComboBox()
        self.card_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.card_selector.setMinimumWidth(130)

        self.side_selector = QComboBox()
        self.side_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.side_selector.setMinimumWidth(130)
        self.side_selector.addItems(["Voir Recto", "Voir Verso"])

        self.controls_layout.addWidget(self.card_selector)
        self.controls_layout.addWidget(self.side_selector)
        self.controls_layout.addStretch()

        layout.addLayout(self.controls_layout)

        self.web_view = SafeWebEngineView()
        layout.addWidget(self.web_view)

    def _connect_signals(self) -> None:
        self.card_selector.currentIndexChanged.connect(self._render)
        self.side_selector.currentIndexChanged.connect(self._render)

    def set_empty_state(self, message: str = "Sélectionnez un élément pour le prévisualiser.") -> None:
        """Affiche un message par défaut quand aucune carte n'est chargée."""
        text_color = "#8C8C8C" if is_dark_mode() else "#6E6E6E"
        placeholder = f"<div style='display: flex; height: 100vh; align-items: center; justify-content: center; color: {text_color}; font-family: sans-serif; text-align: center;'>{message}</div>"
        self.web_view.setHtmlSafe(placeholder)

    def update_preview(self, note_type: NoteTypeModel | None, fields_dict: dict[str, str], override_templates: list | None = None, override_css: str | None = None) -> None:
        """Met à jour les données et rafraîchit l'aperçu HTML."""
        if not note_type and not override_templates:
            self.set_empty_state()
            return

        self.current_fields = fields_dict

        if override_templates is not None:
            self.current_templates = override_templates
        else:
            self.current_templates = json.loads(cast(str, note_type.templates)) if note_type and note_type.templates else []

        if override_css is not None:
            self.current_css = override_css
        else:
            self.current_css = getattr(note_type, "css_style", "") or ""

        self.card_selector.blockSignals(True)
        is_cloze, selected_tmpl_idx = sync_preview_card_selector(
            selector=self.card_selector,
            templates=self.current_templates,
            current_fields=self.current_fields,
        )
        self.card_selector.blockSignals(False)

        self._render(is_cloze=is_cloze, selected_tmpl_idx=selected_tmpl_idx)

    @Slot()
    def _render(self, is_cloze: bool = False, selected_tmpl_idx: int = 0) -> None:
        """Génère le HTML final et l'injecte dans le navigateur WebEngine."""
        if not self.current_templates:
            return

        if is_cloze is None or selected_tmpl_idx is None:
            from ankiforge.ui.widgets.cloze_manager import is_template_cloze

            is_cloze = is_template_cloze(self.current_templates)
            selected_tmpl_idx = max(0, self.card_selector.currentIndex())

        tmpl, card_idx = get_preview_template(
            templates=self.current_templates,
            is_cloze=is_cloze,
            selected_index=selected_tmpl_idx,
        )

        is_recto = self.side_selector.currentIndex() == 0
        raw_html = tmpl.get("qfmt", "") if is_recto else tmpl.get("afmt", "")

        cur_fieds = AnkiFields(self.current_fields.copy())

        final_html = render_anki_card(
            raw_html=raw_html,
            css=self.current_css,
            fields_dict=cur_fieds,
            is_recto=is_recto,
            front_html=tmpl.get("qfmt", ""),
            is_dark_mode=is_dark_mode(),
            template_index=card_idx,
        )

        media_dir = get_app_data_dir() / "media"
        media_dir.mkdir(exist_ok=True)
        base_url = QUrl.fromLocalFile(str(media_dir) + "/")

        self.web_view.setHtmlSafe(final_html, base_url)

    def clear_memory(self) -> None:
        """Nettoie la RAM du moteur web."""
        self.web_view.clear_memory()
