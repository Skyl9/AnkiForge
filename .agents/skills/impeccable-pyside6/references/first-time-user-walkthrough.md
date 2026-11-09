# Guide du Nouvel Utilisateur & UX Writing — AnkiForge

Ce guide formalise l'audit d'onboarding et l'évaluation avec un regard extérieur ("Fresh Eyes"), ainsi que le dictionnaire d'éradication du jargon technique dans l'interface PySide6 d'AnkiForge.

---

## 1. Protocole du "Cognitive Walkthrough" en 4 Questions (Lentille `/first-eyes`)

Lorsqu'un développeur conçoit une vue d'AnkiForge, il est biaisé par sa connaissance intime du code (modèles Peewee, serveur MCP, DAG, tokens). La passe `/first-eyes` force l'agent à adopter la posture d'un étudiant ou enseignant qui découvre l'application pour la première fois.

### A. Le Test des 3 Secondes à Froid
En ouvrant cet écran pour la toute première fois sans documentation, le nouvel utilisateur doit pouvoir répondre instantanément à trois questions fondamentales :
1. **Où suis-je ?** (Le titre de la vue et le fil d'Ariane sont-ils limpides ?)
2. **À quoi sert cet écran ?** (Une phrase d'accroche explicite résume-t-elle le bénéfice produit ?)
3. **Quelle est la toute première action à faire ?** (Le bouton d'action principale est-il mis en valeur sans ambiguïté ?)

Si le regard erre plus de 3 secondes sans point focal évident, la vue échoue au test.

---

### B. Le Crash-Test "Jour 1 / Base Vierge" (Cold Start)
Que voit l'utilisateur qui vient tout juste d'installer AnkiForge ?
- **Interdiction formelle des tables et listes vides muettes** : un tableau vide avec des en-têtes grisâtres donne l'impression d'une application cassée ou inachevée.
- **Obligation de l'état d'accueil engageant (`EmptyStateWidget`)** :
  - Une illustration vectorielle ou icône Phosphor thématique (ex. `ph.sparkle` ou `ph.cards`).
  - Un titre bienveillant et vulgarisé.
  - Une explication en une phrase de ce que l'utilisateur va accomplir ici.
  - Un ou deux boutons d'action directe (ex. *"✨ Découvrir les modèles prêts à l'emploi"* ou *"➕ Importer un premier cours"*).
  - Un mini-guide d'onboarding en 2 ou 3 étapes numérotées.

---

### C. L'Audit Anti-Effet "Cockpit d'Avion"
Les LLM ont tendance à exposer tous les paramètres possibles sur un seul écran (température LLM, top_p, chunk size en tokens, overlap, connecteurs MCP, seuils d'alignement).
- **Règle de Divulgation Progressive en UI** : N'afficher d'emblée que les 2 ou 3 réglages indispensables (ex: Sujet du cours, Modèle de carte cible, Nombre approximatif de cartes).
- **Valeurs par défaut intelligentes** : Tous les paramètres avancés doivent être préconfigurés avec des valeurs optimales recommandées.
- **Sections secondaires ou repliables** : Reléguer la tuyauterie technique dans un panneau *"Options avancées"* replié par défaut ou dans un tiroir dédié.

---

### D. L'Explicabilité des Contrôles Désactivés (`setEnabled(False)`)
Rien n'est plus frustrant qu'un bouton d'action primaire grisé sans aucune explication.
- **Règle d'explicabilité obligatoire** : Tout bouton désactivé doit informer l'utilisateur de la condition manquante.
- Deux mécanismes autorisés :
  1. **`setToolTip` dynamique** : Expliquer la condition bloquante (ex: *"Sélectionnez au moins un chapitre du document pour lancer la génération"*).
  2. **Micro-texte d'aide contextuel** : Afficher une mention discrète sous le bouton (`10px`, `COLOR_TEXT_MUTED`).

```python
# ✅ IMPECCABLE : Bouton désactivé auto-explicatif
if not has_selected_sections:
    self.btn_generate.setEnabled(False)
    self.btn_generate.setToolTip(self.tr("Cochez au moins une section du document ci-dessus pour forger des cartes."))
else:
    self.btn_generate.setEnabled(True)
    self.btn_generate.setToolTip(self.tr("Générer les cartes d'apprentissage pour les sections sélectionnées."))
```

---

## 2. Dictionnaire UX Writing & Anti-Jargon d'AnkiForge (Lentille `/clarify`)

Le vocabulaire interne des développeurs ne doit jamais contaminer la surface utilisateur.

### Table de Traduction Concrète UI

| ❌ Jargon Développeur / Interne | ✅ Microcopy Humaine (Orientée Action/Bénéfice) | Contexte UI Réel dans AnkiForge |
| :--- | :--- | :--- |
| `Serveur MCP in-process` / `Outils MCP` | **Assistant IA connecté** / **Actions de l'assistant** | En-têtes d'inspecteur, dialogue d'outils |
| `init_workspace` / `Init Workspace` | **Préparer le dossier du projet** | Écran d'accueil et configuration initiale |
| `NoteType` / `Modèle Peewee` | **Type de carte** *(ex. Recto/Verso, Texte à trous)* | Sélecteur de modèle, dialogue de cartes |
| `Chunking sémantique` | **Découpage intelligent du document** | Panneau d'importation de documents |
| `Vector Store` / `Index FAISS` | **Index de recherche sémantique** | Paramètres d'indexation locale |
| `Pipeline DAG` / `Orchestrator` | **Chaîne de création automatique** | Éditeur et lanceur de flux IA |
| `Persona` / `System Prompt` | **Profil d'assistant** *(ex. Médecine, Droit, Concours)* | Atelier de personas et agents |
| `Token budget dépassé` | **Texte trop volumineux pour une seule passe** | Alertes et compteurs de génération |
| `Coverage Gap` / `Sections orphelines` | **Passages du cours sans carte flash** | Matrice de couverture documentaire |
| `db.atomic()` / `PeeweeIntegrityError` | **Cette carte ou ce paquet existe déjà** | Toasts d'erreur lors de l'enregistrement |
| `on_delete CASCADE` | **Supprime également les cartes associées** | Dialogue de confirmation de suppression |
| `Levenshtein C-Extension` | **Moteur de détection des doublons accéléré** | Paramètres système & diagnostics |

---

## 3. Anatomie d'un Message d'Erreur Non Anxiogène

Une alerte ou un toast d'erreur ne doit jamais jeter une stacktrace Python à la figure de l'utilisateur (`KeyError`, `OperationalError: table locked`).

Tout message d'erreur doit comporter impérativement 3 éléments structurés :
1. **Le constat simple** : Ce qui vient de se passer, sans jargon technique.
2. **La cause probable** : Pourquoi l'opération n'a pas pu aboutir.
3. **L'action de déblocage** : L'étape exacte pour résoudre le problème.

```text
❌ MAUVAIS (Slop brut) :
"Erreur 500 : PipelineOrchestrator failed at step 3: RateLimitError"

✅ IMPECCABLE (Clair et orienté action) :
"Impossible de générer les cartes pour ce chapitre.
Le service d'intelligence artificielle est temporairement saturé.
Attendez quelques secondes puis cliquez sur Réessayer, ou passez sur un modèle local Ollama."
```

---

## 4. Rassurance avant Action Critique

Pour supprimer la peur d'endommager ses données ou son cours :
- **Préciser l'innocuité sur les originaux** : Mentionner explicitement *"Votre fichier PDF d'origine ne sera pas modifié"*.
- **Transparence sur les coûts & quotas** : Pour toute génération IA distante, préciser *"Estimation : ~0.02 $ (12 cartes)"* ou *"Modèle local : 100% gratuit et hors-ligne"*.
- **Confirmation explicite des suppressions** : Énoncer clairement le volume impacté (*"Supprimer le deck 'Pharmacologie' et ses 142 cartes ?"* au lieu d'un vague *"Êtes-vous sûr ?"*).
