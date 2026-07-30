# Services IA et Analyse (AnkiForge)

## 1. Agnosticisme et Stratégie des Modèles
L'application adopte une stratégie **Agnostique et Local-First** pour protéger les données de l'utilisateur tout en garantissant des performances maximales.
* **Le Pattern Adapter :** Le code d'AnkiForge n'est pas lié à un SDK spécifique (OpenAI, Anthropic). Il utilise une couche d'abstraction (ex: API compatible OpenAI) permettant de brancher n'importe quel modèle.
* **Ollama (Local) :** Par défaut, pour des raisons de confidentialité (ex: cours de médecine, documents internes), l'application pointe vers un daemon local (Ollama) sur `localhost:11434`.
* **Cloud API :** Si l'utilisateur manque de puissance GPU pour des tâches massives, il peut renseigner une clé API (OpenAI, Anthropic, Gemini) dans les paramètres.

## 2. Agentique vs Pipeline One-Shot
La philosophie d'AnkiForge est d'utiliser le bon paradigme IA pour le bon cas d'usage, car ils ne répondent pas aux mêmes contraintes UX.

### A. Les Pipelines One-Shot (Déterministes)
* **Cas d'usage :** Les vues `creation_view.py`, `pipelines_view.py` et `analysis_view.py`.
* **Philosophie :** Le travail à la chaîne (ex: génération depuis un PDF de 50 pages, ou audit Linter Wozniak de 500 cartes).
* **Mécanique :** Un flux strict et prédictible : *Chunking du texte* ➔ *RAG (Retrieval-Augmented Generation) pour le contexte* ➔ *Prompt contraint (Output JSON)* ➔ *Mise à jour de l'UI (Barre de progression)*.
* **Avantage :** Pas d'hallucination "comportementale" d'un agent qui se perd. C'est rapide, parallélisable dans des QThreads, et parfait pour le Human-in-the-loop où l'on veut juste relire des résultats finaux.

### B. Le Système Agentique (Le Consultant)
* **Cas d'usage :** La vue `consultant_view.py`.
* **Philosophie :** L'exploration et la requête complexe. C'est un copilote conversationnel intelligent intégré à l'IDE.
* **Mécanique :** Basé sur le **Model Context Protocol (MCP)**. L'Agent IA agit comme un Client MCP. AnkiForge embarque un Serveur MCP natif qui expose les outils (ex: `execute_peewee_query()`, `get_cards_by_tag()`) de manière standardisée.
* **Avantage :** L'utilisateur peut faire des requêtes en langage naturel comme : *"Trouve toutes mes cartes d'anatomie qui ont plus de 15 révisions (Sangsues) et propose-moi de les scinder en deux"*. L'agent génère le SQL, récupère les données, analyse et propose une UI de validation.

## 3. Cartographie des Fonctionnalités IA

### Dans Création & Pipelines (Génération)
* **Génération Hiérarchique :** L'IA ne recrache pas des cartes en vrac. Elle génère d'abord un plan/squelette du document source, puis génère des cartes accrochées à cette hiérarchie pour éviter la "connaissance orpheline".
* **Auto-Tagging :** Classification automatique des nouvelles cartes dans les bons sous-paquets avec les tags appropriés.

### Dans Analyse & Audit (Maintenance)
* **Linter Wozniak :** Détection des mauvaises pratiques (Cloze trop long, texte surchargé) et proposition de reformulation atomique.
* **Détection Sémantique de Doublons :** Au-delà du Levenshtein (en C natif pour le texte), l'IA via embeddings permet de trouver les doublons de *sens* (ex: "Rôle de la mitochondrie" vs "À quoi sert la centrale énergétique ?").
* **Diagnostic et Traçabilité des Sources :** 
  * *Traçabilité Structurelle :* Liaison via l'ORM (Peewee) entre les cartes et leur document d'origine. Calcul d'un indicateur de couverture (densité de la source vs nombre de cartes générées).
  * *Moteur Anti-Hallucination :* L'IA vérifie si le verso des cartes ne contredit pas ou n'invente pas des faits par rapport au document source.

### Dans Modèles de Cartes (Stylisation)
* **Génération de Snippets :** Le Consultant peut être appelé pour générer du code CSS/HTML (ex: "Crée-moi un bloc d'alerte rouge arrondi") afin d'enrichir l'inventaire de styles de l'utilisateur.
