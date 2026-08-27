"""
Dialogue interactif de configuration et de gestion des règles d'audit Wozniak et catégories personnalisées.
Permet à l'utilisateur de créer, modifier, activer/désactiver et catégoriser ses règles d'analyse IA.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import LinterRuleModel, seed_default_linter_rules
from ankiforge.ui.components.buttons import PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.icon_loader import load_phosphor_icon

logger = logging.getLogger(__name__)


class LinterRulesManagerDialog(QDialog):
    """
    Dialogue de gestion des règles et catégories d'audit du Linter.
    """

    rules_updated = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("⚙️ Atelier des Règles d'Audit & Catégories Personnalisées")
        self.resize(920, 620)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {DesignTokens.BG_MAIN};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
            QLineEdit, QTextEdit, QComboBox {{
                background-color: {DesignTokens.BG_INPUT};
                color: {DesignTokens.TEXT_PRIMARY};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                padding: 6px;
                font-family: {DesignTokens.FONT_MAIN};
            }}
            QLineEdit:focus, QTextEdit:focus, QComboBox:focus {{
                border-color: {DesignTokens.ACCENT_PRIMARY};
            }}
            QListWidget {{
                background-color: {DesignTokens.BG_PANEL};
                border: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 6px;
                color: {DesignTokens.TEXT_PRIMARY};
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 8px;
                border-bottom: 1px solid {DesignTokens.BORDER_COLOR};
                border-radius: 4px;
            }}
            QListWidget::item:hover {{
                background-color: {DesignTokens.BG_HOVER};
            }}
            QListWidget::item:selected {{
                background-color: {DesignTokens.BG_HOVER};
                color: {DesignTokens.TEXT_PRIMARY};
            }}
        """)

        self._current_rule_id: Optional[int] = None
        self._setup_ui()
        self._load_rules()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Header Bar
        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sliders", color=DesignTokens.ACCENT_PRIMARY).pixmap(24, 24))
        header.addWidget(icon_lbl)

        title_lbl = QLabel("Configuration des Règles d'Audit & Catégories Personnalisées")
        title_lbl.setFont(QFont(DesignTokens.FONT_MAIN, 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY};")
        header.addWidget(title_lbl)
        header.addStretch()

        btn_reset = SecondaryButton("Réinitialiser règles d'origine")
        btn_reset.setIcon(load_phosphor_icon("ph.arrows-counter-clockwise", color=DesignTokens.COLOR_YELLOW))
        btn_reset.clicked.connect(self._on_reset_defaults)
        header.addWidget(btn_reset)

        layout.addLayout(header)

        # 2. Main Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- PANNEAU GAUCHE : Liste des Règles & Filtres ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 8, 0)
        left_layout.setSpacing(8)

        # Filtre & Recherche
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Rechercher une règle...")
        self.search_input.textChanged.connect(self._filter_rules)
        search_row.addWidget(self.search_input)
        left_layout.addLayout(search_row)

        self.category_filter_combo = QComboBox()
        self.category_filter_combo.addItem("Toutes les catégories", userData="all")
        self.category_filter_combo.currentIndexChanged.connect(self._filter_rules)
        left_layout.addWidget(self.category_filter_combo)

        # Liste des règles avec Checkboxes
        self.rules_list = QListWidget()
        self.rules_list.itemClicked.connect(self._on_rule_selected)
        self.rules_list.itemChanged.connect(self._on_rule_item_changed)
        left_layout.addWidget(self.rules_list, 1)

        # Actions gauche
        left_actions = QHBoxLayout()
        btn_new = PrimaryButton("Nouvelle Règle")
        btn_new.setIcon(load_phosphor_icon("ph.plus", color="white"))
        btn_new.clicked.connect(self._on_new_rule)

        self.btn_delete = SecondaryButton("Supprimer")
        self.btn_delete.setIcon(load_phosphor_icon("ph.trash", color=DesignTokens.COLOR_RED))
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete_rule)

        left_actions.addWidget(btn_new)
        left_actions.addWidget(self.btn_delete)
        left_layout.addLayout(left_actions)

        splitter.addWidget(left_widget)

        # --- PANNEAU DROIT : Formulaire d'Édition ---
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)

        right_widget = QWidget()
        self.right_layout = QVBoxLayout(right_widget)
        self.right_layout.setContentsMargins(8, 0, 0, 0)
        self.right_layout.setSpacing(10)

        form_title = QLabel("Détails & Instructions de la Règle")
        form_title.setFont(QFont(DesignTokens.FONT_MAIN, 11, QFont.Weight.Bold))
        form_title.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; border-bottom: 1px solid {DesignTokens.BORDER_COLOR}; padding-bottom: 4px;")
        self.right_layout.addWidget(form_title)

        # Nom
        self.right_layout.addWidget(QLabel("Nom de la règle :"))
        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ex: Principe d'Atomicité Minimale")
        self.right_layout.addWidget(self.txt_name)

        # Catégorie & Label
        cat_row = QHBoxLayout()
        cat_box_layout = QVBoxLayout()
        cat_box_layout.addWidget(QLabel("Identifiant Catégorie :"))
        self.txt_category = QLineEdit()
        self.txt_category.setPlaceholderText("Ex: cat-atomicite, cat-medical, cat-vocab")
        cat_box_layout.addWidget(self.txt_category)

        lbl_box_layout = QVBoxLayout()
        lbl_box_layout.addWidget(QLabel("Titre affiché dans les KPIs :"))
        self.txt_category_label = QLineEdit()
        self.txt_category_label.setPlaceholderText("Ex: Atomicité & Restructuration")
        lbl_box_layout.addWidget(self.txt_category_label)

        cat_row.addLayout(cat_box_layout)
        cat_row.addLayout(lbl_box_layout)
        self.right_layout.addLayout(cat_row)

        # Style (Couleur et Icône)
        style_row = QHBoxLayout()
        col_box = QVBoxLayout()
        col_box.addWidget(QLabel("Couleur (Hex) :"))
        self.txt_color = QLineEdit(DesignTokens.COLOR_RED)
        col_box.addWidget(self.txt_color)

        ico_box = QVBoxLayout()
        ico_box.addWidget(QLabel("Icône Phosphor :"))
        self.txt_icon = QLineEdit("squares-four")
        ico_box.addWidget(self.txt_icon)

        style_row.addLayout(col_box)
        style_row.addLayout(ico_box)
        self.right_layout.addLayout(style_row)

        # Statut actif
        self.chk_is_active = QCheckBox("Activer cette règle lors de l'audit IA")
        self.chk_is_active.setChecked(True)
        self.chk_is_active.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-weight: bold;")
        self.right_layout.addWidget(self.chk_is_active)

        # Description
        self.right_layout.addWidget(QLabel("Description pédagogique :"))
        self.txt_desc = QTextEdit()
        self.txt_desc.setMaximumHeight(60)
        self.txt_desc.setPlaceholderText("Explication de ce que cette règle vise à vérifier.")
        self.right_layout.addWidget(self.txt_desc)

        # Prompt Injection
        self.right_layout.addWidget(QLabel("Instruction système passée à l'IA (Prompt Injection) :"))
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setMaximumHeight(80)
        self.txt_prompt.setPlaceholderText("Consigne stricte pour l'IA (ex: Si le verso fait plus de 20 mots, signale une erreur et reformule...).")
        self.right_layout.addWidget(self.txt_prompt)

        # Exemples Few-Shot
        self.right_layout.addWidget(QLabel("Exemple de mauvaise carte (JSON) :"))
        self.txt_example_bad = QTextEdit()
        self.txt_example_bad.setMaximumHeight(60)
        self.txt_example_bad.setPlaceholderText('{"Recto": "Question complexe...", "Verso": "Réponse surchargée..."}')
        self.right_layout.addWidget(self.txt_example_bad)

        self.right_layout.addWidget(QLabel("Exemple de carte corrigée (JSON) :"))
        self.txt_example_good = QTextEdit()
        self.txt_example_good.setMaximumHeight(60)
        self.txt_example_good.setPlaceholderText('{"Recto": "Question atomique ?", "Verso": "Réponse claire", "Champ Annexe Extra": "Contexte"}')
        self.right_layout.addWidget(self.txt_example_good)

        # Bouton Sauvegarder
        self.btn_save = PrimaryButton("Enregistrer la Règle")
        self.btn_save.setIcon(load_phosphor_icon("ph.floppy-disk", color="white"))
        self.btn_save.clicked.connect(self._on_save_rule)
        self.right_layout.addWidget(self.btn_save)

        self.right_layout.addStretch()
        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)

        splitter.setSizes([380, 520])
        layout.addWidget(splitter, 1)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = SecondaryButton("Fermer")
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _load_rules(self) -> None:
        """Charge toutes les règles depuis Peewee et peuple la liste et le filtre."""
        seed_default_linter_rules()
        rules = list(LinterRuleModel.select().order_by(LinterRuleModel.category, LinterRuleModel.name))

        self.rules_list.blockSignals(True)
        self.rules_list.clear()

        # Peuple le combo des catégories
        categories = sorted(list({r.category for r in rules if r.category}))
        self.category_filter_combo.currentData()
        self.category_filter_combo.blockSignals(True)
        self.category_filter_combo.clear()
        self.category_filter_combo.addItem("Toutes les catégories", userData="all")
        for cat in categories:
            sample_rule = next((r for r in rules if r.category == cat), None)
            label = sample_rule.category_label if sample_rule and sample_rule.category_label else cat
            self.category_filter_combo.addItem(f"📁 {label}", userData=cat)
        self.category_filter_combo.blockSignals(False)

        for rule in rules:
            item = QListWidgetItem()
            status_symbol = "🟢" if rule.is_active else "⚪"
            item.setText(f"{status_symbol} {rule.name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if rule.is_active else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, rule.id)
            self.rules_list.addItem(item)

        self.rules_list.blockSignals(False)

        if self.rules_list.count() > 0:
            self.rules_list.setCurrentRow(0)
            self._on_rule_selected(self.rules_list.item(0))

    def _filter_rules(self) -> None:
        search_txt = self.search_input.text().strip().lower()
        cat_filter = self.category_filter_combo.currentData()

        for i in range(self.rules_list.count()):
            item = self.rules_list.item(i)
            rule_id = item.data(Qt.ItemDataRole.UserRole)
            rule = LinterRuleModel.get_or_none(LinterRuleModel.id == rule_id)
            if not rule:
                continue

            match_search = not search_txt or search_txt in rule.name.lower() or (rule.description and search_txt in rule.description.lower())
            match_cat = cat_filter == "all" or rule.category == cat_filter

            item.setHidden(not (match_search and match_cat))

    def _on_rule_selected(self, item: QListWidgetItem) -> None:
        if not item:
            return

        rule_id = item.data(Qt.ItemDataRole.UserRole)
        rule = LinterRuleModel.get_or_none(LinterRuleModel.id == rule_id)
        if not rule:
            return

        self._current_rule_id = rule.id
        self.btn_delete.setEnabled(True)

        self.txt_name.setText(rule.name)
        self.txt_category.setText(rule.category or "cat-atomicite")
        self.txt_category_label.setText(rule.category_label or "Atomicité & Restructuration")
        self.txt_color.setText(rule.color or DesignTokens.COLOR_RED)
        self.txt_icon.setText(rule.icon_name or "squares-four")
        self.chk_is_active.setChecked(bool(rule.is_active))
        self.txt_desc.setPlainText(rule.description or "")
        self.txt_prompt.setPlainText(rule.prompt_injection or "")
        self.txt_example_bad.setPlainText(rule.example_bad or "")
        self.txt_example_good.setPlainText(rule.example_good or "")

    def _on_rule_item_changed(self, item: QListWidgetItem) -> None:
        """Met à jour l'état is_active de la règle lors d'un clic direct sur la case à cocher."""
        rule_id = item.data(Qt.ItemDataRole.UserRole)
        if not rule_id:
            return

        rule = LinterRuleModel.get_or_none(LinterRuleModel.id == rule_id)
        if rule:
            is_active = item.checkState() == Qt.CheckState.Checked
            if rule.is_active != is_active:
                rule.is_active = is_active
                rule.save()
                status_symbol = "🟢" if is_active else "⚪"
                item.setText(f"{status_symbol} {rule.name}")
                if self._current_rule_id == rule.id:
                    self.chk_is_active.setChecked(is_active)
                self.rules_updated.emit()

    def _on_new_rule(self) -> None:
        """Prépare le formulaire pour la création d'une nouvelle règle."""
        self._current_rule_id = None
        self.btn_delete.setEnabled(False)
        self.txt_name.setText("Nouvelle Règle d'Audit")
        self.txt_category.setText("cat-custom")
        self.txt_category_label.setText("Règles Personnalisées")
        self.txt_color.setText(DesignTokens.COLOR_GREEN)
        self.txt_icon.setText("check-circle")
        self.chk_is_active.setChecked(True)
        self.txt_desc.setPlainText("Description de votre règle d'audit...")
        self.txt_prompt.setPlainText("Consigne stricte pour l'IA...")
        self.txt_example_bad.setPlainText('{"Recto": "...", "Verso": "..."}')
        self.txt_example_good.setPlainText('{"Recto": "...", "Verso": "...", "Champ Annexe Extra": "..."}')
        self.txt_name.setFocus()

    def _on_save_rule(self) -> None:
        """Sauvegarde ou crée la règle en base de données."""
        name = self.txt_name.text().strip()
        if not name:
            show_toast(self, "Le nom de la règle est obligatoire.", is_error=True)
            return

        cat = self.txt_category.text().strip() or "cat-custom"
        cat_label = self.txt_category_label.text().strip() or "Règles Personnalisées"
        color = self.txt_color.text().strip() or DesignTokens.COLOR_RED
        icon_name = self.txt_icon.text().strip() or "squares-four"
        is_active = self.chk_is_active.isChecked()
        desc = self.txt_desc.toPlainText().strip()
        prompt = self.txt_prompt.toPlainText().strip()
        ex_bad = self.txt_example_bad.toPlainText().strip()
        ex_good = self.txt_example_good.toPlainText().strip()

        try:
            if self._current_rule_id:
                rule = LinterRuleModel.get_by_id(self._current_rule_id)
                rule.name = name
                rule.category = cat
                rule.category_label = cat_label
                rule.color = color
                rule.icon_name = icon_name
                rule.is_active = is_active
                rule.description = desc
                rule.prompt_injection = prompt
                rule.example_bad = ex_bad
                rule.example_good = ex_good
                rule.save()
                show_toast(self, f"Règle '{name}' mise à jour.")
            else:
                rule = LinterRuleModel.create(
                    name=name,
                    category=cat,
                    category_label=cat_label,
                    color=color,
                    icon_name=icon_name,
                    is_active=is_active,
                    description=desc,
                    prompt_injection=prompt,
                    example_bad=ex_bad,
                    example_good=ex_good,
                )
                self._current_rule_id = rule.id
                show_toast(self, f"Règle '{name}' créée avec succès !")

            self._load_rules()
            self.rules_updated.emit()

        except Exception as e:
            logger.error("Erreur sauvegarde règle : %s", e)
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer la règle : {e}")

    def _on_delete_rule(self) -> None:
        if not self._current_rule_id:
            return

        rule = LinterRuleModel.get_or_none(LinterRuleModel.id == self._current_rule_id)
        if not rule:
            return

        reply = QMessageBox.question(
            self,
            "Supprimer la règle",
            f"Voulez-vous vraiment supprimer la règle '{rule.name}' ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            rule.delete_instance()
            self._current_rule_id = None
            show_toast(self, "Règle supprimée.")
            self._load_rules()
            self.rules_updated.emit()

    def _on_reset_defaults(self) -> None:
        """Rétablit les règles Wozniak d'origine."""
        reply = QMessageBox.question(
            self,
            "Réinitialiser les règles",
            "Voulez-vous réinitialiser toutes les règles d'audit aux valeurs d'origine de Piotr Wozniak ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            LinterRuleModel.delete().execute()
            seed_default_linter_rules()
            show_toast(self, "Règles Wozniak d'origine rétablies !")
            self._load_rules()
            self.rules_updated.emit()
