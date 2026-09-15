"""Boîte de dialogue interactive pour la restructuration documentaire par IA."""

import logging
from typing import Any

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.markdown.ai_structurer import (
    AIDocumentStructurer,
    StructuringOptions,
    StructuringProfile,
)
from ankiforge.ui.components import PrimaryButton, SecondaryButton
from ankiforge.ui.components.model_selector import ModelSelectorWidget
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class StructuringWorker(QThread):
    """Worker asynchrone pour la structuration de documents sans bloquer l'UI."""

    progress = Signal(str, float)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        content: str,
        options: StructuringOptions,
        provider: LLMProvider | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.content = content
        self.options = options
        self.provider = provider

    def run(self) -> None:
        try:
            result = AIDocumentStructurer.structure_document(
                content=self.content,
                options=self.options,
                ai_provider=self.provider,
                progress_callback=lambda msg, ratio: self.progress.emit(msg, ratio),
            )
            self.finished.emit(result)
        except Exception as e:
            logger.exception("Erreur de structuration IA : %s", e)
            self.error.emit(str(e))


class AIDocumentStructureDialog(QDialog):
    """Dialogue de configuration, prévisualisation et application de la structuration IA."""

    structure_applied = Signal(str)  # Émis pour remplacer dans l'éditeur actif
    structure_saved_as_copy = Signal(str)  # Émis pour créer un nouveau document

    def __init__(
        self,
        doc_title: str,
        content: str,
        ai_manager: Any | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.doc_title = doc_title
        self.original_content = content
        self.ai_manager = ai_manager
        self.structured_result = ""
        self._worker: StructuringWorker | None = None

        self.setWindowTitle(f"Structurer avec l'IA — {doc_title}")
        self.resize(920, 680)
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        # 1. En-tête informatif
        header_card = QFrame()
        header_card.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 12px;
            }}
        """)
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(12)

        ico_lbl = QLabel()
        ico_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(32, 32))
        h_layout.addWidget(ico_lbl)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        title_lbl = QLabel(f"Restructuration Documentaire Intelligente : <b>{self.doc_title}</b>")
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        subtitle_lbl = QLabel("Transforme les transcriptions orales (YouTube / Audio) et textes bruts en cours didactiques structurés (KaTeX, chapitres, vocabulaire).")
        subtitle_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        info_layout.addWidget(title_lbl)
        info_layout.addWidget(subtitle_lbl)
        h_layout.addLayout(info_layout, 1)

        layout.addWidget(header_card)

        # 2. Options de structuration & Modèle IA
        config_box = QFrame()
        config_box.setStyleSheet(f"""
            QFrame {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
            }}
        """)
        c_layout = QVBoxLayout(config_box)
        c_layout.setSpacing(10)

        row_settings = QHBoxLayout()
        row_settings.setSpacing(14)

        # Choix du profil
        col_prof = QVBoxLayout()
        col_prof.setSpacing(4)
        lbl_prof = QLabel("Profil pédagogique :")
        lbl_prof.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_SECONDARY};")
        self.cb_profile = QComboBox()
        self.cb_profile.addItem("🎓 Synthèse Didactique & Pédagogique (Cours, KaTeX, Définitions)", StructuringProfile.DIDACTIC.value)
        self.cb_profile.addItem("📝 Retranscription Polie & Chapitrée (Verbatim structuré)", StructuringProfile.POLISHED_VERBATIM.value)
        self.cb_profile.addItem("⚡ Fiche de Synthèse (Cheatsheet, Tableaux, Points Clés)", StructuringProfile.EXECUTIVE_SUMMARY.value)
        self.cb_profile.setStyleSheet(f"""
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 5px;
                font-size: 12px;
            }}
        """)
        col_prof.addWidget(lbl_prof)
        col_prof.addWidget(self.cb_profile)
        row_settings.addLayout(col_prof, 1)

        # Sélecteur de modèle LLM
        col_model = QVBoxLayout()
        col_model.setSpacing(4)
        lbl_model = QLabel("Moteur IA utilisé :")
        lbl_model.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_SECONDARY};")
        self.model_selector = ModelSelectorWidget(allow_inherit=True, show_badges=False, parent=self)
        col_model.addWidget(lbl_model)
        col_model.addWidget(self.model_selector)
        row_settings.addLayout(col_model, 1)

        c_layout.addLayout(row_settings)

        # Rangée des cases à cocher
        cb_row = QHBoxLayout()
        cb_row.setSpacing(16)
        self.chk_timestamps = QCheckBox("Conserver les repères temporels [MM:SS]")
        self.chk_timestamps.setChecked(True)
        self.chk_katex = QCheckBox("Normaliser KaTeX ($..$ / $$..$$)")
        self.chk_katex.setChecked(True)
        self.chk_takeaways = QCheckBox("Générer les Points Clés à Retenir")
        self.chk_takeaways.setChecked(True)

        cb_row.addWidget(self.chk_timestamps)
        cb_row.addWidget(self.chk_katex)
        cb_row.addWidget(self.chk_takeaways)
        cb_row.addStretch()

        self.btn_run = PrimaryButton("⚡ Structurer le document")
        self.btn_run.setFixedHeight(30)
        self.btn_run.clicked.connect(self._on_start_structuring)
        cb_row.addWidget(self.btn_run)

        c_layout.addLayout(cb_row)

        # Barre de progression et état
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.hide()
        c_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("Prêt à structurer.")
        self.lbl_status.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        c_layout.addWidget(self.lbl_status)

        layout.addWidget(config_box)

        # 3. Vue comparatif côte-à-côte (Original vs Résultat)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panneau Gauche : Original
        orig_container = QWidget()
        orig_layout = QVBoxLayout(orig_container)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_layout.setSpacing(4)
        lbl_orig = QLabel(f"Texte d'origine ({len(self.original_content.split()):,} mots) :")
        lbl_orig.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_MUTED};")
        self.txt_original = QPlainTextEdit()
        self.txt_original.setPlainText(self.original_content)
        self.txt_original.setReadOnly(True)
        self.txt_original.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_MUTED};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 11px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        orig_layout.addWidget(lbl_orig)
        orig_layout.addWidget(self.txt_original, 1)
        splitter.addWidget(orig_container)

        # Panneau Droit : Résultat Structuré
        res_container = QWidget()
        res_layout = QVBoxLayout(res_container)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(4)
        lbl_res = QLabel("Résultat structuré par l'IA :")
        lbl_res.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.ACCENT_PRIMARY};")
        self.txt_result = QPlainTextEdit()
        self.txt_result.setPlaceholderText("Le document structuré et formaté apparaîtra ici après génération...")
        self.txt_result.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                font-family: '{DesignTokens.FONT_CODE}';
                font-size: 12px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM}px;
                padding: 6px;
            }}
        """)
        res_layout.addWidget(lbl_res)
        res_layout.addWidget(self.txt_result, 1)
        splitter.addWidget(res_container)

        splitter.setSizes([350, 550])
        layout.addWidget(splitter, 1)

        # 4. Barre d'actions inférieure (Permettre les deux : Remplacer ou Copie)
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self.btn_cancel = SecondaryButton("Fermer")
        self.btn_cancel.clicked.connect(self.reject)
        bottom_bar.addWidget(self.btn_cancel)

        bottom_bar.addStretch()

        self.btn_save_copy = SecondaryButton("📄 Créer une copie structurée")
        self.btn_save_copy.setIcon(load_phosphor_icon("ph.copy", color=DesignTokens.COLOR_BLUE))
        self.btn_save_copy.setToolTip("Enregistre un nouveau document 'Titre (Structuré IA)' dans votre collection")
        self.btn_save_copy.setEnabled(False)
        self.btn_save_copy.clicked.connect(self._on_save_as_copy)
        bottom_bar.addWidget(self.btn_save_copy)

        self.btn_apply_editor = PrimaryButton("💾 Remplacer dans l'éditeur")
        self.btn_apply_editor.setIcon(load_phosphor_icon("ph.check", color="white"))
        self.btn_apply_editor.setToolTip("Remplace le contenu actuel de l'éditeur par le résultat structuré")
        self.btn_apply_editor.setEnabled(False)
        self.btn_apply_editor.clicked.connect(self._on_apply_to_editor)
        bottom_bar.addWidget(self.btn_apply_editor)

        layout.addLayout(bottom_bar)

    @Slot()
    def _on_start_structuring(self) -> None:
        """Déclenche la restructuration asynchrone par l'IA."""
        raw_prof = str(self.cb_profile.currentData())
        profile = StructuringProfile(raw_prof)

        options = StructuringOptions(
            profile=profile,
            preserve_timestamps=self.chk_timestamps.isChecked(),
            normalize_katex=self.chk_katex.isChecked(),
            include_executive_summary=True,
            include_key_takeaways=self.chk_takeaways.isChecked(),
        )

        # Résolution du provider IA
        provider = None
        selected_model = self.model_selector.get_current_model()
        if selected_model is not None:
            provider = AIManager.create_provider_from_config(selected_model)

        self.btn_run.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(10)
        self.lbl_status.setText("Initialisation de l'IA...")

        self._worker = StructuringWorker(
            content=self.original_content,
            options=options,
            provider=provider,
            parent=self,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    @Slot(str, float)
    def _on_worker_progress(self, msg: str, ratio: float) -> None:
        self.progress_bar.setValue(int(ratio * 100))
        self.lbl_status.setText(msg)

    @Slot(str)
    def _on_worker_finished(self, structured_text: str) -> None:
        self.structured_result = structured_text
        self.txt_result.setPlainText(structured_text)
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        self.btn_apply_editor.setEnabled(True)
        self.btn_save_copy.setEnabled(True)
        self.lbl_status.setText(f"✅ Structuration terminée ({len(structured_text.split()):,} mots générés).")

    @Slot(str)
    def _on_worker_error(self, err_msg: str) -> None:
        self.progress_bar.hide()
        self.btn_run.setEnabled(True)
        self.lbl_status.setText(f"❌ Erreur : {err_msg}")

    @Slot()
    def _on_apply_to_editor(self) -> None:
        text = self.txt_result.toPlainText().strip()
        if text:
            self.structure_applied.emit(text)
            self.accept()

    @Slot()
    def _on_save_as_copy(self) -> None:
        text = self.txt_result.toPlainText().strip()
        if text:
            self.structure_saved_as_copy.emit(text)
            self.accept()
