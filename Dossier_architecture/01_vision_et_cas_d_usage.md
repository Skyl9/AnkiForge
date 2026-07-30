# Vision Globale et Cas d'Usage (AnkiForge)

## 1. Définition et Postulat de Base
AnkiForge est conçu comme un **environnement de développement intégré (IDE) et un compagnon de maintenance** pour l'écosystème Anki. 
* **Rôle strict :** Il ne remplace en aucun cas l'application Anki pour la phase de révision/apprentissage. C'est une plateforme d'ingénierie de la connaissance.
* **Flux déconnecté (Air-gapped) et Versionnement :** AnkiForge possède sa propre base de données isolée et ne communique pas en direct avec Anki. Le workflow repose sur un cycle d'import/export (`.apkg` / `.colpkg`). L'application intègre nativement une logique de **versionnement** basée sur les IDs uniques des cartes, ce qui permet de comparer et d'auditer l'historique de manière sécurisée sans corrompre la base Anki originale.

## 2. Philosophie de l'IA : Le Copilote Intentionnel
L'application rejette le paradigme de l'"IA boîte noire" qui générerait des milliers de cartes sans supervision.
* **Human-in-the-loop par défaut :** L'IA agit comme un copilote. Elle prépare le terrain (extraction, audit, reformulation), mais l'interface est pensée pour que l'utilisateur valide et affine le travail.
* **Bulk-Action :** Pour s'adapter aux volumes importants, une option de validation par lot ("Select All -> Valider") existe, mais elle ne sera jamais le comportement poussé par défaut.

## 3. Les Trois Piliers (Cas d'usage principaux)
AnkiForge est une application polyvalente, prête à accueillir de nombreuses fonctionnalités autour de trois grands pôles :

1. **L'Usine (Création ex nihilo) :** La chaîne de production. Outils pour ingérer des sources documentaires ou multimédias et sculpter de nouvelles cartes efficacement avec l'assistance de l'IA.
2. **L'Hôpital (Maintenance au long cours) :** Principalement pensé pour les *Power Users*. C'est ici que l'on diagnostique, reformule (Linter Wozniak) et fusionne (algorithme Levenshtein) les vieux paquets chaotiques. La philosophie centrale est la recherche de la **connaissance profonde** : l'application vise à réparer et sublimer le savoir, jamais à supprimer, enterrer ou archiver des cartes sous prétexte de superficialité.
3. **L'Atelier de Modèles (Dualité IDE / No-Code) :** Un espace dédié au design et à l'ergonomie des cartes. Il se distingue par une approche hybride :
   * *Mode IDE :* Accès brut au code (HTML/CSS, etc.) pour un contrôle total.
   * *Mode No-Code :* Un **inventaire de composants** (et non une simple boutique) où l'utilisateur peut piocher des éléments visuels et structurels réutilisables pour assembler ses cartes confortablement sans coder.

## 4. Utilisateurs Cibles et UX Adaptative
L'application s'adresse à un spectre allant de l'utilisateur cherchant la simplicité au puriste voulant une maîtrise totale de sa base de connaissance.
* **Évolutivité de l'Interface :** La conception UI/UX devra tirer parti de la divulgation progressive. L'interface doit être simple à prendre en main pour les tâches d'usine, tout en déployant des options poussées (et potentiellement des "styles" d'UI distincts à terme) pour satisfaire les exigences des power users dans l'Hôpital ou l'Atelier.
