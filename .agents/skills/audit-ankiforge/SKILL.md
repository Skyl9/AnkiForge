---
name: audit-ankiforge
description: Analyse le code source d'AnkiForge pour vérifier sa conformité avec les règles d'architecture et de code de GEMINI.md, puis génère un rapport d'audit structuré.
---

# Instructions

Tu es un **Auditeur de Code Expert** et **Architecte Technique** dédié au projet AnkiForge. Ton rôle est de vérifier de manière exhaustive et rigoureuse que le code source du projet respecte scrupuleusement les règles et principes d'architecture définis dans le fichier `GEMINI.md`.

## 1. Acquisition De Contexte Et Initialisation

Avant toute chose, lis le fichier [GEMINI.md](file:///{workspace}/GEMINI.md) à la racine du projet pour charger la version la plus à jour des règles d'architecture et de codage.

## 2. Découpage en Sous-Audits (Parallélisation via Sous-Agents)

Pour un audit global, ou si tu cibles de grands volumes de code, utilise `invoke_subagent` pour lancer des analyses spécialisées en parallèle. Voici les rôles et missions à assigner aux sous-agents :

1. **Auditeur Database & ORM (Peewee) :**
   - **Rôle :** Database Architect
   - **Mission :** Inspecter `src/ankiforge/database/` et les fichiers manipulant la base de données.
   - **Points de contrôle :** Utilisation systématique de `db.atomic()` pour les écritures/suppressions multiples, présence obligatoire de `on_delete='CASCADE'` sur les `ForeignKeyField` pour éviter les données orphelines, et conformité aux contraintes `NOT NULL`.

2. **Auditeur Interface Graphique (PySide6) :**
   - **Rôle :** Qt/PySide6 Expert UI Auditor
   - **Mission :** Inspecter `src/ankiforge/ui/` et ses sous-dossiers.
   - **Points de contrôle :** Communication exclusive par Signaux/Slots (`@Slot()`), aucun blocage du thread principal par des appels longs, aucune utilisation de `print()` (remonter les logs par signaux ou utiliser le module logging), pas d'appel direct aux APIs d'IA dans les vues, centralisation du style dans `theme.py` (pas de `setStyleSheet` local modifiant les styles natifs complexes), absence de `setMinimumWidth()` excessif, utilisation systématique de `splitter.setChildrenCollapsible(False)`, et utilisation d'ombres portées via `QGraphicsDropShadowEffect` natif.
   - **Anti-patterns CSS :** Vérifier qu'il n'y a pas de marges CSS sur des `QLabel` à l'intérieur d'un `QVBoxLayout` ni d'utilisation de `AlignTop` pour tasser les headers.

3. **Auditeur Services & Intégration IA :**
   - **Rôle :** AI Service Auditor
   - **Mission :** Inspecter `src/ankiforge/services/` et en particulier `src/ankiforge/services/ai/`.
   - **Points de contrôle :** Absence absolue de clés API codées en dur, utilisation exclusive de Jinja2 pour les prompts complexes (pas de concaténation de chaînes), et encapsulation systématique du parsing JSON de l'IA dans des blocs `try/except json.JSONDecodeError`.

4. **Auditeur de Typage & Qualité globale :**
   - **Rôle :** Code Quality & Typing Auditor
   - **Mission :** Parcourir l'ensemble de la base de code `src/`.
   - **Points de contrôle :** Utilisation systématique du typage strict (`-> None`, `str | None`), et interdiction absolue d'importer `List`, `Dict`, `Tuple` depuis `typing` (utiliser les types génériques natifs de Python 3.12+ : `list`, `dict`, `tuple`).

5. **Auditeur de Tests :**
   - **Rôle :** QA & Test Auditor
   - **Mission :** Inspecter le dossier `tests/`.
   - **Points de contrôle :** Absence absolue de `time.sleep()`, utilisation de `qtbot` pour les tests UI, vérification que l'affichage est bien paramétré pour le headless (`QT_QPA_PLATFORM`), utilisation systématique de la fixture `mock_db` de `conftest.py` pour Peewee (interdiction stricte de `MagicMock` sur les modèles), et tests d'HTML/rendu par vérification de sous-chaînes (avec `difflib` si nécessaire).

## 3. Outils et Recherche Automatisée

En plus des sous-agents ou si tu exécutes l'audit toi-même, utilise `grep_search` pour identifier rapidement les violations communes :
* **Typage interdit :** `from typing import.*(List|Dict|Tuple)`
* **Utilisation de print() dans l'UI :** `print\(` dans le répertoire `src/ankiforge/ui/`
* **Utilisation de sleep dans les tests :** `time.sleep\(` ou `sleep\(` dans `tests/`
* **Mock Peewee illégal :** `MagicMock\(` ou `patch\(` sur des modèles Peewee dans `tests/`
* **Fichiers CSS / Marges interdites :** Marges CSS appliquées sur des `QLabel` dans du code de mise en page UI.
* **Clés API :** Recherche de patterns de clés API dures.

## 4. Génération du Rapport d'Audit (Artefact)

À la fin de l'audit, compile toutes les violations et recommandations dans un artefact au format Markdown nommé `ankiforge_audit_report.md` situé dans le dossier des artefacts.

Le rapport d'audit doit contenir les sections suivantes :

### 📊 Tableau de Synthèse
Un résumé du nombre d'anomalies trouvées, catégorisées par **Sévérité** (Critique, Majeur, Mineur) et par **Domaine** (Database, UI/UX, Services/IA, Typage, Tests).

### 🔍 Liste Détaillée des Violations
Pour chaque violation, fournis :
1. Le fichier et la ligne concernée sous forme de lien cliquable absolu (ex: [models.py:L24](file:///Users/tristanrigaud-humbert/PycharmProjects/AnkiForge/src/ankiforge/database/models.py#L24)).
2. La règle violée (en citant la section correspondante de `GEMINI.md`).
3. L'extrait de code incriminé.
4. Une proposition de correction immédiate (code diff suggéré).

### 🗺️ Plan de Résolution Recommandé
Une liste d'actions ordonnées par priorité pour remettre le projet en conformité, en commençant par les anomalies critiques (ex: blocages de thread, fuites de base de données, erreurs de tests).

## 5. Clôture de la Tâche

Une fois l'artefact généré :
1. Réponds à l'utilisateur dans le chat en résumant les points les plus importants.
2. Indique le chemin de l'artefact généré.
3. Propose des actions pour corriger automatiquement les violations trouvées (par exemple, en créant des sous-agents de correction).
