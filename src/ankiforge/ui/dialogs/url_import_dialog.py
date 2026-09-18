"""Dialogue d'import web fonctionnel : lot d'URLs, options, prévisualisation,
gestion des cas limites (anti-bot, SPA, paywall) et dédoublonnage.

Produit des DocumentModel(file_type="web") directement réutilisables par les
pipelines de génération de cartes (Studio de Création).
"""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ankiforge.repositories.document_repository import DocumentRepository
from ankiforge.services.parsing.web_importer import WebImporter, WebImportError, WebImportRequest, WebImportResult, payload_to_result
from ankiforge.services.workers.url_import_worker import UrlImportTask, UrlImportWorker
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)

_JS_RETRY_CATEGORIES = {"empty_dynamic", "render_js_required"}


class UrlImportDialog(QDialog):
    """Dialogue modal d'import de pages web (une ou plusieurs URLs par lot)."""

    import_completed = Signal(list)
    cards_requested = Signal(int)

    def __init__(self, parent: Any | None = None) -> None:
        super().__init__(parent)
        self.doc_repo = DocumentRepository()
        self._rows: dict[int, dict[str, Any]] = {}
        self._worker: UrlImportWorker | None = None
        self._js_pending: list[int] = []
        self._pending_titles: dict[int, str] = {}

        self.setWindowTitle("Importer depuis le Web")
        self.resize(880, 620)

        self._setup_ui()
        self._populate_folders()

    # ── Construction UI ───────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        self.setStyleSheet(f"background-color: {DesignTokens.BG_MAIN};")

        header = QHBoxLayout()
        header.setSpacing(10)
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.link", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        icon_lbl.setStyleSheet("border: none; background: transparent;")

        title_box = QVBoxLayout()
        title_lbl = QLabel("Importer depuis le Web")
        title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 15, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border: none; background: transparent;")

        sub_lbl = QLabel("Analyse, prévisualisation puis import de votre contenu pour la génération de cartes.")
        sub_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)

        header.addWidget(icon_lbl)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        url_lbl = QLabel("URLs (une par ligne)")
        url_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(url_lbl)

        self.url_editor = QPlainTextEdit()
        self.url_editor.setPlaceholderText("https://fr.wikipedia.org/wiki/…\nhttps://blog.example.com/article-1")
        self.url_editor.setMaximumHeight(90)
        self.url_editor.setStyleSheet(self._editor_style())
        layout.addWidget(self.url_editor)

        self.chk_images = QCheckBox("Télécharger les images")
        self.chk_images.setToolTip("Enregistre les images de la page dans les médias du profil et les référence dans le Markdown.")
        self.chk_images.setStyleSheet(self._checkbox_style())

        self.chk_pagination = QCheckBox("Fusionner les articles multi-pages")
        self.chk_pagination.setToolTip("Suit les liens 'page suivante' (rel=next) et assemble les pages en un seul document.")
        self.chk_pagination.setStyleSheet(self._checkbox_style())
        self.chk_pagination.toggled.connect(self._on_pagination_toggled)

        self.spin_max_pages = QSpinBox()
        self.spin_max_pages.setRange(1, 10)
        self.spin_max_pages.setValue(3)
        self.spin_max_pages.setEnabled(False)
        self.spin_max_pages.setToolTip("Nombre maximum de pages à fusionner.")
        self.spin_max_pages.setStyleSheet(
            f"QSpinBox {{ background:{DesignTokens.BG_INPUT}; color:{DesignTokens.TEXT_PRIMARY};"
            f" border:1px solid {DesignTokens.BORDER_COLOR}; border-radius:{DesignTokens.RADIUS_SM}px; padding:2px 4px; }}"
        )

        self.chk_js = QCheckBox("Rendu JavaScript si page dynamique (SPA)")
        self.chk_js.setToolTip("Tente un rendu via le moteur Web intégré lorsque le contenu statique est vide (sites générés côté client).")
        self.chk_js.setStyleSheet(self._checkbox_style())

        self.cmb_folder = QComboBox()
        self.cmb_folder.setToolTip("Dossier de destination dans la bibliothèque de documents.")
        self.cmb_folder.setMinimumWidth(180)
        self.cmb_folder.setStyleSheet(self._combo_style())

        options_frame = QFrame()
        options_frame.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px;")
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(10, 8, 10, 8)
        options_layout.setSpacing(12)
        for widget in self._option_widgets():
            options_layout.addWidget(widget)
        options_layout.addWidget(self.chk_js)
        options_layout.addStretch()
        options_layout.addWidget(QLabel("Dossier:"))
        options_layout.addWidget(self.cmb_folder)
        layout.addWidget(options_frame)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "URL", "Statut", "Titre"])
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 260)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(self._table_style())
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        preview_panel = QFrame()
        preview_panel.setStyleSheet(f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px;")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(12, 10, 12, 10)
        preview_layout.setSpacing(6)

        preview_header = QHBoxLayout()
        title_caption = QLabel("Titre du document")
        title_caption.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        preview_header.addWidget(title_caption)
        preview_header.addStretch()
        preview_layout.addLayout(preview_header)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Titre du document importé (modifiable)")
        self.txt_title.setStyleSheet(
            f"QLineEdit {{ background:{DesignTokens.BG_INPUT}; color:{DesignTokens.TEXT_PRIMARY};"
            f" border:1px solid {DesignTokens.BORDER_COLOR}; border-radius:{DesignTokens.RADIUS_SM}px; padding:6px 8px; }}"
        )
        preview_layout.addWidget(self.txt_title)

        self.lbl_warnings = QLabel("")
        self.lbl_warnings.setWordWrap(True)
        self.lbl_warnings.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW_TEXT}; font-size: 11px; background: transparent; border: none;")
        preview_layout.addWidget(self.lbl_warnings)

        content_caption = QLabel("Contenu extrait (Markdown)")
        content_caption.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        preview_layout.addWidget(content_caption)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setPlaceholderText("Sélectionnez une URL analysée pour prévisualiser son contenu…")
        self.preview_edit.setStyleSheet(self._editor_style())
        preview_layout.addWidget(self.preview_edit, 1)

        preview_footer = QHBoxLayout()
        self.btn_render_js = SecondaryButton("Rendre avec JavaScript")
        self.btn_render_js.setToolTip("Active le moteur Web intégré pour extraire une page générée dynamiquement.")
        self.btn_render_js.setEnabled(False)
        self.btn_render_js.clicked.connect(self._on_render_selected_with_js)
        preview_footer.addWidget(self.btn_render_js)
        preview_footer.addStretch()
        preview_layout.addLayout(preview_footer)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(preview_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.lbl_summary = QLabel("")
        self.lbl_summary.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; background: transparent; border: none;")

        self.btn_analyze = PrimaryButton("Analyser les URLs")
        self.btn_analyze.setIcon(load_phosphor_icon("ph.magnifying-glass", color=DesignTokens.TEXT_PRIMARY))
        self.btn_analyze.clicked.connect(self._on_analyze)

        self.btn_cancel = SecondaryButton("Annuler")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel_batch)

        self.btn_import = PrimaryButton("Importer les documents")
        self.btn_import.setEnabled(False)
        self.btn_import.clicked.connect(self._on_import)

        self.btn_cards = SecondaryButton("Créer des cartes")
        self.btn_cards.setToolTip("Ouvre le Studio de Création sur le dernier document importé.")
        self.btn_cards.setEnabled(False)
        self.btn_cards.clicked.connect(self._on_create_cards)

        self.btn_close = SecondaryButton("Fermer")
        self.btn_close.clicked.connect(self.reject)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addWidget(self.lbl_summary)
        footer.addStretch()
        footer.addWidget(self.btn_cards)
        footer.addWidget(self.btn_import)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_analyze)
        footer.addWidget(self.btn_close)
        layout.addLayout(footer)

    def _option_widgets(self) -> list[Any]:
        return [
            self.chk_images,
            self.chk_pagination,
            QLabel("Pages max:"),
            self.spin_max_pages,
        ]

    @staticmethod
    def _editor_style() -> str:
        return (
            f"QPlainTextEdit {{ background:{DesignTokens.BG_INPUT}; color:{DesignTokens.TEXT_PRIMARY};"
            f" border:1px solid {DesignTokens.BORDER_COLOR};border-radius:{DesignTokens.RADIUS_MD}px;"
            f" padding:8px; selection-background-color:{DesignTokens.ACCENT_BORDER}; }}"
        )

    def _checkbox_style(self) -> str:
        return f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none; spacing: 6px;"

    def _combo_style(self) -> str:
        return (
            f"QComboBox {{ background:{DesignTokens.BG_INPUT}; color:{DesignTokens.TEXT_PRIMARY};"
            f" border:1px solid {DesignTokens.BORDER_COLOR}; border-radius:{DesignTokens.RADIUS_SM}px; padding:4px 8px; }}"
            f"QComboBox QAbstractItemView {{ background:{DesignTokens.BG_PANEL}; color:{DesignTokens.TEXT_PRIMARY};"
            f" selection-background-color:{DesignTokens.ACCENT_PRIMARY}; }}"
        )

    def _table_style(self) -> str:
        return (
            f"QTableWidget {{ background:{DesignTokens.BG_INPUT}; color:{DesignTokens.TEXT_PRIMARY}; border:1px solid {DesignTokens.BORDER_COLOR};"
            f"border-radius:8px; gridline-color:{DesignTokens.BORDER_COLOR}; selection-background-color:{DesignTokens.ACCENT_BG}; }}"
            f"QHeaderView::section {{ background:{DesignTokens.BG_PANEL}; color:{DesignTokens.TEXT_SECONDARY}; border:none; padding:6px; font-weight:600; }}"
        )

    def _populate_folders(self) -> None:
        folders = self.doc_repo.get_all_folders()
        self.cmb_folder.addItem("(Aucun dossier)", None)
        for folder in folders:
            self.cmb_folder.addItem(folder.name, folder.id)

    @Slot(bool)
    def _on_pagination_toggled(self, checked: bool) -> None:
        self.spin_max_pages.setEnabled(checked)

    # ── Analyse du lot ────────────────────────────────────────────────────────

    def _collect_requests(self) -> list[tuple[WebImportRequest | None, WebImportError | None]]:
        lines = [line.strip() for line in self.url_editor.toPlainText().splitlines() if line.strip()]
        collected: list[tuple[WebImportRequest | None, WebImportError | None]] = []
        for raw in lines:
            try:
                req = WebImportRequest(
                    url=WebImporter._normalize_url(raw),
                    download_images=self.chk_images.isChecked(),
                    follow_pagination=self.chk_pagination.isChecked(),
                    max_pages=self.spin_max_pages.value() if self.chk_pagination.isChecked() else 1,
                )
                collected.append((req, None))
            except WebImportError as e:
                collected.append((None, e))
        return collected

    @Slot()
    def _on_analyze(self) -> None:
        collected = self._collect_requests()
        if not collected:
            show_toast(self, "Saisissez au moins une URL.", is_error=True)
            return

        self._rows = {}
        self._js_pending = []
        self._pending_titles = {}
        self.table.setRowCount(0)
        self.table.clearSelection()

        for idx, (req, err) in enumerate(collected):
            st: dict[str, Any] = {
                "raw": req.url if req else "",
                "request": req,
                "result": None,
                "error": None,
                "error_category": None,
                "status": "pending",
                "saved_doc_id": None,
                "existing_doc_id": None,
            }
            self._rows[idx] = st
            self._insert_row(st, idx)
            if req is None and err is not None:
                st["error"] = err.message
                st["error_category"] = err.category
                st["status"] = "error"
                self._update_row_cell(idx, 1, st["raw"], DesignTokens.TEXT_MUTED)
                self._update_row_cell(idx, 2, f"URL invalide : {err.message}", DesignTokens.COLOR_RED_TEXT)

        self._launch_static_batch()

    def _insert_row(self, st: dict[str, Any], idx: int) -> None:
        self.table.insertRow(idx)
        self._update_row_cell(idx, 0, str(idx + 1), DesignTokens.TEXT_SECONDARY)
        self._update_row_cell(idx, 1, st["raw"] or "…", DesignTokens.TEXT_PRIMARY)
        self._update_row_cell(idx, 2, "En attente…", DesignTokens.TEXT_MUTED)
        self._update_row_cell(idx, 3, "", DesignTokens.TEXT_MUTED)

    def _launch_static_batch(self) -> None:
        tasks: list[UrlImportTask] = []
        for idx, st in self._rows.items():
            if st["status"] == "error" or st["saved_doc_id"] is not None or st["request"] is None:
                continue
            tasks.append(UrlImportTask(index=idx, request=st["request"]))
        if not tasks:
            self._finalize_analysis()
            return
        self._start_worker(tasks, label="Analyse")

    def _start_worker(self, tasks: list[UrlImportTask], label: str) -> None:
        if not tasks:
            self._finalize_analysis()
            return
        self.btn_analyze.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_import.setEnabled(False)
        self.btn_cards.setEnabled(False)

        worker = UrlImportWorker(tasks)
        worker.url_started.connect(self._on_url_started)
        worker.url_finished.connect(self._on_url_finished)
        worker.url_failed.connect(self._on_url_failed)
        worker.log_signal.connect(lambda msg: logger.debug("Import web : %s", msg))
        worker.cancelled.connect(self._on_batch_cancelled)
        worker.batch_finished.connect(self._on_batch_finished)
        self._worker = worker
        self._update_batch_status(f"{label} en cours… ({len(tasks)} URL(s))")
        worker.start()

    @Slot(int, str)
    def _on_url_started(self, index: int, url: str) -> None:
        if index not in self._rows:
            return
        self._rows[index]["status"] = "running"
        self._update_row_cell(index, 1, url, DesignTokens.TEXT_PRIMARY)
        self._update_row_cell(index, 2, "Analyse en cours…", DesignTokens.COLOR_BLUE_TEXT)

    @Slot(int, dict)
    def _on_url_finished(self, index: int, payload: dict[str, Any]) -> None:
        st = self._rows.get(index)
        if st is None:
            return
        result = payload_to_result(payload)
        st["result"] = result
        st["error"] = None
        st["error_category"] = None
        st["status"] = "ok"
        st["existing_doc_id"] = self._detect_existing(result.url)
        status_text = "Prêt à importer ✓"
        if st["existing_doc_id"]:
            status_text = "Déjà importé — mise à jour proposée ↑"
        self._update_row_cell(index, 2, status_text, DesignTokens.COLOR_GREEN_TEXT)
        self._update_row_cell(index, 3, result.title, DesignTokens.TEXT_PRIMARY)
        self._refresh_summary()
        self._refresh_preview_if_selected(index)

    @Slot(int, str, str, str)
    def _on_url_failed(self, index: int, url: str, message: str, category: str) -> None:
        st = self._rows.get(index)
        if st is None:
            return
        st["error"] = message
        st["error_category"] = category
        st["status"] = "error"
        self._update_row_cell(index, 1, url, DesignTokens.TEXT_PRIMARY)
        self._update_row_cell(index, 2, f"Échec — {message}", DesignTokens.COLOR_RED_TEXT)
        hint = "Page dynamique — un rendu JS est disponible." if category in _JS_RETRY_CATEGORIES else ""
        self._update_row_cell(index, 3, hint, DesignTokens.COLOR_YELLOW_TEXT)
        if category in _JS_RETRY_CATEGORIES and self.chk_js.isChecked():
            self._js_pending.append(index)
        self._refresh_summary()
        self._refresh_preview_if_selected(index)

    @Slot(int, int)
    def _on_batch_finished(self, ok: int, failed: int) -> None:
        pending_errors = [i for i in self._js_pending if i in self._rows and self._rows[i].get("status") == "error"]
        if pending_errors and self.chk_js.isChecked():
            self._render_js_for_pending(pending_errors)
            return
        if self._js_pending:
            self._js_pending = []
        self._finalize_analysis()

    @Slot()
    def _on_cancel_batch(self) -> None:
        self._cancel_running_worker()

    @Slot()
    def _on_batch_cancelled(self) -> None:
        self._worker = None
        self.btn_cancel.setEnabled(False)
        self.btn_analyze.setEnabled(True)
        for idx, st in self._rows.items():
            if st["status"] == "running":
                st["status"] = "pending"
                self._update_row_cell(idx, 2, "Annulé", DesignTokens.TEXT_MUTED)
        self._refresh_summary()

    # ── Repli JavaScript ──────────────────────────────────────────────────────

    @Slot()
    def _on_render_selected_with_js(self) -> None:
        row = self.table.currentRow()
        if row in self._rows:
            self._render_js_for_pending([row])

    def _render_js_for_pending(self, indexes: list[int]) -> None:
        from ankiforge.services.parsing.web_js_renderer import render_page_to_html

        self._js_pending = [i for i in self._js_pending if i not in indexes]
        targets = [i for i in indexes if i in self._rows and self._rows[i]["request"] is not None]
        if not targets:
            self._finalize_analysis()
            return

        tasks: list[UrlImportTask] = []
        self.btn_cancel.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for idx in targets:
                st = self._rows[idx]
                self._update_row_cell(idx, 2, "Rendu JavaScript…", DesignTokens.COLOR_BLUE_TEXT)
                try:
                    html, final_url = render_page_to_html(st["raw"], timeout_ms=20000)
                    tasks.append(UrlImportTask(index=idx, request=st["request"], rendered_html=html, base_url=final_url or st["raw"]))
                except Exception as e:
                    st["error"] = str(e)
                    st["error_category"] = "js_render_failed"
                    st["status"] = "error"
                    self._update_row_cell(idx, 2, f"Échec du rendu JS — {e}", DesignTokens.COLOR_RED_TEXT)
                self._refresh_summary()
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        if tasks:
            self._start_worker(tasks, label="Extraction du rendu JS")
        else:
            self._finalize_analysis()

    # ── Import des documents ──────────────────────────────────────────────────

    @Slot()
    def _on_import(self) -> None:
        ok_keys = [idx for idx, st in self._rows.items() if st["status"] == "ok" and st["result"] is not None and st["saved_doc_id"] is None]
        if not ok_keys:
            show_toast(self, "Aucune URL valide à importer.", is_error=True)
            return

        folder = self.cmb_folder.currentData()
        folder_model = self.doc_repo.get_folder_by_id(int(folder)) if folder else None

        dedup_keys = [idx for idx in ok_keys if self._rows[idx].get("existing_doc_id")]
        update_existing = False
        if dedup_keys:
            reply = QMessageBox.question(
                self,
                "Contenu déjà importé",
                f"{len(dedup_keys)} URL(s) correspondent déjà à un document existant.\nVoulez-vous mettre à jour les documents existants (contenu rafraîchi) ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            update_existing = reply == QMessageBox.StandardButton.Yes

        saved_ids: list[int] = []
        errors: list[str] = []
        for idx in ok_keys:
            st = self._rows[idx]
            result = st["result"]
            if result is None:
                continue
            title = self._pending_titles.get(idx) or result.title
            try:
                doc = self.doc_repo.save_imported_document(
                    title=title,
                    content=result.content,
                    file_type=result.doc_type,
                    source_url=result.url,
                    doc_id_to_update=st["existing_doc_id"] if update_existing and st["existing_doc_id"] else None,
                    folder=folder_model,
                )
                st["saved_doc_id"] = doc.id
                saved_ids.append(doc.id)
                self._update_row_cell(idx, 2, "Importé ✓", DesignTokens.COLOR_GREEN_TEXT)
            except Exception as e:
                logger.exception("Erreur lors de l'import du document %s : %s", result.url, e)
                errors.append(f"{result.url} : {e}")
                self._update_row_cell(idx, 2, "Erreur d'import", DesignTokens.COLOR_RED_TEXT)

        if saved_ids:
            self.import_completed.emit(saved_ids)
            self.btn_cards.setEnabled(True)
            show_toast(self, f"{len(saved_ids)} document(s) importé(s) avec succès.")
        if errors:
            show_toast(self, "Certaines URL n'ont pas pu être importées.", is_error=True)
        self._refresh_summary()

    @Slot()
    def _on_create_cards(self) -> None:
        for st in self._rows.values():
            if st.get("saved_doc_id"):
                self.cards_requested.emit(int(st["saved_doc_id"]))
                self.accept()
                return
        show_toast(self, "Importez d'abord au moins un document.", is_error=True)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _detect_existing(self, source_url: str) -> int | None:
        doc = self.doc_repo.get_document_by_source_url(source_url)
        return doc.id if doc else None

    def _finalize_analysis(self) -> None:
        self._worker = None
        self.btn_analyze.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        any_ok = any(st["status"] == "ok" for st in self._rows.values())
        self.btn_import.setEnabled(any_ok)
        self._refresh_summary()

    def _update_batch_status(self, text: str) -> None:
        self.lbl_summary.setText(text)

    def _refresh_summary(self) -> None:
        total = len(self._rows)
        ok = sum(1 for st in self._rows.values() if st["status"] == "ok")
        err = sum(1 for st in self._rows.values() if st["status"] == "error")
        run = sum(1 for st in self._rows.values() if st["status"] == "running")
        label = f"{total} URL(s)"
        if ok:
            label += f" • {ok} prête(s) ✓"
        if err:
            label += f" • {err} échec(s)"
        if run:
            label += f" • {run} en cours"
        self.lbl_summary.setText(label)

    def _update_row_cell(self, row: int, col: int, text: str, color: str) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        item = QTableWidgetItem(text)
        item.setForeground(QBrush(QColor(color)))
        if col == 1:
            item.setToolTip(text)
        self.table.setItem(row, col, item)

    @Slot()
    def _on_selection_changed(self) -> None:
        row = self.table.currentRow()
        st = self._rows.get(row)
        if st is None:
            self._clear_preview()
            return
        if st.get("status") == "ok" and st.get("result") is not None:
            result: WebImportResult = st["result"]
            self.txt_title.setText(self._pending_titles.get(row, "") or result.title)
            self.preview_edit.setPlainText(result.content)
            warnings = list(result.warnings)
            if result.flags.get("dynamic"):
                warnings.append("Page générée dynamiquement (JS) — un rendu peut avoir été nécessaire.")
            self.lbl_warnings.setText(" • ".join(warnings) if warnings else "")
            self.btn_render_js.setEnabled(False)
        elif st.get("status") == "error":
            self.txt_title.setText("")
            self.preview_edit.setPlainText(f"— Échec de l'analyse —\n\n{st.get('error') or 'Erreur inconnue'}")
            self.lbl_warnings.setText("")
            self.btn_render_js.setEnabled(st.get("error_category") in _JS_RETRY_CATEGORIES)
        else:
            self._clear_preview()

    def _refresh_preview_if_selected(self, index: int) -> None:
        if self.table.currentRow() == index:
            self._on_selection_changed()

    def _clear_preview(self) -> None:
        self.txt_title.setText("")
        self.preview_edit.clear()
        self.lbl_warnings.setText("")
        self.btn_render_js.setEnabled(False)

    def reject(self) -> None:
        self._cancel_running_worker()
        super().reject()

    def closeEvent(self, event: Any) -> None:
        self._cancel_running_worker()
        super().closeEvent(event)

    def _cancel_running_worker(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
