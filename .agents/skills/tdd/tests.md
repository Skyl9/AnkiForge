# Bons et Mauvais Tests dans AnkiForge 🧪

Ce guide fournit des exemples comparatifs concrets en Python 3.12 sur les **3 piliers d'AnkiForge** : algorithmique pure, persistance Peewee ORM et composants UI PySide6 headless.

---

## 1. Pilier Algorithmique Pure : Services Métier & Linter

### ❌ Mauvais Test (Couplé aux détails privés & tautologique)
```python
# MAUVAIS : inspecte les méthodes privées et recalcule la valeur attendue
def test_linter_checks_rule():
    service = LinterService()
    # Violation : appel d'une méthode privée interne
    tokens = service._tokenize_text("Qu'est-ce que l'ADN ? Acide désoxyribonucléique.")
    # Violation : assertion sur l'état intermédiaire
    assert len(tokens) == 8
    # Violation tautologique : recalcule le résultat de la même façon que l'algo
    expected_score = sum(1 for t in tokens if len(t) > 3)
    assert service._compute_density(tokens) == expected_score
```

### ✅ Bon Test (Vérifie le comportement observable via l'interface publique)
```python
# BON : teste le résultat métier public sans se soucier du découpage interne
def test_linter_flags_non_atomic_card():
    service = LinterService()
    card_content = {
        "front": "Quelles sont les 5 étapes du cycle cellulaire ?",
        "back": "1. G1\n2. S\n3. G2\n4. M\n5. Cytocinèse",
    }
    
    report = service.audit_card(card_content)
    
    # Vérifie le comportement attendu selon la règle 4 de Wozniak (Atomicité)
    assert not report.is_valid
    assert any(violation.rule_id == "WOZNIAK_04" for violation in report.violations)
    assert "diviser en cartes individuelles" in report.violations[0].suggestion
```

---

## 2. Pilier Données & Persistance : Peewee ORM

### ❌ Mauvais Test (Mocke l'ORM ou accède au curseur brut)
```python
# MAUVAIS : mocke l'ORM Peewee, ne teste aucune contrainte réelle de schéma
from unittest.mock import MagicMock

def test_create_note_saves_to_db():
    mock_model = MagicMock()
    # Ce mock ne teste ni les contraintes NOT NULL, ni les ForeignKey, ni SQLite
    mock_model.create.return_value = MagicMock(id=42)
    
    note = create_note(mock_model, title="Test")
    assert note.id == 42
    mock_model.create.assert_called_once()
```

### ✅ Bon Test (Utilise la base SQLite isolée en mémoire partagée `mock_db`)
```python
# BON : utilise la fixture canonique 'mock_db' en mémoire partagée
def test_note_creation_cascades_to_cards(mock_db):
    deck = DeckModel.create(name="Biologie")
    note_type = NoteTypeModel.create(name="Basique", css="")
    
    note = NoteModel.create(
        deck=deck,
        note_type=note_type,
        fields_data={"Front": "Mitochondrie", "Back": "Centrale énergétique"},
    )
    card = CardModel.create(note=note, deck=deck, ord=0)
    
    # Test d'intégrité référentielle réelle (on_delete='CASCADE')
    note.delete_instance(recursive=True)
    
    assert CardModel.select().where(CardModel.id == card.id).count() == 0
```

---

## 3. Pilier Interface Graphique : Composants PySide6 Headless

### ❌ Mauvais Test (Absence de headless, inspection de variables internes)
```python
# MAUVAIS : bloque sans headless, vérifie une variable privée sans déclencher de signal
def test_tag_input_widget():
    widget = TagInputWidget()
    widget._raw_text = "biologie, medecine"  # Manipulation d'état interne
    widget._parse_tags()
    assert widget._internal_tag_list == ["biologie", "medecine"]
    # Pas de nettoyage : fuite mémoire de widget Qt
```

### ✅ Bon Test (Headless via `qtbot`, simulation d'événement et signaux)
```python
# BON : utilise qtbot, nettoie le widget et vérifie l'événement et le signal émis
from PySide6.QtCore import Qt

def test_tag_input_emits_signal_on_enter(qtbot, cleanup_qt_widgets):
    widget = TagInputWidget()
    cleanup_qt_widgets(widget)
    qtbot.addWidget(widget)
    
    with qtbot.waitSignal(widget.tags_changed, timeout=1000) as blocker:
        qtbot.keyClicks(widget.line_edit, "biologie, medecine")
        qtbot.keyClick(widget.line_edit, Qt.Key.Key_Return)
        
    assert blocker.args[0] == ["biologie", "medecine"]
    assert widget.line_edit.text() == ""
```
