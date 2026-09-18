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
| **Google Gemini** | `gemini-3.5-flash-lite`, `gemini-2.0-flash`, `gemini-1.5-pro` | Fenêtre de contexte gigantesque, rapidité remarquable, modèle `flash-lite` économique. | `GEMINI_API_KEY` |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini`, `o3-mini`, `o1` | Rigueur extrême dans le respect des schémas JSON stricts (*Structured Outputs*). | `OPENAI_API_KEY` |
| **Anthropic** | `claude-3-7-sonnet`, `claude-3-5-sonnet`, `claude-3-5-haiku` | Raisonnement hybride étendu, qualité littéraire et pédagogique inégalée. | `ANTHROPIC_API_KEY` |
| **Groq** | `llama-3.3-70b-versatile`, `deepseek-r1-distill-llama-70b` | Vitesse d'inférence phénoménale sur puces LPU (plus de 500 tokens/seconde). | `GROQ_API_KEY` |

!!! tip "Vérification des modèles"
    La liste exhaustive et actualisée des `ModelSpec` (contexte, vitesse, coût, auto-détection des capacités vision) est disponible dans `src/ankiforge/services/ai/model_catalog.py`. Pour les modèles **Ollama locaux**, AnkiForge interroge `POST /api/show` et détecte automatiquement les capacités réelles du modèle présent sur votre machine.

---

## 🔁 3. Résilience & Politique de Retry (`services/ai/retry.py`)

Quel que soit le fournisseur, les appels réseau échouent inévitablement un jour (timeout, quotas 429, erreurs serveur 5xx). AnkiForge applique une **politique de retry unifiée** sur l'ensemble de ses appels LLM :

- **Codes transitoires retryables** : `408, 409, 425, 429, 500, 502, 503, 504` — les autres erreurs (JSON invalide, clé refusée `401/403`) sont propagées immédiatement.
- **Backoff exponentiel borné** : délai initial `base_delay` doublé à chaque tentative, plafonné à `max_delay`, puis **jitter** pour éviter l'effet thundering-herd.
- **Versions synchrone et asynchrone** : `with_retry` / `with_retry_async` — la variante `async` repose sur `asyncio.sleep` pour ne **jamais geler l'event loop** pendant l'attente.
- **Journalisation** : chaque tentative ratée est tracée en `WARNING` avec le libellé de l'opération, la tentative courante et le délai avant la prochaine.
- **Télémétrie unifiée** : les contextes d'exécution (fournisseur, modèle, profondeur de retry) sont propagés aux compteurs de coûts et tokens (`TokenUsageModel`), donnant une vision consolidée par pipeline.

!!! tip "Optimisation du budget"
    Pendant un épisode de `429` (rate-limit), le backoff exponentiel protège votre budget aussi bien que votre latence : moins de tentatives agressives = moins d'appels facturés.

---

## 💰 4. Suivi Budgétaire & Métrologie (`PricingService`)

L'utilisation d'APIs payantes peut susciter des craintes de surcoût imprévu. AnkiForge intègre un dispositif de traçabilité financière temps réel :
- **Comptage Précis des Tokens** : Enregistrement de chaque requête (tokens d'entrée et tokens de sortie) via `TokenUsageModel`.
- **Calcul Financier Dynamique** : Le service `PricingService` applique les grilles tarifaires officielles actualisées pour chaque fournisseur.
- **Tableau de Bord & Cockpit** : Suivez à tout moment vos dépenses cumulées du jour, du mois ou par projet directement dans les paramètres de l'application.

---

## 🌍 5. Références Utiles

- [Fournisseurs & gestion des clés dans le guide d'installation](../installation.md)
- [Code source du catalogue de modèles](https://github.com/Skyl9/AnkiForge/blob/main/src/ankiforge/services/ai/model_catalog.py)
- [Depuis GitHub](https://github.com/Skyl9/AnkiForge)
