# Modal dédié de transcription d'album et ciblage du périmètre

**Statut :** accepté

La transcription d'un album cesse d'être un déclenchement aveugle et global depuis la barre d'outils : elle s'articule autour d'un **modal dédié explicite** (`AlbumTranscriptionDialog`), d'un **ciblage dynamique du périmètre** (respectueux des états dérivés et des planches périmées), de **directives de formatage modulaires** et d'une **tolérance aux pannes avec reprise chirurgicale**.

## Le défaut

Dans `AlbumViewerWidget` (`album_viewer.py:687-701`), la transcription était pilotée par un sélecteur déroulant de catégorie et un bouton d'action directe.

Quatre défauts majeurs en découlaient :

1. **L'absence de discernement de périmètre (tout ou rien).** L'action traitait systématiquement l'album entier. Si l'utilisateur ajoutait 2 planches à un album de 80 planches ou pivotait une seule planche (la rendant `stale` conformément à l'ADR 0011), il devait soit re-transcrire les 80 planches — consommant inutilement du temps et des tokens d'API — soit renoncer à mettre à jour la planche modifiée.
2. **L'inaccessibilité des directives d'extraction.** Les consignes d'extraction (conversion des équations en LaTeX KaTeX, tableaux Markdown/HTML, description textuelle dense des figures et schémas scientifiques, consignes terminologiques) étaient figées dans les catégories prédéfinies ou le code du service, inaccessibles à l'utilisateur sans aller modifier la configuration globale du profil dans les réglages IA.
3. **Le silence et la confusion face au moteur matériel Apple Vision.** Le moteur natif macOS Apple Vision réalise une détection optique haute vitesse sans modèle de langage (VLM). Laisser l'utilisateur supposer que des directives de prompt ou des réglages de température allaient s'appliquer à ce moteur créait un état trompeur.
4. **L'amnésie en cas d'échec partiel.** En cas d'erreur réseau, de timeout ou de rate-limit sur quelques planches lors d'un traitement par lot, le worker se terminait par un simple décompte (`X planches en échec`), sans mémoriser les planches concernées ni offrir de moyen de relancer uniquement les échecs sans tout recommencer.

## Options considérées

1. **Multiplier les boutons et menus dans la barre d'outils de l'album :** rejeté. Cela surchargerait la barre d'outils, masquerait les dépendances logiques entre le moteur et les options de prompt, et rendrait l'interface confuse.
2. **Garder un dialogue modal bloquant pendant toute l'exécution :** rejeté. L'utilisateur doit pouvoir observer la mise à jour visuelle des vignettes dans la grille en temps réel et continuer de naviguer sans avoir une boîte de dialogue figée devant son espace de travail.
3. **Modal dédié de configuration (`AlbumTranscriptionDialog`) + exécution asynchrone dans l'album avec reprise chirurgicale :** **retenu**.

## Conséquences

- **`AlbumTranscriptionDialog` est le point d'entrée unique de paramétrage de transcription.** Il remplace le sélecteur déroulant partiel de la barre d'outils par un bouton clair *« Transcrire l'album… »*.
- **Le périmètre de transcription est vérifié dynamiquement en direct :**
  - Quatre modes exclusifs : *Tout l'album*, *Planches non transcrites uniquement*, *Planches périmées (`stale`)*, *Intervalle personnalisé*.
  - Les effectifs de chaque mode sont calculés et affichés en direct ; toute option résolvant à 0 planche désactive le lancement avec mention explicite, interdisant les passes à vide.
- **Les directives de transcription sont composables :**
  - Toggles dédiés : Formules LaTeX ($...$), Tableaux structurés, Descriptions des figures/schémas, Hiérarchie des titres.
  - Champ d'instructions spécifiques complémentaires.
  - Règles de garde strictes préservées (aucun bavardage méta).
- **Repli explicite pour Apple Vision :** La sélection du moteur matériel désactive et estompe les directives de langage et réglages avancés avec un message didactique, rendant compte de la réalité technique sans décalage d'interface.
- **Tolérance aux pannes et relance chirurgicale :** `AlbumOCRWorker` collecte les `failed_page_ids`. En cas d'échec partiel, la barre de progression propose une action directe *« Relancer les échecs (N) »* qui cible instantanément les seules planches avortées.
- **Persistance granulaire :** Les préférences générales de formatage et la catégorie par défaut sont conservées dans `SettingsService`, tandis que le périmètre et les instructions libres sont contextualisés à l'album ouvert.
