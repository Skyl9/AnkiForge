# Vision Globale et Cas d'Usage (AnkiForge)

## 1. Définition et Postulat de Base
AnkiForge est conçu comme un **environnement de développement intégré (IDE) et un compagnon de maintenance** pour l'écosystème Anki. 
* **Rôle strict :** Il ne remplace en aucun cas l'application Anki pour la phase de révision/apprentissage. C'est une plateforme d'ingénierie de la connaissance.
* **Flux déconnecté (Air-gapped) et Versionnement :** AnkiForge possède sa propre base de données isolée et ne communique pas en direct avec Anki. Le workflow repose sur un cycle d'import/export (`.apkg` / `.colpkg`). L'application intègre nativement une logique de **versionnement** basée sur les IDs uniques des cartes, ce qui permet de comparer et d'auditer l'historique de manière sécurisée sans corrompre la base Anki originale.

## 2. Philosophie de l'IA : Le Copilote Intentionnel
L'application rejette le paradigme de l'"IA boîte noire" qui générerait des milliers de cartes sans supervision.
* **Human-in-the-loop par défaut :** L'IA agit comme un copilote. Elle prépare le terrain (extraction, audit, reformulation), mais l'interface est pensée pour que l'utilisateur valide et affine le travail.
* **Bulk-Action :** Pour s'adapter aux volumes importants, une option de validation par lot ("Select All -> Valider") existe, mais elle ne sera jamais le comportement poussé par défaut.

## 3. Les Cas d'Usage Principaux (Les Vues de l'Application)
AnkiForge est une application polyvalente, prête à accueillir de nombreuses fonctionnalités réparties dans ses différents modules :

1. **Création & Pipelines (Génération de connaissances) :** Outils pour ingérer des sources documentaires (`documents_view.py`) ou multimédias et sculpter de nouvelles cartes efficacement avec l'assistance de l'IA au travers de pipelines automatisés (`creation_view.py`, `pipelines_view.py`).
2. **Analyse, Audit & Édition (Maintenance au long cours) :** Principalement pensé pour les *Power Users*. C'est ici que l'on diagnostique, reformule (Linter Wozniak) et fusionne (algorithme Levenshtein) les paquets chaotiques (`analysis_view.py`, `edition_view.py`). La philosophie centrale est la recherche de la **connaissance profonde** : l'application vise à réparer et sublimer le savoir, jamais à supprimer, enterrer ou archiver des cartes sous prétexte de superficialité.
3. **Modèles de Cartes (Customisation avancée et Stylisation) :** Un espace dédié au design et à l'ergonomie (`card_models_view.py`). Il permet de forger des **Modèles de cartes** complets. Il se distingue par une approche hybride :
   * *Édition manuelle (IDE) :* Accès brut au code (HTML/CSS/Jinja) pour créer et modifier les modèles avec un contrôle absolu.
   * *L'Inventaire de Styles :* Un répertoire de classes, de composants CSS et de templates pré-conçus. L'objectif n'est pas de faire du glisser-déposer basique, mais d'appliquer et de combiner ces styles sur un modèle. L'utilisateur peut ajouter ses propres styles à l'inventaire pour les réutiliser à l'infini et en faire de véritables templates dynamiques.

## 4. Utilisateurs Cibles et UX Adaptative
L'application s'adresse à un spectre allant de l'utilisateur cherchant la simplicité au puriste voulant une maîtrise totale de sa base de connaissance.
* **Évolutivité de l'Interface :** La conception UI/UX tire parti de la divulgation progressive. L'interface est simple à prendre en main pour les tâches d'usine, tout en déployant des options poussées pour satisfaire les exigences des power users dans l'Hôpital ou l'Atelier.
