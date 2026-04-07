# Architecture du Code

AnkiForge est construit avec une architecture modulaire séparant clairement l'interface utilisateur, la logique métier et la persistance des données.

##  Structure des dossiers

- `src/ankiforge/database/` : Contient les modèles **Peewee** (ORM). C'est la seule couche autorisée à parler à la base de données SQLite.
- `src/ankiforge/ui/` : Contient les widgets et vues **PySide6**. Aucune requête réseau ni traitement lourd ne doit bloquer ces composants.
- `src/ankiforge/services/` : Le cœur de l'application (IA, Parsing PDF, Export Anki).
- `tests/` : Tous les tests unitaires gérés par **Pytest**, isolés via une base de données en RAM.

## Base de données (Peewee)
Nous utilisons **SQLite** couplé à l'ORM Peewee. 

**Règles de conception :**
* Toutes les relations utilisent `on_delete='CASCADE'` pour éviter les données orphelines (ex: supprimer un Paquet supprime ses Cartes).
* Les opérations lourdes d'écriture sont enveloppées dans des transactions (`db.atomic()`) pour garantir l'intégrité.

## Module C Natif (Performance)
Pour des raisons de performances, le calcul de la distance de Levenshtein (utilisé pour la détection de doublons de cartes) est codé via une extension C native.