"""
Widget d'Inspection & Espace de Travail (Workspace Inspector) pour le Consultant IA.

Fournit :
- Un visualiseur de diffs comparatifs haute fidélité (Recto/Verso avant/après, CSS).
- Un mode d'Édition Directe (Direct Edit) permettant d'ajuster le texte avant validation.
- Une File d'attente de propositions (Patch Queue) pour traiter les lots de modifications (N/M).
- Un Garde-Fou humain explicite ([ ✅ Appliquer ], [ ❌ Rejeter ], [ ✅ Tout appliquer (N) ]).
- Un aperçu visuel en direct KaTeX / HTML de la carte résultante.
"""

from __future__ import annotations

import difflib
import html
import json
import logging
import uuid
from typing import Any

from peewee import PeeweeException, fn
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import (
    CardModel,
    DeckModel,
    NoteModel,
    NoteTypeModel,
    NoteVersionModel,
    db,
)
from ankiforge.ui.components import (
    Badge,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.card_preview_widget import CardPreviewWidget
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class WorkspaceInspectorWidget(QWidget):
    """
    Panneau interactif de travail (Workspace IDE) avec Garde-Fou, Diff Viewer,
    Édition Directe et gestion des propositions par lot (Patch Queue).
    """

    action_applied = Signal(str)
    action_rejected = Signal(str)
    action_reverted = Signal(str)
    next_step_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._patch_queue: list[dict[str, Any]] = []
        self._current_index: int = 0
        self._last_applied_patch: dict[str, Any] | None = None
        self._setup_ui()
        self.set_empty_state()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # ── 1. En-tête & Statut du Garde-Fou ─────────────────────────────────
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        lbl_title = QLabel("WORKSPACE & GARDE-FOU")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()

        self.status_badge = Badge("En veille", variant="status")
        header_layout.addWidget(self.status_badge)
        main_layout.addLayout(header_layout)

        # ── 2. Navigation de la File d'Attente de Propositions (Batch Queue) ──
        self.queue_bar = QFrame()
        self.queue_bar.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 4px;
            }}
        """)
        queue_layout = QHBoxLayout(self.queue_bar)
        queue_layout.setContentsMargins(4, 2, 4, 2)
        queue_layout.setSpacing(6)

        self.btn_prev_patch = QPushButton("◀")
        self.btn_prev_patch.setFixedSize(24, 24)
        self.btn_prev_patch.clicked.connect(self._on_prev_patch)
        queue_layout.addWidget(self.btn_prev_patch)

        self.lbl_queue_status = QLabel("Proposition 0 / 0")
        self.lbl_queue_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_queue_status.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 11px; font-weight: bold;")
        queue_layout.addWidget(self.lbl_queue_status, 1)

        self.btn_next_patch = QPushButton("▶")
        self.btn_next_patch.setFixedSize(24, 24)
        self.btn_next_patch.clicked.connect(self._on_next_patch)
        queue_layout.addWidget(self.btn_next_patch)

        self.btn_apply_all = PrimaryButton("Tout appliquer")
        self.btn_apply_all.setFixedHeight(24)
        self.btn_apply_all.setIcon(load_phosphor_icon("ph.check-circle", color="white"))
        self.btn_apply_all.clicked.connect(self._on_apply_all_clicked)
        queue_layout.addWidget(self.btn_apply_all)

        main_layout.addWidget(self.queue_bar)

        # Bannière Garde-Fou
        self.banner_guard = QFrame()
        self.banner_guard.setStyleSheet("""
            QFrame {
                background-color: rgba(234, 179, 8, 0.1);
                border: 1px solid rgba(234, 179, 8, 0.4);
                border-radius: 6px;
                padding: 6px;
            }
        """)
        banner_layout = QHBoxLayout(self.banner_guard)
        banner_layout.setContentsMargins(6, 4, 6, 4)
        banner_layout.setSpacing(6)

        icon_guard = QLabel()
        icon_guard.setPixmap(load_phosphor_icon("ph.shield-check", color=DesignTokens.COLOR_YELLOW).pixmap(16, 16))
        banner_layout.addWidget(icon_guard)

        self.lbl_guard_msg = QLabel("<b>Garde-Fou actif :</b> Validez ou éditez ci-dessous avant d'enregistrer en BDD.")
        self.lbl_guard_msg.setStyleSheet(f"color: {DesignTokens.COLOR_YELLOW}; font-size: 11px;")
        banner_layout.addWidget(self.lbl_guard_msg, 1)
        main_layout.addWidget(self.banner_guard)

        # ── 3. Onglets : Diff / Édition Directe / Rendu KaTeX ──────────────────
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                background-color: {DesignTokens.BG_PANEL};
            }}
            QTabBar::tab {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                padding: 6px 10px;
                border-top-left-radius: {DesignTokens.RADIUS_SM}px;
                border-top-right-radius: {DesignTokens.RADIUS_SM}px;
                font-size: 11px;
                font-weight: 500;
            }}
            QTabBar::tab:selected {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

        # Onglet 1 : Diff Comparatif
        diff_widget = QWidget()
        diff_layout = QVBoxLayout(diff_widget)
        diff_layout.setContentsMargins(8, 8, 8, 8)
        diff_layout.setSpacing(8)

        self.diff_browser = QTextBrowser()
        self.diff_browser.setOpenExternalLinks(True)
        self.diff_browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 12px;
            }}
        """)
        diff_layout.addWidget(self.diff_browser, 1)

        # Onglet 2 : Édition Directe (Direct Edit)
        edit_widget = QWidget()
        edit_layout = QVBoxLayout(edit_widget)
        edit_layout.setContentsMargins(8, 8, 8, 8)
        edit_layout.setSpacing(6)

        lbl_edit_help = QLabel("✏️ Modifiez directement le texte de la proposition avant de l'appliquer :")
        lbl_edit_help.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        edit_layout.addWidget(lbl_edit_help)

        self.direct_edit = QPlainTextEdit()
        self.direct_edit.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 8px;
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: {DesignTokens.FONT_CODE};
                font-size: 12px;
            }}
            QPlainTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)
        self.direct_edit.textChanged.connect(self._on_direct_edit_changed)
        edit_layout.addWidget(self.direct_edit, 1)

        # Onglet 3 : Aperçu Visuel & Rendu Anki WebEngine
        preview_widget = QWidget()
        prev_layout = QVBoxLayout(preview_widget)
        prev_layout.setContentsMargins(4, 4, 4, 4)
        prev_layout.setSpacing(4)

        self.card_preview = CardPreviewWidget(parent=self, show_header=True)
        prev_layout.addWidget(self.card_preview, 1)

        self.preview_browser = QTextBrowser()
        self.preview_browser.setOpenExternalLinks(True)
        self.preview_browser.hide()
        prev_layout.addWidget(self.preview_browser)

        self.tabs.addTab(diff_widget, "🔍 Diff Comparatif")
        self.tabs.addTab(edit_widget, "✏️ Édition Directe")
        self.tabs.addTab(preview_widget, "👁️ Aperçu Anki")
        main_layout.addWidget(self.tabs, 1)

        # ── 4. Barre d'Actions Garde-Fou ─────────────────────────────────────
        self.actions_frame = QFrame()
        self.actions_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        actions_layout = QHBoxLayout(self.actions_frame)
        actions_layout.setContentsMargins(4, 4, 4, 4)
        actions_layout.setSpacing(6)

        self.btn_apply = PrimaryButton("Appliquer")
        self.btn_apply.setIcon(load_phosphor_icon("ph.check-circle", color="white"))
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        actions_layout.addWidget(self.btn_apply)

        self.btn_revert = SecondaryButton("Annuler (Revert)")
        self.btn_revert.setIcon(load_phosphor_icon("ph.arrow-u-up-left", color=DesignTokens.COLOR_YELLOW))
        self.btn_revert.clicked.connect(self._on_revert_clicked)
        self.btn_revert.hide()
        actions_layout.addWidget(self.btn_revert)

        self.btn_reject = SecondaryButton("Rejeter")
        self.btn_reject.setIcon(load_phosphor_icon("ph.x-circle", color=DesignTokens.COLOR_RED))
        self.btn_reject.clicked.connect(self._on_reject_clicked)
        actions_layout.addWidget(self.btn_reject)

        self.btn_copy_patch = SecondaryButton("Copier")
        self.btn_copy_patch.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.TEXT_PRIMARY))
        self.btn_copy_patch.clicked.connect(self._on_copy_patch_clicked)
        actions_layout.addWidget(self.btn_copy_patch)

        main_layout.addWidget(self.actions_frame)

        # ── 5. Suggestions Proactives (Next Steps) ───────────────────────────
        lbl_next = QLabel("SUGGESTIONS D'ACTIONS SUIVANTES")
        lbl_next.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 10px; font-weight: bold; letter-spacing: 0.5px;")
        main_layout.addWidget(lbl_next)

        self.chips_container = QWidget()
        self.chips_layout = QVBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(4)
        main_layout.addWidget(self.chips_container)

    def set_empty_state(self) -> None:
        """Réinitialise le workspace à l'état de veille."""
        self._patch_queue.clear()
        self._current_index = 0
        self._last_applied_patch = None
        self.status_badge.setText("En veille")
        self.banner_guard.hide()
        self.queue_bar.hide()
        self.btn_apply.setEnabled(False)
        self.btn_revert.hide()
        self.btn_reject.setEnabled(False)
        self.btn_copy_patch.setEnabled(False)

        empty_html = f"""
        <div style="text-align: center; color: {DesignTokens.TEXT_MUTED}; margin-top: 40px; font-family: sans-serif;">
            <p style="font-size: 14px; font-weight: bold;">Aucune proposition en attente</p>
            <p style="font-size: 12px;">Lorsque le Consultant IA propose une refactorisation ou scission de carte,<br>le diff comparatif avant/après et l'éditeur direct s'afficheront ici.</p>
        </div>
        """
        self.diff_browser.setHtml(empty_html)
        self.preview_browser.setHtml(empty_html)
        if hasattr(self, "card_preview"):
            self.card_preview.set_empty_state("Aucune carte sélectionnée pour l'aperçu.")
        self.direct_edit.clear()

    def add_patch_to_queue(self, patch: dict[str, Any]) -> None:
        """Ajoute une proposition à la file d'attente."""
        self._patch_queue.append(patch)
        self._current_index = len(self._patch_queue) - 1
        self._render_current_patch()

    def update_diff_view(
        self,
        title: str,
        original_text: str | dict[str, Any],
        modified_text: str | dict[str, Any] | list[Any],
        patch_type: str = "card",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Affiche une proposition et l'ajoute à la file d'attente active."""
        patch_item = {
            "title": title,
            "type": patch_type,
            "original": original_text,
            "modified": modified_text,
            "metadata": metadata or {},
        }
        self._patch_queue = [patch_item]
        self._current_index = 0
        self._render_current_patch()

    def _render_current_patch(self) -> None:
        if not self._patch_queue or self._current_index >= len(self._patch_queue):
            self.set_empty_state()
            return

        patch = self._patch_queue[self._current_index]
        total = len(self._patch_queue)

        self.status_badge.setText(f"🛡️ En attente ({self._current_index + 1}/{total})")
        self.banner_guard.show()
        self.queue_bar.setVisible(total > 1)
        self.lbl_queue_status.setText(f"Proposition {self._current_index + 1} / {total}")
        self.btn_apply_all.setText(f"Tout appliquer ({total})")
        self.btn_prev_patch.setEnabled(self._current_index > 0)
        self.btn_next_patch.setEnabled(self._current_index < total - 1)

        self.btn_apply.setEnabled(True)
        self.btn_reject.setEnabled(True)
        self.btn_copy_patch.setEnabled(True)

        orig_str = json.dumps(patch["original"], ensure_ascii=False, indent=2) if isinstance(patch["original"], dict | list) else str(patch["original"])
        mod_str = json.dumps(patch["modified"], ensure_ascii=False, indent=2) if isinstance(patch["modified"], dict | list) else str(patch["modified"])

        # Diff unifié
        diff_lines = list(
            difflib.unified_diff(
                orig_str.splitlines(keepends=True),
                mod_str.splitlines(keepends=True),
                fromfile="Original (Actuel en BDD)",
                tofile="Proposition IA (Garde-Fou)",
                n=3,
            )
        )

        html_lines = [f"<div style='font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY}; margin-bottom: 6px; font-size: 13px;'>{html.escape(patch.get('title', ''))}</div>"]

        if not diff_lines:
            html_lines.append(f"<div style='color: {DesignTokens.COLOR_BLUE};'>Aucune différence textuelle détectée.</div>")
        else:
            for raw_line in diff_lines:
                line = raw_line.rstrip("\n")
                escaped = html.escape(line)
                if line.startswith("+") and not line.startswith("+++"):
                    html_lines.append(f"<div style='background-color: rgba(34, 197, 94, 0.15); color: {DesignTokens.COLOR_GREEN}; padding: 2px 4px; font-weight: 500;'>{escaped}</div>")
                elif line.startswith("-") and not line.startswith("---"):
                    html_lines.append(f"<div style='background-color: rgba(239, 68, 68, 0.15); color: {DesignTokens.COLOR_RED}; padding: 2px 4px; text-decoration: line-through;'>{escaped}</div>")
                elif line.startswith("@@"):
                    html_lines.append(f"<div style='color: {DesignTokens.COLOR_BLUE}; font-weight: bold; margin-top: 4px; padding: 2px 4px;'>{escaped}</div>")
                else:
                    html_lines.append(f"<div style='color: {DesignTokens.TEXT_PRIMARY}; padding: 1px 4px;'>{escaped}</div>")

        self.diff_browser.setHtml("".join(html_lines))

        # Remplir l'éditeur direct
        self.direct_edit.blockSignals(True)
        self.direct_edit.setPlainText(mod_str)
        self.direct_edit.blockSignals(False)

        # Remplir l'aperçu avec rendu haute fidélité
        self.preview_browser.setHtml(self._build_preview_html(patch))

        # Rendu officiel Anki dans CardPreviewWidget
        if hasattr(self, "card_preview"):
            p_type = patch.get("type", "card")
            nt = None
            note_id = patch.get("note_id") or (patch.get("metadata", {}).get("note_id") if isinstance(patch.get("metadata"), dict) else None)
            if note_id:
                try:
                    n = NoteModel.get_or_none(NoteModel.id == int(note_id))
                    if n:
                        nt = n.note_type
                except (ValueError, TypeError, PeeweeException):
                    pass
            if not nt:
                nt = NoteTypeModel.select().first()

            preview_fields: dict[str, str] = {}
            raw_mod = patch.get("modified")
            if isinstance(raw_mod, str) and raw_mod.strip().startswith(("{", "[")):
                try:
                    raw_mod = json.loads(raw_mod)
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            if p_type == "card" and isinstance(raw_mod, dict):
                preview_fields = {str(k): str(v) for k, v in raw_mod.items()}
            elif p_type == "split" and isinstance(raw_mod, list) and raw_mod:
                c0 = raw_mod[0]
                preview_fields = {str(k): str(v) for k, v in c0.items()} if isinstance(c0, dict) else {"Front": str(c0)}
            elif isinstance(raw_mod, dict):
                preview_fields = {str(k): str(v) for k, v in raw_mod.items()}
            elif isinstance(raw_mod, str):
                preview_fields = {"Front": raw_mod}

            override_css = patch["modified"] if p_type == "css" and isinstance(patch.get("modified"), str) else None
            self.card_preview.update_preview(note_type=nt, fields_dict=preview_fields, override_css=override_css)

    def _build_preview_html(self, patch: dict[str, Any]) -> str:
        """Construit un aperçu haute fidélité selon le type de proposition (carte, scission, modèle/CSS)."""
        p_type = patch.get("type", "card")
        modified = patch.get("modified")
        title = html.escape(str(patch.get("title", "Aperçu de la carte")))

        if p_type == "card" and isinstance(modified, dict):
            fields_html = []
            for f_name, f_val in modified.items():
                f_name_esc = html.escape(str(f_name))
                f_val_str = html.escape(str(f_val)).replace("\n", "<br>")
                fields_html.append(f"""
                    <div style="margin-bottom: 12px;">
                        <div style="font-size: 10px; font-weight: bold; color: {DesignTokens.COLOR_YELLOW}; margin-bottom: 4px;">{f_name_esc}</div>
                        <div style="background: {DesignTokens.BG_MAIN}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 4px; padding: 8px 10px; color: {DesignTokens.TEXT_PRIMARY};">
                            {f_val_str}
                        </div>
                    </div>
                """)
            content_block = "".join(fields_html) if fields_html else "<i>Champs vides</i>"
            return f"""
                <div style="font-family: {DesignTokens.FONT_MAIN}; padding: 6px;">
                    <div style="font-size: 12px; font-weight: bold; color: {DesignTokens.COLOR_BLUE}; margin-bottom: 10px;">🎴 {title}</div>
                    <div style="border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 8px; padding: 14px; background: {DesignTokens.BG_PANEL};">
                        {content_block}
                    </div>
                </div>
            """

        elif p_type == "split" and isinstance(modified, list):
            cards_html = []
            for i, c_dict in enumerate(modified, 1):
                c_fields = []
                if isinstance(c_dict, dict):
                    for k, v in c_dict.items():
                        c_fields.append(f"<div><b style='color: {DesignTokens.COLOR_YELLOW}; font-size: 10px;'>{html.escape(str(k))} :</b> {html.escape(str(v))}</div>")
                else:
                    c_fields.append(f"<div>{html.escape(str(c_dict))}</div>")

                cards_html.append(f"""
                    <div style="border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 10px; background: {DesignTokens.BG_PANEL}; margin-bottom: 8px;">
                        <div style="font-size: 11px; font-weight: bold; color: {DesignTokens.COLOR_GREEN}; margin-bottom: 6px;">Carte atomique #{i}</div>
                        {"".join(c_fields)}
                    </div>
                """)
            return f"""
                <div style="font-family: {DesignTokens.FONT_MAIN}; padding: 6px;">
                    <div style="font-size: 12px; font-weight: bold; color: {DesignTokens.COLOR_BLUE}; margin-bottom: 10px;">✂️ {title} ({len(modified)} cartes)</div>
                    {"".join(cards_html)}
                </div>
            """

        else:
            mod_str = json.dumps(modified, ensure_ascii=False, indent=2) if isinstance(modified, dict | list) else str(modified)
            escaped_body = html.escape(mod_str).replace("\n", "<br>")
            return f"""
                <div style="font-family: {DesignTokens.FONT_MAIN}; padding: 6px;">
                    <div style="font-size: 12px; font-weight: bold; color: {DesignTokens.COLOR_BLUE}; margin-bottom: 8px;">{title}</div>
                    <div style="border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: 6px; padding: 12px; background: {DesignTokens.BG_PANEL}; font-family: monospace; font-size: 12px;">
                        {escaped_body}
                    </div>
                </div>
            """

    @Slot()
    def _on_direct_edit_changed(self) -> None:
        """Met à jour le contenu modifié en temps réel suite à une saisie utilisateur."""
        if not self._patch_queue or self._current_index >= len(self._patch_queue):
            return

        txt = self.direct_edit.toPlainText().strip()
        try:
            parsed = json.loads(txt)
            self._patch_queue[self._current_index]["modified"] = parsed
        except Exception:
            self._patch_queue[self._current_index]["modified"] = txt

    @Slot()
    def _on_prev_patch(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._render_current_patch()

    @Slot()
    def _on_next_patch(self) -> None:
        if self._current_index < len(self._patch_queue) - 1:
            self._current_index += 1
            self._render_current_patch()

    @Slot()
    def _on_apply_clicked(self) -> None:
        """Garde-Fou validé pour l'élément courant."""
        if not self._patch_queue or self._current_index >= len(self._patch_queue):
            return

        patch = self._patch_queue.pop(self._current_index)
        self._last_applied_patch = patch
        self._persist_patch(patch)

        if self._patch_queue:
            self._current_index = min(self._current_index, len(self._patch_queue) - 1)
            self._render_current_patch()
        else:
            self.status_badge.setText("✅ Appliqué en BDD")
            self.banner_guard.hide()
            self.queue_bar.hide()
            self.btn_apply.setEnabled(False)
            self.btn_reject.setEnabled(False)
            self.btn_revert.show()

    @Slot()
    def _on_revert_clicked(self) -> None:
        """Annule la dernière action appliquée et restaure l'état précédent en BDD."""
        if not self._last_applied_patch:
            return

        patch = self._last_applied_patch
        p_type = patch.get("type", "card")
        note_id = patch.get("note_id") or (patch.get("metadata", {}).get("note_id") if isinstance(patch.get("metadata"), dict) else None)
        orig = patch.get("original")

        try:
            if p_type == "card" and note_id:
                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note and orig:
                    with db.atomic():
                        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        if active_v:
                            active_v.is_active = False
                            active_v.save()
                        new_v_num = (note.versions.select(fn.MAX(NoteVersionModel.version_number)).scalar() or 1) + 1
                        NoteVersionModel.create(
                            note=note,
                            version_number=new_v_num,
                            content=json.dumps(orig, ensure_ascii=False) if isinstance(orig, dict | list) else str(orig),
                            source="consultant_workspace_revert",
                            is_active=True,
                        )
            self.status_badge.setText("↩️ Annulé en BDD")
            self.btn_revert.hide()
            self.btn_apply.setEnabled(True)
            self.btn_reject.setEnabled(True)
            self._last_applied_patch = None
            self.action_reverted.emit(f"Modification de la note #{note_id} annulée")
            show_toast(self, "Modification annulée avec succès !")
        except Exception as e:
            logger.error("Erreur lors de l'annulation workspace : %s", e)
            show_toast(self, f"Erreur d'annulation : {e}", is_error=True)

    @Slot()
    def _on_apply_all_clicked(self) -> None:
        """Garde-Fou validé : applique TOUTE la file d'attente en une transaction atomique."""
        if not self._patch_queue:
            return

        count = len(self._patch_queue)
        with db.atomic():
            for patch in list(self._patch_queue):
                self._persist_patch(patch)

        self._patch_queue.clear()
        self.status_badge.setText(f"✅ {count} modifications appliquées")
        self.banner_guard.hide()
        self.queue_bar.hide()
        self.btn_apply.setEnabled(False)
        self.btn_reject.setEnabled(False)
        show_toast(self, f"{count} modifications enregistrées avec succès en BDD !")
        self.action_applied.emit(f"{count} modifications appliquées par lot")

    @Slot()
    def _on_reject_clicked(self) -> None:
        """Garde-Fou rejeté pour l'élément courant."""
        if not self._patch_queue or self._current_index >= len(self._patch_queue):
            return

        self._patch_queue.pop(self._current_index)
        if self._patch_queue:
            self._current_index = min(self._current_index, len(self._patch_queue) - 1)
            self._render_current_patch()
        else:
            self.status_badge.setText("❌ Proposition rejetée")
            self.banner_guard.hide()
            self.queue_bar.hide()
            self.btn_apply.setEnabled(False)
            self.btn_reject.setEnabled(False)

        show_toast(self, "Proposition rejetée.")
        self.action_rejected.emit("Proposition rejetée")

    def _persist_patch(self, patch: dict[str, Any]) -> None:
        """Persiste concrètement un patch en base SQLite."""
        p_type = patch.get("type", "card")
        metadata = patch.get("metadata", {})
        modified = patch.get("modified")
        note_id = patch.get("note_id") or metadata.get("note_id")

        try:
            if p_type == "css":
                model_name = metadata.get("note_type_name", "")
                snippet = metadata.get("snippet", str(modified))
                nt = NoteTypeModel.get_or_none(NoteTypeModel.name == model_name) if model_name else NoteTypeModel.select().first()
                if nt:
                    with db.atomic():
                        nt.css_style = (nt.css_style or "") + f"\n\n/* Appliqué depuis le Workspace */\n{snippet}"
                        nt.save()
                    self.action_applied.emit(f"CSS validé pour {nt.name}")

            elif p_type in ("model", "note_type"):
                model_name = patch.get("note_type_name") or metadata.get("note_type_name", "")
                nt = NoteTypeModel.get_or_none(NoteTypeModel.name == model_name) if model_name else None
                if not nt and patch.get("note_type_id"):
                    nt = NoteTypeModel.get_or_none(NoteTypeModel.id == int(patch["note_type_id"]))
                if nt:
                    with db.atomic():
                        if isinstance(modified, dict):
                            if "css_style" in modified:
                                nt.css_style = str(modified["css_style"])
                            if "fields_schema" in modified:
                                nt.fields_schema = json.dumps(modified["fields_schema"], ensure_ascii=False) if isinstance(modified["fields_schema"], list) else str(modified["fields_schema"])
                            if "templates" in modified:
                                nt.templates = json.dumps(modified["templates"], ensure_ascii=False) if isinstance(modified["templates"], list) else str(modified["templates"])
                            if "description" in modified:
                                nt.description = str(modified["description"])
                        elif isinstance(modified, str):
                            nt.css_style = modified
                        nt.save()
                    self.action_applied.emit(f"Modèle de carte '{nt.name}' mis à jour en BDD")

            elif p_type == "card" and note_id:
                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note:
                    with db.atomic():
                        active_v = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                        if active_v:
                            active_v.is_active = False
                            active_v.save()
                        new_v_num = (note.versions.select(fn.MAX(NoteVersionModel.version_number)).scalar() or 1) + 1
                        NoteVersionModel.create(
                            note=note,
                            version_number=new_v_num,
                            content=json.dumps(modified, ensure_ascii=False) if isinstance(modified, dict) else str(modified),
                            source="consultant_workspace",
                            is_active=True,
                        )
                    self.action_applied.emit(f"Note #{note.id} refactorisée")

            elif p_type == "split" and note_id:
                cards_list = modified if isinstance(modified, list) else []
                note = NoteModel.get_or_none(NoteModel.id == int(note_id))
                if note and cards_list:
                    card_rel = note.cards.first()
                    target_deck = card_rel.deck if card_rel else DeckModel.select().first()
                    with db.atomic():
                        for c_data in cards_list:
                            new_note = NoteModel.create(guid=str(uuid.uuid4())[:12], note_type=note.note_type, tags=note.tags, status="pending")
                            NoteVersionModel.create(note=new_note, version_number=1, content=json.dumps(c_data, ensure_ascii=False), source="consultant_split", is_active=True)
                            if target_deck:
                                CardModel.create(note=new_note, deck=target_deck, template_index=0)
                        note.status = "archived"
                        note.save()
                    self.action_applied.emit(f"Note #{note.id} scindée")

        except Exception as e:
            logger.error("Erreur _persist_patch workspace : %s", e)

    @Slot()
    def _on_copy_patch_clicked(self) -> None:
        """Copie le patch JSON dans le presse-papiers."""
        if not self._patch_queue or self._current_index >= len(self._patch_queue):
            return
        cb = QApplication.clipboard()
        if cb:
            cb.setText(json.dumps(self._patch_queue[self._current_index], ensure_ascii=False, indent=2))
        show_toast(self, "Patch copié dans le presse-papiers !")

    def set_next_steps(self, steps: list[str]) -> None:
        """Affiche les suggestions d'actions suivantes."""
        while self.chips_layout.count() > 0:
            item = self.chips_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not steps:
            empty_lbl = QLabel("Aucune suggestion")
            empty_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
            self.chips_layout.addWidget(empty_lbl)
            return

        for step in steps:
            btn = QPushButton(step)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {DesignTokens.BG_PANEL};
                    border: 1px solid {DesignTokens.BORDER_COLOR};
                    border-radius: {DesignTokens.RADIUS_SM}px;
                    padding: 5px 8px;
                    text-align: left;
                    font-size: 11px;
                    color: {DesignTokens.TEXT_PRIMARY};
                }}
                QPushButton:hover {{
                    background-color: {DesignTokens.BG_HOVER};
                    border-color: {DesignTokens.ACCENT_PRIMARY};
                    color: {DesignTokens.ACCENT_PRIMARY};
                }}
            """)
            btn.clicked.connect(lambda _, s=step: self.next_step_requested.emit(s))
            self.chips_layout.addWidget(btn)
