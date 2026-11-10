# ADR 0057 : Outillage MCP d'ingestion documentaire d'autorité, détection des lacunes et décloisonnement de collection

**Statut :** accepté

## 1. Contexte

Le profil AnkiForge héberge à la fois des documents de référence indexés dans le moteur RAG local (sections, chapitres, fragments `DocumentChunkModel` et adresses de région `ADR 0010`) et des paquets de cartes (`DeckModel`, `NoteModel`). La traçabilité entre ces deux univers est assurée de manière déterministe par `CoverageAlignmentService` (`ADR 0009`) via les associations `NoteChunkLinkModel`.

Cependant, les agents externes (Claude Code, agy, Cursor, ou agents MCP in-process) se heurtaient à trois manques majeurs :
1. **Absence d'outillage d'évaluation des lacunes à l'échelle du domaine :** L'analyse paquet par paquet crée une illusion de lacune (faux positifs) si l'utilisateur possède déjà des cartes pertinentes réparties dans des paquets transversaux. De plus, une lacune de connaissances ne se résume pas à un concept manquant : elle inclut les cartes non atomiques (violant la formulation minimale de Wozniak) et l'absence de cartes comparatives créant du liant entre notions voisines.
2. **Absence de contrôle d'ancrage factuel (grounding) unitaire :** Aucun outil MCP n'évalue si les assertions formulées dans les champs d'une carte sont fidèlement étayées par les chunks documentaires rattachés, rendant difficile la détection d'hallucinations ou d'approximations.
3. **Impossibilité pour l'agent d'apporter une source externe vérifiée à la volée :** L'agent externe ne pouvait pas ingérer une source web fiable dans la bibliothèque locale de façon sécurisée (plafond de taille de message MCP de 32 000 caractères selon `ADR 0048`, risque SSRF sur les réseaux locaux).

Par ailleurs, l'adjonction d'un outil MCP monolithique de génération de cartes aurait constitué un doublon injustifié avec l'API existante de mutation par lots (`create_notes_batch`, `propose_cards_batch_refactor`, `Staged Bundles`).

## 2. Décision

### 2.1 Outillage MCP Analytique & Ingestion Hybride

Le registre MCP (`MCPToolRegistry`) expose trois nouveaux outils spécialisés :

1. **`ingest_authority_source(transport_mode: str, locator: str, title: str = "", inline_content: str = "", authority_metadata_json: str = "{}") -> str`** :
   - Assure l'ingestion documentaire polymorphe selon 3 modes de transport adaptés aux plafonds volumétriques (`ADR 0048`) :
     - `url` : téléchargement direct d'une page web publique avec bouclier anti-SSRF strict (rejet immédiat de `127.0.0.1`, `localhost`, `10.*`, `192.168.*`, `172.16-31.*`).
     - `file_staging` : importation d'un document lourd (PDF, grand Markdown) déposé au préalable dans le répertoire sécurisé du profil (`~/.ankiforge/staging/`), avec garde-fou contre le path traversal.
     - `inline_markdown` : enregistrement direct d'extraits textuels courts ($< 30\,000$ caractères) passés dans `inline_content`.
   - **Idempotence garantie** : détection des sources déjà présentes par URL ou empreinte SHA-256 pour éviter toute duplication.
   - **Certification d'autorité** : enrichissement du document par des métadonnées de fiabilité (type de source, score d'autorité de 0 à 100).
   - **Découpage RAG immédiat** : délégation au point d'entrée unique `reindex_service.reindex_document(doc.id)`.

2. **`diagnose_domain_knowledge_gaps(subject: str, target_deck: str = "", reference_document_id: int | None = None, blueprint_json: str = "", include_suspended: bool = False) -> str`** :
   - Exécute un protocole neuro-symbolique en 3 passes inversées pour armer le tamis lexical :
     - **Passe 1 (Cadrage du Domaine & Blueprint)** : ancrage documentaire déterministe (`reference_document_id` respectant ADR 0010 avec remontée récursive h3/h4 vers h2 et repli automatique en tranches équilibrées pour documents sans titres) ou cartographie fournie par l'agent externe (`blueprint_json` avec bornage anti-DoS), sans jamais invoquer l'IA interne d'AnkiForge sous pilotage externe.
     - **Passe 2 (Décloisonnement, Libération SQLite & Deck Virtuel)** : extraction par une unique requête SQL Peewee avec pivots `.switch(CardModel)` explicites et libération du curseur (< 50 ms), intégration de l'overlay virtuel des Staged Bundles actifs (`is_staged=True`), regroupement dédoublonné par note avec résolution multi-cartes et rattachement multi-paquets, traçabilité des repêchages via `RescuedCardEntry`, nettoyage HTML profond (`<style>`, `<script>`, entités), garde-fous sur acronymes courts ($\le 2$ lettres), prise en compte de la hiérarchie des sous-paquets (`::`) insensible à la casse, et tamis lexical haute performance en passe unique $\mathcal{O}(N)$ via mégapatron disjonctif précompilé (< 150 ms sur 50 000 cartes).
     - **Passe 3 (Diagnostic Tripartite & Métrologie chiffrée)** :
       - *Type 1 (Concepts absents)* : notions clés non couvertes par aucune carte active du profil, avec preuve textuelle (`source_excerpt`), tags de section slugifiés et résolution automatique du paquet dominant si `target_deck` n'est pas renseigné.
       - *Type 2 (Déficit d'atomicité & surcharge cognitive)* : évaluation qualitative du bloc principal (séparation visuelle essentielle vs annexe, exemption du contexte des clozes, détection des omissions Cloze composites selon Wozniak 8, neutralisation étendue des blocs techniques et formules mathématiques scientifiques Anki / LaTeX / MathJax `[$]`, `\[`, `$$`, tolérance des énumérations concises de 3-4 mots simples, pénalisation de l'empilement dense $\ge 5$ puces ou $> 45$ mots).
       - *Type 3 (Manque de liant & nuances fines)* : détection des paires de concepts sus isolément sans pont relationnel, explorant 4 registres sémantiques bilingues FR/EN avec négation contrastive (distinction, conditionnalité, causalité, synergie).
       - *Métrologie adaptative & Télémétrie* : calcul de `DomainMetrics` avec convention de neutralité et repondération (65/35) lorsque le domaine ne requiert aucune relation (`total_relations == 0`), et mesure horodatée en millisecondes (`telemetry`).
   - **Garde-fou volumétrique ADR 0048, Double Export Atomique & Isolation par Profil** : persistance intégrale automatique sous `profiles/<nom>/reports/domain_gaps_<slug>_latest.json` (machine avec slug assaini anti-traversée) et `domain_gaps_<slug>_latest.md` (synthèse exécutive humaine avec jauges textuelles Unicode `[████░░]`, callouts Obsidian, badges, tableaux et échappement des `|`) avec écriture atomique (`os.replace`), rotation (max 10 archives) et retour d'un résumé priorisé à l'agent MCP avec les clés `full_report_path` et `full_markdown_report_path`.

