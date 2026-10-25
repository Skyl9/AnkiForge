# Spécification — Benchmark du flux de cadrage et d’implémentation

## Problématique (Problem Statement)

AnkiForge dispose de deux chemins de préparation avant implémentation, mais
leur effet relatif n’est pas établi :

- cadrage formel par `/to-spec`, découpage par `/to-tickets`, puis
  `/implement` ;
- cadrage approfondi par `/grill-with-docs`, puis `/implement` directement sur
  le ticket cadré.

Le benchmark doit mesurer cette décision sur les mêmes tickets, sans laisser
l’agent connaître à l’avance les critères qui détermineront sa réussite. Il
doit distinguer la qualité intrinsèque du logiciel livré de l’effort
opératoire nécessaire pour obtenir un résultat acceptable.

## Solution proposée

Construire un benchmark contrôlé à deux bras, sur les mêmes tickets :

- **Bras A — pipeline spécification** : `/to-spec` → `/to-tickets`, puis
  `/implement` sur chaque ticket produit.
- **Bras B — pipeline grill** : `/grill-with-docs`, puis `/implement` sur le
  ticket issu du cadrage.

Chaque ticket est dupliqué depuis le même commit initial et assigné aux deux
bras dans des workspaces indépendants. Les critères d’évaluation, les tests
cachés et les références attendues sont préparés avant l’exécution et
conservés dans un espace inaccessible aux agents exécutants. Les tickets
synthétiques standardisés constituent l’échantillon principal ; quelques
tickets réels servent ensuite de validation externe, sans être utilisés pour
calibrer les seuils.

Le résultat est évalué par des assertions exécutables, une revue humaine
aveugle et des mesures de coût. Un score global ne peut pas compenser un échec
bloquant : régression de données, violation d’une contrainte de sécurité,
échec du build ou corruption du dépôt.

## User Stories (Extensives)

1. En tant que responsable technique, je veux comparer objectivement deux
   stratégies de cadrage afin de choisir le flux par défaut d’AnkiForge.
2. En tant qu’évaluateur, je veux figer les critères avant les runs afin
   d’éviter l’ajustement opportuniste des seuils après observation des sorties.
3. En tant que mainteneur, je veux mesurer la complétude du cadrage et des
   tickets afin de séparer un défaut de spécification d’un défaut
   d’implémentation.
4. En tant que mainteneur, je veux compter le temps de cadrage, les reprises,
   les fichiers touchés et les tests afin de quantifier le coût réel, pas
   seulement le succès final.
5. En tant qu’utilisateur, je veux que les tickets réels confirment la
   conclusion obtenue sur les cas synthétiques sans devenir eux-mêmes un jeu
   d’entraînement.

## Décisions d’Implémentation

### Unité expérimentale et échantillonnage

- Une unité est un ticket vertical, issu d’un domaine (UI, service, données ou
  intégration), avec une couture et des critères observables.
- Préparer au minimum 6 tickets synthétiques : 2 simples, 2 moyens et 2
  multi-couches. Ajouter 3 à 5 tickets réels pour la réplication externe.
- Exécuter chaque ticket dans les deux bras, avec un ordre alterné et des
  workspaces séparés afin de réduire les effets de fatigue, de modèle ou de
  contexte.
- Interdire la réutilisation d’un workspace, d’un historique de conversation
  ou d’un cache de résultat entre les bras.

### Artefacts et instrumentation

Le dispositif doit produire un manifeste JSON par run contenant :

- identifiant opaque du lot, bras expérimental, commit initial et versions ;
- prompts et sorties du cadrage (`/to-spec` + `/to-tickets` ou
`/grill-with-docs`) et de `/implement` ;
- horodatages, nombre de tours, tokens/coût si disponibles ;
- fichiers modifiés, diff final, tests lancés et résultats ;
- demandes de clarification, reprises et corrections postérieures ;
- verdicts des tests publics, des tests cachés et de la revue aveugle.

Les références et critères cachés doivent être stockés séparément du contexte
fourni à l’agent. Le harnais doit refuser un run incomplet plutôt que produire
un succès par défaut.

### Critères définis avant exécution

Les critères sont regroupés en six dimensions, chacune notée de 0 à 4 :

