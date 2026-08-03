# Architecture Technique & Dépendances (AnkiForge)

## 1. Stack Fondamentale et Gestion des Dépendances
* **Interface & ORM :** L'application est un exécutable de bureau natif (PySide6) couplé à une base de données locale (SQLite) gérée par `peewee`. L'évolution du schéma de la BDD est sécurisée par `peewee_migrate`.
* **Gestionnaire de dépendances :** L'écosystème Python du projet est intégralement géré via **`uv`**, garantissant une résolution ultra-rapide et un environnement (`pyproject.toml`) reproductible de manière stricte.

## 2. Stratégie des Dépendances Lourdes (Lazy Loading Persistant)
Pour éviter qu'AnkiForge ne pèse plusieurs gigaoctets (à cause des bibliothèques de Machine Learning), l'architecture sépare le "Core" des "Extensions".
* **LLM Locaux :** L'application n'embarque aucune dépendance LLM lourde (`transformers`, `torch`). L'exécution locale s'appuie exclusivement sur des appels API vers un daemon externe (ex: **Ollama**), allégeant drastiquement le poids du logiciel.
* **Extraction & Outils lourds (ex: Marker, yt-dlp) :** Ils ne sont **pas** inclus dans le binaire par défaut. L'application intègre un système de *Lazy Installation* (Installation à la volée). Si l'utilisateur a besoin de convertir un PDF complexe via l'IA locale, AnkiForge télécharge et isole cet environnement (via `uv`) dans un dossier de données utilisateur persistant (à côté de la BDD SQLite).
* **Avantage :** Lors d'une mise à jour de l'application AnkiForge, l'utilisateur n'a pas à retélécharger ces dépendances massives, elles survivent aux cycles de release.

## 3. Compilation et Distribution (Nuitka)
L'application n'est pas distribuée sous forme de script Python pur, mais est compilée pour des performances maximales et une distribution simplifiée.
* **Compilateur :** Utilisation de **Nuitka**, qui traduit le code Python en C avant de le compiler. Cela offre un gain de vitesse notable et masque le code source.
* **CI/CD :** Le processus de compilation est automatisé via des **GitHub Actions** pour produire des exécutables pré-compilés.
* **Cross-Platform :** Bien que l'application soit principalement développée et ciblée pour **macOS** actuellement, l'architecture logicielle (chemins de fichiers, librairies) respecte scrupuleusement les standards multi-plateformes pour garantir un déploiement futur sans heurt sur Windows/PC.

## 4. Asynchronisme (La Règle du Zéro-Freeze)
AnkiForge impose une séparation stricte entre le thread de l'interface graphique (Main Thread) et la logique métier.
* **Workers (QThread / QRunnable) :** Toute opération susceptible de bloquer l'UI plus de 50ms (appels API, parsing, requêtes SQL complexes, calculs algorithmiques) est impérativement exécutée en arrière-plan. La communication avec l'UI se fait exclusivement via les Signaux/Slots de Qt.

## 5. Accélération Bas Niveau (Modules Natifs hybrides)
L'architecture intègre des modules natifs pour surmonter les goulots d'étranglement algorithmiques de Python sur les gros paquets.
* **Extensions C :** Les algorithmes critiques (comme la distance de Levenshtein pour la détection de doublons) sont écrits en C natif et compilés lors du build GitHub Actions.
* **Résilience (Fallback Python) :** Chaque module optimisé possède obligatoirement une implémentation pure Python de secours. Si le binaire dynamique échoue à charger sur une architecture spécifique, l'application bascule silencieusement sur le Python pur.
