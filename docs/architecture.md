# Architecture Technique d'AnkiForge 🏗️

AnkiForge repose sur une architecture robuste et modulaire, conçue pour la performance et la fiabilité. Le projet suit un pattern **MVC (Modèle-Vue-Contrôleur)** strict pour séparer la logique métier de l'interface utilisateur.

## Le Pattern MVC

1.  **Modèle (Database)** : Utilise l'ORM **Peewee** avec SQLite. Cette couche gère la persistance des cartes, des documents, des configurations IA et de l'historique des versions.
2.  **Vue (UI)** : Construite avec **PySide6** (Qt pour Python). L'interface est découpée en vues indépendantes et widgets réutilisables, centralisés dans `src/ankiforge/ui/`.
3.  **Contrôleur (Services/Workers)** : Les services (`src/ankiforge/services/`) orchestrent la logique complexe (IA, parsing, exports), tandis que les Workers (`QThread`) assurent la fluidité de l'UI en déportant les calculs lourds.

## Fluidité et Multithreading

L'interface graphique ne bloque jamais. Chaque opération lourde (génération de cartes, parsing de PDF volumineux) est exécutée dans un `QThread` dédié.

*   **Workers UI** : Gèrent les tâches éphémères déclenchées par l'utilisateur.
*   **BackgroundDaemon** : Un démon de fond ("La Forge Immortelle") qui scanne en permanence la file d'attente des travaux en base de données pour exécuter les tâches asynchrones, même après un redémarrage de l'application.

## Extension C (Levenshtein)

Pour la détection de doublons et le calcul de similarité entre les cartes, AnkiForge utilise une extension native en **C**. Cela permet de traiter des milliers de comparaisons en quelques millisecondes, là où une implémentation Python pure serait un goulot d'étranglement.

## Gestion des Médias et Documents

*   **Marker** : Moteur de Deep Learning utilisé pour convertir les PDF en Markdown structuré avec extraction d'images.
*   **Trafilatura** : Utilisé pour le scraping web "propre" (boilerplate removal).
*   **MediaManager** : Centralise le stockage des images dans le dossier utilisateur et garantit l'intégrité des liens HTML dans les flashcards.
