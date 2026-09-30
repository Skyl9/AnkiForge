# Adresser une région par son nœud, et écarter sans détruire

**Statut :** accepté

L'exclusion d'une portion de document cesse d'être un acte destructif et devient une **règle déclarée**, exprimée dans une **adresse de région** durables. Une région est adressée de trois façons seulement — le nœud, sa lignée, sa page — et jamais par l'identité d'un fragment. Le conteneur structural gagne un axe d'Origine : *Dérivé* ou *Déclaré*.

## Le défaut

L'exclusion n'était adressable qu'au niveau du fil d'Ariane, et son prédicat était un **test de sous-chaîne** (`low_entry in low_path`, `document_repository.py:381`). Deux conséquences en découlaient.

**La granularité.** Un titre global porte souvent un bloc de texte entre lui et son premier sous-titre — préambule, avertissement institutionnel, page de garde. Ce bloc est un fragment à part entière, au fil d'Ariane **nu** du parent. L'utilisateur ne pouvait ni l'écarter, ni le neutraliser : la seule adresse disponible était le titre lui-même, dont l'exclusion emporte toute la lignée. La catégorie ainsi créée ne pouvait être ni couverte, ni désactivable — un motif signalé par un utilisateur dans le tableau de suivi.

**L'accumulation.** exclusion destructive, trous de pagination et cartes de chapitre partageaient une **liste JSON non typée**. Le prédicat était réimplémenté en six endroits, dont deux en sémantique *exacte* (`delimitation_dialog.py:3527`) et quatre en sémantique *sous-chaîne* : l'interface pouvait afficher une section comme incluse pendant que le filtre l'excluait. Le mode cartes de chapitre écrivait `"[]"` et effaçait toute trace de ses exclusions. La couverture de ce mode était atteinte par **accumulation de cas particuliers** dans une structure unique — chaque besoin nouveau ajoutait une sémantique au lieu d'une valeur à un paramètre.

L'exclusion étant destructive, la matière était supprimée et `NoteChunkLinkModel.chunk` en `on_delete="CASCADE"` détruisait les liens de couverture du sous-arbre. Les cartes survive, leur provenance non.

## Options considérées

1. **Créer des « conteneurs structurels » définis par l'utilisateur** : rejeté. Un conteneur nommé est un objet durable dont l'identité doit survivre à la réingestion — c'est précisément le piège de l'ADR 0009, où un identifiant de fragment était devenu une preuve de présence périmée. Retenu comme *origine* du conteneur existant plutôt que comme un objet distinct.
2. **Adresser la région par l'identifiant du fragment** : rejeté pour la même raison que l'ADR 0009. L'identifiant d'un fragment est détruit à chaque réingestion ; une règle fondée dessus produirait des exclusions orphelines.
3. **Rendre le fil d'Ariane nu adressable comme une entité distincte de sa lignée** : **retenu**. Le modèle sépare déjà les deux — le contenu propre d'un titre porte le fil nu, ses descendants portent le même préfixe suffixé de `HEADING_SEPARATOR`. Aucune identité nouvelle n'est nécessaire ; seule la sémantique du prédicat change.
4. **Traiter « garder la région comme unité mesurable » comme un troisième verbe** : rejeté car elle tombe gratuitement. Une région adressable est déjà une unité de couverture distincte ; le cas (c) n'est pas une action, c'est une conséquence de l'adressabilité.
5. **Un seul verbe (exclure)** : rejeté. Un booléen unique ne peut pas servir les deux besoins : si la région disparaît, elle n'est plus lisible ; si elle reste et devient une cible de génération, l'utilisateur ne peut pas signaler qu'elle ne doit pas compter.
6. **Supprimer le seuil de 25 mots** : rejeté. Il reste le critère de l'origine *Dérivée* ; seule son usage pour l'origine *Déclarée* devient une aide à la déclaration.
7. **Un nom par origine** (« conteneur déclaré » vs « conteneur structural ») : rejeté. Deux noms pour un seul drapeau produisent une ambiguïté que rien ne permet ensuite de lever à la lecture d'un écran.
8. **Conserver l'exclusion destructive** : rejeté. L'écartement non destructif est la condition pour que la région demeure réintégrable et que sa persistance soit une règle et non un état figé.

