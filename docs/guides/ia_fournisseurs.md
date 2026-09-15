# Fournisseurs LLM & Agnosticisme 🤖

AnkiForge a été conçu selon un impératif d'**agnosticisme absolu** vis-à-vis des fournisseurs d'intelligence artificielle : aucune dépendance propriétaire n'est imposée, et le choix entre puissance du cloud et confidentialité totale du local reste entre vos mains.

---

## 💻 1. Modèles Locaux (Confidentialité Maximale)

L'utilisation de modèles locaux est la méthode recommandée pour le traitement de documents médicaux, juridiques ou confidentiels.

### Ollama (Standard par défaut)
- **Fonctionnement** : AnkiForge communique directement avec le démon Ollama via son API REST locale (`http://localhost:11434`).
- **Poids logiciel** : Aucune dépendance lourde Python (`torch`, `transformers`) n'est embarquée dans AnkiForge, ce qui permet à l'application de rester légère et rapide.
- **Modèles conseillés** :
  ```bash
  # Modèle polyvalent très rapide (recommandé pour machines légères) :
  ollama run llama3.2:latest

  # Modèle francophone d'une excellente rigueur pédagogique :
  ollama run mistral:latest

  # Modèle orienté code et raisonnement structuré :
  ollama run qwen2.5-coder:latest
  ```

### LM Studio & Backends Compatibles OpenAI
Tout serveur local exposant une interface conforme à la spécification standard OpenAI (comme **LM Studio**, **LocalAI** ou **vLLM**) peut être utilisé en indiquant simplement son URL de base (ex: `http://localhost:1234/v1`).

---

## ☁️ 2. Fournisseurs Cloud (Haute Vitesse & Raisonnement Avancé)

Pour traiter de très volumineux corpus de texte ou générer des démonstrations mathématiques poussées, AnkiForge supporte nativement les leaders du marché via `FlexibleAIService` :

| Fournisseur | Modèles Supportés | Points Forts | Clé d'API Requise |
| :--- | :--- | :--- | :--- |
| **Google Gemini** | `gemini-1.5-flash`, `gemini-1.5-pro` | Fenêtre de contexte gigantesque (jusqu'à 1M+ tokens), rapidité remarquable, tarif très avantageux. | `GEMINI_API_KEY` |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` | Rigueur extrême dans le respect des schémas JSON stricts (*Structured Outputs*). | `OPENAI_API_KEY` |
| **Anthropic** | `claude-3-5-sonnet`, `claude-3-haiku` | Qualité littéraire et pédagogique inégalée, excellente nuance dans les reformulations. | `ANTHROPIC_API_KEY` |
| **Groq** | `llama-3.3-70b-versatile`, `mixtral-8x7b` | Vitesse d'inférence phénoménale sur puces LPU (plus de 500 tokens/seconde). | `GROQ_API_KEY` |

---

## 💰 3. Suivi Budgétaire & Métrologie (`PricingService`)

L'utilisation d'APIs payantes peut susciter des craintes de surcoût imprévu. AnkiForge intègre un dispositif de traçabilité financière temps réel :
- **Comptage Précis des Tokens** : Enregistrement de chaque requête (tokens d'entrée et tokens de sortie) via `TokenUsageModel`.
- **Calcul Financier Dynamique** : Le service `PricingService` applique les grilles tarifaires officielles actualisées pour chaque fournisseur.
- **Tableau de Bord & Cockpit** : Suivez à tout moment vos dépenses cumulées du jour, du mois ou par projet directement dans les paramètres de l'application.
