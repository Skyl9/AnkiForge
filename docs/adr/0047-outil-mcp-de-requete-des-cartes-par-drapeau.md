# ADR 0047 : Outil MCP de requête des cartes par drapeau

**Statut :** accepté

## 1. Contexte

Les cartes importées d'Anki portent un drapeau de couleur dans `CardModel.flags`.
Le registre MCP fournit déjà la mutation `set_card_flag`, mais un agent devait
utiliser une requête SQL directe pour retrouver les cartes par couleur. Cette
surface contourne le contrat métier des outils MCP et expose inutilement le
schéma de persistance.

## 2. Décision

Le registre MCP expose un outil de lecture dédié `get_flagged_cards`. Son contrat
est le suivant :

- `flag` est obligatoire et accepte soit un nom canonique (`none`, `red`,
  `orange`, `green`, `blue`, `pink`, `turquoise`, `purple`), soit une valeur
  numérique Anki de `0` à `7` ; l'outil normalise la valeur avant la réponse ;
- `deck_name` est facultatif et applique une égalité exacte sur le nom du
  paquet ; son absence couvre toute la collection ;
- `none` est une valeur valide et permet de retrouver les cartes sans drapeau ;
- `limit` et `offset` bornent toujours la réponse, avec un plafond strict et un
  ordre déterministe croissant par identifiant de carte ;
- chaque résultat expose l'identifiant de carte, l'identifiant de note, le
  paquet, le drapeau normalisé (nom et valeur) et un aperçu structuré des
  champs de la note ;
- la réponse est toujours JSON et contient les filtres normalisés, le total et
  `items`; une recherche sans résultat renvoie `items: []`, sans erreur ;
- toutes les cartes correspondantes sont visibles, y compris les cartes
  suspendues et les cartes sœurs issues d'une même note.

L'outil passe par `MCPToolRegistry` et le schéma `DEFAULT_CONSULTANT_TOOLS`.
L'agent n'a pas besoin de connaître ni d'émettre du SQL.

## 3. Raisons

Cette interface réutilise la convention MCP de pagination existante tout en
stabilisant la représentation des drapeaux déjà employée par `set_card_flag`.
Le tri par identifiant rend les pages reproductibles, et la réponse vide
uniforme évite de distinguer artificiellement un paquet vide d'une collection
sans correspondance. La visibilité complète préserve l'observation fidèle des
données Anki ; le filtrage des cartes suspendues reste une décision aval de
l'appelant.

## 4. Conséquences

- Les agents disposent d'une lecture métier sûre pour préparer des audits ou
  des corrections de drapeaux.
- Le schéma SQL et les valeurs brutes de `flags` ne sont plus nécessaires pour
  ce cas d'usage.
- L'outil doit conserver une validation stricte des couleurs et des valeurs
  numériques, ainsi que des limites de pagination, afin de ne pas produire de
  requêtes ou de réponses non bornées.
