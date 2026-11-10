---
name: doubt-driven-development
description: >-
  Soumet chaque proposition technique, cadrage ou implémentation à une critique active et systématique ("penser contre") avant validation. Identifie les hypothèses implicites, défaillances silencieuses et active le doute automatique si le nombre d'inconnus dépasse le seuil critique.
  Use when the user asks to "penser contre moi", "critiquer ma proposition", "revue contradictoire", "adversarial review", "doubt-driven-development", "refait une passe critique", or when implementing with unverified assumptions.
  When NOT to use: Do not use for mechanical refactorings, trivial one-liners, or when speed is explicitly requested.
---

# Doubt-Driven Development — Critique Active ("Penser Contre")

Une réponse affirmée avec assurance n'est pas nécessairement exacte. Dans les sessions longues, l'accumulation de contexte transforme insensiblement de simples hypothèses en prétendus « faits ». Le Doubt-Driven Development matérialise une contre-revue dans un contexte vierge — biaisée pour **réfuter** plutôt que valider — avant qu'une décision structurante ne soit figée.

Ce skill a pour fonction explicite de **penser contre l'auteur** : stress-tester l'artefact, chercher ce qui claque, et proposer des améliorations concrètes.

## 🎯 1. Seuil d'Activation Automatique (Unknowns Ratio)

Avant d'écrire du code ou de figer une architecture, classer chaque assertion technique :
- **`[Prouvé]`** : Fait certifié par lecture physique du code source (`read_file`, schéma SQLite, doc officielle).
- **`[Supposition]`** : Hypothèse non vérifiée (ex. "ce champ existe", "cette boucle est rapide", "ce mock suffit").
- **`[Inconnu]`** : Zone d'ombre explicite (ex. concurrence de threads Qt, latence réseau, contrat flou).

> [!IMPORTANT]
> **Règle du Seuil Incompressible** : Si $\text{Suppositions} + \text{Inconnus} \ge 2$ (ou si le ratio d'inconnus $\ge 30\%$), **le Doubt-Driven Development se déclenche AUTOMATIQUEMENT**. Interdiction formelle de coder avant d'avoir instruit les doutes et transformé les suppositions en faits certifiés.

## 🔄 2. Matrice d'Intervention aux 5 Étapes du Ticket AnkiForge

| Étape Ticket | Question Contradictoire Clé | Déclencheur DDD |
| :--- | :--- | :--- |
| **1. Cadrage (`/triage`, `/grill-with-docs`)** | Résout-on le bon problème ? Existe-t-il une solution 10x plus simple sans ajouter de modèle/outil ? | Besoin flou, frontière floue. |
| **2. Spécification (`/to-spec`)** | La spec viole-t-elle des invariants des 5 Piliers ? Quels sont les cas d'erreur ignorés ? | Changement d'API ou de schéma. |
| **3. Découpage (`/to-tickets`)** | Les tickets sont-ils couplés ? Les signatures prescrites correspondent-elles au code réel ? | $\ge 3$ fichiers ou jargon dense. |
| **4. Implémentation (`/implement`, `/tdd`)** | L'implémentation repose-t-elle sur des suppositions ? Quel invariant relationnel/perf est menacé ? | **Automatique si $\ge 2$ suppositions.** |
| **5. Clôture & Revue (`/code-review`)** | Quels effets de bord silencieux ou fuites de ressources ont échappé aux tests rapides ? | Systématique avant merge/commit. |

## 🏛️ 3. Les 5 Piliers d'Adversité Systémique (Passes Multi-Cycles)

À chaque cycle critique (commandé via *"Refait une passe critique"* ou auto-déclenché), balayer méthodiquement :

| Pilier d'Adversité | Question Contradictoire | Exemples de Pièges Détectés |
| :--- | :--- | :--- |
| **1. Réalité Relationnelle BDD** | L'artefact présume-t-il de relations directes inexistantes dans Peewee ? | Joindre `NoteModel` à `DeckModel` sans le pivot `CardModel` (`OperationalError`). |
| **2. Échelle & Complexité** | L'opération dégénère-t-elle en $\mathcal{O}(N \times K)$ sur 50k cartes ? | Scanner 50k cartes avec 150 regex (7,5M tests) au lieu d'un automate compilé en $\mathcal{O}(N)$. |
| **3. Sémantique & Bilinguisme** | Les marqueurs linguistiques couvrent-ils les variations de registre et négations ? | Oublier que la négation (`n'est pas`) prouve une distinction, ou confondre un acronyme court. |
| **4. Sécurité Filesystem & Formats** | Les fichiers ou exceptions masquent-ils des failles ? | Injection `try: except: continue` (Bandit B112/CWE-703), traversée de répertoires (`../../`). |
| **5. Overlays Transactionnels** | L'analyse prend-elle en compte l'état en mémoire et le Two-Phase Commit ? | Ignorer l'overlay virtuel Staged Bundles (`is_staged=True`) empêchant de mesurer le gain. |

## 🧭 4. Processus Opérationnel en 5 Étapes

1. **CLAIM** : Formuler l'affirmation technique en 2-3 lignes et isoler son enjeu.
2. **EXTRACT** : Transmettre uniquement l'artefact et le contrat technique sans les conclusions de l'auteur.
3. **DOUBT** : Mandat contradictoire biaisé pour réfuter. Chercher les cas limites, violations de contrat et fausses certitudes.
4. **RECONCILE** : Classer les retours (Contrat ambigu ➔ reformuler ; Défaut ➔ corriger ; Compromis ➔ documenter ; Faux positif ➔ rejeter).
5. **CONVERGENCE** : Arrêt dès que les remarques deviennent mineures, après accord explicite ou au terme des passes thématiques.

## 📋 Format de Restitution

| # | Point critiqué | Risque / Inconvénient | Correction suggérée | Statut (accepte / refuse / compromis) |

Verdict final motivé : **Accepter**, **Accepter avec réserves**, ou **Refuser**.

## ⛔ Ne PAS utiliser ce skill si...

- Opérations mécaniques (renommage, formatage, déplacement de fichiers).
- Modifications triviales d'une ligne dont la correction est évidente.
- Vitesse explicitement demandée par l'utilisateur.
- Proposition déjà validée après une première passe sans nouvel élément.
