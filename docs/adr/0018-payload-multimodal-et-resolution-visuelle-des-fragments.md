# Payload multimodal et résolution visuelle des fragments

**Statut :** Accepté

Afin de permettre aux modèles de vision (VLM) d'analyser fidèlement les planches d'albums et les documents illustrés sans altérer le texte persisté ni casser la rotation durable, nous rejetons l'injection de balises images fabriquées dans les fragments (Option A) au profit d'une couture unique de **résolution visuelle de fragment** transportant les images en payload explicite (`extra_images`, Option B). Pour les PDF, le texte extrait par Marker OCR avec ses images intégrées prime sur le document binaire brut. En génération, le modèle reçoit conjointement la transcription OCR existante et l'image haute fidélité rendue dans son orientation réelle.

## Options considérées

1. **Option A — Balise `<img>` synthétique injectée dans le contenu du fragment** : Rejeté.
   - **Violation d'ADR 0011 (Rotation durable)** : `prepare_multimodal_payload` résolvait le fichier physique direct sur le disque (`media_dir / filename`). Or le fichier sur disque n'est jamais réécrit lors d'une rotation : le VLM recevait des planches couchées, et cette lecture directe violait le test de garde `test_album_seam_guard.py`.
   - **Pollution de la provenance (ADR 0009)** : Inscrire du balisage HTML/Markdown fabriqué dans `chunk.content` réintroduisait une redondance artificielle alors que `DocumentChunkModel` et `DocumentPageModel` portent déjà les clés étrangères vers `MediaModel`.

2. **Option B — Résolution visuelle explicite via la couture et transport en `extra_images`** : **Retenu**.
   - La planche est résolue par `AlbumService.render_page_image(page)`, qui applique fidèlement `page.rotation` en mémoire.
   - L'image encodée est transmise dans le tableau `extra_images` de `prepare_multimodal_payload`. Le texte reste pur et le test de garde est respecté.

3. **Image seule sans transcription vs Synergie Texte OCR + Image haute fidélité** :
   - Rejeté : Écraser la transcription par un texte factice (« Analyse visuelle multimodale... ») privait le modèle de vision des termes techniques exacts, noms propres et formules mathématiques LaTeX.
   - Retenu : Le prompt fournit conjointement la transcription OCR disponible et la planche en haute résolution, avec directive d'exploiter l'image pour les schémas, liaisons spatiales et diagrammes. Pour les documents PDF, le système s'appuie sur le texte et les figures extraits par Marker OCR plutôt que sur le parsing brut du PDF.

4. **Granularité d'envoi & Maîtrise des tokens** :
   - **Batch Factory** : Traitement découpé à granularité fine : 1 tâche batch / 1 fragment = 1 planche transmise par invite LLM, garantissant zéro dépassement de quotas.
   - **Studio de Création** : L'utilisateur est responsable de la sélection de planches. L'interface affiche une estimation des tokens visuels consommés et ne bloque qu'en cas de dépassement strict du plafond physique imposé par l'API du fournisseur (ex. limite de 20 images chez Anthropic), invitant alors à basculer vers la Batch Factory.

## Conséquences

- **Couture unique** : La résolution visuelle de fragment centralise l'accès aux planches pour le Studio de Création, la Batch Factory, les pipelines DAG et la récupération visuelle du RAG (`RAG - Scores RRF et Récupération Visuelle`).
- **Élimination de l'angle mort Batch** : `BatchWorker` et `CreationTaskPayload` propagent l'identité de l'album et des fragments, rendant la Batch Factory pleinement opérationnelle pour les albums en mode vision.
- **Transparence pour l'utilisateur** : Le Studio de Création prévient les explosions de coûts sans restreindre arbitrairement l'utilisateur tant que les limites matérielles des API sont respectées.
