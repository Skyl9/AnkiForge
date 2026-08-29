from typing import Any

import markdown
from PySide6.QtCore import QEvent, Qt, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.components import (
    Badge,
    DangerButton,
    IconButton,
    PrimaryButton,
    SecondaryButton,
    StyledTextEdit,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon


class DocumentEditorWidget(QWidget):
    """Conteneur pour l'éditeur de texte source et la barre d'outils de génération associée."""

    generate_requested = Signal(str, str)  # text_source, source_title
    cancel_requested = Signal()

    def __init__(self, content: str = "", source_title: str = "Saisie Libre", doc_model: Any | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.source_title = source_title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self.doc_model = doc_model
        self.pdf_document = None

        # --- Segmented Control pour vue PDF / Markdown ---
        self.view_toggle_frame = QFrame()
        self.view_toggle_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 2px;
            }}
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px 12px;
                color: {DesignTokens.TEXT_MUTED};
                font-weight: 500;
            }}
            QPushButton:checked {{
                background: {DesignTokens.ACCENT_PRIMARY};
                color: white;
            }}
        """)
        toggle_layout = QHBoxLayout(self.view_toggle_frame)
        toggle_layout.setContentsMargins(2, 2, 2, 2)
        toggle_layout.setSpacing(0)

        self.btn_view_pdf = QPushButton("PDF")
        self.btn_view_pdf.setCheckable(True)
        self.btn_view_pdf.setChecked(True)

        self.btn_view_md = QPushButton("Markdown Stylisé")
        self.btn_view_md.setCheckable(True)

        toggle_layout.addWidget(self.btn_view_pdf)
        toggle_layout.addWidget(self.btn_view_md)

        self.btn_view_pdf.clicked.connect(lambda: self._on_view_toggled("pdf"))
        self.btn_view_md.clicked.connect(lambda: self._on_view_toggled("md"))

        toggle_container = QHBoxLayout()
        toggle_container.addStretch()
        toggle_container.addWidget(self.view_toggle_frame)
        toggle_container.addStretch()
        layout.addLayout(toggle_container)

        self.view_toggle_frame.hide()

        self.editor_stack = QStackedWidget()

        # PDF Viewer Container avec bandeau de portée asservi
        self.pdf_container = QWidget()
        pdf_layout = QVBoxLayout(self.pdf_container)
        pdf_layout.setContentsMargins(0, 0, 0, 0)
        pdf_layout.setSpacing(6)

        self._pdf_selected_pages: list[int] = []

        # 1. Bandeau de Portée PDF
        self.pdf_scope_banner = QFrame()
        self.pdf_scope_banner.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 2px 6px;
            }}
        """)
        scope_banner_layout = QHBoxLayout(self.pdf_scope_banner)
        scope_banner_layout.setContentsMargins(6, 4, 6, 4)
        scope_banner_layout.setSpacing(8)

        ico_pdf_scope = QLabel()
        ico_pdf_scope.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.COLOR_BLUE).pixmap(14, 14))
        ico_pdf_scope.setStyleSheet("border: none; background: transparent;")

        self.lbl_pdf_scope_status = QLabel("Portée : Pages 1 à 10")
        self.lbl_pdf_scope_status.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-weight: 600; font-size: 11px; border: none; background: transparent;")

        self.badge_pdf_scope = Badge("Dans la portée", variant="success")

        scope_banner_layout.addWidget(ico_pdf_scope)
        scope_banner_layout.addWidget(self.lbl_pdf_scope_status)
        scope_banner_layout.addWidget(self.badge_pdf_scope)
        scope_banner_layout.addStretch()

        self.btn_pdf_scope_prev = IconButton("ph.caret-left", "Page précédente de la sélection", 16)
        self.btn_pdf_scope_prev.clicked.connect(self._on_pdf_scope_prev)

        self.lbl_pdf_scope_cur = QLabel("Page 1 / 10")
        self.lbl_pdf_scope_cur.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: 600; border: none; background: transparent;")

        self.btn_pdf_scope_next = IconButton("ph.caret-right", "Page suivante de la sélection", 16)
        self.btn_pdf_scope_next.clicked.connect(self._on_pdf_scope_next)

        scope_banner_layout.addWidget(self.btn_pdf_scope_prev)
        scope_banner_layout.addWidget(self.lbl_pdf_scope_cur)
        scope_banner_layout.addWidget(self.btn_pdf_scope_next)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {DesignTokens.BORDER_COLOR}; font-size: 11px; margin: 0 4px; background: transparent; border: none;")
        scope_banner_layout.addWidget(sep)

        self.btn_pdf_zoom_out = IconButton("ph.magnifying-glass-minus", "Dézoomer (Ctrl -)", 16)
        self.btn_pdf_zoom_out.clicked.connect(self._on_pdf_zoom_out)

        self.lbl_pdf_zoom = QLabel("100%")
        self.lbl_pdf_zoom.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: 600; min-width: 32px; background: transparent; border: none;")
        self.lbl_pdf_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.btn_pdf_zoom_in = IconButton("ph.magnifying-glass-plus", "Zoomer (Ctrl +)", 16)
        self.btn_pdf_zoom_in.clicked.connect(self._on_pdf_zoom_in)

        self.btn_pdf_fit_width = IconButton("ph.arrows-out-line-horizontal", "Ajuster à la largeur", 16)
        self.btn_pdf_fit_width.clicked.connect(self._on_pdf_fit_width)

        scope_banner_layout.addWidget(self.btn_pdf_zoom_out)
        scope_banner_layout.addWidget(self.lbl_pdf_zoom)
        scope_banner_layout.addWidget(self.btn_pdf_zoom_in)
        scope_banner_layout.addWidget(self.btn_pdf_fit_width)

        pdf_layout.addWidget(self.pdf_scope_banner)

        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_document = QPdfDocument(self)
            self.pdf_view = QPdfView()
            self.pdf_view.setDocument(self.pdf_document)
            self.pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
            if hasattr(self.pdf_view, "pageNavigator"):
                self.pdf_view.pageNavigator().currentPageChanged.connect(self._on_pdf_page_changed)
            if hasattr(self.pdf_view, "viewport"):
                self.pdf_view.viewport().installEventFilter(self)
            self.pdf_view.installEventFilter(self)
            pdf_layout.addWidget(self.pdf_view, 1)
        except ImportError:
            self.pdf_view = QWidget()
            pdf_layout.addWidget(self.pdf_view, 1)

        self.editor_stack.addWidget(self.pdf_container)

        self.raw_editor = StyledTextEdit()
        self.raw_editor.setStyleSheet(f"font-family: '{DesignTokens.FONT_CODE}';")
        self.raw_editor.setPlaceholderText("Saisissez ou collez directement votre extrait de cours ici (ex: notes de cours, résumés, chapitres PDF)...")
        self.raw_editor.textChanged.connect(self._on_text_changed)

        self.markdown_viewer = QTextBrowser()
        self.markdown_viewer.setOpenExternalLinks(True)
        self.markdown_viewer.setStyleSheet(
            f"background-color: {DesignTokens.BG_INPUT}; "
            f"color: {DesignTokens.TEXT_PRIMARY}; "
            f"border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: {DesignTokens.RADIUS_SM}px; "
            f"padding: 12px; "
            f"font-family: '{DesignTokens.FONT_MAIN}';"
        )

        self.editor_stack.addWidget(self.raw_editor)
        self.editor_stack.addWidget(self.markdown_viewer)

        if self.doc_model and getattr(self.doc_model, "file_type", "") == "pdf" and getattr(self.doc_model, "original_media", None):
            from ankiforge.utils.paths import get_app_data_dir

            pdf_path = get_app_data_dir() / "media" / self.doc_model.original_media.filename
            if pdf_path.exists() and self.pdf_document is not None:
                self.pdf_document.load(str(pdf_path))
                self.view_toggle_frame.show()
                self._on_view_toggled("pdf")
        layout.addWidget(self.editor_stack, 1)

        bot_widget = QWidget()
        bot_widget.setStyleSheet("background: transparent;")
        bot_layout = QHBoxLayout(bot_widget)
        bot_layout.setContentsMargins(0, 8, 0, 0)

        self.tokens_lbl = QLabel("Aa 0 chars  |  ~0 Tokens")
        self.tokens_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-family: '{DesignTokens.FONT_CODE}'; font-size: 11px;")
        bot_layout.addWidget(self.tokens_lbl)
        bot_layout.addStretch()

        self.btn_paste = SecondaryButton("Coller")
        self.btn_paste.setIcon(load_phosphor_icon("ph.clipboard", color=DesignTokens.TEXT_PRIMARY))
        self.btn_paste.clicked.connect(self.raw_editor.paste)

        self.btn_generate = PrimaryButton("Générer (Ctrl+Enter)")
        self.btn_generate.setIcon(load_phosphor_icon("ph.play", color="white"))
        self.btn_generate.clicked.connect(self._on_generate_clicked)

        self.btn_cancel = DangerButton("Arrêter", ghost=True)
        self.btn_cancel.setIcon(load_phosphor_icon("ph.stop-circle", color=DesignTokens.COLOR_RED))
        self.btn_cancel.hide()
        self.btn_cancel.clicked.connect(self.cancel_requested.emit)

        bot_layout.addWidget(self.btn_paste)
        bot_layout.addWidget(self.btn_generate)
        bot_layout.addWidget(self.btn_cancel)
        layout.addWidget(bot_widget)

        self.set_content(content)

    @Slot(str)
    def _on_view_toggled(self, mode: str) -> None:
        self.btn_view_pdf.setChecked(mode == "pdf")
        self.btn_view_md.setChecked(mode == "md")

        if mode == "pdf":
            self.editor_stack.setCurrentWidget(self.pdf_container)
        else:
            self.editor_stack.setCurrentWidget(self.markdown_viewer)

    def set_pdf_scope(self, pages: list[int]) -> None:
        """Met à jour la portée active du PDF et asservit le bandeau de navigation."""
        self._pdf_selected_pages = sorted(pages)
        if not self._pdf_selected_pages:
            self.lbl_pdf_scope_status.setText("Aucune page sélectionnée")
            self.badge_pdf_scope.setText("0 page")
            self.badge_pdf_scope.set_variant("danger")
            return

        count = len(self._pdf_selected_pages)
        first_p = self._pdf_selected_pages[0]
        last_p = self._pdf_selected_pages[-1]

        if count == 1:
            self.lbl_pdf_scope_status.setText(f"Portée : Page {first_p}")
        else:
            self.lbl_pdf_scope_status.setText(f"Portée : Pages {first_p} à {last_p} ({count} pages)")

        self.jump_pdf_to_page(first_p - 1)
        self._update_scope_indicator(first_p - 1)

    @Slot(int)
    def _on_pdf_page_changed(self, current_page_idx: int) -> None:
        self._update_scope_indicator(current_page_idx)

    def _update_scope_indicator(self, current_page_idx: int) -> None:
        if not self._pdf_selected_pages:
            return

        current_1_based = current_page_idx + 1
        if current_1_based in self._pdf_selected_pages:
            idx_in_scope = self._pdf_selected_pages.index(current_1_based) + 1
            self.badge_pdf_scope.setText("Dans la portée")
            self.badge_pdf_scope.set_variant("success")
            self.lbl_pdf_scope_cur.setText(f"Sélection {idx_in_scope} / {len(self._pdf_selected_pages)} (p. {current_1_based})")
        else:
            self.badge_pdf_scope.setText(f"Hors-portée (p. {current_1_based})")
            self.badge_pdf_scope.set_variant("warning")
            self.lbl_pdf_scope_cur.setText(f"Page {current_1_based}")

    @Slot()
    def _on_pdf_scope_prev(self) -> None:
        if not self._pdf_selected_pages or not hasattr(self, "pdf_view") or not hasattr(self.pdf_view, "pageNavigator"):
            return
        cur_p = self.pdf_view.pageNavigator().currentPage() + 1
        prev_candidates = [p for p in self._pdf_selected_pages if p < cur_p]
        if prev_candidates:
            self.jump_pdf_to_page(prev_candidates[-1] - 1)
        else:
            self.jump_pdf_to_page(self._pdf_selected_pages[0] - 1)

    @Slot()
    def _on_pdf_scope_next(self) -> None:
        if not self._pdf_selected_pages or not hasattr(self, "pdf_view") or not hasattr(self.pdf_view, "pageNavigator"):
            return
        cur_p = self.pdf_view.pageNavigator().currentPage() + 1
        next_candidates = [p for p in self._pdf_selected_pages if p > cur_p]
        if next_candidates:
            self.jump_pdf_to_page(next_candidates[0] - 1)
        else:
            self.jump_pdf_to_page(self._pdf_selected_pages[-1] - 1)

    @Slot()
    def _on_pdf_zoom_in(self) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "setZoomFactor"):
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            new_factor = min(3.0, self.pdf_view.zoomFactor() * 1.2)
            self.pdf_view.setZoomFactor(new_factor)
            self.lbl_pdf_zoom.setText(f"{int(new_factor * 100)}%")

    @Slot()
    def _on_pdf_zoom_out(self) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "setZoomFactor"):
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_view.setZoomMode(QPdfView.ZoomMode.Custom)
            new_factor = max(0.4, self.pdf_view.zoomFactor() / 1.2)
            self.pdf_view.setZoomFactor(new_factor)
            self.lbl_pdf_zoom.setText(f"{int(new_factor * 100)}%")

    @Slot()
    def _on_pdf_fit_width(self) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "setZoomMode"):
            from PySide6.QtPdfWidgets import QPdfView

            self.pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.lbl_pdf_zoom.setText("Auto")

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if hasattr(self, "pdf_view") and (obj == self.pdf_view or (hasattr(self.pdf_view, "viewport") and obj == self.pdf_view.viewport())) and event.type() == QEvent.Type.Wheel:
            modifiers = event.modifiers()
            if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
                delta = event.angleDelta().y()
                if delta > 0:
                    self._on_pdf_zoom_in()
                elif delta < 0:
                    self._on_pdf_zoom_out()
                return True
        return super().eventFilter(obj, event)

    def jump_pdf_to_page(self, page_index: int) -> None:
        if hasattr(self, "pdf_view") and hasattr(self.pdf_view, "pageNavigator"):
            from PySide6.QtCore import QPointF

            self.pdf_view.pageNavigator().jump(page_index, QPointF(0, 0), self.pdf_view.zoomFactor())

    def set_content(self, content: str) -> None:
        if self.source_title == "Saisie Libre":
            self.editor_stack.setCurrentWidget(self.raw_editor)
            self.raw_editor.setPlainText(content)
        else:
            html = markdown.markdown(content, extensions=["fenced_code", "tables"])
            self.markdown_viewer.setHtml(html)
            if hasattr(self, "btn_view_pdf") and self.btn_view_pdf.isChecked():
                self.editor_stack.setCurrentWidget(self.pdf_container)
            else:
                if hasattr(self, "btn_view_md"):
                    self.btn_view_md.setChecked(True)
                self.editor_stack.setCurrentWidget(self.markdown_viewer)
        self._on_text_changed()

    @Slot()
    def _on_text_changed(self) -> None:
        text = self.get_text()
        chars = len(text)
        words = len(text.split())
        estimated_tokens = int(words * 1.3)
        self.tokens_lbl.setText(f"Aa {chars} chars  |  ~{estimated_tokens} Tokens")

    @Slot()
    def _on_generate_clicked(self) -> None:
        self.generate_requested.emit(self.get_text(), getattr(self, "source_title", "Saisie Libre"))

    def get_text(self) -> str:
        if self.source_title == "Saisie Libre":
            return self.raw_editor.toPlainText().strip()
        else:
            return self.markdown_viewer.toPlainText().strip()

    def set_generation_state(self, is_generating: bool) -> None:
        self.btn_generate.setEnabled(not is_generating)
        if is_generating:
            self.btn_generate.hide()
            self.btn_cancel.show()
        else:
            self.btn_generate.show()
            self.btn_cancel.hide()
