"""Dialogue d'édition et de test de scripts Python personnalisés pour les étapes DAG."""

import json
from typing import Any, Optional

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import PythonToolModel
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.tools.tool_service import ToolService
from ankiforge.ui.components import SecondaryButton, PrimaryButton
from ankiforge.ui.theme import DesignTokens


class ToolEditorDialog(QDialog):
    """Fenêtre modale permettant de concevoir, modifier et tester un script d'outil Python."""

    DEFAULT_TEMPLATE = '''def run(state):
    """
    Fonction principale exécutée lors de l'étape DAG.
    Paramètre :
        state : instance de PipelineRunState
    Variables utiles :
        cards = state.get_variable("generated_cards")
        last_out = state.get_variable("last_output")
        text_source = state.get_variable("text_source")
    Retour :
        Valeur ou dictionnaire de résultat
    """
    cards = state.get_variable("generated_cards")
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict) and "Front" in card:
                card["Front"] = card["Front"].strip()
        state.set_variable("generated_cards", cards)
    
    return {"status": "success", "processed_cards": len(cards) if isinstance(cards, list) else 0}
'''

    def __init__(self, tool: Optional[PythonToolModel] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.tool = tool
        self.setWindowTitle("Éditeur d'Outil Python" if not tool else f"Éditer : {tool.display_name}")
        self.resize(750, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)
        self._setup_ui()
        if tool:
            self._load_tool(tool)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # En-tête
        lbl_header = QLabel("🐍 Conception de Script Python pour Workflow DAG")
        lbl_header.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(lbl_header)

        # 1. Identifiant & Nom d'affichage
        row_names = QHBoxLayout()
        row_names.setSpacing(10)

        col_name = QVBoxLayout()
        lbl_name = QLabel("Identifiant technique (name) :")
        lbl_name.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("ex: clean_custom_formulas")
        self.edit_name.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 6px; border-radius: 4px;")
        col_name.addWidget(lbl_name)
        col_name.addWidget(self.edit_name)

        col_display = QVBoxLayout()
        lbl_display = QLabel("Nom d'affichage (Interface) :")
        lbl_display.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.edit_display = QLineEdit()
        self.edit_display.setPlaceholderText("ex: 🧹 Nettoyeur Formules Spéciales")
        self.edit_display.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 6px; border-radius: 4px;")
        col_display.addWidget(lbl_display)
        col_display.addWidget(self.edit_display)

        row_names.addLayout(col_name, 1)
        row_names.addLayout(col_display, 2)
        layout.addLayout(row_names)

        # 2. Description
        lbl_desc = QLabel("Description du traitement :")
        lbl_desc.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        self.edit_desc = QLineEdit()
        self.edit_desc.setPlaceholderText("Expliquez brièvement ce que fait ce filtre ou script...")
        self.edit_desc.setStyleSheet(f"background: {DesignTokens.BG_INPUT}; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_PRIMARY}; padding: 6px; border-radius: 4px;")
        layout.addWidget(lbl_desc)
        layout.addWidget(self.edit_desc)

        # 3. Éditeur de code Python
        lbl_code = QLabel("Code Python exécutable (doit contenir 'def run(state):') :")
        lbl_code.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold; margin-top: 4px;")
        layout.addWidget(lbl_code)

        self.edit_code = QTextEdit()
        self.edit_code.setText(self.DEFAULT_TEMPLATE)
        self.edit_code.setStyleSheet(f"""
            QTextEdit {{
                background-color: #0b0d11;
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: #a5d6ff;
                font-family: monospace;
                font-size: 12px;
                line-height: 1.4;
                padding: 8px;
                border-radius: 6px;
            }}
        """)
        layout.addWidget(self.edit_code, 1)

        # 4. Console de test unitaire
        self.edit_console = QTextEdit()
        self.edit_console.setReadOnly(True)
        self.edit_console.setMaximumHeight(80)
        self.edit_console.setPlaceholderText("Console de test : Cliquez sur '🧪 Tester le Script' pour valider...")
        self.edit_console.setStyleSheet(f"""
            QTextEdit {{
                background-color: {DesignTokens.BG_INPUT};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                color: {DesignTokens.TEXT_SECONDARY};
                font-family: monospace;
                font-size: 11px;
                padding: 4px;
                border-radius: 4px;
            }}
        """)
        layout.addWidget(self.edit_console)

        # 5. Boutons d'action
        row_actions = QHBoxLayout()
        self.btn_test = SecondaryButton("🧪 Tester le Script")
        self.btn_test.clicked.connect(self._on_test_clicked)
        row_actions.addWidget(self.btn_test)

        row_actions.addStretch()

        btn_cancel = QPushButton("Annuler")
        btn_cancel.setStyleSheet(f"background: transparent; border: 1px solid {DesignTokens.BORDER_COLOR}; color: {DesignTokens.TEXT_MUTED}; padding: 6px 14px; border-radius: 4px;")
        btn_cancel.clicked.connect(self.reject)
        row_actions.addWidget(btn_cancel)

        self.btn_save = PrimaryButton("💾 Enregistrer l'Outil")
        self.btn_save.clicked.connect(self._on_save_clicked)
        row_actions.addWidget(self.btn_save)

        layout.addLayout(row_actions)

    def _load_tool(self, tool: PythonToolModel) -> None:
        self.edit_name.setText(tool.name)
        if tool.is_builtin:
            self.edit_name.setReadOnly(True)
        self.edit_display.setText(tool.display_name)
        self.edit_desc.setText(tool.description or "")
        self.edit_code.setText(tool.code)

    def _on_test_clicked(self) -> None:
        """Exécute un test du script sur un état d'essai."""
        code = self.edit_code.toPlainText()
        if "def run(" not in code:
            self.edit_console.setHtml("<span style='color: #ef4444;'>❌ Erreur : Le script doit définir une fonction 'def run(state):'.</span>")
            return

        try:
            compile(code, "<test_custom_tool>", "exec")
        except SyntaxError as e:
            self.edit_console.setHtml(f"<span style='color: #ef4444;'>❌ Erreur de syntaxe Python : {e}</span>")
            return

        state = PipelineRunState(initial_prompt="Exemple de texte mathématique avec $x^2$ et <p></p>")
        state.set_variable(
            "generated_cards",
            [
                {"Front": "  Quelle est la formule d'Euler ?  ", "Back": "e^{i\\pi} + 1 = 0"},
                {"Front": "Quelle est la formule d'Euler ?", "Back": "Doublon quasi-identique"},
            ],
        )

        local_scope: dict[str, Any] = {}
        global_scope: dict[str, Any] = {"state": state, "json": json}
        try:
            exec(code, global_scope, local_scope)  # nosec B102
            run_fn = local_scope.get("run") or global_scope.get("run")
            if not callable(run_fn):
                self.edit_console.setHtml("<span style='color: #ef4444;'>❌ 'run' n'est pas appelable.</span>")
                return

            res = run_fn(state)
            self.edit_console.setHtml(
                f"<span style='color: #10b981;'><b>✅ Exécution réussie !</b></span><br>"
                f"<span style='color: #94a3b8;'>Résultat : {res}</span><br>"
                f"<span style='color: #94a3b8;'>Cartes : {len(state.get_variable('generated_cards', []))}</span>"
            )
        except Exception as e:
            self.edit_console.setHtml(f"<span style='color: #ef4444;'>❌ Exception à l'exécution : {e}</span>")

    def _on_save_clicked(self) -> None:
        name = self.edit_name.text().strip()
        display = self.edit_display.text().strip()
        desc = self.edit_desc.text().strip()
        code = self.edit_code.toPlainText().strip()

        if not name or not display:
            QMessageBox.warning(self, "Champs requis", "Veuillez spécifier un identifiant et un nom d'affichage.")
            return

        if "def run(" not in code:
            QMessageBox.warning(self, "Signature requise", "Le code doit définir la fonction 'def run(state):'.")
            return

        try:
            compile(code, "<custom_tool>", "exec")
        except SyntaxError as e:
            QMessageBox.critical(self, "Erreur de syntaxe", f"Impossible d'enregistrer : {e}")
            return

        is_builtin = self.tool.is_builtin if self.tool else False
        ToolService.create_or_update_tool(
            name=name,
            display_name=display,
            description=desc,
            code=code,
            is_builtin=is_builtin,
        )
        self.accept()
