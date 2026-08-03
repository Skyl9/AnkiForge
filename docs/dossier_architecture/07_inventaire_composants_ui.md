# Inventaire des Composants UI (Audit & Design System)

Ce document maintient la liste détaillée des widgets et composants réutilisables PySide6 développés pour AnkiForge. Il sert de base pour les audits d'interface (WCAG, consistance visuelle, refactoring).
Tous ces composants se trouvent dans `src/ankiforge/ui/components/`.

## 1. Composants Atomiques (Fondations)
* **Boutons (`buttons.py`) :** Boutons primaires, secondaires, boutons avec icônes. Doivent tous respecter les Design Tokens pour le hover/focus.
* **Badges (`badges.py`) :** Étiquettes visuelles (ex: statuts, compteurs de tags).
* **Inputs (`inputs.py`) :** Champs de texte, zones de recherche, textareas (GlowLineEdit, etc.). Doivent gérer le focus ring pour l'accessibilité clavier.
* **Listes (`lists.py`) :** Widgets de liste personnalisés.
* **Tables (`tables.py`) :** Vues tabulaires (ex: grilles de résultats QTableView personnalisées).

## 2. Composants Structurels (Layout)
* **Onglets (`tabs.py`) :** Gestion de la navigation principale ou secondaire par onglets.
* **Panneaux (`panels.py`) :** Les fameux `IdePanel` et dock widgets pour le multi-fenêtrage. Doivent supporter le détachement propre sans fuite mémoire.

## 3. Composants Métier Complexes (Smart Widgets)
Ces composants embarquent de la logique métier spécifique à AnkiForge :
* **Sélecteurs Modaux :**
  * `deck_select_window.py` : Fenêtre de sélection de Deck sous forme d'arbre.
  * `tag_select_window.py` : Fenêtre de sélection de Tags.
* **Widgets de l'Hôpital (Analyse & Audit) :**
  * `linter_widgets.py` : Composants dédiés à l'affichage des cartes malades et des propositions Wozniak.
  * `duplicate_widgets.py` : Matrice de similitude et inspecteur de fusion de doublons (Merge).

---
*Règle d'Audit :* Avant toute création d'un nouveau widget dans une vue, le développeur ou l'IA doit consulter cette liste pour vérifier si un composant atomique existant ne peut pas être assemblé ou étendu.*
