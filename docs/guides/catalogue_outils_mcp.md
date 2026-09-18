# Catalogue Exhaustif des Outils MCP 🗂️

Le serveur MCP (`ankiforge.services.ai.mcp_server`) expose **29 outils**, **4 ressources** et **3 prompts** prédéfinis au Consultant IA et à tout client MCP compatible (Cursor, Claude Desktop, VS Code + Copilot).

---

## 🛡️ 1. Audit & Qualité Wozniak

| Outil | Signature | Description | Garde-fous |
| :--- | :--- | :--- | :--- |
| `audit_deck_wozniak` | `(deck_name: str) → str` | Audit global d'un paquet selon les 20 règles de Piotr Wozniak (atomicité, interférences, redondance). | Lecture seule. |
| `audit_card_wozniak` | `(note_id: int) → str` | Analyse chirurgicale d'une carte spécifique au regard des 20 règles. | Lecture seule. |
| `find_duplicate_cards` | `(deck_name: str = "", threshold: float = 0.75) → str` | Détection de cartes quasi-identiques via distance Levenshtein. | Lecture seule, seuil paramétrable. |
| `propose_card_refactor` | `(note_id: int, new_fields_json: str, explanation: str = "") → str` | Propose une reformulation de carte avec Diff pour validation humaine. | **Garde-Fou** : aucune écriture sans approbation explicite. |
| `propose_card_split` | `(note_id: int, new_cards_json: str, explanation: str = "") → str` | Scinde une note dense en N cartes atomiques avec Diff comparatif. | **Garde-Fou** : même protection que refactor. |

---

## 🎨 2. Modèles de Cartes & CSS

| Outil | Signature | Description |
| :--- | :--- | :--- |
| `list_note_types` | `() → str` | Liste tous les modèles de cartes (Note Types) enregistrés. |
| `get_note_type_details` | `(note_type_name: str) → str` | Structure complète : champs requis, templates HTML recto/verso, feuille CSS. |
| `propose_note_type_refactor` | `(note_type_name: str, new_fields_schema_json: str = "", new_css: str = "", new_templates_json: str = "", new_description: str = "", explanation: str = "") → str` | Modification structurelle avec Garde-Fou Diff. |
| `propose_css_tune` | `(note_type_name: str, css_snippet: str, selector: str = "") → str` | Injection CSS avec aperçu live avant enregistrement. |

---

## 📊 3. Analyse SRS & Santé de Collection

| Outil | Signature | Description |
| :--- | :--- | :--- |
| `get_collection_panorama_360` | `() → str` | Vision globale exhaustive : paquets, cartes, sangsues, santé globale. |
| `get_deck_stats` | `(deck_name: str) → str` | Statistiques détaillées d'un paquet (total, révisions, difficultés). |
| `inspect_deck_deep_scan` | `(deck_name: str) → str` | Analyse des distributions d'intervalles SRS et cartes sangsues prioritaires. |
| `get_cards_by_deck_or_tag` | `(deck_name: str = "", tag: str = "", limit: int = 20) → str` | Consultation filtrée par paquet ou tag avec pagination. |
| `find_cards_by_content` | `(query: str, deck_name: str = "", limit: int = 8) → str` | Recherche par mot-clé dans question/réponse pour retrouver le `note_id`. |
| `get_note_full_profile_360` | `(note_id: int) → str` | Profil complet 360° d'une note (cartes, historique Time Machine, stats SRS, tags). |

---

## 🗄️ 4. Base de Données (Lecture Seule)

| Outil | Signature | Description | Sécurité |
| :--- | :--- | :--- | :--- |
| `query_peewee` | `(sql_query: str) → str` | Requête SQL `SELECT` sur SQLite en lecture seule. | **Authorizer SQLite** : rejet strict des opérations d'écriture, des accès aux tables sensibles et des secrets API. |

---

## 🔍 5. Recherche Vectorielle & Documents RAG

| Outil | Signature | Description |
| :--- | :--- | :--- |
| `search_document` | `(query: str, document_id: int) → str` | Recherche sémantique via FAISS dans un document spécifique avec extraits contextuels. |

---

## ✍️ 6. Formatage & Structuration Markdown

