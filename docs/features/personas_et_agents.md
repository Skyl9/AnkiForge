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

## 🧪 4. Simulateur Unitaire (`AgentTestDialog`)

Avant de déployer un nouveau persona dans un pipeline de production traitant des centaines de pages :
1. Ouvrez l'**Éditeur de Personas**.
2. Cliquez sur **Tester l'Agent** pour ouvrir la boîte de dialogue de simulation (`AgentTestDialog`).
3. Injectez un échantillon de texte source ou une consigne de test.
4. Observez la réponse générée en temps réel, le temps de réponse et le respect du schéma JSON.
5. Ajustez vos consignes système et réitérez jusqu'à obtenir un comportement parfait.
