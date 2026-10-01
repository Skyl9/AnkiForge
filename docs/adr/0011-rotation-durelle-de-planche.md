# Rotation durable de planche

**Statut :** accepté

La rotation d'une planche cesse d'être un réglage d'affichage : elle devient une **propriété durable de la planche**, appliquée **à la lecture** par une couture unique, et toute modification invalide l'état dérivé de la planche. Le fichier image n'est jamais réécrit.

## Le défaut

`DocumentPageModel.rotation` (`rag.py:60`) était déjà persisté, mais **un seul** de ses neuf consommateurs l'honorait. La compilation PDF l'appliquait (`album_service.py:297`) ; les huit autres lisaient le fichier brut : la vignette (`album_viewer.py:144`), l'inspecteur (`:357`), la remise à l'éditeur d'occlusion (`:426`), la transcription OCR (`ocr_service.py:260`), la description dense du RAG visuel (`visual_rag_service.py:128`), les vignettes d'album du Studio de Création (`document_editor.py:501`) et l'aperçu de délimitation (`delimitation_dialog.py:1747`).

Trois conséquences en découlaient.

**Le silence.** « Les modifications des livres d'images ne semblent pas être prises en compte » : la rotation est bien enregistrée, l'interface la montre, et la transcription comme le RAG continuent de décrire une planche couchée. Rien ne signale l'écart — c'est la pire des deux issues, un état faux sans témoin.

**La corruption en aval.** L'éditeur d'occlusion recevait l'image brute : les masques SVG sont cuits à des coordonnées qui ne correspondent plus à ce que l'utilisateur voit. Contrairement à un simple décalage d'affichage, ici c'est une **donnée fausse** — le masque est la réponse à une question posée sur la mauvaise image.

**La duplication.** Chaque consommateur réimplémentait son propre chargement d'image, sans contrainte. Un neuvième consommateur fourvoyé n'était qu'à une ligne, et rien n'aurait échoué.

Deux défauts voisins partageaient la même cause racine : la vignette chargeait l'image **en pleine résolution** puis la transformait en `SmoothTransformation` sur le thread GUI (`album_viewer.py:141-165`) — « tourner une image à 90° freeze l'image » ; et « ajuster à la fenêtre » positionnait `_zoom_factor = 1.0`, c'est-à-dire 100 % de la résolution native, jamais la taille de la fenêtre (`album_viewer.py:247`).

## Options considérées

1. **Inscrire la rotation dans le fichier image à l'écriture** : rejeté. `MediaManager` déduplique par MD5 (`media_manager.py:25-30`) : deux planches peuvent partager un même fichier. Écrire dessus pivoterait gratuit la planche voisine, et détruirait l'original — ce que l'ADR 0010 refuse pour une région. Une rotation est une **règle**, pas une réécriture.
2. **Traiter la rotation comme un réglage d'affichage** : rejeté. L'utilisateur a pivoté un scan de travers et attend que l'OCR et les cartes soient justes ; un réglage d'affichage ne peut pas le lui garantir. Cela obligerait en outre la compilation PDF à cesser d'appliquer la rotation, et sa docstring (« en appliquant fidèlement les rotations définies sur chaque page ») deviendrait un mensonge.
3. **Régénérer OCR et index de façon synchrone à chaque rotation** : rejeté. Sur un album de 200 planches, cela signifie 200 appels à un modèle de vision sur le thread GUI. Le coût et le gel dépassent le bénéfice.
4. **Laisser les consommateurs parallèles, corriger seulement les cinq internes à l'album** : rejeté. C'est la situation actuelle ; elle laisse les trois consommateurs satellites afficher des planches couchées et l'occlusion cuire des masques faux. Le problème n'est pas le nombre de bugs, c'est l'absence de point d'entrée unique.
5. **Une couture unique appliquant la rotation à la lecture, invalidant l'état dérivé** : **retenu**.

## Conséquences

- **`AlbumService.render_page_image(page)` est le seul moyen de lire une planche.** Il rend un `PIL.Image.Image` — la représentation que la transcription, la compilation et le modèle de vision parlent déjà — accompagné d'un adaptateur `QPixmap` pour l'interface. Une **seule** représentation, pour que deux coutures ne puissent pas dériver l'une de l'autre.
- Un **test de garde** énumère les modules autorisés à lire `page.media.filename`. C'est une contrainte au niveau source, assumée : ce dépôt a déjà une culture de linter (`Hopital Audit`, `Wozniak`), une règle invérifiable à l'exécution n'y aurait pas sa place.
- L'**état dérivé** — transcription, description dense — est **périmé** dès que la planche change. Une rotation vide `ocr_text`, retire le fragment indexé de la planche et marque son `status` `stale`. L'interface affiche « transcription périmée » et propose de retranscrire ; elle ne le fait pas d'elle-même, pour ne pas engager une dépense de tokens sans y être invitée. Le même principe que « une carte non rattachée reste hors couverture » : un lien absent se voit et se corrige, un lien inventé se constate trop tard.
- `prepare_visual_chunks` doit savoir **recalculer une planche** et non l'album entier ; sans cela, le choix se réduit à réindexer tout l'album ou à laisser une planche définitivement périmée.
- **L'état dérivé périmé est visible, jamais servi.** Conformément à la déclaration « la déclaration fait autorité » sur `supports_vision`, un album dont la catégorie de transcription pointe vers un modèle texte seul doit être refusée à l'entrée, pas échouer vaguement.
- `crop_data` et `bounding_boxes` (`rag.py:61,63`) sont des **colonnes mortes** : déclarées par la migration `024`, sans aucune lecture ni écriture dans le code. Elles ne sont pas supprimées ici — ce serait du bruit sans rapport — mais la **couture est le lieu d'un recadrage futur**, pas un troisième mécanisme parallèle.

## Compléments d'implémentation

### Le contraste n'a jamais existé

Le curseur « Contraste » de l'inspecteur (`album_viewer.py:379-384`) convertit l'image en `ARGB32` puis la reconvertit en `QPixmap` sans **aucun** ajustement : il est remis à zéro à chaque changement de page (`:352`). Un contrôle qui ment est pire que son absence ; il est supprimé, sans terme de glossaire — un terme ne se définit pas pour une fonctionnalité qui n'a jamais existé.

### La compilation PDF était morte depuis son introduction

`album_viewer.py:775` appelait `compile_album_to_pdf(..., output_pdf_path=out_path)` alors que la signature est `output_path` (`album_service.py:276`) : `TypeError` garanti, rattrapé en `:777` et transformé en échec d'action. La compilation exige en outre un worker, la boucle ouvrant chaque planche pleine résolution dans PIL sur le thread GUI — c'est le même gel que la rotation, une couche plus bas.
