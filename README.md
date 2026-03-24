# AnkiForge

AnkiForge est une application de bureau puissante conçue pour automatiser et optimiser la création de flashcards Anki grâce à l'Intelligence Artificielle.
Fini le copier-coller manuel : générez des paquets entiers avec un formatage parfait (HTML/CSS/LaTeX) directement depuis vos cours.

## ✨ Fonctionnalités clés

* **🤖 Architecture Multi-Agents (Pipeline IA)** : Configurez des chaînes d'IA (ex: Extracteur -> Linteur -> Contrôleur Qualité) pour des résultats précis.
* **📝 Éditeur de Modèles Avancé** : Éditez vos types de notes avec un support HTML/CSS complet et une prévisualisation web en temps réel.
* **👁️ Prévisualisation Native** : Rendu en direct identique à Anki (supporte les balises conditionnelles `{{#Champ}}` et MathJax/LaTeX).
* **🗃️ Navigateur de Base de Données** : Éditez, filtrez et organisez vos cartes générées avant de les exporter.
* **📦 Export Natif `.apkg`** : Générez des paquets compatibles à 100% avec l'écosystème Anki.

## 🛠️ Stack Technique

* **Langage** : Python 3.12+
* **Interface Graphique** : PySide6 (Qt) + QtWebEngine
* **Base de Données** : SQLite (via l'ORM Peewee)
* **IA & Modèles** : Support Ollama (LLM locaux) / Gemini / Groq via injection de dépendance.
* **Templating** : Jinja2
* **Export Anki** : Genanki

## 🚀 Installation & Lancement

1. **Cloner le projet**
   ```bash
   git clone [https://github.com/votre-nom/AnkiForge.git](https://github.com/votre-nom/AnkiForge.git)
   cd AnkiForge