# Désencastrer les deux axes d'apparence dans la persistance

**Statut :** accepté

La préférence d'apparence ne sera plus persistée comme un identifiant de thème unique. On persiste **la Famille de Thème choisie** et **la Source du Mode** (Sombre manuel / Clair manuel / Système) ; la Variante effective devient un calcul dérivé de ces deux axes.

## Options considérées
1. **Conserver `theme_id` + un drapeau booléen `follow_system`** : Rejeté car il laisse intact le défaut structurel — un seul scalaire continue de porter deux notions distinctes (l'identité graphique et le régime visuel), et rien dans le modèle ne dit que ce sont deux axes.
2. **Stocker une sentinelle dans `theme_id` (ex. `"auto"`)** : Rejeté car `theme_id` est validé et résolu par `get_family_for_theme`, qui attend un identifiant de thème ou de famille réel ; une sentinelle casse ce contrat et le repli silencieux.
3. **Séparer les deux axes** : Retenu car c'est la seule option qui aligne la persistance sur le modèle à deux axes déjà décrit dans `DESIGN.md` (Mode d'Apparence × Famille de Thème), et qui rend « Suivre le thème système » exprimable comme une règle plutôt que comme un point.

## Conséquences
- La lecture paresseuse avec normalisation au premier accès est préférée à une migration explicite : `SettingModel` est un magasin clé/valeur sans migration de schéma possible, et la normalisation paresseuse rattrape aussi les profils que les anciennes versions ont écrits.
- Le choix explicite d'une Famille par l'utilisateur prime sur la Famille suggérée par le layout : la table layout→famille devient une valeur par défaut, appliquée seulement tant qu'aucune Famille n'a été choisie.
- Ce refactor transverse est suivi dans un ticket dédié, dont dépend le ticket « Suivre le thème système » : il change le contrat de persistance pour tous ses consommateurs (modale des paramètres, démarrage de la fenêtre principale, sélecteur de layout) et mérite donc ses propres tests.
