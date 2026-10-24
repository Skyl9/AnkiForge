# Prototypage d'Interface PySide6 🖼️

Construire **plusieurs variantes structurellement différentes** d'un widget, dialogue ou panneau PySide6 pour trancher graphiquement une hésitation d'ergonomie avant toute implémentation définitive.

---

## 1. Principes dans AnkiForge

Dans l'environnement desktop Qt/PySide6 d'AnkiForge, le prototypage UI s'appuie sur deux approches :

### Approche A : Banc d'Essai Autonome Dédié (Préférée)
Créer un script de démonstration jetable (ex: `script/prototype_<nom_vue>.py`) instanciant un dialogue ou une fenêtre de banc d'essai contenant un **`QStackedWidget`** pour basculer instantanément entre les variantes via une barre d'onglets ou des boutons radio.

```python
# Exemple de banc d'essai PySide6 jetable
from PySide6.QtWidgets import QApplication, QDialog, QVBoxLayout, QStackedWidget, QRadioButton, QHBoxLayout


class PrototypeDialog(QDialog):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        # Sélecteur de variantes
        selector = QHBoxLayout()
        self.stack = QStackedWidget()

        btn_a = QRadioButton("Variante A (Panneau latéral)")
        btn_b = QRadioButton("Variante B (Accordéon compact)")
        btn_a.toggled.connect(lambda chk: self.stack.setCurrentIndex(0) if chk else None)
        btn_b.toggled.connect(lambda chk: self.stack.setCurrentIndex(1) if chk else None)
        selector.addWidget(btn_a)
        selector.addWidget(btn_b)
        btn_a.setChecked(True)

        # Ajout des variantes expérimentales
        self.stack.addWidget(VariantAWidget())
        self.stack.addWidget(VariantBWidget())

        layout.addLayout(selector)
        layout.addWidget(self.stack)
```

### Approche B : Validation Visuelle Headless
Pour inspecter le rendu sans serveur graphique X11/Wayland actif :
- Utiliser la commande canonique : `uv run python script/capture_view.py --output /tmp/proto.png`
- Ou déléguer la capture au skill `ui-screenshot` pour afficher l'image directement à l'utilisateur.

---

## 2. Règles du Prototypage d'Interface

1. **Différences structurelles, pas de simples teintes** : les variantes doivent proposer des hiérarchies d'information distinctes (ex: disposition 2 colonnes vs onglets empilés), pas seulement un ajustement de marge.
2. **Données simulées (In-Memory)** : injecter des objets légers fictifs pour alimenter les listes et graphiques sans toucher à la base de données réelle.
3. **Respect des Tokens `DESIGN.md`** : styliser via `StyleEngine` et `DesignTokens` pour que le prototype reflète fidèlement le rendu des 12 thèmes de l'application.
4. **Code jetable** : une fois la variante gagnante retenue, coder le widget définitif selon les standards rigoureux (typage strict 100%, tests headless `pytest-qt`, `tr()`). Supprimer le script jetable.
