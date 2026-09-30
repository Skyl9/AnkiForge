# Format d'échange de thèmes : conteneur Famille, charge utile tolérante

**Statut :** accepté

Un fichier de thème exporté est un **conteneur de Famille de Thème** — il porte les deux variantes, sombre et claire — dont la charge utile est **tolérante** : chaque variante ne déclare que les jetons qu'elle définit, et l'import n'écrase que les champs présents.

## Options considérées
1. **Conteneur = Famille, charge utile complète** : simple, mais exporte une variante claire intacte que l'utilisateur n'a jamais touchée, et rend l'import destructeur sur les jetons non précisés.
2. **Unité = une seule Variante, avec un indicateur de régime explicite** : respecte « je n'exporte que ce que j'ai modifié », mais contredit le modèle à deux axes et impose à l'utilisateur de raisonnaer sur des variantes isolées.
3. **Delta strict contre la base de la Famille** : fichiers les plus petits, mais le roundtrip dépend de l'état exact de la base et devient fragile dès qu'une famille change.
4. **Conteneur = Famille, charge utile tolérante** : Retenu car le conteneur respecte le modèle à deux axes, tandis que la tolérance permet aux options 2 et 3 de s'exprimer en interne — un delta n'est qu'une charge utile partielle — sans jamais figer le format.

## Conséquences
- Les jetons **dérivés** (fonds et bordures teintés, textes sur accent) ne sont exportés que lorsqu'ils sont explicitement définis dans la Variante. La distinction entre « absent » et « vide » est donc porteuse de sens et fait partie du contrat du format.
- Les `DesignTokens` ne sont jamais exportés : ils sont intégralement dérivés de la Variante active, et un échange de jetons dérivés serait une source de vérité concurrente.
- Le format est versionné. Le comportement face à une version plus récente que celle connue doit être tranché avant implémentation : c'est la seule décision de ce format encore ouverte.
- Ce format est public dès la première exportation : le conteneur ne pourra plus passer de Famille à Variante sans casser les fichiers déjà échangés.
