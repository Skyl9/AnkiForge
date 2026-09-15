# Personas & Modèles d'Agents 🎭

Dans AnkiForge, les agents ne sont pas de simples invites de commande génériques. Le système de **Personas** permet de structurer, spécialiser et tester un catalogue complet d'assistants pédagogiques adaptés à vos différents domaines d'étude.

---

## 📁 1. Hiérarchie et Organisation en Dossiers

Pour éviter la dispersion de vos prompts au fur et à mesure de l'enrichissement de votre atelier :
- **Dossiers et Sous-Dossiers Récursifs** (`PersonaFolderModel`) : Classez vos personas par thématique (ex: `Médecine ➔ Pharmacologie`, `Langues ➔ Japonais JLPT`, `Droit ➔ Droit Civil`).
- **Recherche et Filtrage** : Localisez rapidement un persona par mots-clés, portée ou modèle LLM assigné.
- **Duplication & Héritage** : Clonez un persona existant pour créer une variante sans repartir de zéro.

---

## 🌐 2. Portées Dédiées (*Scopes*)

Chaque persona se voit attribuer une portée d'intervention précise afin de cloisonner ses responsabilités :

| Portée | Symbole | Rôle & Usage |
| :--- | :---: | :--- |
| **Pipeline DAG** | ⚡ | Conçu spécifiquement pour être invoqué comme étape de traitement automatique au sein d'un graphe DAG. |
| **Consultant MCP** | 🤝 | Équipé pour dialoguer interactivement avec l'utilisateur et orchestrer des outils MCP sur la base SQLite. |
| **Universel** | 🌐 | Disponible simultanément pour les flux de création, l'audit et l'assistance interactive. |

---

## ⚙️ 3. Configuration Avancée & Moteur Jinja2

Chaque persona encapsule une configuration technique complète :
- **Modèle LLM Dédié** : Possibilité d'assigner un modèle spécifique (ex: `mistral` local pour la confidentialité, ou `gpt-4o` pour des synthèses hautement complexes).
- **Hyperparamètres d'Inférence** : Contrôle fin de la température (créativité vs déterminisme) et de la fenêtre de contexte.
- **Templates Jinja2** : Le prompt système prend en charge des variables contextuelles dynamiques :
  ```jinja2
  Tu es un professeur spécialiste en {{ domaine }}.
  Règles d'extraction :
  - Formate chaque concept selon la règle d'atomicité de Wozniak.
  - Niveau cible : {{ niveau_etude | default('Universitaire') }}.
  ```

---

## 🛡️ 4. Agents Dédiés au MCP & Cloisonnement des Outils (*Tool Scoping*)

Pour garantir la sécurité et la pertinence des interventions de l'IA, chaque persona dédié au MCP peut se voir restreindre précisément la liste des outils auxquels il a accès (`allowed_tools`).

### 📦 Catalogue Unifié des 24 Outils MCP
Les outils sont répartis en 5 grandes familles fonctionnelles :
1. **Consultation & Statistiques** : `get_deck_stats`, `inspect_deck_deep_scan`, `get_collection_panorama_360`, `get_cards_by_deck_or_tag`, `find_cards_by_content`, `get_note_full_profile_360`.
2. **Audit & Optimisation Wozniak** : `audit_deck_wozniak`, `audit_card_wozniak`, `find_duplicate_cards`, `propose_card_refactor`, `propose_card_split`.
3. **Modèles & Rendu Visuel** : `list_note_types`, `get_note_type_details`, `update_card_model_css`, `preview_rendered_card`, `propose_note_type_refactor`, `propose_css_tune`.
4. **Documentation & Aide** : `search_app_documentation`, `read_app_doc_page`, `list_app_doc_topics`, `get_feature_quick_help`.
5. **Données & Scripts** : `query_peewee`, `search_document`, `search_attached_documents`, `analyze_coverage_gaps`, `execute_python_tool`.

### ⚡ Préréglages d'Usine (*Presets*) en 1-Clic
L'interface de gestion des agents (`AgentsView`) propose un sélecteur de presets permettant de configurer instantanément les permissions d'un agent :
- **🛡️ Auditeur Wozniak** : Spécialisé en atomicité, détection de doublons et scission de cartes.
- **🎨 Architecte Modèles & CSS** : Spécialisé en refonte graphique, injection de style et templates HTML/Jinja2.
- **📊 Analyste Rétention & SRS** : Spécialisé en santé des paquets, cartes sangsues et métriques d'apprentissage.
- **📚 Chercheur RAG & Documents** : Exploration des sources documentaires, index vectoriels et détection des lacunes (*Gap Analysis*).
- **⚡ Administrateur BDD & Scripts** : Accès direct aux requêtes SQL Peewee transactionnelles et aux scripts Python.
- **🌐 Consultant Universel** : Accès intégral sans restriction (`*`).