## Conséquences

- L'**adresse de région** est un paramètre à trois valeurs — `node:` (contenu propre), `heading:` (lignée), `page:` (page). C'est cette valeur qui remplace l'accumulation de sémantiques : un nouveau besoin ajoute une valeur, pas un cas particulier.
- La liste d'adresses est **typée**. Les entrées **sans préfixe** sont lues comme `heading:`, ce qui rend les profils existants exacts : **aucune migration de données** n'est nécessaire. L'ambiguïté d'un titre littéralement nommé « 4 », aujourd'hui lu comme un trou de page (`document_scope_dialog.py:274-277`), disparaît.
- Les deux verbes sont **deux colonnes** : *écarter* retire la région du document et de sa couverture ; *neutraliser* la retire du seul dénominateur. Un conteneur *Déclaré* est un conteneur neutralisé ; un conteneur *Dérivé* s'obtient par le seuil.
- La contrainte `has_descendants` (`chunking_service.py:238`) est **relaxée pour l'origine *Déclarée* uniquement**. La règle dérivée est inchangée : sans cela, tous les profils existants verraient leur couverture changer d'une réingestion à l'autre.
- Une règle est **réévaluée à chaque réingestion**, jamais mémorisée sous forme d'état figé. C'est ce qui distingue une règle d'un résidu — l'exact contraire du `chunk:` de l'ADR 0009.
- `CoverageAlignmentService.resolve_attachment` **consulte l'écartement** et s'abstient : le palier `lexical` ne peut pas désigner une région écartée. Jusqu'ici ce défaut était inoffensif, les fragments écartés étant supprimés ; l'écartement non destructif l'active. Une exclusion que l'analyse peut ignorer n'est pas une exclusion, c'est un commentaire.
- Le prédicat d'adressage est **unifié en un seul point**. Les six implémentations concurrentes (deux *exactes*, quatre *sous-chaîne*) cèdent la place à une règle unique, sans quoi l'écartement non destructif reste contredit par les chemins de réécriture.
- Le mode cartes de chapitre cesse d'écrire `"[]"` : un écartement déclaré laisse une trace persistée, ce qui le distingue d'un simple bornage de pages.

## Compléments d'implémentation

### La borne de pages fait partie de la règle

`start_page`/`end_page` n'est pas un cadrage d'affichage : c'est une composante de l'exclusion.
Une page hors de la borne est donc hors périmètre au même titre qu'une région écartée, pour la
couverture comme pour la génération. Sans cela, un document délimité aux pages 3 à 8 continuerait
de compter ses pages 9 et 10 dans le dénominateur, et la couverture rapportée serait fausse.

### L'abstention lexicale est une décision, pas une panne

`CoverageAlignmentService` abandonne le rattachement d'une carte dont le texte n'échoe aucun
fragment de sa partie. Un lien absent se voit et se corrige ; un lien inventé se constate trop
tard, quand une carte porte une affirmation que la source ne contient pas.

### Le RAG filtre deux fois, et sait se taire

La règle est appliquée à l'indexation, où elle évite d'écrire ce qui n'a pas à être écrit, **et**
au moment de répondre, où elle seule est effective sans attendre une réindexation que rien
n'impose. Un document dont toutes les régions sont écartées voit son index retiré : laisser
l'artefact en place reviendrait à faire répondre l'index par le nom du document, c'est-à-dire à
faire dépendre la règle du fait qu'on a pensé à reconstruire.

### Granularités d'adresse et matière propre

`node:` existe pour une raison de couverture, pas d'ergonomie : neutraliser un chapitre par son
seul titre rendrait conteneurs des sous-sections qui ont leur propre contenu. C'est ce cas
d'école — le préambule d'un chapitre — qui rend `heading:` et `node:` deux règles différentes.
