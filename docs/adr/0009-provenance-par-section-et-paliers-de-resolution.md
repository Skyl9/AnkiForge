# Identifier une provenance par sa section, pas par son fragment

**Statut :** accepté

La provenance d'une carte est identifiée par le couple (document, fil d'Ariane) et non par l'identifiant du fragment qui l'a produite. `chunk:` n'est plus écrit. Le rattachement d'une note à un fragment reste une désignation précise, mais il est **tracé** : le palier qui l'a désignée est persisté sur le lien.

## Le défaut

`build_document_tags` écrivait `chunk:<id>` comme tag de provenance. Cet identifiant désigne un artefact du découpage : il est propre à une passe d'ingestion et disparaît à la suivante. Après réingestion, les tags pointent vers des fragments qui n'existent plus et la couverture tombe à zéro alors que les cartes sont intactes. Sur le profil de développement, 24 tags `chunk:` sur 24 étaient pendants.

Le défaut de résolution qui rendait cela irréparable est un `if`/`elif` : la présence d'un `chunk:` — même invalide — court-circuitait les paliers suivants, dont la `section:` qui aurait très bien pu résoudre. Une donnée périmée devenait ainsi une preuve de présence.

## Options considérées

1. **Continuer d'écrire `chunk:` et le rafraîchir à la réingestion** : rejeté car la réingestion est précisément l'opération qui invalide ces identifiants ; il faudrait un appariement à faire au moment où l'information est déjà perdue.
2. **Migrer les `chunk:` vers des `section:`** : rejeté en raison du coût disproportionné. La réparation est déjà obtenue gratuitement par la synchronisation, qui s'exécute de toute façon.
3. **Écrire la section uniquement, sans arrêt du rattachement par fragment** : retenu. La section est l'identité durable, le fragment la désignation précise ; confondre les deux niveaux était la cause du problème.
4. **Ajouter un identifiant de section stable aux fragments** : rejeté car la table des fragments est reconstruite à chaque ingestion, et un identifiant y survivrait mal. Le fil d'Ariane est déjà cette adresse, et il est lisible par un humain dans le document.
5. **Échouer strictement quand rien ne résout** : rejeté car l'utilisateur a retenu un repli permissif. L'alternative opposée — rattacher hors de la partie sur un simple recouvrement lexical — produit un faux lien, plus trompeur que son absence.

## Conséquences

- `build_document_tags` n'accepte plus de `chunk_id`, et n'écrit `page:` que si une page est un fait avéré. Les PDFs et Markdown continus ne produisent donc plus de `page:1` : ce tag était une supposition présentée comme un fait.
- Les tags d'ancienne forme restent lisibles. Les clés de section issues d'une numérotation video (`[00:01]`) sont tolérées à la lecture et retirées à l'écriture : elles changeaient de valeur selon le lecteur.
- `CoverageAlignmentService.resolve_attachment` est l'unique politique de résolution, appelée à la création, au batch et en synchronisation. `resolve_finest_chunk_for_card` n'en est qu'un wrapper.
- La colonne `NoteChunkLinkModel.resolution` est nullable : les liens antérieurs n'ont pas de palier connu, et inscrire `NULL = lexique` serait une affirmation fausse.
- La synchronisation devient **réparatrice** : elle réécrit les tags périmés et les supprime. C'est le mécanisme par lequel les profils existants se corrigent, sans migration.
- Le rapport expose `repaired_notes` et `resolution_breakdown`. Un lien présumé par recouvrement lexical reste indiscernable d'un lien prouvé tant que l'interface ne les sépare pas — c'est la suite naturelle.
- L'import d'un paquet Anki ne déclenche pas de synchronisation : une note importée sans étiquette de provenance n'a rien à résoudre. Le rattacher automatiquement serait une attribution non demandée.
