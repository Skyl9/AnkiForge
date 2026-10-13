# Provenance d'une occlusion possédée par l'appelant, résolue en `exact` sur le fragment de la figure

**Statut :** accepté

Une note Image Occlusion créée depuis une **Figure** d'un document — ou une planche d'album — reçoit sa provenance (tags `doc:`, `section:`, `page:` et lien `NoteChunkLinkModel`) **non** du service d'occlusion, mais de **l'appelant qui détient le contexte visuel**. `ImageOcclusionService` et `ImageOcclusionDialog` restent agnostiques du document. Le rattachement passe par l'unique politique `CoverageAlignmentService.resolve_attachment(source_chunk_id=…)` et se résout au palier `exact`, puisqu'on connaît le fragment porteur de la figure au lieu de le déduire.

## Le défaut

`ImageOcclusionService.create_occlusion_notes` (`image_occlusion_service.py:457`) crée ses `NoteModel` avec pour seuls tags ceux de la boîte de dialogue : aucun tag `doc:`/`section:`/`page:`, aucun `NoteChunkLinkModel`. L'affordance album existante (`album_viewer.py:854`) ouvre le dialogue puis **jette** `get_created_notes()`. Une carte d'occlusion est donc aujourd'hui orpheline de sa source, où qu'elle soit produite.

## Options considérées

1. **Rendre le service d'occlusion conscient du document** (il reçoit `doc_id`/`heading_path`/`page` et écrit tags + lien) : **rejeté**. Cela couplerait un service de cartes à l'arborescence documentaire, alors que le motif en place (`creation_view`, `batch_view`) fait posséder la provenance par l'appelant. Deux sources de vérité pour la même question divergeraient, — précisément la divergence que l'ADR 0009 a supprimée en centralisant le rattachement.
2. **Provenance possédée par l'appelant, résolue en `exact`** : **retenu**. La galerie de figures connaît le fragment de la figure ; la vue album connaît la planche. Tous deux réutilisent `resolve_attachment` (ADR 0009) et n'écrivent jamais un lien hors de cette politique.

## Conséquences

- La galerie de figures lit par la couture visuelle (ADR 0018), étendue d'un mode **listing** : elle ne duplique pas la sélection des images.
- Le chemin **album est recâblé** : il consomme désormais `get_created_notes()` et rattache, comme le fera le chemin document. Une occlusion de planche n'est plus moins tracée qu'une occlusion de figure.
- Le service d'occlusion demeure réutilisable hors document (image collée, fichier arbitraire) sans provenance — un état légitime, et non un défaut.