3. **`verify_card_grounding(note_id: int) -> str`** :
   - Extrait les champs textuels de la note et charge les fragments sources associés via `NoteChunkLinkModel`.
   - Si aucun lien n'existe, tente une résolution via `CoverageAlignmentService.resolve_attachment`.
   - Fournit à l'agent un bilan d'ancrage factuel : verdict d'alignement (`grounded`, `partially_grounded`, `unlinked`), citations textuelles exactes des chunks sources correspondants, et points d'attention ou dérives éventuelles.

### 2.2 Exploitation des Mutations Existantes & Staged Bundles

Aucun outil MCP redondant de création de cartes n'est introduit. Pour enrichir un deck ou remédier aux lacunes identifiées :
- L'agent assemble un Staged Bundle via `begin_staged_bundle`.
- Il soumet les nouvelles cartes via `create_notes_batch` ou les corrections de cartes existantes via `propose_cards_batch_refactor`, en renseignant scrupuleusement les métadonnées et tags de traçabilité (`source:<slug>`, `section:<slug>`, etc.).
- Il clôture le lot via `commit_staged_bundle`.

### 2.3 Scission en Deux Compétences Agentiques (`.agents/skills/`)

Le catalogue accueille deux compétences complémentaires respectant le standard `agentskills.io` :

1. **`audit-couverture-deck`** (Audits Spécialisés) :
   - Rôle : Diagnostic passif en lecture seule.
   - Analyse la couverture d'un deck ou d'un domaine, quantifie les angles morts conceptuels et audite l'ancrage factuel des cartes existantes.
   - Restitue un rapport d'audit exhaustif priorisé sans effectuer de mutation.

2. **`enrichissement-deck-ia`** (Socle Technique / RAG) :
   - Rôle : Enrichissement et curation active.
   - S'appuie sur le rapport d'audit ou les lacunes identifiées, formule des cartes conformes aux 20 règles de formulation de Piotr Wozniak, exige une preuve textuelle exacte (citation) pour chaque carte, et soumet un Staged Bundle de propositions de cartes vérifiées.

### 2.4 Garde-fous Anti-Hallucination & Sécurité

- **Obligation de preuve textuelle dans le skill :** Le contrat du skill `enrichissement-deck-ia` interdit formellement de générer une carte sans citation textuelle extraite d'un fragment existant dans le profil actif.
- **Résolubilité des tags de traçabilité :** Tout enrichissement doit comporter les tags de provenance permettant à `CoverageAlignmentService` d'établir un lien résolu (`exact`, `section` ou `page`).
- **Bouclier SSRF local :** Tout import par URL bloque immédiatement les adresses de bouclage, plages privées et métadonnées cloud.

## 3. Raisons

1. **Hygiène du serveur MCP (Anti-Bloat) :** Évite de créer des outils concurrents à `create_notes_batch` et préserve la responsabilité unique de chaque outil : l'analyse pour les outils d'audit, la mutation pour le bus de staging Two-Phase Commit.
2. **Architecture Local-First & Frugalité :** L'ingestion polymorphe respecte les limites mémoires locales et évite les dépendances à des API distantes payantes.
3. **Élimination de l'effet silo (Cross-Deck) :** La recherche décloisonnée reflète fidèlement la mémoire réelle de l'utilisateur au lieu d'une partition arbitraire en paquets.
4. **Séparation des responsabilités (SoC) :** La séparation entre un audit passif (`audit-couverture-deck`) et une remédiation active (`enrichissement-deck-ia`) permet de dissocier l'évaluation de la décision de mutation.

## 4. Conséquences

- Trois nouveaux outils déclarés dans `mcp_server.py` et enregistrés dans `DEFAULT_CONSULTANT_TOOLS` (passage de 81 à 84 outils MCP).
- Deux nouvelles compétences intégrées au catalogue `.agents/skills/` et documentées dans `AGENTS.md` et `GEMINI.md`.
- Enrichissement du glossaire métier dans `CONTEXT.md`.
- Traçabilité documentaire complète et immunisation contre les hallucinations lors des campagnes d'enrichissement de deck.
