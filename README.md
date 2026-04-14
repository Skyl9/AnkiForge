#  AnkiForge

![Python Version](https://img.shields.io/badge/python-3.12%2B-blue.svg)
![PySide6](https://img.shields.io/badge/PySide6-GUI-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

**AnkiForge** est une application de bureau native et robuste conçue pour automatiser, optimiser et orchestrer la création de flashcards Anki grâce à l'Intelligence Artificielle.

Fini le copier-coller manuel et le formatage laborieux : importez vos PDF, assemblez vos agents IA, et générez des paquets entiers avec un formatage parfait (HTML/CSS/LaTeX) prêts à être exportés vers Anki.

*(Insérez ici un GIF ou une capture d'écran de l'interface principale)*

---

## Fonctionnalités Principales

* **L'Usine à Cartes (Traitement par lots)** : Importez de lourds PDF (traités via OCR *Marker*). AnkiForge découpe intelligemment le texte (Chunking Sémantique ou Overlap) et génère des cartes en arrière-plan.
* **Studio Consultant IA** : Une interface de discussion avancée. Utilisez `@` pour charger vos documents ou paquets Anki en contexte, et `/` pour lancer des commandes (ex: `/audit` pour trouver des erreurs dans vos cartes).
* **L'Archiviste IA (Auto-Tagging)** : Sélectionnez des centaines de cartes orphelines et laissez l'IA lire leur contenu pour leur attribuer des tags pertinents automatiquement.
* **Bouclier Anti-Hallucination** : Un parseur JSON ultra-résilient qui force n'importe quel LLM (même les plus petits modèles locaux) à respecter la structure stricte de votre base de données.
* **La Forge Immortelle (Background Daemon)** : Les tâches longues (OCR, génération de masse) tournent en tâche de fond sur une base SQLite. Si vous fermez l'application, le travail reprendra exactement là où il s'est arrêté au prochain lancement.
* **Détection de Doublons Ultra-Rapide** : Résolution des conflits "façon Git" avec calcul de distance de Levenshtein propulsé par une extension native en C.
* ️**Prévisualisation Native Anki** : Rendu en direct identique au moteur d'Anki (support des balises conditionnelles `{{#Champ}}`, `{{cloze:Texte}}` et MathJax/LaTeX).

## Stack Technique

AnkiForge a été pensé pour être agnostique, rapide et maintenable :

* **Moteur & GUI** : Python 3.12+ / PySide6 (Qt) / QtWebEngine
* **Base de Données** : SQLite via l'ORM *Peewee*
* **Gestionnaire de Paquets** : `uv` (Astral)
* **LLMs Supportés** : Ollama (Local), Google Gemini, Groq, Anthropic, OpenAI.
* **Extraction PDF** : `marker-pdf` (Deep Learning OCR)
* **Performances** : Extension C native (`levenshtein_distance.c`)
* **Exportation** : Compatibilité `.apkg` 100% native via `genanki`

## Installation & Lancement

### Prérequis
* Python 3.12 ou supérieur
* [uv](https://docs.astral.sh/uv/) installé sur votre système
* *(Optionnel)* Un compilateur C (GCC/Clang) pour compiler l'extension de performance.

### Étapes

1. **Cloner le projet**
   ```bash
   git clone [https://github.com/votre-nom/AnkiForge.git](https://github.com/votre-nom/AnkiForge.git)
   cd AnkiForge
2. **Installer les dépendances avec `uv`**
   ```bash
   uv sync
   ```

3. **Compiler l'extension C (Recommandé pour la vitesse)**
   ```bash
   # Sur Linux / macOS
   gcc -shared -o src/ankiforge/c_ext/levenshtein_distance.so -fPIC src/ankiforge/c_ext/levenshtein_distance.c
   # Note: L'application fonctionnera quand même sans, via un fallback en Python (difflib).
   ```

4. **Lancer l'application**
   ```bash
   uv run ankiforge
   ```

## ⚙️ Configuration IA

Au premier lancement, AnkiForge créera un fichier `.env` dans son dossier de données (ex: `~/.ankiforge/.env` ou `AppData/Local/AnkiForge`). 
Vous pouvez y configurer vos clés API, ou le faire directement depuis l'interface graphique (Onglet **Configuration IA**).

## 📦 Build & Déploiement

Le projet inclut des scripts pour compiler l'application en exécutables autonomes (`.exe` / `.app`) :
* **Développement rapide** : Via PyInstaller (voir `build_script/AnkiForge.spec`).
* **Production optimisée** : Via Nuitka pour des performances maximales (voir `build_script/build_prod_mac.sh`).

## 🤝 Contribution

Les contributions (Pull Requests) sont les bienvenues ! 
Pour développer :
1. Créez une branche (`git checkout -b feature/ma-nouvelle-feature`)
2. Vérifiez votre code avec Ruff (`uv run ruff check . --fix`)
3. Vérifiez le typage avec Mypy (`uv run mypy src/ankiforge`)
4. Lancez la suite de tests (`uv run pytest`)

Consultez le fichier `docs/architecture.md` pour comprendre la structure du projet.

## 📜 Licence

Distribué sous la licence MIT. Voir le fichier `LICENSE` pour plus d'informations.