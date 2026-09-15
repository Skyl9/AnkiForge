"""
Boîte de dialogue moderne de Retours & Suggestions d'AnkiForge.
Permet aux utilisateurs de signaler des anomalies avec diagnostics système anonymisés
ou de proposer de nouvelles fonctionnalités, avec envoi GitHub Issues 1-clic et export Markdown.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.services.feedback_service import (
    BugReportData,
    FeatureIdeaData,
    FeedbackService,
    SystemDiagnosticInfo,
)
from ankiforge.ui.components.buttons import IconButton, PrimaryButton, SecondaryButton
from ankiforge.ui.components.inputs import GlowLineEdit
from ankiforge.ui.theme import DesignTokens, apply_shadow
from ankiforge.ui.widgets.toast import ToastLevel, show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class FeedbackDialog(QDialog):
    """
    Modale bivalente de retour utilisateur :
    - Onglet 1 : Signalement de bug avec diagnostic système et logs récents sanitisés.
    - Onglet 2 : Boîte à idées et propositions de fonctionnalités structurées.
    """

    def __init__(
        self,
        tab: str = "bug",
        initial_title: str = "",
        context_error: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Retours & Suggestions AnkiForge")
        self.setMinimumSize(780, 640)
        self.resize(820, 680)
        self.setObjectName("FeedbackDialog")

        # Diagnostics collectés en arrière-plan immédiat
        self._diagnostics: SystemDiagnosticInfo = FeedbackService.collect_diagnostics()
        self._initial_tab = tab
        self._initial_title = initial_title
        self._context_error = context_error

        self._setup_ui()
        self._apply_styles()

        # Raccourci Échap pour fermer
        shortcut_esc = QShortcut(QKeySequence("Escape"), self)
        shortcut_esc.activated.connect(self.close)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(20, 18, 20, 18)
        root_layout.setSpacing(14)

        # ── 1. En-tête Moderne ──
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon = load_phosphor_icon("chat-circle-dots", color=DesignTokens.ACCENT_PRIMARY)
        if not icon.isNull():
            icon_lbl.setPixmap(icon.pixmap(28, 28))
        header_layout.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        main_title = QLabel("Retours & Suggestions")
        main_title.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {DesignTokens.TEXT_PRIMARY};")
        title_col.addWidget(main_title)

        sub_title = QLabel("Partagez un problème rencontré ou proposez une nouvelle fonctionnalité pour faire évoluer AnkiForge.")
        sub_title.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        title_col.addWidget(sub_title)

        header_layout.addLayout(title_col, stretch=1)

        btn_close = IconButton("ph.x", tooltip="Fermer la fenêtre (Échap)", size=26)
        btn_close.clicked.connect(self.close)
        header_layout.addWidget(btn_close)

        root_layout.addWidget(header_widget)

        # ── 2. Onglets Segmentés (Bug vs Idée) ──
        self.tab_bar = QTabBar()
        self.tab_bar.setExpanding(False)
        self.tab_bar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tab_bar.addTab("🐛 Signaler un bug")
        self.tab_bar.addTab("💡 Proposer une idée")
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        root_layout.addWidget(self.tab_bar)

        # ── 3. Stacked Widget avec ScrollArea ──
        self.stacked_widget = QStackedWidget()

        # Onglet 1 : Formulaire Bug
        bug_scroll = QScrollArea()
        bug_scroll.setWidgetResizable(True)
        bug_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.bug_widget = self._create_bug_tab_widget()
        bug_scroll.setWidget(self.bug_widget)
        self.stacked_widget.addWidget(bug_scroll)

        # Onglet 2 : Formulaire Fonctionnalité
        feature_scroll = QScrollArea()
        feature_scroll.setWidgetResizable(True)
        feature_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.feature_widget = self._create_feature_tab_widget()
        feature_scroll.setWidget(self.feature_widget)
        self.stacked_widget.addWidget(feature_scroll)

        root_layout.addWidget(self.stacked_widget, stretch=1)

        # ── 4. Barre d'actions Inférieure (Footer) ──
        footer_frame = QFrame()
        footer_layout = QHBoxLayout(footer_frame)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.setSpacing(10)

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN}; font-size: 12px; font-weight: 600;")
        footer_layout.addWidget(self.lbl_status)
        footer_layout.addStretch(1)

        self.btn_copy = SecondaryButton("📋 Copier Markdown")
        self.btn_copy.setToolTip("Copier le rapport complet au format Markdown dans le presse-papier")
        self.btn_copy.setFixedHeight(32)
        self.btn_copy.clicked.connect(self._on_copy_clicked)
        footer_layout.addWidget(self.btn_copy)

        self.btn_export = SecondaryButton("💾 Exporter (.md)...")
        self.btn_export.setToolTip("Enregistrer le rapport dans un fichier Markdown")
        self.btn_export.setFixedHeight(32)
        self.btn_export.clicked.connect(self._on_export_clicked)
        footer_layout.addWidget(self.btn_export)

        self.btn_github = PrimaryButton("🚀 Ouvrir sur GitHub Issues ↗")
        self.btn_github.setToolTip("Ouvrir GitHub dans le navigateur avec le ticket et les diagnostics pré-remplis")
        self.btn_github.setFixedHeight(32)
        apply_shadow(self.btn_github, blur=10, offset_y=0, color="rgba(99, 102, 241, 0.4)")
        self.btn_github.clicked.connect(self._on_github_clicked)
        footer_layout.addWidget(self.btn_github)

        root_layout.addWidget(footer_frame)

        # Sélectionner l'onglet initial
        if self._initial_tab == "feature":
            self.tab_bar.setCurrentIndex(1)
        else:
            self.tab_bar.setCurrentIndex(0)

    def _create_bug_tab_widget(self) -> QWidget:
        """Construit le formulaire de signalement de bug."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(10)

        # Titre
        lbl_title = QLabel("Titre du problème :")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_title)

        self.bug_title_input = GlowLineEdit(placeholder="Ex: Erreur lors de l'exportation d'un paquet de cartes...")
        if self._initial_title:
            self.bug_title_input.setText(self._initial_title)
        layout.addWidget(self.bug_title_input)

        # Sévérité & Environnement info row
        row_params = QHBoxLayout()
        row_params.setSpacing(12)

        col_sev = QVBoxLayout()
        lbl_sev = QLabel("Sévérité :")
        lbl_sev.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        col_sev.addWidget(lbl_sev)

        self.bug_severity_combo = QComboBox()
        self.bug_severity_combo.addItems(
            [
                "Normal",
                "Faible / Cosmétique",
                "Élevé / Bloquant",
                "Crash complet",
            ]
        )
        if self._context_error:
            self.bug_severity_combo.setCurrentText("Élevé / Bloquant")
        col_sev.addWidget(self.bug_severity_combo)
        row_params.addLayout(col_sev, stretch=1)

        # Info badge
        col_badge = QVBoxLayout()
        lbl_badge_title = QLabel("Profil & Version :")
        lbl_badge_title.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        col_badge.addWidget(lbl_badge_title)

        lbl_badge = QLabel(f"Profil : {self._diagnostics.active_profile} · {self._diagnostics.ankiforge_version}")
        lbl_badge.setStyleSheet(
            f"background-color: {DesignTokens.BG_PANEL}; border: 1px solid {DesignTokens.BORDER_COLOR}; "
            f"border-radius: {DesignTokens.RADIUS_SM}; color: {DesignTokens.TEXT_SECONDARY}; padding: 6px 10px; font-size: 11px;"
        )
        col_badge.addWidget(lbl_badge)
        row_params.addLayout(col_badge, stretch=2)

        layout.addLayout(row_params)

        # Étapes de reproduction
        lbl_steps = QLabel("Étapes pour reproduire :")
        lbl_steps.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_steps)

        self.bug_steps_edit = QTextEdit()
        self.bug_steps_edit.setPlaceholderText("1. Aller sur le Studio de Création...\n2. Sélectionner un document Markdown...\n3. Cliquer sur 'Générer les flashcards'...")
        self.bug_steps_edit.setFixedHeight(75)
        layout.addWidget(self.bug_steps_edit)

        # Comportement observé vs attendu (côte à côte)
        obs_exp_row = QHBoxLayout()
        obs_exp_row.setSpacing(10)

        col_obs = QVBoxLayout()
        lbl_obs = QLabel("Comportement observé :")
        lbl_obs.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        col_obs.addWidget(lbl_obs)
        self.bug_observed_edit = QTextEdit()
        self.bug_observed_edit.setPlaceholderText("Ce qui s'est produit ou message d'erreur affiché...")
        self.bug_observed_edit.setFixedHeight(75)
        if self._context_error:
            self.bug_observed_edit.setText(f"Erreur interceptée :\n{self._context_error}")
        col_obs.addWidget(self.bug_observed_edit)
        obs_exp_row.addLayout(col_obs)

        col_exp = QVBoxLayout()
        lbl_exp = QLabel("Comportement attendu :")
        lbl_exp.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        col_exp.addWidget(lbl_exp)
        self.bug_expected_edit = QTextEdit()
        self.bug_expected_edit.setPlaceholderText("Ce qui aurait dû se produire...")
        self.bug_expected_edit.setFixedHeight(75)
        col_exp.addWidget(self.bug_expected_edit)
        obs_exp_row.addLayout(col_exp)

        layout.addLayout(obs_exp_row)

        # Checkbox diagnostics
        self.bug_include_diag_cb = QCheckBox("Inclure les diagnostics système anonymisés et les logs récents de l'application (recommandé)")
        self.bug_include_diag_cb.setChecked(True)
        self.bug_include_diag_cb.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: 12px; margin-top: 4px;")
        self.bug_include_diag_cb.toggled.connect(self._on_diag_checkbox_toggled)
        layout.addWidget(self.bug_include_diag_cb)

        # Tiroir repliable d'inspection des diagnostics
        self.btn_toggle_drawer = QPushButton("▶ Afficher les informations de diagnostic système collectées")
        self.btn_toggle_drawer.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_drawer.setStyleSheet(f"text-align: left; background: transparent; border: none; color: {DesignTokens.ACCENT_PRIMARY}; font-size: 11px; padding: 2px 0;")
        self.btn_toggle_drawer.clicked.connect(self._toggle_diagnostics_drawer)
        layout.addWidget(self.btn_toggle_drawer)

        self.diag_preview_edit = QTextEdit()
        self.diag_preview_edit.setReadOnly(True)
        self.diag_preview_edit.setFont(QFont("monospace", 10))
        self.diag_preview_edit.setFixedHeight(130)
        self.diag_preview_edit.setText(self._diagnostics.to_markdown(include_logs=True))
        self.diag_preview_edit.setVisible(False)
        layout.addWidget(self.diag_preview_edit)

        layout.addStretch(1)
        return widget

    def _create_feature_tab_widget(self) -> QWidget:
        """Construit le formulaire de proposition d'idée ou de fonctionnalité."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(10)

        # Titre
        lbl_title = QLabel("Titre de la fonctionnalité :")
        lbl_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_title)

        self.feature_title_input = GlowLineEdit(placeholder="Ex: Raccourci clavier universel pour basculer de profil...")
        layout.addWidget(self.feature_title_input)

        # Catégorie & Priorité
        row_meta = QHBoxLayout()
        row_meta.setSpacing(12)

        col_cat = QVBoxLayout()
        lbl_cat = QLabel("Catégorie :")
        lbl_cat.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        col_cat.addWidget(lbl_cat)

        self.feature_cat_combo = QComboBox()
        self.feature_cat_combo.addItems(
            [
                "Studio de Création",
                "RAG & Documents",
                "Édition & Navigateur",
                "Modèles de Cartes",
                "Agents & Pipelines IA",
                "Interface & Ergonomie",
                "Autre",
            ]
        )
        col_cat.addWidget(self.feature_cat_combo)
        row_meta.addLayout(col_cat, stretch=1)

        col_prio = QVBoxLayout()
        lbl_prio = QLabel("Priorité souhaitée :")
        lbl_prio.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        col_prio.addWidget(lbl_prio)

        self.feature_prio_combo = QComboBox()
        self.feature_prio_combo.addItems(
            [
                "Très utile",
                "Optionnel (Nice-to-have)",
                "Essentiel",
            ]
        )
        col_prio.addWidget(self.feature_prio_combo)
        row_meta.addLayout(col_prio, stretch=1)

        layout.addLayout(row_meta)

        # Problème résolu / Cas d'usage
        lbl_problem = QLabel("Quel problème ou besoin cette fonctionnalité résout-elle ?")
        lbl_problem.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_problem)

        self.feature_problem_edit = QTextEdit()
        self.feature_problem_edit.setPlaceholderText("Décrivez le contexte d'utilisation, le cas concret d'usage ou la frustration actuelle que vous rencontrez...")
        self.feature_problem_edit.setFixedHeight(90)
        layout.addWidget(self.feature_problem_edit)

        # Solution suggérée
        lbl_sol = QLabel("Comment imaginez-vous cette fonctionnalité ?")
        lbl_sol.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: 600; font-size: 12px;")
        layout.addWidget(lbl_sol)

        self.feature_solution_edit = QTextEdit()
        self.feature_solution_edit.setPlaceholderText("Décrivez le comportement attendu, l'emplacement idéal dans l'interface ou les options souhaitées...")
        self.feature_solution_edit.setFixedHeight(95)
        layout.addWidget(self.feature_solution_edit)

        layout.addStretch(1)
        return widget

    def _apply_styles(self) -> None:
        """Applique les styles globaux basés sur DesignTokens."""
        self.setStyleSheet(
            f"""
            QDialog#FeedbackDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTabBar::tab {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_SECONDARY};
                padding: 6px 14px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-bottom: none;
                border-top-left-radius: {DesignTokens.RADIUS_SM};
                border-top-right-radius: {DesignTokens.RADIUS_SM};
                margin-right: 4px;
                font-weight: 600;
                font-size: 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.ACCENT_PRIMARY};
                border-bottom: 2px solid {DesignTokens.ACCENT_PRIMARY};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM};
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 6px;
                font-size: 12px;
            }}
            QTextEdit:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: {DesignTokens.RADIUS_SM};
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px 8px;
                font-size: 12px;
                min-height: 26px;
            }}
            QComboBox:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QComboBox QAbstractItemView {{
                background-color: {DesignTokens.BG_PANEL};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                selection-background-color: {DesignTokens.BG_ACTIVE};
                selection-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QCheckBox {{
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 3px;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                background-color: {DesignTokens.BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {DesignTokens.ACCENT_PRIMARY};
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
        """
        )

    def _on_tab_changed(self, index: int) -> None:
        self.stacked_widget.setCurrentIndex(index)
        self.lbl_status.clear()

    def _toggle_diagnostics_drawer(self) -> None:
        show_it = self.diag_preview_edit.isHidden()
        self.diag_preview_edit.setVisible(show_it)
        prefix = "▼ Masquer" if show_it else "▶ Afficher"
        self.btn_toggle_drawer.setText(f"{prefix} les informations de diagnostic système collectées")

    def _on_diag_checkbox_toggled(self, checked: bool) -> None:
        self.btn_toggle_drawer.setEnabled(checked)
        self.diag_preview_edit.setEnabled(checked)

    def _build_current_report(self) -> tuple[str, str, str]:
        """
        Génère (titre, markdown_body, github_label) selon l'onglet actif.
        """
        is_bug = self.tab_bar.currentIndex() == 0

        if is_bug:
            title = self.bug_title_input.text().strip() or "Anomalie dans l'application"
            include_diag = self.bug_include_diag_cb.isChecked()
            data = BugReportData(
                title=title,
                severity=self.bug_severity_combo.currentText(),
                steps=self.bug_steps_edit.toPlainText(),
                observed=self.bug_observed_edit.toPlainText(),
                expected=self.bug_expected_edit.toPlainText(),
                include_diagnostics=include_diag,
                diagnostic_info=self._diagnostics if include_diag else None,
                custom_traceback=self._context_error,
            )
            body = FeedbackService.build_bug_report_markdown(data)
            label = "bug"
            full_title = f"[Bug] {title}"
        else:
            title = self.feature_title_input.text().strip() or "Proposition de fonctionnalité"
            data_feat = FeatureIdeaData(
                title=title,
                category=self.feature_cat_combo.currentText(),
                problem=self.feature_problem_edit.toPlainText(),
                solution=self.feature_solution_edit.toPlainText(),
                priority=self.feature_prio_combo.currentText(),
            )
            body = FeedbackService.build_feature_request_markdown(data_feat)
            label = "enhancement"
            full_title = f"[Feature] {title}"

        return full_title, body, label

    def _on_copy_clicked(self) -> None:
        """Copie le rapport Markdown dans le presse-papier."""
        _, body, _ = self._build_current_report()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(body)
            self.lbl_status.setText("✓ Rapport copié dans le presse-papier !")
            show_toast(
                parent=self,
                message="Le rapport Markdown a été copié dans votre presse-papier.",
                level=ToastLevel.SUCCESS,
                title="Copié",
                duration_ms=3000,
            )

    def _on_export_clicked(self) -> None:
        """Exporte le rapport dans un fichier Markdown choisi par l'utilisateur."""
        title, body, _ = self._build_current_report()
        clean_title = "".join(c for c in title if c.isalnum() or c in ("-", "_")).lower()[:30] or "rapport"
        default_filename = f"ankiforge_feedback_{clean_title}.md"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Enregistrer le rapport de retour",
            default_filename,
            "Markdown (*.md);;Tous les fichiers (*)",
        )
        if file_path:
            FeedbackService.export_report_to_file(Path(file_path), body)
            self.lbl_status.setText(f"✓ Rapport enregistré : {Path(file_path).name}")
            show_toast(
                parent=self,
                message=f"Rapport sauvegardé avec succès dans {Path(file_path).name}",
                level=ToastLevel.SUCCESS,
                title="Export Réussi",
                duration_ms=4000,
            )

    def _on_github_clicked(self) -> None:
        """Ouvre le navigateur sur GitHub avec l'URL pré-remplie."""
        title, body, label = self._build_current_report()
        url_str = FeedbackService.build_github_issue_url(title=title, body=body, label=label)

        # Ouvrir l'URL dans le navigateur par défaut
        qurl = QUrl(url_str)
        QDesktopServices.openUrl(qurl)
        self.lbl_status.setText("✓ Page GitHub ouverte dans votre navigateur")
        show_toast(
            parent=self,
            message="Le ticket a été préparé sur GitHub. Vérifiez et cliquez sur 'Submit issue'.",
            level=ToastLevel.INFO,
            title="GitHub Issues",
            duration_ms=4000,
        )
