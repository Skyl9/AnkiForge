"""
Tests de validation pour la personnalisation des règles d'audit Wozniak,
la création de catégories personnalisées, et la normalisation universelle des propositions IA.
"""

import json

from PySide6.QtCore import Qt

from ankiforge.database.models import LinterRuleModel, seed_default_linter_rules
from ankiforge.services.ai.linter import normalize_linter_suggestion
from ankiforge.services.workers.linter_worker import LinterWorker
from ankiforge.ui.components.linter_rules_dialog import LinterRulesManagerDialog
from ankiforge.ui.views.analysis_view import AIWozniakLinterTab


def test_normalize_linter_suggestion_variants():
    """Vérifie la normalisation robuste de tous les formats de réponse émis par l'IA."""
    # 1. Format anglais (Front / Back)
    sug_en = {"Front": "What is Python?", "Back": "A language", "Tags": "#prog"}
    norm_en = normalize_linter_suggestion(sug_en)
    assert norm_en["Recto"] == "What is Python?"
    assert norm_en["Verso"] == "A language"
    assert "Tags" in norm_en
    assert "Champ Annexe Extra" in norm_en

    # 2. Format question / réponse
    sug_qr = {"question": "Quelle est la capitale ?", "reponse": "Paris", "extra": "France"}
    norm_qr = normalize_linter_suggestion(sug_qr)
    assert norm_qr["Recto"] == "Quelle est la capitale ?"
    assert norm_qr["Verso"] == "Paris"
    assert norm_qr["Champ Annexe Extra"] == "France"

    # 3. Format texte brut JSON échappé
    sug_str = json.dumps({"Recto": "Q1", "Verso": "R1"})
    norm_str = normalize_linter_suggestion(sug_str)
    assert norm_str["Recto"] == "Q1"
    assert norm_str["Verso"] == "R1"

    # 4. Format multi-cartes / subcards atomiques
    sug_multi = {
        "subcards": [
            {"Recto": "Notion 1", "Verso": "Détail 1"},
            {"Recto": "Notion 2", "Verso": "Détail 2"},
        ]
    }
    norm_multi = normalize_linter_suggestion(sug_multi)
    assert "1. Notion 1 | 2. Notion 2" in norm_multi["Recto"]
    assert "1. Détail 1 | 2. Détail 2" in norm_multi["Verso"]
    assert "2 Cartes Atomiques" in norm_multi["NoteType"]


def test_linter_rules_manager_dialog_crud(qtbot, monkeypatch):
    """Vérifie la modale de configuration des règles : ajout, modification, activation/désactivation."""
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

    seed_default_linter_rules()

    dialog = LinterRulesManagerDialog()
    qtbot.addWidget(dialog)

    # Vérification du chargement des règles initiales
    assert dialog.rules_list.count() >= 4

    # 1. Création d'une nouvelle règle personnalisée
    dialog._on_new_rule()
    dialog.txt_name.setText("Règle Anglicismes & Vocabulaire")
    dialog.txt_category.setText("cat-vocabulaire")
    dialog.txt_category_label.setText("Vocabulaire & Langage")
    dialog.txt_color.setText("#10b981")
    dialog.txt_icon.setText("book-open")
    dialog.chk_is_active.setChecked(True)
    dialog.txt_prompt.setPlainText("Signale tout anglicisme injustifié dans la carte.")
    dialog._on_save_rule()

    # Vérification en base
    created_rule = LinterRuleModel.get_or_none(LinterRuleModel.name == "Règle Anglicismes & Vocabulaire")
    assert created_rule is not None
    assert created_rule.category == "cat-vocabulaire"
    assert created_rule.is_active is True

    # 2. Désactivation directe via la checkbox de la liste
    first_item = dialog.rules_list.item(0)
    first_item.setCheckState(Qt.CheckState.Unchecked)
    # Trigger itemChanged
    dialog._on_rule_item_changed(first_item)
    updated_rule = LinterRuleModel.get_by_id(first_item.data(Qt.ItemDataRole.UserRole))
    assert updated_rule.is_active is False

    # 3. Réinitialisation aux règles par défaut
    dialog._on_reset_defaults()
    assert LinterRuleModel.select().count() == 4


def test_ai_wozniak_tab_dynamic_categories(qtbot):
    """Vérifie que AIWozniakLinterTab génère dynamiquement les KPI cards basées sur les règles configurées."""
    seed_default_linter_rules()

    # Ajout d'une règle dans une 5ème catégorie custom
    LinterRuleModel.get_or_create(
        name="Norme Médicale CIM-11",
        defaults={
            "category": "cat-medical",
            "category_label": "Normes Médicales & Cliniques",
            "color": "#06b6d4",
            "icon_name": "first-aid",
            "is_active": True,
            "prompt_injection": "Vérifie les codes CIM-11.",
        },
    )

    tab = AIWozniakLinterTab()
    qtbot.addWidget(tab)

    # 5 catégories doivent être présentes dans l'interface
    assert "cat-medical" in tab.kpi_cards
    assert tab.kpi_cards["cat-medical"].title == "Normes Médicales & Cliniques"

    # Vérification du basculement sur la catégorie personnalisée
    tab.on_category_kpi_clicked("cat-medical")
    assert tab.active_category == "cat-medical"


def test_linter_worker_builds_dynamic_prompt():
    """Vérifie que le worker injecte bien toutes les règles actives dans le system prompt."""
    seed_default_linter_rules()

    worker = LinterWorker(note_ids=[1])
    prompt = worker._build_dynamic_prompt()

    assert "Tu es un auditeur de flashcards expert" in prompt
    assert "Principe d'Atomicité Minimale" in prompt
    assert "Formatage KaTeX" in prompt
    assert "Questions Univoques" in prompt
    assert "FORMAT DE RÉPONSE STRICT" in prompt
    assert '"Recto"' in prompt
    assert '"Verso"' in prompt
