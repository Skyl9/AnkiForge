"""
Dialogue d'invitation non-bloquante pour la transmission des rapports de crash.
Permet de visualiser l'incident en toute transparence (traceback, environnement),
de copier ou exporter le rapport Markdown sanitisé, ou de le transmettre sur GitHub.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.crash_reporter_service import (
    CrashReport,
    CrashReporterService,
)
from ankiforge.services.feedback_service import FeedbackService, SystemDiagnosticInfo
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_phosphor_icon
from ankiforge.version import get_version_info

logger = logging.getLogger(__name__)


class CrashReportDialog(QDialog):
    """
    Dialogue non-bloquant de proposition de transmission du crash report.
    Affiche un aperçu exhaustif des données envoyées (secrets masqués),
    propose la copie / l'export ou l'ouverture GitHub, et permet de désactiver
    l'invite au démarrage via les préférences.
    """

    def __init__(
        self,
        crash_info: CrashReport,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CrashReportDialog")
        # Invite explicitement non-bloquante pour laisser l'utilisateur interagir avec l'application
        self.setModal(False)
        self.setWindowTitle(self.tr("Rapport d'arrêt inattendu d'AnkiForge"))
        self.setMinimumSize(720, 560)
        self.resize(780, 640)

        self.crash_info = crash_info
        self._diagnostics: SystemDiagnosticInfo = FeedbackService.collect_diagnostics()
        self._markdown_payload: str = CrashReporterService.build_markdown_report(self.crash_info, self._diagnostics)

        self._setup_ui()
        self._apply_styles()

        # Raccourci Échap pour fermer et acquitter
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self._on_ignore_clicked)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(22, 20, 22, 18)
        root_layout.setSpacing(14)

        # ── 1. En-tête avec Icône d'alerte et bouton fermer ──
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        icon_lbl = QLabel()
        icon = load_phosphor_icon("warning-octagon", color=DesignTokens.COLOR_RED)
        if not icon.isNull():
            icon_lbl.setPixmap(icon.pixmap(30, 30))
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(3)

        main_title = QLabel(self.tr("AnkiForge s'est arrêté de manière inattendue"))
        main_title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(main_title)

        sub_title = QLabel(self.tr("Un incident est survenu lors de la session précédente. Vous pouvez nous aider à le corriger en transmettant ce rapport anonymisé."))
        sub_title.setWordWrap(True)
        sub_title.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(sub_title)

        header_layout.addLayout(title_col, stretch=1)

        btn_close = IconButton("ph.x", tooltip=self.tr("Fermer (Échap)"), size=26)
        btn_close.clicked.connect(self._on_ignore_clicked)
        header_layout.addWidget(btn_close)

        root_layout.addWidget(header_widget)

        # ── 2. Bandeau de métadonnées de l'incident ──
        meta_frame = QFrame()
        meta_frame.setObjectName("MetaFrame")
        meta_frame.setStyleSheet(
            f"QFrame#MetaFrame {{ background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; border-radius: {DesignTokens.RADIUS_MD}px; padding: 6px 12px; }}"
        )
        meta_layout = QHBoxLayout(meta_frame)
        meta_layout.setContentsMargins(8, 6, 8, 6)
        meta_layout.setSpacing(16)

        v_info = get_version_info()
        ts_text = self.crash_info.timestamp or self.tr("Date inconnue")

        meta_layout.addWidget(QLabel(tr("📅 %1", ts_text)))
        meta_layout.addWidget(QLabel(tr("⚙️ Profil : %1", self.crash_info.active_profile)))
        meta_layout.addWidget(QLabel(tr("📦 Version : v%1", v_info.short_display_version)))
        meta_layout.addWidget(QLabel(tr("💻 OS : %1", self.crash_info.os_platform)))
        meta_layout.addStretch(1)

        root_layout.addWidget(meta_frame)

        # ── 3. Label de transparence et zone d'aperçu ──
        preview_header_layout = QHBoxLayout()
        lbl_preview_title = QLabel(self.tr("Aperçu des données transmises (clés d'API et secrets automatiquement masqués) :"))
        lbl_preview_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        preview_header_layout.addWidget(lbl_preview_title)
        preview_header_layout.addStretch(1)

        lbl_shield = QLabel(self.tr("🔒 Données anonymisées"))
        lbl_shield.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 11px; font-weight: 600;")
        preview_header_layout.addWidget(lbl_shield)

        root_layout.addLayout(preview_header_layout)

        self.preview_edit = QTextEdit()
        self.preview_edit.setObjectName("CrashPreviewEdit")
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setFont(QFont(DesignTokens.FONT_CODE, 10))
        self.preview_edit.setText(self._markdown_payload)
        root_layout.addWidget(self.preview_edit, stretch=1)

        # ── 4. Option de désactivation de l'invite (Préférence) ──
        self.chk_dont_ask = QCheckBox(self.tr("Ne plus me proposer de transmettre les rapports de crash au démarrage"))
        self.chk_dont_ask.setChecked(not CrashReporterService.is_prompt_enabled())
        self.chk_dont_ask.setStyleSheet(f"color: {DesignTokens.TEXT_SECONDARY}; font-size: 11.5px;")
        self.chk_dont_ask.toggled.connect(self._on_dont_ask_toggled)
        root_layout.addWidget(self.chk_dont_ask)

        # ── 5. Pied de page d'actions (Footer) ──
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(10)

        # Côté Gauche : Consultation du fichier de log
        self.btn_view_log = SecondaryButton("📂 Voir le log")
        self.btn_view_log.setToolTip(self.tr("Ouvrir le fichier crash.log avec votre éditeur par défaut"))
        self.btn_view_log.setFixedHeight(32)
        self.btn_view_log.clicked.connect(self._on_view_log_clicked)
        footer_layout.addWidget(self.btn_view_log)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 12px; font-weight: 600;")
        footer_layout.addWidget(self.lbl_status)
        footer_layout.addStretch(1)

        # Côté Droit : Copier, Exporter, Personnaliser, Transmettre, Ignorer
        self.btn_ignore = SecondaryButton("Ignorer")
        self.btn_ignore.setToolTip(self.tr("Fermer cette invite sans transmettre le rapport"))
        self.btn_ignore.setFixedHeight(32)
        self.btn_ignore.clicked.connect(self._on_ignore_clicked)
        footer_layout.addWidget(self.btn_ignore)

        self.btn_copy = SecondaryButton("📋 Copier le rapport")
        self.btn_copy.setToolTip(self.tr("Copier le rapport complet au format Markdown dans le presse-papier"))
        self.btn_copy.setFixedHeight(32)
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        footer_layout.addWidget(self.btn_copy)

        self.btn_export = SecondaryButton("💾 Exporter (.md)...")
        self.btn_export.setToolTip(self.tr("Enregistrer le rapport dans un fichier Markdown"))
        self.btn_export.setFixedHeight(32)
        self.btn_export.clicked.connect(self._on_export_clicked)
        footer_layout.addWidget(self.btn_export)

        self.btn_customize = SecondaryButton("✏️ Personnaliser...")
        self.btn_customize.setToolTip(self.tr("Ouvrir le formulaire de signalement complet pour ajouter vos remarques"))
        self.btn_customize.setFixedHeight(32)
        self.btn_customize.clicked.connect(self._on_customize_clicked)
        footer_layout.addWidget(self.btn_customize)

        self.btn_send = PrimaryButton("🚀 Transmettre sur GitHub ↗")
        self.btn_send.setToolTip(self.tr("Ouvrir GitHub Issues dans le navigateur avec le rapport pré-rempli"))
        self.btn_send.setFixedHeight(32)
        apply_shadow(self.btn_send, blur=10, offset_y=0, color=DesignTokens.ACCENT_GLOW)
        self.btn_send.clicked.connect(self._on_send_clicked)
        footer_layout.addWidget(self.btn_send)

        root_layout.addLayout(footer_layout)

    def _apply_styles(self) -> None:
        self.setStyleSheet(f"""
            QDialog#CrashReportDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTextEdit#CrashPreviewEdit {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_MD}px;
                padding: 10px;
                line-height: 1.4;
            }}
            QTextEdit#CrashPreviewEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """)

    def _on_dont_ask_toggled(self, checked: bool) -> None:
        """Enregistre immédiatement la préférence utilisateur."""
        CrashReporterService.set_prompt_enabled(not checked)

    def _on_copy_clicked(self) -> None:
        """Copie le rapport Markdown dans le presse-papier et acquitte le crash."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._markdown_payload)
        CrashReporterService.acknowledge_crash(self.crash_info)
        self.lbl_status.setText(self.tr("✓ Rapport copié dans le presse-papier !"))

    def _on_export_clicked(self) -> None:
        """Exporte le rapport dans un fichier Markdown local et acquitte le crash."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Exporter le rapport de crash"),
            str(Path.home() / "ankiforge_crash_report.md"),
            self.tr("Fichiers Markdown (*.md)"),
        )
        if file_path:
            try:
                CrashReporterService.export_crash_report(Path(file_path), self._markdown_payload)
                CrashReporterService.acknowledge_crash(self.crash_info)
                self.lbl_status.setText(self.tr("✓ Rapport enregistré avec succès !"))
            except OSError as e:
                logger.error("Erreur lors de l'exportation du crash report : %s", e)

    def _on_view_log_clicked(self) -> None:
        """Ouvre le fichier crash.log avec l'éditeur par défaut du système."""
        log_path = self.crash_info.log_file or CrashReporterService.get_crash_log_path()
        if log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))
        else:
            self.lbl_status.setText(self.tr("Fichier crash.log introuvable."))

    def _on_customize_clicked(self) -> None:
        """Bascule vers FeedbackDialog en mode bug/crash avec la trace pré-remplie."""
        CrashReporterService.acknowledge_crash(self.crash_info)
        self.close()

        from ankiforge.ui.dialogs.feedback_dialog import FeedbackDialog

        dialog = FeedbackDialog(
            tab="bug",
            initial_title=self.tr("Arrêt inattendu de l'application"),
            context_error=self.crash_info.traceback,
            parent=self.parentWidget(),
        )
        dialog.exec()

    def _on_send_clicked(self) -> None:
        """Ouvre GitHub Issues avec le rapport pré-rempli et acquitte l'incident."""
        CrashReporterService.acknowledge_crash(self.crash_info)
        url_str = CrashReporterService.build_github_issue_url(self.crash_info, self._diagnostics)
        QDesktopServices.openUrl(QUrl(url_str))
        self.lbl_status.setText(self.tr("✓ Page GitHub ouverte dans le navigateur !"))
        self.close()

    def _on_ignore_clicked(self) -> None:
        """Ferme la modale et marque l'incident comme acquitté."""
        CrashReporterService.acknowledge_crash(self.crash_info)
        if self.chk_dont_ask.isChecked():
            CrashReporterService.set_prompt_enabled(False)
        self.close()
