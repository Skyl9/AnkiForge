# Bibliothèque de thèmes en fichiers JSON, pas en table

**Statut :** accepté

Les Familles et Variantes personnalisées résideront dans un répertoire de fichiers JSON sous le dossier de données de l'application, comme source de vérité unique. Le registre en mémoire du moteur de style sera peuplé au démarrage par balayage de ce répertoire.

## Options considérées
1. **Nouvelle table Peewee pour les thèmes** : Rejeté car la finalité du produit est le partage : un thème se copie, se versionne, s'archive et se colle dans un ticket. Un fichier est le format d'échange naturel ; une base n'apporte rien de plus et imposerait une migration pour un besoin qui est celui d'un fichier.
2. **Table comme cache, fichier comme vérité** : Rejeté comme complexité inutile — deux couches à garder synchronisées pour un jeu de données qui tient en quelques kilo-octets.
3. **Fichiers JSON comme vérité unique** : Retenu car le répertoire rend le partage natif, reste inspectable et versionnable, et donne enfin un consommateur réel à `register_theme`, jusqu'ici appelé uniquement par un test.

## Conséquences
- La bibliothèque est **globale à l'installation et partagée entre tous les profils**. Un profil ne crée pas de thèmes : il pointe vers une Famille de la bibliothèque. La distinction entre « contenu » (bibliothèque, globale) et « préférence » (sélection, par profil) est explicite.
- L'import d'un fichier dont le nom entre encollision renomme systématiquement avec un suffixe numérique et ne peut jamais écraser ; l'identifiant de la Variante est réécrit pour dériver du nom de fichier, afin qu'il n'existe pas deux vérités concurrentes.
- La persistance des préférences de sélection reste inchangée et demeure par profil ; seule la charge utile des thèmes est nouvelle.
