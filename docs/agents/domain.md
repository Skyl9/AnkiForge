# Domain Docs

Comment les skills d'ingénierie doivent consommer la documentation de domaine de ce repo lors de l'exploration du code.

## Avant d'explorer, lire

- **`CONTEXT.md`** à la racine du repo (glossaire de domaine), ou
- **`CONTEXT-MAP.md`** à la racine s'il existe : il pointe vers un `CONTEXT.md` par contexte. Lire ceux qui concernent le sujet.
- **`docs/adr/`** : lire les ADR touchant la zone de travail. En multi-contexte, vérifier aussi `src/<contexte>/docs/adr/`.

Si certains de ces fichiers n'existent pas, **continuer silencieusement**. Ne pas signaler leur absence, ne pas suggérer de les créer d'emblée. Le skill `/domain-modeling` (atteint via `/grill-with-docs` et `/improve-codebase-architecture`) les crée paresseusement quand des termes ou décisions sont réellement résolus.

## Structure de fichiers

Repo mono-contexte (cas quasi-universel ici) :

```
/
├── CONTEXT.md
├── docs/adr/
│   └── 0001-<slug>.md
└── src/
```

Repo multi-contexte (présence d'un `CONTEXT-MAP.md` à la racine) :

```
/
├── CONTEXT-MAP.md
├── docs/adr/                          ← décisions globales au système
└── src/
    ├── <contexte>/
    │   ├── CONTEXT.md
    │   └── docs/adr/                  ← décisions propres au contexte
    └── ...
```

## Utiliser le vocabulaire du glossaire

Quand la sortie nomme un concept de domaine (titre d'issue, proposition de refactor, hypothèse, nom de test), utiliser le terme tel que défini dans `CONTEXT.md`. Ne pas dériver vers des synonymes que le glossaire évite explicitement.

Si le concept nécessaire n'est pas encore dans le glossaire, c'est un signal : soit vous inventez un langage que le projet n'utilise pas (reconsidérer), soit c'est une vraie lacune (la noter pour `/domain-modeling`).

## Signaler les conflits d'ADR

Si la sortie contredit un ADR existant, le signaler explicitement plutôt que de le passer sous silence :

> _Contredit ADR-0007 (event-sourced orders), mais vaut la peine d'être rouvert parce que…_
