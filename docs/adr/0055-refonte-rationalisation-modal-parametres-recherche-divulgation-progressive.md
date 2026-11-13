# ADR 0055 : Refonte & Rationalisation du Modal de Paramètres (Recherche Instantanée, Divulgation Progressive & Enrichissement Métier)

- **Statut** : Accepté
- **Date** : 2026-11-04
- **Décideurs** : Équipe d'ingénierie AnkiForge & Tristan Rigaud-Humbert
- **Périmètre** : `src/ankidraft/ui/widgets/settings_modal/`, `SettingsModal`, tous les onglets (`tabs/`), moteur de recherche, persistance (`SettingsService` & `QSettings`).

---

## 1. Contexte & Problématique

La modale de paramètres (`SettingsModal`) centralise l'ensemble des réglages applicatifs d'AnkiForge à travers 9 onglets thématiques (`Général`, `Moteurs IA`, `Anki & Formats`, `Audio & TTS`, `Maintenance`, `Extensions`, `Soutien`, `Clavier`, `Aide & Guides`, plus `Développeur` en mode dev).

Avec l'évolution du produit, plusieurs limites ergonomiques et fonctionnelles sont apparues :
1. **Densité d'information et surcharge cognitive** : certains onglets mélangent sans hiérarchie des options usuelles (ex. dossier d'exportation, thème) et des réglages pointus ou d'infrastructure (ex. taille max anti zip-bomb, algorithme de compression zstd, token MCP, purge avancée).
2. **Absence de recherche textuelle globale** : un utilisateur cherchant un réglage précis (ex. "police markdown", "température", "timeout") doit inspecter séquentiellement plusieurs onglets.
3. **Lacunes sur des réglages clés du workflow quotidien** :
   - Personnalisation de l'éditeur Markdown (taille de police, retour à la ligne automatique, numérotation des lignes).
   - Paramètres globaux de génération IA (température par défaut, budget max de tokens, timeout de requête).
   - Comportement système (délai d'auto-sauvegarde, confirmation de fermeture, réouverture du dernier projet).
   - Audio & TTS (vitesse de lecture par défaut, voix par défaut par langue).

---

## 2. Décisions d'Architecture

### 2.1. Conservation de la Structure Repère (9 Onglets Thématiques)
L'arborescence des 9 onglets existants est strictement préservée pour maintenir les repères ergonomiques de l'utilisateur :
- `Général`
- `Moteurs IA`
- `Anki & Formats`
- `Audio & TTS`
- `Maintenance`
- `Extensions`
- `Soutien`
- `Clavier`
- `Aide & Guides`
- (`Développeur` conditionné par `is_development()`)

### 2.2. Divulgation Progressive via `CollapsibleSettingsGroup`
Pour réduire la charge cognitive sans restreindre le contrôle des power-users, un composant réutilisable conforme au Design System (`DESIGN.md`) est introduit :
- **Composant** : `CollapsibleSettingsGroup(title: str, parent: QWidget | None = None)`
- **Aspect visuel** : chevron Phosphor pivotant `ph.caret-right` (0° -> 90°), intitulé stylisé, badge discret indiquant le nombre d'options avancées masquées, bordure subtile.
- **Comportement** : replié par défaut. Les options niches (anti zip-bomb, compression zstd, configuration avancée MCP, purge time machine) sont déplacées dans ces accordéons au sein de leurs sections respectives.

### 2.3. Moteur de Recherche Instantanée & Vue Aplatie (`SettingsRegistry` & `SettingsSearchView`)
- **Barre de recherche intégrée** : un champ de saisie avec icône `ph.magnifying-glass` et raccourci clavier `Ctrl+F` est inséré en haut de la barre latérale des onglets.
- **Architecture de registre déclaratif (`SettingsRegistry`)** :
  - Pour préserver le principe de chargement différé (*lazy-loading*) des onglets et garantir une latence d'ouverture nulle (<1ms), un registre déclaratif indexe statiquement les métadonnées de chaque réglage :
    ```python
    @dataclass(frozen=True)
    class SettingDescriptor:
        key: str
        label: str
        description: str
        keywords: tuple[str, ...]
        tab_index: int
        section_name: str
        widget_attr: str
    ```
- **Vue aplatie de résultats** :
  - Dès 2 caractères saisis, le `QStackedWidget` bascule vers une vue de recherche aplatie façon macOS / JetBrains.
  - Chaque résultat affiche son fil d'Ariane (`Onglet > Section > Option`), une description contextuelle et une mise en évidence des termes recherchés.
  - La sélection d'un résultat active l'onglet cible (instancié à la volée si nécessaire), fait défiler la vue jusqu'au widget concerné, ouvre l'accordéon si l'option est dans un `CollapsibleSettingsGroup`, et applique une pulsation visuelle temporaire d'accentuation.
  - La touche `Échap` dans le champ efface la recherche et restaure l'onglet précédemment affiché.

### 2.4. Enrichissements Fonctionnels Prioritaires
Les nouveaux réglages suivants sont intégrés :
1. **Éditeur Markdown (Onglet Général)** :
   - Nouvelle section dédiée `ÉDITEUR & AFFICHAGE DE TEXTE` :
     - Taille de police en pt (`editor/font_size`, défaut 13pt).
     - Numérotation des lignes activable (`editor/line_numbers`, booléen, défaut True).
     - Retour à la ligne automatique (`editor/word_wrap`, booléen, défaut True).
2. **Paramètres Système (Onglet Général)** :
   - Confirmation à la fermeture si des modifications sont non exportées (`app/confirm_on_exit`, booléen).
   - Délai d'auto-sauvegarde en secondes (`app/autosave_interval_sec`, défaut 30s).
   - Réouverture automatique du dernier document au démarrage (`app/restore_last_project`, booléen).
3. **Moteurs IA (Onglet Moteurs IA)** :
   - Température par défaut (`ai/default_temperature`, float 0.0 à 1.0, pas de 0.05, défaut 0.3).
   - Budget max de tokens par requête (`ai/max_tokens_budget`, entier 500 à 16000, défaut 4000).
   - Timeout réseau des requêtes en secondes (`ai/request_timeout_sec`, défaut 60s).
4. **Audio & TTS (Onglet Audio & TTS)** :
   - Vitesse de lecture par défaut (`tts/default_speed`, float 0.5x à 2.0x, pas de 0.05, défaut 1.0x).
   - Voix par défaut par langue (FR, EN) persistées par profil.

### 2.5. Modèle de Persistance Hybride Conforme
L'isolation des données respecte l'architecture du projet :
- **Par Profil via `SettingsService` (SQLite)** : réglages spécifiques à l'espace de travail d'un profil (`editor/*`, `ai/*`, `tts/*`, formats et fusions Anki).
- **Global Application via `QSettings`** : réglages transversaux touchant au cycle de vie du processus (`profiles/*`, `feedback/*`, `app/confirm_on_exit`, `app/restore_last_project`).

---

## 3. Conséquences & Bénéfices

- **Ergonomie** : l'interface gagne en clarté immédiate grâce à la dissimulation des options ultra-pointues dans les accordéons, tout en offrant une recherche instantanée guidée par fil d'Ariane.
- **Performance & Parcimonie** : le registre déclaratif garantit que le lazy-loading des onglets reste actif, sans aucun surcoût au lancement du modal.
- **Productivité utilisateur** : l'accès direct aux réglages de police, d'IA par défaut et d'auto-sauvegarde comble les attentes opérationnelles des power-users.
