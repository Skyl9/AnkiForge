# Approfondissement de Modules (Deepening) 🔍

Comment approfondir un ensemble de modules superficiels (shallow) en toute sécurité selon leurs catégories de dépendances, en s'appuyant sur le vocabulaire de [SKILL.md](SKILL.md) : **module**, **interface**, **couture (seam)**, **adaptateur (adapter)**.

---

## 1. Catégories de Dépendances dans AnkiForge

Lors de l'évaluation d'un candidat à l'approfondissement, classifier ses dépendances. La catégorie détermine la façon dont le module approfondi sera testé à travers sa couture :

### 1. In-process (Calcul pur)
- **Nature** : Algorithmique pure, manipulation d'arbres de titres (`HeadingTree`), calcul de distances Levenshtein, état en mémoire, aucune I/O.
- **Stratégie** : Toujours approfondissable sans couture d'indirection. Fusionner les modules et tester directement via la nouvelle interface publique.

### 2. Localement substituable (Persistance Peewee)
- **Nature** : Dépendances disposant d'un équivalent local transparent en test.
- **Exemple AnkiForge** : SQLite sur disque (`~/.ankiforge/profiles/<profile>/ankiforge.db`) en production ➔ SQLite en mémoire partagée (`file:memdb_test_<worker>?mode=memory&cache=shared` via la fixture `mock_db`) en test.
- **Stratégie** : La couture est interne au framework BDD. Le module approfondi s'exécute contre la base mémoire sans introduire de port artificiel dans son interface publique.

### 3. Outillage Multimédia & Outils Lourds
- **Nature** : Outils locaux optionnels ou asynchrones (Marker OCR pour les PDF, Edge-TTS pour l'audio, sous-processus d'analyse).
- **Stratégie** : Définir un protocole / port clair au niveau du service. Injecter le convertisseur ou le synthétiseur audio. En production : adaptateur réel. En test : adaptateur mémoire léger produisant un faux fichier ou un Markdown prédéfini.

### 4. Véritables externes (Fournisseurs d'IA & LLM)
- **Nature** : Services tiers que nous ne contrôlons pas directement (OpenAI, Gemini, Anthropic, Ollama).
- **Stratégie** : Le module approfondi (ex: `ExtractionPipeline`, `PersonaService`) accepte son port `LLMProvider` par injection de dépendance. Les tests injectent un adaptateur mock déterministe retournant des réponses JSON prédéfinies, sans aucun appel réseau réel.

---

## 2. Discipline des Coutures (Seams)

- **Un seul adaptateur = couture hypothétique. Deux adaptateurs = couture réelle.** N'introduisez pas de protocole/port d'indirection à moins qu'au moins deux adaptateurs ne soient justifiés (typiquement : implémentation de production + fake/mock déterministe pour les tests).
- **Coutures internes vs coutures externes** : Un module profond peut posséder des coutures internes (privées à son implémentation) utilisées par ses sous-composants, en plus de sa couture externe publique. N'exposez jamais les coutures internes dans l'interface publique simplement pour les besoins d'un test.

---

## 3. Stratégie de Test : Remplacer, ne pas Empiler

- Les anciens tests unitaires fins sur des micro-fonctions privées deviennent du déchet dès lors que des tests robustes à l'interface du module approfondi existent : les supprimer.
- Écrire les nouveaux tests à l'interface publique du module approfondi. **L'interface est la surface de test**.
- Les tests vérifient les résultats observables, jamais l'état interne.
- Les tests doivent survivre aux refactorisations internes du module : si un test doit être modifié lors d'un refactoring interne sans changement de comportement observable, c'est qu'il teste au-delà de l'interface.