### 🔒 Sécurité à l'Exécution (Double Barrière)
1. **Filtrage amont des schémas d'outils** : Le moteur `ConsultantEngine` ne transmet au LLM que les définitions d'outils autorisées pour le persona actif. Le LLM n'a donc même pas connaissance des outils non autorisés.
2. **Interception défensive en aval** : Si un LLM tente d'invoquer un outil hors de son périmètre, l'appel est bloqué au niveau du runtime (`_execute_tool_call`), consigné en journal de sécurité, et renvoie un message d'accès refusé.

---

---

## ✨ 5. Galerie de Modèles & Assistant de Création Rapide (*Wizard*)

Pour éviter le syndrome de la page blanche et permettre aux utilisateurs de démarrer instantanément, AnkiForge intègre un **Assistant de Création Visuel** (`PersonaCreationWizardDialog`) proposant 8 profils d'usine hautement calibrés :

| Modèle Prêt à l'Emploi | Icône | Catégorie | Format | Spécialité Pédagogique |
| :--- | :---: | :--- | :---: | :--- |
| **Générateur Atomique Wozniak** | 🧠 | Pédagogie & SRS | JSON | Questions univoques et concises (règle des 2-3 secondes). |
| **Professeur de Langues & Vocabulaire** | 🌍 | Langues & Traduction | JSON | Lexique contextuel, phonétique IPA et phrase d'exemple bilingue. |
| **Spécialiste Médical & Anatomie** | 🩺 | Sciences & Médical | JSON | Rigueur sémiologique, chaînes physiopathologiques et diagnostics. |
| **Formules Scientifiques & KaTeX** | 📐 | Sciences & Médical | JSON | Rendu mathématique parfait `$ ... $`, unités SI et hypothèses. |
| **Générateur de Cloze (Textes à trous)** | 🧩 | Format Spécialisé | Cloze | Occlusions contextuelles syntaxe Anki `{{c1::terme::indice}}`. |
| **Droit, Normes & Jurisprudence** | ⚖️ | Sciences Humaines | JSON | Visas légaux, conditions cumulatives et effets juridiques. |
| **Consultant Audit & Optimisation MCP** | 🤝 | Audit & MCP | MD | Détection de doublons Levenshtein et refonte interactive. |
| **Architecte Modèles & CSS Anki** | 🎨 | Design & Modèles | MD | Templates Jinja2 propres, responsive et compatible Dark Mode. |

Les utilisateurs avancés peuvent basculer à tout moment sur l'onglet **Agent Vierge Personnalisé** pour créer un persona à partir d'une feuille blanche.

---

## 📋 6. Canevas de Prompts & Antisèche des Variables Jinja2

L'éditeur de persona intègre deux assistants de productivité directement dans l'onglet *Instructions & Prompt* :
- **📋 Insérer un Canevas de Prompt** : Déploie un menu d'architectures de prompts pré-structurés (Formulation Atomique, Cloze Anki, Vocabulaire bilingue, Sciences KaTeX, Diagnostic ReAct).
- **ℹ️ Guide des Variables (`VariableHelperDialog`)** : Une modale interactive récapitulant les balises disponibles (`{{ text_source }}`, `{{ fields }}`, `{{ retrieved_chunks }}`, `{{ last_output }}`, `{{ item }}`, `{{ initial_prompt }}`), leur contexte d'injection et un exemple de valeur avec bouton d'insertion en 1-clic.

---

## 🧪 7. Simulateur Unitaire & Échantillons en 1-Clic (`AgentTestDialog`)

Avant de déployer un persona dans un pipeline de production traitant des centaines de pages :
1. Ouvrez l'**Éditeur de Personas**.
2. Cliquez sur **Tester l'Agent** pour ouvrir la boîte de dialogue de simulation (`AgentTestDialog`).
3. Choisissez un extrait réaliste dans le menu déroulant **Échantillons de cours** (Biologie / Photosynthèse, Histoire / Révolution, Anglais des Affaires, Thermodynamique, Responsabilité Civile).
4. Cliquez sur **Exécuter le Test** : observez l'interpolation Jinja2 en direct et la réponse générée par le modèle sans avoir à saisir manuellement de texte.