| Dimension | Mesure principale |
|---|---|
| Spécification | exigences, invariants, hors périmètre et seam explicités |
| Tickets | verticalité, autonomie, dépendances et critères vérifiables |
| Fonctionnel | tests cachés et scénarios d’acceptation réussis |
| Robustesse | non-régression, typage, lint, migrations et erreurs explicites |
| Maintenabilité | diff minimal, conventions et absence de duplication évitable |
| Opérationnel | temps, tours, tokens/coût et nombre de reprises |

Le score qualité est la moyenne pondérée des cinq premières dimensions. Le
score d’efficacité est le score qualité divisé par le coût normalisé. Les
seuils sont fixés avant le premier run :

- **Réussite forte** : aucun bloquant, tests cachés ≥ 95 %, qualité ≥ 3,2/4 ;
- **Réussite acceptable** : aucun bloquant, tests cachés ≥ 85 %, qualité ≥
  2,7/4 ;
- **Échec** : tout autre cas, ou présence d’un bloquant.

Les pondérations, seuils et règles de blocage sont versionnés dans le
manifeste d’évaluation avant le lancement. L’agent ne reçoit que la demande
fonctionnelle et les contraintes normales du dépôt, pas cette grille.

### Analyse et décision

Comparer les bras sur :

- taux de réussite forte et acceptable par ticket apparié ;
- taux de tickets livrés sans reprise ;
- nombre médian de reprises et de régressions ;
- temps et coût séparés du cadrage, puis temps et coût d’implémentation ;
- qualité du cadrage avant toute implémentation ;
- dispersion des résultats entre lots.

Utiliser la médiane et l’intervalle interquartile pour le coût et le temps.
Pour les proportions, fournir l’intervalle de confiance exact ou bootstrap.
La conclusion « le pipeline spécification est préférable » n’est autorisée que
si le bras A améliore la réussite forte d’au moins 10 points de pourcentage
sans augmenter le coût total médian de plus de 20 %. La conclusion inverse
suit la même règle pour le bras B. Dans les autres cas, adopter une règle
hybride fondée sur la complexité, les dépendances et le coût de cadrage.

### Sources documentaires prises en compte

- OpenAI, *Working with evals* :
  https://developers.openai.com/api/docs/guides/evals — définir la tâche,
  exécuter sur un jeu d’entrées, analyser puis itérer ; utiliser des critères
  explicites et des références.
- OpenAI, *Graders* :
  https://developers.openai.com/api/docs/guides/graders — combiner des
  vérifications binaires, des scores partiels et des graders de code ; séparer
  les données de référence des sorties évaluées.
- Anthropic, *Building effective agents* :
  https://www.anthropic.com/research/building-effective-agents — préférer la
  solution la plus simple, mesurer le compromis performance/latence/coût, et
  utiliser un évaluateur séparé quand les critères sont clairs.
- SWE-bench, dépôt officiel :
  https://github.com/SWE-bench/SWE-bench — évaluer sur des tâches réelles,
  exécuter dans un harnais reproductible et conserver des journaux de run ;
  le cache doit être invalidé quand l’entrée évaluée change.

## Décisions de Test

- Tester le harnais lui-même avec des lots jouets : manifeste incomplet,
  sortie non conforme, test caché en échec, workspace sale et run interrompu.
- Tester la reproductibilité sur un même commit initial et vérifier que les
  deux bras ne partagent aucun artefact mutable.
- Exécuter les validations AnkiForge prévues par le ticket : tests ciblés,
  `ruff`, `mypy` et la porte `script/verify.py` selon le périmètre.
- Utiliser une revue humaine aveugle sur le diff et les rapports, avec deux
  évaluateurs lorsque la notation subjective intervient. Mesurer l’accord et
  arbitrer les écarts selon une règle pré-écrite.
- Ne jamais utiliser un LLM évaluateur comme unique oracle pour la correction
  fonctionnelle : les tests exécutables et les invariants du dépôt priment.

## Hors Périmètre (Out of Scope)

- Comparer des modèles, des fournisseurs ou des températures différentes.
- Modifier le fonctionnement de `/to-spec`, `/to-tickets`, `/grill-with-docs`
  ou `/implement` avant d’avoir établi une mesure de référence.
- Publier les critères cachés dans les prompts, les tickets ou le dépôt visible
  par l’agent exécutant.
- Déduire une conclusion générale à partir d’un seul ticket réel.
- Automatiser la fusion ou le commit des résultats ; le benchmark produit des
  rapports et des diffs inspectables, sans commit autonome.
