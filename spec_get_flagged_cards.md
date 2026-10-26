# Spécification technique — `get_flagged_cards`

## Problématique (Problem Statement)

Les cartes Anki portent un drapeau de couleur dans `CardModel.flags`, mais les
agents MCP ne disposent pas d'un outil de lecture métier correspondant. Pour
retrouver les cartes rouges, suspendues ou sans drapeau, ils doivent actuellement
connaître le schéma SQLite et utiliser `query_peewee`, ce qui augmente le
couplage à la persistance et fragilise l'interprétation des valeurs `0..7`.

L'objectif est de fournir une lecture MCP bornée, déterministe et sans SQL
direct, compatible avec les usages d'audit et de préparation de mutations.

## Solution proposée

Ajouter `MCPToolRegistry.get_flagged_cards` et l'enregistrer dans
`DEFAULT_CONSULTANT_TOOLS`.

L'outil reçoit un drapeau obligatoire, éventuellement un nom exact de paquet,
ainsi que `limit` et `offset`. Il normalise les noms de couleurs et les valeurs
numériques Anki, filtre directement `CardModel`, puis retourne toujours un JSON
structuré contenant les filtres effectifs, le total et les éléments paginés.

Chaque élément représente une carte physique et expose :

- `card_id` ;
- `note_id` ;
- `deck_name` ;
- `flag` (nom canonique) et `flag_value` (entier `0..7`) ;
- `fields`, issus de la version active de la note et décodés en objet JSON
  lorsque possible.

