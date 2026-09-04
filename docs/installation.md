# Guide d'Installation 📦

Ce guide détaille l'installation complète d'AnkiForge, la compilation des extensions natives en C, la configuration des modèles d'intelligence artificielle (locaux ou cloud) et le paramétrage du sous-système audio.

---

## 💻 Prérequis Système

Avant de commencer, assurez-vous de disposer des éléments suivants :

- **Système d'exploitation** : macOS (Apple Silicon / Intel), Linux (Ubuntu 22.04+, Debian, Fedora, Arch) ou Windows 10/11 (64-bit).
- **Python 3.12+** : Requis pour la syntaxe moderne (PEP 695 generics, unions `X | Y`).
- **uv** : Le gestionnaire de packages et de projets Python ultra-rapide recommandé par le projet.
- **Compilateur C** : `clang` (Xcode Command Line Tools sur macOS), `gcc` (Linux) ou `MSVC` (Windows) pour la compilation native de l'extension Levenshtein.
- **Git** : Pour cloner le dépôt.

---

## 📥 1. Cloner et Installer les Dépendances

### Installation de `uv` (si nécessaire)
```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Cloner le dépôt AnkiForge
```bash
git clone https://github.com/Skyl9/AnkiForge.git
cd AnkiForge
```

### Créer l'environnement virtuel et synchroniser
Grâce à `uv`, toutes les dépendances (PySide6, Peewee, KaTeX renderer, Edge-TTS, Zensical, etc.) sont installées en quelques secondes :

```bash
uv sync
```

---

## ⚡ 2. Compilation de l'Extension C Native (Levenshtein)

AnkiForge intègre un module C natif (`c_ext/levenshtein_distance.c`) qui accélère considérablement l'algorithme de détection des cartes similaires et doublons.

Pour compiler la bibliothèque partagée (`.so` sur macOS/Linux, `.pyd` sur Windows) :

```bash
uv run python setup_c.py build_ext --inplace
```

> [!TIP]
> **Fallback Automatique :** Si vous ne disposez pas d'un compilateur C ou si la compilation échoue, AnkiForge bascule automatiquement et de manière transparente sur une implémentation pure Python (`ankiforge.utils.c_bridge`). Aucune interruption de service n'a lieu !

---

## 🧠 3. Configuration des Fournisseurs d'Intelligence Artificielle

AnkiForge est **100% agnostique** vis-à-vis des modèles de langage (LLM). Vous pouvez travailler de manière totalement hors-ligne et confidentielle, ou exploiter des modèles cloud de pointe.

=== "Option 1 : 100% Local & Hors-ligne (Ollama - Recommandé)"

    Pour garantir une confidentialité absolue de vos données d'apprentissage :
    1. Installez **Ollama** depuis [ollama.com](https://ollama.com).
    2. Téléchargez un modèle performant pour la structuration de flashcards :
       ```bash
       ollama run llama3.2:latest
       # ou pour des capacités de raisonnement accrues :
       ollama run mistral:latest
       ```
    3. AnkiForge se connecte automatiquement à l'API Ollama locale sur `http://localhost:11434`.

=== "Option 2 : APIs Cloud (Gemini, OpenAI, Anthropic, Groq)"

    Vous pouvez configurer vos clés d'API directement dans l'interface graphique (**Paramètres ➔ Fournisseurs IA**) ou via un fichier `.env` à la racine du projet :

    ```env
    # Google Gemini
    GEMINI_API_KEY="AIzaSy..."

    # OpenAI
    OPENAI_API_KEY="sk-proj-..."

    # Anthropic Claude
    ANTHROPIC_API_KEY="sk-ant-..."

    # Groq (Inférence ultra-rapide)
    GROQ_API_KEY="gsk_..."
    ```

    > [!IMPORTANT]
    > **Sécurité des secrets :** AnkiForge intègre un filtre de masquage asynchrone (`SecretRedactionFilter`). Vos clés d'API ne seront jamais enregistrées en clair dans les logs ou les traces d'erreurs.

---

## 🎙️ 4. Configuration de la Synthèse Vocale (TTS)

AnkiForge propose deux moteurs de synthèse vocale pour oraliser vos flashcards :

1. **Edge-TTS (Par défaut)** : Synthèse vocale neuronale haute qualité de Microsoft. Fonctionne immédiatement via Internet sans nécessiter de clé d'API.
2. **Piper TTS (Local & Hors-ligne)** : Moteur ONNX ultra-léger et rapide. Le binaire et les voix sont téléchargés automatiquement dans `~/.ankiforge/sidecars/piper/` lors du premier choix de Piper dans les paramètres.

> [!NOTE]
> Dans **Paramètres ➔ Audio & TTS**, vous pouvez sélectionner précisément votre périphérique de sortie audio (ex. *Haut-parleurs MacBook Pro* ou *AirPods*) afin d'éviter tout conflit de routage audio avec le système d'exploitation.

---

## 🚀 5. Lancement de l'Application

Une fois l'installation terminée, lancez AnkiForge d'une simple commande :

```bash
uv run ankiforge
```

Pour consulter la présente documentation localement avec rechargement à chaud :

```bash
uv run zensical serve
```

L'interface de documentation sera accessible à l'adresse `http://127.0.0.1:8000`.
