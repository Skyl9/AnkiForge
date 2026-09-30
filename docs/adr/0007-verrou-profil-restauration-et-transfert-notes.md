# Verrouillage par profil, restauration granulaire et préservation des identités au transfert

Pour prévenir les corruptions SQLite lors d'accès concurrents tout en autorisant l'usage multi-profils, l'application utilise un verrou exclusif par profil (`QLockFile` sur `.profile.lock`). Lors du transfert de contenu entre profils, l'identité canonique (GUID) des notes est obligatoirement conservée afin de permettre une réconciliation et fusion déterministe ultérieure sans générer de faux doublons. Enfin, la restauration granulaire impose un instantané de sécurité pré-restauration suivi d'un redémarrage propre du processus pour garantir la remise à zéro des états Peewee, du cache FTS5 et des workers d'arrière-plan.

## Statut
Accepté

## Options considérées
- **Verrou applicatif global vs verrou par profil** : Le verrou global interdisait d'ouvrir deux profils distincts en parallèle. Le verrou par profil isole strictement l'écriture sur chaque sous-répertoire de données (`~/.ankiforge/profiles/<nom>/`).
- **Génération de nouveaux GUIDs lors du transfert** : Rejeté pour éviter la duplication fantôme de cartes identiques partagées ou révisées entre profils.
- **Rechargement à chaud (Hot-Reload) de la base de données après restauration** : Rejeté car les connexions Peewee, l'indexation FTS5 et le serveur MCP persistant risquent des incohérences mémoire et des verrous résiduels. Le redémarrage complet du processus assure une transition 100% propre.