| Outil | Signature | Description |
| :--- | :--- | :--- |
| `format_markdown_document` | `(document_id: int = 0, content: str = "", dehyphenate_ocr: bool = True, normalize_katex: bool = True, align_tables: bool = True, normalize_headings: bool = True, clean_whitespace: bool = True) → str` | Nettoyage et normalisation : césures OCR, KaTeX, tables GFM, titres ATX. |
| `get_document_outline` | `(document_id: int = 0, content: str = "") → str` | Arborescence hiérarchique des titres (Outline). |
| `structure_document_sections` | `(document_id: int = 0, content: str = "", max_tokens: int = 800) → str` | Découpage sémantique enrichi avec breadcrumbs et statistiques pour le RAG. |
| `structure_transcript_for_ai` | `(document_id: int = 0, content: str = "", profile: str = "didactic", target_language: str = "fr", preserve_timestamps: bool = True, normalize_latex: bool = True, add_summary: bool = True, add_key_takeaways: bool = True) → str` | Restructuration de transcriptions (YouTube, cours) en Markdown pédagogique structuré. |

---

## 📖 7. Documentation & Base de Connaissances Interne (Zensical)

| Outil | Signature | Description | Base technique |
| :--- | :--- | :--- | :--- |
| `search_app_documentation` | `(query: str, category: str = "", limit: int = 5) → str` | Recherche plein-texte BM25 avec extraits dans toute la doc Zensical. | SQLite FTS5 en mémoire. |
| `read_app_doc_page` | `(doc_path: str, section_anchor: str = "") → str` | Lecture complète ou ciblée d'une page de documentation. | — |
| `list_app_doc_topics` | `(category: str = "") → str` | Sommaire exhaustif classé par thématiques. | Déduit de `zensical.toml`. |
| `get_feature_quick_help` | `(feature_name: str) → str` | Fiche synthétique d'une fonctionnalité clé (Ollama, KaTeX, DAG, Wozniak, Nuitka, Smart Merge, MCP). | Extraction déterministe avec citation de source. |

---

## 🤖 8. Gestion des Agents Dédiés

| Outil | Signature | Description | Portée |
| :--- | :--- | :--- | :--- |
| `list_mcp_agents` | `(scope: str = "mcp") → str` | Liste tous les agents dédiés (Auditeur Wozniak, Architecte CSS, Analyste SRS...) avec leurs outils. | `mcp`, `pipeline`, `all` |
| `get_mcp_agent_details` | `(agent_name: str) → str` | Configuration détaillée : prompt Jinja2, modèle assigné, liste des outils autorisés. | — |
| `invoke_mcp_agent` | `(agent_name: str, message: str, conversation_history_json: str = "[]") → str` | Délègue une tâche à un agent sous son persona et ses permissions strictes. | — |
| `create_or_update_mcp_agent` | `(name: str, description: str, system_prompt: str, allowed_tools_json: str = "[]", persona_type: str = "mcp") → str` | Crée ou met à jour programmatiquement un agent. | **Écriture BDD** : opération créatrice/modify. |

---

## 📡 Ressources MCP

Ces ressources exposées via le protocole MCP permettent aux clients (Claude Desktop, Cursor) de lire directement la base de connaissances d'AnkiForge :

| URI | Description |
| :--- | :--- |
| `docs://topics` | Liste hiérarchique complète des chapitres et pages de la documentation officielle. |
| `docs://page/{doc_path}` | Contenu brut Markdown d'une page de documentation précise. |
| `agents://list` | Catalogue JSON de tous les agents disponibles. |
| `agents://{agent_name}` | Spécification détaillée et consigne système d'un agent particulier. |

---

## 📝 Prompts MCP Prédéfinis

| Prompt | Description | Paramètres |
| :--- | :--- | :--- |
| `explain_ankiforge_feature` | Explique pas à pas une fonctionnalité d'AnkiForge avec extraits de la doc officielle. | `feature_name` |
| `audit_architecture_compliance` | Vérifie qu'un code respecte les principes architecturaux décrits dans le dossier d'architecture. | `target_code_or_rule` |
| `run_with_agent` | Prépare une session de travail en adoptant la posture et les outils d'un agent dédié. | `agent_name`, `task` |

---

## 🔗 Notes Techniques

- **Serveur in-process** : le serveur MCP s'exécute dans le même processus que l'interface Qt — zéro surcoût réseau ni latence IPC.
- **Liste source officielle** : `src/ankiforge/services/ai/mcp_server.py` + `src/ankiforge/services/ai/tools_catalog.py` (24 specs `ToolSpec` + 5 outils agents non catalogués).
- **Complément** : la page [Consultant IA & Protocole MCP](../features/consultant_mcp.md) détaille la boucle ReAct et le fonctionnement du serveur en contexte.

> 🐙 **Code source** : [https://github.com/Skyl9/AnkiForge](https://github.com/Skyl9/AnkiForge)
