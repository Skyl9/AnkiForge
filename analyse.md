# Analyse du Projet AnkiForge

Cette analyse propose des pistes d'amélioration pour renforcer la robustesse technique et enrichir l'expérience utilisateur de l'application.

# Partie Programmation

1.  **Refactoring de `EditionTab` (Décomposition en composants)**  
    Le fichier `src/ankiforge/ui/views/edition_view.py` dépasse les 1300 lignes. Il gère à la fois le filtrage, l'affichage des tableaux, l'édition des notes et l'exportation.  
    *   **Action :** Extraire des widgets autonomes comme `NoteTableWidget`, `NoteEditorWidget` et `FilterSidebar` pour améliorer la lisibilité et faciliter les tests unitaires de chaque partie.

2.  **Migration vers un système robuste (`peewee-migrate`)**  
    Le fichier `src/ankiforge/database/migration.py` utilise actuellement une logique de migration manuelle et séquentielle.  
    *   **Action :** Utiliser pleinement `peewee-migrate` (déjà présent dans les dépendances) pour gérer les migrations de manière déclarative, supportant ainsi les rollbacks et une meilleure gestion des schémas complexes.

3.  **Harmonisation du Typage et des Standards Python**  
    Le projet cible Python 3.12+, mais certaines configurations (Ruff/Mypy dans `pyproject.toml`) mentionnent encore 3.10. Certains imports comme `from mypy.types import Any` sont non-conventionnels.  
    *   **Action :** Mettre à jour la configuration `pyproject.toml` pour forcer 3.12. Remplacer les imports `mypy.types` par `typing`. Utiliser les nouveaux types de Python 3.12 (ex: `type` alias) pour plus de clarté.

4.  **Centralisation et Robustesse du Parsing AI**  
    La logique de nettoyage du JSON et de protection du LaTeX (`parse_ai_json_response` dans `utils.py`) est cruciale.  
    *   **Action :** Transformer cette logique en une classe `AIReponseParser` dédiée, permettant de définir des schémas de validation (via Pydantic ou des dataclasses) pour garantir que les données transmises aux workers sont toujours valides.

5.  **Internationalisation (i18n) et Nettoyage Linguistique**  
    Le code source mélange le français (`cloze_manager.py`) et l'anglais (`note_manager.py`).  
    *   **Action :** Passer l'intégralité du code (noms de variables, fichiers, logs internes) en anglais. Utiliser `Qt Linguist` (.ts/.qm) pour gérer proprement les traductions de l'interface utilisateur (Français/Anglais).

6.  **Gestion Asynchrone du Parsing de Documents (`Marker`)**  
    Le parsing via `Marker` est extrêmement lourd pour le CPU.  
    *   **Action :** Implémenter une véritable file d'attente (Task Queue) avec un `BackgroundDaemon` pour traiter les documents un par un en arrière-plan sans ralentir l'UI, avec une barre de progression globale.

# Partie feature

1.  **Synchronisation directe via AnkiConnect**  
    Actuellement, l'utilisateur doit exporter des fichiers `.apkg` manuellement.  
    *   **Action :** Ajouter une option pour synchroniser instantanément les cartes vers l'application Anki ouverte en utilisant l'API locale `AnkiConnect`.

2.  **Agent "Correcteur/Linter" de Flashcards**  
    Ajouter un mode où l'IA n'est pas créatrice mais critique.  
    *   **Action :** Analyser les cartes créées par l'utilisateur pour détecter les violations des "20 règles de formulation des connaissances" (ex: trop de texte, manque de contexte, ambiguïté).

3.  **Génération Automatique d'Images (Multimodal)**  
    Exploiter les capacités de vision de Gemini ou des modèles locaux.  
    *   **Action :** Proposer de générer ou d'extraire des schémas/images depuis le PDF source pour illustrer automatiquement les cartes (système d'ancrage visuel pour la mémoire).

4.  **Édition de Masse Assistée par IA (Batch Smart Edit)**  
    *   **Action :** Permettre de sélectionner plusieurs cartes dans la vue Edition et de leur appliquer une transformation IA (ex: "Traduire ces 50 cartes en espagnol", "Simplifier le langage", "Extraire les tags").

5.  **Omnibox : Passage à une Palette de Commandes**  
    L'Omnibox actuelle est une barre de recherche de contenu.  
    *   **Action :** La transformer en véritable palette de commandes (type VS Code / Obsidian) permettant de lancer des actions : "Nouveau Cours", "Passer en mode Sombre", "Vider le cache", etc.

6.  **Analyse Multi-Documents et Synthèse**  
    *   **Action :** Pouvoir "lier" plusieurs PDF à un même projet pour que l'IA puisse croiser les informations et éviter de générer des doublons si deux cours traitent du même sujet.

7.  **Visualisation Avancée des Statistiques**  
    *   **Action :** Ajouter des graphiques de répartition des types de cartes, de coût estimé cumulé par projet, et un "Heatmap" d'activité de génération.
