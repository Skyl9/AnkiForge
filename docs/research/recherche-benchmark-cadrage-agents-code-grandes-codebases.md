# Recherche — Benchmark du cadrage préalable des agents de code

## Question étudiée

Existe-t-il une évaluation menée par une entreprise ou un laboratoire industriel
sur une codebase importante comparant directement :

1. un flux de planification et découpage (`/to-spec → /to-tickets →
   /implement`) ;
2. un cadrage approfondi suivi d’une implémentation directe
   (`/grill-with-docs → /implement`) ?

## Conclusion courte

La recherche n’a pas identifié d’étude publique qui isole exactement cette
variable avec ces deux traitements. Les travaux proches évaluent plutôt :

- l’agent complet contre une approche sans agent ou plus simple ;
- une interface d’agent contre une autre ;
- l’autonomie sur des issues réelles ;
- la longueur maximale de tâches qu’un agent peut terminer ;
- l’impact de Copilot sur une tâche de programmation humaine.

Ils justifient le protocole du benchmark AnkiForge, mais ne permettent pas de
conclure que `/to-spec → /to-tickets` est supérieur ou inférieur à
`/grill-with-docs`.

## Sources et degré de correspondance

| Source | Organisation | Échelle et méthode | Résultat utile | Correspondance |
|---|---|---|---|---|
| [SWE-bench Verified](https://openai.com/index/introducing-swe-bench-verified/) | OpenAI + 93 développeurs Python | 1 699 issues de 12 dépôts Python ; sous-ensemble final de 500 tâches ; tests cachés `FAIL_TO_PASS` et `PASS_TO_PASS` | 68,3 % des exemples examinés ont été filtrés pour sous-spécification, tests injustes ou autres défauts ; GPT-4o résolvait 33,2 % du sous-ensemble annoncé | Forte pour le contrôle des tâches et l’évaluation cachée, n’isole pas le workflow de cadrage |
| [Agentless](https://arxiv.org/abs/2407.01489) | Équipe de recherche universitaire | SWE-bench Lite ; pipeline fixe localisation → réparation → validation, sans agent autonome | 32,0 % et 96 correctifs annoncés, avec un coût de 0,70 $ ; une approche simple peut dépasser des agents plus complexes | Très forte pour comparer une décomposition fixe à une autonomie, mais pas une codebase interne d’entreprise |
| [SWE-agent](https://arxiv.org/abs/2405.15793) | Princeton / éditeurs SWE-bench | Issues réelles GitHub et navigation de dépôts complets via une interface agent-ordinateur dédiée | 12,5 % de pass@1 sur SWE-bench dans la version publiée ; l’interface de travail modifie fortement le comportement | Forte pour l’importance de la couture outil/repo, pas pour le choix du cadrage |
| [SWE-bench Multimodal](https://arxiv.org/abs/2410.03859) | Équipe SWE-bench | 617 tâches sur 17 bibliothèques JavaScript, avec éléments visuels | Les meilleurs systèmes textuels chutent sur des tâches visuelles ; SWE-agent atteint 12 % contre 6 % pour le suivant | Forte pour la validité externe et la diversité, pas pour le cadrage |
| [Measuring AI Ability to Complete Long Software Tasks](https://arxiv.org/abs/2503.14499) | METR | Tâches RE-Bench, HCAST et 66 nouvelles tâches ; temps humain et probabilité de réussite | Horizon de 50 % d’environ 50 minutes pour Claude 3.7 Sonnet ; la fiabilité et la récupération après erreur sont déterminantes | Forte pour la mesure du coût et de la longueur, pas pour la structure du workflow |
| [Impact of AI on Developer Productivity](https://arxiv.org/abs/2302.06590) | GitHub / Microsoft Research | Expérience contrôlée auprès de développeurs sur une tâche JavaScript standardisée | Le groupe Copilot termine 55,8 % plus vite que le contrôle | Entreprise et causalité fortes, mais tâche courte et développeur humain ; aucun cadrage agentique comparé |
| [AutoDev](https://arxiv.org/abs/2403.08299) | Microsoft Research | Framework autonome avec planification, édition, build, tests et opérations Git | 91,5 % de pass@1 en génération de code et 87,8 % en génération de tests sur HumanEval | Montre l’intérêt d’un workflow outillé, mais HumanEval n’est pas une grande codebase et aucune ablation du cadrage |

## Ce que ces résultats établissent

### 1. La qualité du ticket est un facteur expérimental, pas une nuisance

SWE-bench Verified montre que le texte de l’issue et les tests peuvent
introduire un biais majeur : 38,3 % des exemples ont été signalés pour
description sous-spécifiée et 61,1 % pour tests susceptibles de rejeter une
solution valide. Le benchmark AnkiForge doit donc valider chaque ticket avant
de comparer les workflows, plutôt que d’attribuer automatiquement un échec à
l’agent.

### 2. Les tests cachés et la non-régression sont indispensables

Le couple `FAIL_TO_PASS` / `PASS_TO_PASS` de SWE-bench est directement
transposable : les critères d’acceptation visibles servent au cadrage, tandis
que les invariants et scénarios cachés mesurent le résultat réel. Les tests
doivent être préparés avant l’exécution et ne pas être transmis à l’agent.

### 3. La simplicité peut être compétitive

Agentless est le précédent le plus proche conceptuellement : il remplace une
boucle agentique ouverte par trois phases déterministes. Cela ne prouve pas
qu’un `/to-spec → /to-tickets` est meilleur, mais justifie de comparer
explicitement un pipeline prescriptif à un cadrage plus libre.

### 4. La longueur de tâche augmente le risque de défaillance

METR observe que la réussite baisse fortement quand la durée humaine augmente.
Un benchmark limité à deux tickets simples, comme le pilote réalisé, ne peut
pas départager sérieusement les workflows : il faut inclure des tâches
multi-fichiers, des dépendances, des migrations et des tests de non-régression.

## Ce qui manque dans les publications

Aucune source consultée ne publie simultanément :

- le même ticket exécuté sous deux stratégies de cadrage ;
- une séparation stricte du coût de cadrage et du coût d’implémentation ;
- un ticket découpé par un workflow de spécification puis comparé à un ticket
  cadré par une interview architecturale ;
- des mesures de reprises, de dérive de périmètre et de qualité du plan ;
- une grande codebase propriétaire avec les artefacts de trajectoire complets.

Les annonces de productivité de Copilot ne répondent pas à cette question :
elles comparent principalement l’accès à l’assistant contre un contrôle humain,
et non deux méthodes d’orchestration d’agent.

## Protocole recommandé pour une réplication plus crédible

1. Construire 12 à 20 tickets appariés sur 4 à 6 dépôts réels de grande taille,
   en séparant UI, service, données, tests et refactorisation.
2. Faire passer chaque ticket dans les deux bras, sur des workspaces et
   historiques indépendants, avec ordre randomisé.
3. Préparer avant les runs les tests cachés, les invariants, la référence
   humaine et une grille d’évaluation non fournie à l’agent.
4. Mesurer séparément :
   - réussite fonctionnelle et non-régression ;
   - qualité du cadrage ;
   - temps, tokens, tours et coût ;
   - reprises, clarifications et fichiers hors périmètre ;
   - défauts introduits puis corrigés.
5. Utiliser comme métrique primaire la réussite forte par ticket apparié ; le
   coût total est secondaire et ne doit jamais compenser une régression.
6. Pré-enregistrer les seuils et publier les résultats par difficulté, car un
   avantage sur les tickets simples peut disparaître sur les tâches longues.

## Réponse à la question initiale

Oui, il existe des résultats industriels et quasi-industriels sur des
codebases ou issues réelles qui justifient les principes du benchmark :
validation humaine des tâches, tests cachés, environnement reproductible,
mesure du coût et difficulté par durée humaine. Non, ces résultats ne mesurent
pas directement le choix entre `/to-spec → /to-tickets → /implement` et
`/grill-with-docs → /implement`. Ce choix reste une question expérimentale
ouverte ; le pilote AnkiForge est donc pertinent, mais doit être élargi avant
toute décision de workflow par défaut.

## Retours de communautés et dépôts open source

Ces sources ne sont pas des évaluations contrôlées au sens scientifique. Elles
sont néanmoins utiles pour identifier les pratiques réellement adoptées, les
coûts observés et les variables à tester.

### Aider : raisonnement séparé de l’édition

Le mainteneur d’Aider décrit un mode **Architect/Editor** où un modèle produit
la solution et un second transforme cette solution en modifications de fichiers
([article Aider](https://aider.chat/2024/09/26/architect.html)). Sur son
benchmark d’édition, `o1-preview` architecte + `o1-mini` ou DeepSeek éditeur
atteint 85 %, contre 79,7 % pour le mode solo `o1-preview`. Pour Claude 3.5
Sonnet, le score passe de 77,4 % à 80,5 % en Architect/Editor.

Ce résultat est proche de la question AnkiForge car il compare une phase de
raisonnement préparatoire à une phase d’exécution. Il ne compare toutefois pas
la qualité d’un document de spécification à celle d’une interview de cadrage,
et le coût/temps des deux étapes n’est pas présenté comme critère primaire.

Le [harnais Aider](https://github.com/Aider-AI/aider/blob/main/benchmark/README.md)
est un bon précédent communautaire : 225 exercices difficiles, exécution
conteneurisée, ordre aléatoire, plusieurs essais, taux de réussite, réponses
malformées, erreurs de syntaxe, épuisement de contexte, timeouts, secondes par
cas et coût total. Il fournit une structure directement réutilisable pour
AnkiForge.

### Claude Code : le plan comme artefact éditable

L’analyse indépendante de
[Armin Ronacher](https://lucumr.pocoo.org/2025/12/17/what-is-plan-mode/)
conclut que le Plan Mode de Claude Code est principalement un fichier Markdown,
des rappels de prompt, un état lecture seule et une demande d’approbation.
L’auteur préfère un fichier de handoff qu’il peut lire et modifier, tandis
qu’il observe que Plan Mode apporte surtout une structure et une interface
d’approbation.

Cela soutient une hypothèse importante : `/to-spec` et `/grill-with-docs`
pourraient produire des bénéfices similaires si leur différence se réduit au
format et à la discipline de l’artefact. Le benchmark doit donc noter
séparément les décisions présentes, la lisibilité/éditabilité du livrable et
l’effet du nom de la commande ou de l’interface.

Un témoignage Hacker News
([Ask HN, juin 2025](https://news.ycombinator.com/item?id=44362244))
décrit un flux Gemini pour clarifier et résumer, revue humaine du résumé,
Claude Code Plan Mode, puis exécution et nettoyage manuel. L’utilisateur
rapporte une qualité perçue très variable et une part importante de travail
avant/après l’agent. C’est un signal qualitatif sur le coût total, pas une
mesure de taux de réussite.

### Plandex : planification progressive sur de très grandes bases

Le dépôt [Plandex](https://github.com/plandex-ai/plandex) se positionne sur les
tâches larges : project map Tree-sitter, 2 millions de tokens de contexte
effectif, projets annoncés jusqu’à 20 millions de tokens, planification de haut
niveau puis détaillée, implémentation, commandes et débogage. Son créateur
décrit sur [Hacker News](https://news.ycombinator.com/item?id=43710576) un
continuum d’autonomie et un sandbox de diff versionné.

Ce n’est pas une preuve comparative, mais un retour d’architecture cohérent
avec une règle adaptative : cadrage et validation fine pour les tâches
complexes, autonomie plus élevée pour les tâches simples. Le benchmark devrait
mesurer le seuil de complexité auquel le cadrage supplémentaire devient
rentable.

### Vibe Kanban : découpage, workspaces et exécution parallèle

Le dépôt [Vibe Kanban](https://github.com/BloopAI/vibe-kanban) organise le
travail sous forme d’issues, crée un workspace et une branche par agent, puis
permet revue de diff et commentaires. Dans son annonce Hacker News
([juillet 2025](https://news.ycombinator.com/item?id=44533004)), l’auteur
explique que l’attente synchrone de 2 à 5 minutes l’a conduit à paralléliser
les agents afin de réserver le temps humain à la planification et à la revue.

Le retour ne montre pas qu’un découpage augmente la correction fonctionnelle.
Il montre que le protocole doit inclure la productivité humaine : temps de
revue, parallélisation possible, isolation des workspaces et coût des conflits
ou intégrations.

### SWE-agent et mini-SWE-agent : simplicité opérationnelle

Le dépôt [SWE-agent](https://github.com/SWE-agent/SWE-agent) indique que
**mini-SWE-agent** a remplacé la version plus complexe tout en conservant des
performances comparables, avec environ 100 lignes Python annoncées dans la
présentation du projet. C’est un signal contre l’hypothèse « plus de workflow
signifie automatiquement meilleur résultat ».

Le benchmark AnkiForge devrait donc inclure une condition minimale
`/implement` sans cadrage spécialisé et mesurer si le coût du cadrage produit
un gain supérieur à son overhead.

### OpenHands : autonomie configurable et isolation

Le dépôt [OpenHands](https://github.com/OpenHands/OpenHands) et son Agent
Canvas décrivent des workspaces séparés, des backends multiples et des
automatisations qui décomposent des issues GitHub en tâches. La documentation
met aussi l’accent sur l’isolation Docker et sur le fait que deux conversations
partageant un même workspace peuvent entrer en conflit.

Cette expérience confirme que l’unité de mesure doit inclure le workspace,
l’historique de conversation et l’état Git ; sinon un bras peut bénéficier
involontairement des artefacts de l’autre.

## Synthèse des retours communautaires

| Observation | Hypothèse à tester |
|---|---|
| Architect/Editor améliore parfois le taux de réussite | Un artefact de cadrage explicite peut aider, mais son coût doit être compté |
| Un plan Markdown éditable est souvent préféré à un état caché | Évaluer le document comme artefact inspectable, pas seulement la conversation |
| Les grandes bases demandent indexation, sélection de contexte et sandbox | Contrôler la taille de la codebase |
| La parallélisation déplace l’effort vers planification et revue | Mesurer la charge humaine et les conflits |
| Des agents plus simples peuvent être compétitifs | Ajouter un bras direct `/implement` |
| Les témoignages rapportent une forte variance | Répéter chaque ticket et publier la dispersion |

## Mise à jour recommandée du benchmark

Pour répondre réellement à la question sur une codebase plus large, ajouter un
troisième bras :

1. **Direct** : ticket brut → `/implement` ;
2. **Spécification** : `/to-spec → /to-tickets → /implement` ;
3. **Cadrage** : `/grill-with-docs → /implement`.

Exécuter les trois bras sur 12 à 20 tickets issus d’une ou plusieurs bases
réelles, avec au moins trois répétitions par ticket et par bras. Conserver le
commit initial, le contexte transmis, les tests cachés, le diff, le coût, les
tours, les reprises et le temps de revue. Sans la baseline directe, il est
impossible de savoir si le coût des deux formes de cadrage produit réellement
un gain par rapport à une demande bien formulée.
