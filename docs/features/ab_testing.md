# Laboratoire de Tests A/B 🧪

Choisir le bon modèle d'IA, calibrer la température ou affiner la formulation d'un prompt complexe peut rapidement devenir coûteux et fastidieux sans outil d'évaluation rigoureux. Le **Laboratoire de Tests A/B** d'AnkiForge offre un banc d'essai comparatif scientifique directement intégré à l'application.

---

## ⚖️ 1. Les Trois Modes d'Expérimentation

Le laboratoire propose trois modes d'évaluation symétriques en double aveugle :

| Mode de Test | Variante A | Variante B | Objectif |
| :--- | :--- | :--- | :--- |
| **Modèle vs Modèle** | Modèle Local (ex: `Llama 3.2 3B`) | Modèle Cloud (ex: `Gemini 1.5 Flash`) | Comparer la précision et le rapport vitesse/coût entre local et cloud sur un même extrait de cours. |
| **Prompt vs Prompt** | Prompt standard "Zero-Shot" | Prompt optimisé "Few-Shot" avec règles d'atomicité | Mesurer l'impact de consignes pédagogiques strictes sur la concision des cartes. |
| **Pipeline vs Pipeline** | Pipeline linéaire simple | Pipeline DAG avec auto-critique et filtrage | Valider l'efficacité d'un flux multi-étapes avant traitement de gros volumes. |

---

## ⚡ 2. Exécution Concurrente et KPIs en Direct

Dès le lancement du test, AnkiForge exécute les deux branches simultanément en arrière-plan via le pool de threads Qt (`QThreadPool`) sans jamais figer l'interface.

Une bannière de métriques en direct (*Live KPIs*) compare instantanément les deux résultats :

```text
┌───────────────────────────────┬───────────────────────────────┐
│          VARIANTE A           │          VARIANTE B           │
├───────────────────────────────┼───────────────────────────────┤
│ Modèle : Ollama llama3.2      │ Modèle : Gemini 1.5 Flash     │
│ ⏱️ Durée : 2 410 ms           │ ⏱️ Durée : 890 ms             │
│ 🃏 Cartes produites : 6       │ 🃏 Cartes produites : 8       │
│ 🪙 Tokens consommés : 1 120   │ 🪙 Tokens consommés : 1 450   │
│ 💵 Coût estimé : 0.00 $       │ 💵 Coût estimé : 0.00018 $    │
└───────────────────────────────┴───────────────────────────────┘
```

---

## 👁️ 3. Comparaison Symétrique 3 Niveaux

Les résultats s'affichent côte à côte selon trois niveaux d'inspection sélectionnables :
1. **Rendu Visuel de la Carte** : Aperçu graphique réel avec styles CSS et rendu KaTeX tel qu'il apparaîtra dans Anki.
2. **Champs Bruts** : Inspection comparative champ par champ (Front, Back, Tags, Clozes) pour vérifier l'exactitude sémantique.
3. **JSON Structuré** : Affichage des données brutes renvoyées par l'API pour diagnostiquer la conformité du schéma.

---

## 📥 4. Importation en 1-Clic

Une fois l'évaluation terminée :
- Cliquez sur **Adopter la Variante A** ou **Adopter la Variante B**.
- Les cartes sélectionnées sont automatiquement injectées dans votre base locale avec leurs métadonnées, prêtes pour l'édition ou l'export.
- La configuration gagnante peut être sauvegardée comme pipeline par défaut en un clic.