Le tri est `CardModel.id ASC`. Le plafond de pagination reprend la convention
MCP existante (`limit` borné à 50, `offset` ramené à zéro s'il est négatif).
Les cartes suspendues et toutes les cartes sœurs sont incluses. Une recherche
sans résultat est un succès avec `items: []`.

## User Stories (Extensives)

1. En tant qu'agent MCP, je veux rechercher les cartes portant une couleur
   canonique, afin de préparer un audit sans écrire de SQL.
2. En tant qu'agent MCP, je veux fournir une valeur numérique Anki de `0` à `7`,
   afin de rester compatible avec les données importées et les outils bas niveau.
3. En tant qu'agent MCP, je veux filtrer par nom exact de paquet, afin de
   limiter une analyse à un périmètre connu sans inclure implicitement les
   sous-paquets.
4. En tant qu'agent MCP, je veux rechercher le drapeau `none`, afin d'identifier
   les cartes qui ne portent aucune couleur.
5. En tant qu'agent MCP, je veux parcourir les résultats avec `limit` et
   `offset`, afin d'éviter les réponses MCP non bornées.
6. En tant qu'agent MCP, je veux recevoir les champs de la note avec chaque
   carte, afin de comprendre le contenu avant de proposer une modification.
7. En tant qu'agent MCP, je veux obtenir un résultat vide structuré lorsque
   aucune carte ne correspond, afin de traiter ce cas sans parser un message
   textuel.
8. En tant qu'utilisateur de la Forge, je veux que les cartes suspendues restent
   visibles dans la recherche, afin que l'état réellement importé depuis Anki
   soit auditable.

## Décisions d'Implémentation

### Modules et interfaces touchés

- `src/ankiforge/services/ai/mcp_tool_registry.py`
  - ajouter une méthode statique `get_flagged_cards(...)` ;
  - définir la table de normalisation couleur/entier, idéalement partagée avec
    la convention déjà utilisée par `set_card_flag` ;
  - utiliser Peewee via `CardModel`, `DeckModel`, `NoteModel` et
    `NoteVersionModel`, sans SQL brut ;
  - trier par identifiant de carte et charger uniquement la page demandée ;
  - décoder la version active de la note avec le helper JSON existant ; en cas
    de contenu non JSON, retourner un objet `{"raw": ...}` plutôt que perdre le
    contenu.
- `DEFAULT_CONSULTANT_TOOLS`
  - enregistrer `get_flagged_cards` avec un schéma JSON déclarant `flag`
    obligatoire et `deck_name`, `limit`, `offset` facultatifs ;
  - documenter les couleurs admises, la valeur `0..7` et la pagination.

### Contrat d'entrée

```json
{
  "flag": "red",
  "deck_name": "Faculté::Biologie",
  "limit": 20,
  "offset": 0
}
```

`flag` accepte les valeurs suivantes :

| Valeur | Nom canonique |
|---:|---|
| 0 | `none` |
| 1 | `red` |
| 2 | `orange` |
| 3 | `green` |
| 4 | `blue` |
| 5 | `pink` |
| 6 | `turquoise` |
| 7 | `purple` |

Les noms sont insensibles à la casse après nettoyage. Toute autre valeur
retourne une réponse JSON d'erreur explicite, sans exécuter la requête.

### Contrat de sortie

Réponse avec correspondances :

```json
{
  "status": "success",
  "filters": {
    "flag": "red",
    "flag_value": 1,
    "deck_name": "Faculté::Biologie",
    "limit": 20,
    "offset": 0
  },
  "total": 1,
  "items": [
    {
      "card_id": 42,
      "note_id": 17,
      "deck_name": "Faculté::Biologie",
      "flag": "red",
      "flag_value": 1,
      "fields": {
        "Recto": "Question",
        "Verso": "Réponse"
      }
    }
  ]
}
```

Réponse sans correspondance :

```json
{
  "status": "success",
  "filters": {
    "flag": "purple",
    "flag_value": 7,
    "deck_name": null,
    "limit": 20,
    "offset": 0
  },
  "total": 0,
  "items": []
}
```

Les erreurs de validation et les erreurs d'exécution restent explicites dans un
JSON `{"status": "error", "message": "..."}`. Aucun fallback de succès ne doit
masquer une exception.

### Schéma de base de données et flux d'état

Aucune migration n'est nécessaire. L'outil effectue une lecture seule sur
`CardModel.flags`, avec jointure vers le paquet et la note. Il ne modifie ni
les cartes, ni les notes, ni les journaux de révision.

### Composants d'interface utilisateur

Aucun composant UI n'est requis. Le catalogue MCP expose l'outil aux agents
externes et au `ConsultantEngine` via le registre existant.

## Décisions de Test

- Ajouter un test d'intégration dans `tests/services/ai/test_mcp_tool_registry.py`
  ou le fichier MCP système approprié, avec la fixture `mock_db`.
- Créer au minimum deux cartes sœurs, dont une suspendue, et plusieurs paquets
  afin de vérifier que :
  - la couleur et l'entier retournent le même résultat ;
  - `none` fonctionne ;
  - le paquet exact n'inclut pas un sous-paquet ;
  - les cartes suspendues sont conservées ;
  - le tri par `card_id` et la pagination sont déterministes ;
  - une page vide retourne `status=success`, `total` correct et `items=[]` ;
  - une couleur invalide retourne `status=error` ;
  - les champs actifs de la note sont présents.
- Étendre le test de schéma existant dans
  `tests/services/ai/test_consultant_pagination.py` afin de vérifier la
  présence de l'outil, de ses paramètres et du caractère obligatoire de
  `flag`.
- Exécuter les tests ciblés avec l'environnement headless et les fixtures de
  base existantes :
  `uv run pytest tests/services/ai/test_mcp_tool_registry.py tests/services/ai/test_consultant_pagination.py`.

La couture principale à tester est l'appel public
`MCPToolRegistry.get_flagged_cards` sur la base de test, puis sa présence dans
le catalogue consommé par l'orchestrateur. Aucun appel réseau, LLM ou
retriever vectoriel n'est requis.

## Hors Périmètre (Out of Scope)

- Modifier `set_card_flag` ou le comportement d'application des drapeaux.
- Inclure automatiquement les sous-paquets.
- Ajouter un filtre par suspension, tag, type de note, échéance ou statistiques
  SRS.
- Dédupliquer les cartes sœurs pour ne retourner qu'une carte par note.
- Ajouter une migration, une table de référence ou une couleur personnalisée.
- Ajouter une interface graphique de recherche ou une action de mutation.
- Remplacer ou assouplir la sécurité de `query_peewee`.
