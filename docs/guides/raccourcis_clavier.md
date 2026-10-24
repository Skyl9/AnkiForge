# Référence des Raccourcis Clavier ⌨️

<!-- ⚠️ DOCUMENT AUTO-GÉNÉRÉ DEPUIS src/ankiforge/ui/shortcuts/catalog.py - NE PAS MODIFIER MANUELLEMENT -->
<!-- Exécutez 'uv run python script/check_shortcuts_drift.py --fix' pour régénérer -->

Cette page constitue la **référence officielle et exhaustive** de l'ensemble des raccourcis clavier d'AnkiForge, issue du registre central déclaratif (`src/ankiforge/ui/shortcuts/`) conformément à l'**ADR 0032**.

> [!NOTE]
> Tous les raccourcis listés ci-dessous peuvent être visualisés, recherchés et personnalisés dans l'application via les **Paramètres (Ctrl+,) > onglet Clavier**.

---

## 🏛️ Architecture & Règles Clavier

1. **Hiérarchie stricte des portées (4 paliers)** :
    - **Dialogue** : priorité absolue lors d'une boîte de dialogue modale ouverte.
    - **Widget** : actif uniquement lorsque le composant spécifique (table, liste, canvas) a le focus.
    - **Vue** : actif dans la vue courante affichée du classeur principal.
    - **Application** : global à l'ensemble du logiciel (palette de commandes, navigation, paramètres).
2. **Priorité absolue à la saisie de texte** : lorsqu'un champ de saisie (`QLineEdit`, `QTextEdit`, KaTeX) a le focus, les touches nues et commandes d'édition ne déclenchent jamais d'action de carte intempestive.
3. **Séquences protégées** : les raccourcis système indispensables (`Ctrl+C`, `Ctrl+V`, `Ctrl+Z`, `Ctrl+A`, `Ctrl+W`, `Ctrl+Q`) ne sont pas réassignables pour prévenir toute corruption ergonomique.

---

## 📋 Inventaire des Raccourcis (98 actions)

### Application

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Palette de commandes** | <kbd>Ctrl+K</kbd> | `Application` | Ouvre la palette de commandes globale omnibox | `app.command_palette` |
| **Paramètres** | <kbd>Ctrl+,</kbd> | `Application` | Ouvre la boîte de dialogue des paramètres | `app.settings` |
| **Enregistrer** | <kbd>Ctrl+S</kbd> | `Application` | Routeur unique d'enregistrement dans la vue active | `app.save` |
| **Action primaire de la vue** | <kbd>Ctrl+Return</kbd> | `Application` | Déclenche l'action principale de la vue active (génération, exécution) | `app.run_primary` |
| **Rechercher** | <kbd>Ctrl+F</kbd> | `Application` | Active le champ de recherche de la vue active | `app.find` |
| **Importer un paquet Anki (.apkg)** | <kbd>Ctrl+Shift+I</kbd> | `Application` | Ouvre l'assistant d'importation de collection ou de paquet | `app.import` |
| **Exporter des cartes Anki (.apkg)** | <kbd>Ctrl+Alt+E</kbd> | `Application` | Ouvre la boîte de dialogue d'export de cartes | `app.export` |
| **Visite guidée d'AnkiForge** | <kbd>F1</kbd> | `Application` | Lance la visite interactive des fonctionnalités | `app.tour` |
| **Historique des versions** | <kbd>Ctrl+H</kbd> | `Vue` | Affiche la machine à remonter le temps et les versions antérieures | `view.history` |

### Navigation

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Aller à la vue 1** | <kbd>Alt+1</kbd> | `Application` | — | `nav.view_1` |
| **Aller à la vue 2** | <kbd>Alt+2</kbd> | `Application` | — | `nav.view_2` |
| **Aller à la vue 3** | <kbd>Alt+3</kbd> | `Application` | — | `nav.view_3` |
| **Aller à la vue 4** | <kbd>Alt+4</kbd> | `Application` | — | `nav.view_4` |
| **Aller à la vue 5** | <kbd>Alt+5</kbd> | `Application` | — | `nav.view_5` |
| **Aller à la vue 6** | <kbd>Alt+6</kbd> | `Application` | — | `nav.view_6` |
| **Aller à la vue 7** | <kbd>Alt+7</kbd> | `Application` | — | `nav.view_7` |
| **Aller à la vue 8** | <kbd>Alt+8</kbd> | `Application` | — | `nav.view_8` |
| **Aller à la vue 9** | <kbd>Alt+9</kbd> | `Application` | — | `nav.view_9` |
| **Vue suivante** | <kbd>Ctrl+Tab</kbd> | `Application` | — | `nav.next_view` |
| **Vue précédente** | <kbd>Ctrl+Shift+Tab</kbd> | `Application` | — | `nav.prev_view` |

### Édition

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Déplacer vers un paquet…** | <kbd>Ctrl+D</kbd> | `Vue` | Déplace les cartes ou notes sélectionnées vers un autre paquet | `edition.move_to_deck` |
| **Nouveau paquet…** | <kbd>Ctrl+N</kbd> | `Vue` | Crée un nouveau paquet de cartes | `edition.new_deck` |
| **Tout décocher** | <kbd>Ctrl+Shift+A</kbd> | `Vue` | Décoche et désélectionne toutes les cartes de la vue | `edition.deselect_all` |
| **Éditer la note ciblée** | <kbd>Ctrl+E</kbd> | `Vue` | Active l'éditeur de champs pour la note sélectionnée | `edition.edit_note` |
| **Éditer la note ciblée (touche rapide)** | <kbd>E</kbd> *(touche nue)* | `Widget` | Active l'éditeur depuis la table des cartes | `edition.edit_note_bare` |
| **Changer le type de note…** | <kbd>Ctrl+Shift+M</kbd> | `Vue` | Modifie le type de note du lot sélectionné | `edition.change_model` |
| **Basculer Cartes / Notes** | <kbd>Ctrl+Alt+T</kbd> | `Vue` | Alterne l'affichage entre les cartes unitaires et les notes parentes | `edition.toggle_display_mode` |
| **Rechercher / remplacer ciblé…** | <kbd>Ctrl+Alt+F</kbd> | `Vue` | Ouvre l'édition groupée pré-armée sur Rechercher et Remplacer | `edition.find_replace` |
| **Supprimer la sélection** | <kbd>Ctrl+Delete</kbd> | `Vue` | Supprime définitivement les cartes ou notes sélectionnées | `edition.delete` |
| **Suspendre / réactiver** | <kbd>Ctrl+J</kbd> | `Vue` | Bascule l'état suspendu des cartes ou notes sélectionnées | `edition.suspend` |
| **Suspendre / réactiver (table)** | <kbd>!</kbd> *(touche nue)* | `Widget` | Bascule l'état suspendu depuis la table focalisée | `edition.suspend_bare` |
| **Édition groupée…** | <kbd>Ctrl+Shift+E</kbd> | `Vue` | Ouvre la boîte de dialogue d'édition groupée de cartes | `edition.group_edit` |
| **Afficher / Masquer l'aperçu** | <kbd>Ctrl+P</kbd> | `Vue` | Bascule le volet latéral d'aperçu de la carte | `edition.toggle_preview` |
| **Replier / déplier la liste des cartes** | <kbd>Ctrl+Shift+T</kbd> | `Vue` | Replie ou déplie le panneau tabulaire des cartes | `edition.toggle_table` |
| **Carte précédente** | <kbd>Alt+Up</kbd> | `Vue` | Sélectionne la carte précédente dans la table | `edition.prev_card` |
| **Carte suivante** | <kbd>Alt+Down</kbd> | `Vue` | Sélectionne la carte suivante dans la table | `edition.next_card` |
| **Aucun drapeau** | <kbd>Ctrl+0</kbd> | `Vue` | Retire tout drapeau des cartes sélectionnées | `edition.flag_0` |
| **Drapeau 1 (Rouge)** | <kbd>Ctrl+1</kbd> | `Vue` | — | `edition.flag_1` |
| **Drapeau 2 (Orange)** | <kbd>Ctrl+2</kbd> | `Vue` | — | `edition.flag_2` |
| **Drapeau 3 (Vert)** | <kbd>Ctrl+3</kbd> | `Vue` | — | `edition.flag_3` |
| **Drapeau 4 (Bleu)** | <kbd>Ctrl+4</kbd> | `Vue` | — | `edition.flag_4` |
| **Drapeau 5 (Rose)** | <kbd>Ctrl+5</kbd> | `Vue` | — | `edition.flag_5` |
| **Drapeau 6 (Turquoise)** | <kbd>Ctrl+6</kbd> | `Vue` | — | `edition.flag_6` |
| **Drapeau 7 (Violet)** | <kbd>Ctrl+7</kbd> | `Vue` | — | `edition.flag_7` |
| **Gras** | <kbd>Ctrl+B</kbd> | `Vue` | Applique la mise en gras au texte sélectionné | `edition.format_bold` |
| **Italique** | <kbd>Ctrl+I</kbd> | `Vue` | Applique l'italique au texte sélectionné | `edition.format_italic` |
| **Souligné** | <kbd>Ctrl+U</kbd> | `Vue` | Applique le soulignement au texte sélectionné | `edition.format_underline` |
| **Trou Cloze** | <kbd>Ctrl+Shift+C</kbd> | `Vue` | Insère une suppression masquée Anki | `edition.format_cloze` |
| **Formule KaTeX** | <kbd>Ctrl+M</kbd> | `Vue` | Insère un bloc ou une formule mathématique KaTeX | `edition.format_math` |
| **Code inline** | <kbd>Ctrl+K</kbd> | `Vue` | Enveloppe le texte sélectionné dans des balises de code | `edition.format_code` |

### Studio & Batch

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Nouvelle saisie** | <kbd>Ctrl+N</kbd> | `Vue` | Ouvre un nouvel onglet de saisie libre dans le Studio de Création | `creation.new_input` |
| **Composer le lot…** | <kbd>Ctrl+N</kbd> | `Vue` | Ouvre le dialogue de composition et de découpage de lot | `batch.compose` |
| **Valider la carte (Espace)** | <kbd>Space</kbd> *(touche nue)* | `Widget` | Marque la carte ciblée comme validée | `review.validate_space` |
| **Valider la carte (V)** | <kbd>V</kbd> *(touche nue)* | `Widget` | Marque la carte ciblée comme validée | `review.validate_v` |
| **Rejeter la carte (Suppr)** | <kbd>Delete</kbd> *(touche nue)* | `Widget` | Rejette la carte ciblée | `review.reject_delete` |
| **Rejeter la carte (Retour)** | <kbd>Backspace</kbd> *(touche nue)* | `Widget` | Rejette la carte ciblée | `review.reject_backspace` |
| **Rejeter la carte (R)** | <kbd>R</kbd> *(touche nue)* | `Widget` | Rejette la carte ciblée | `review.reject_r` |
| **Éditer la carte** | <kbd>E</kbd> *(touche nue)* | `Widget` | Active l'édition de la carte ciblée | `review.edit` |
| **Carte précédente** | <kbd>Alt+Left</kbd> | `Widget` | Sélectionne la carte précédente dans la table de revue | `review.prev_card` |
| **Carte suivante** | <kbd>Alt+Right</kbd> | `Widget` | Sélectionne la carte suivante dans la table de revue | `review.next_card` |
| **Tranche précédente** | <kbd>Alt+Up</kbd> | `Widget` | Bascule vers la tâche ou tranche précédente dans la revue du lot | `review.prev_task` |
| **Tranche suivante** | <kbd>Alt+Down</kbd> | `Widget` | Bascule vers la tâche ou tranche suivante dans la revue du lot | `review.next_task` |

### Documents

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Importer un document** | <kbd>Ctrl+O</kbd> | `Vue` | Ouvre l'explorateur pour importer un fichier ou cours | `documents.import_file` |
| **Nouvel album…** | <kbd>Ctrl+N</kbd> | `Vue` | Crée un nouvel album documentaire d'images | `documents.new_album` |
| **Délimiter la portée…** | <kbd>Ctrl+Alt+P</kbd> | `Vue` | Ouvre la boîte de délimitation de portée du document | `documents.delimit_scope` |
| **Vectoriser dans le RAG** | <kbd>Ctrl+Alt+R</kbd> | `Vue` | Lance l'indexation vectorielle du document actif pour la recherche sémantique | `documents.vectorize` |
| **Afficher / masquer la couverture** | <kbd>Ctrl+Alt+C</kbd> | `Vue` | Bascule l'affichage du panneau d'inspection de couverture et de structure | `documents.toggle_coverage` |

### Analyse & Audit

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Réindexer les sources** | <kbd>Ctrl+Alt+R</kbd> | `Vue` | Réindexe la matière ou le document ciblé dans l'analyse | `analysis.reindex` |
| **Aligner les sources** | <kbd>Ctrl+Alt+A</kbd> | `Vue` | Synchronise et aligne les cartes Anki aux sections sources | `analysis.align_sources` |
| **Forger le fragment ciblé** | <kbd>Ctrl+Alt+F</kbd> | `Vue` | Ouvre le Studio de Création sur la section orpheline ciblée | `analysis.forge_fragment` |

### Types de Note

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Nouveau type de note** | <kbd>Ctrl+N</kbd> | `Vue` | Crée un nouveau modèle de carte | `models.new_type` |
| **Dupliquer le type de note** | <kbd>Ctrl+Shift+D</kbd> | `Vue` | Duplique le modèle de carte actuellement sélectionné | `models.duplicate` |
| **Importer un type de note (JSON)…** | <kbd>Ctrl+Alt+O</kbd> | `Vue` | Importe une définition de type de note depuis un fichier JSON | `models.import_json` |
| **Exporter le type de note (JSON)…** | <kbd>Ctrl+Alt+E</kbd> | `Vue` | Exporte le modèle de carte sélectionné au format JSON | `models.export_json` |
| **Formater le document** | <kbd>Ctrl+Alt+L</kbd> | `Widget` | Réindente et nettoie le code HTML ou CSS dans l'éditeur | `code.format` |

### Pipelines & Agents

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Nouvel agent** | <kbd>Ctrl+N</kbd> | `Vue` | Crée un nouvel agent IA dans l'atelier | `agents.new` |
| **Dupliquer l'agent** | <kbd>Ctrl+Shift+D</kbd> | `Vue` | Clone l'agent IA sélectionné | `agents.duplicate` |
| **Nouveau pipeline** | <kbd>Ctrl+N</kbd> | `Vue` | Crée un nouveau pipeline DAG | `pipelines.new` |
| **Monter l'étape** | <kbd>Ctrl+Up</kbd> | `Vue` | Déplace l'étape sélectionnée vers le haut dans le DAG | `pipelines.move_step_up` |
| **Descendre l'étape** | <kbd>Ctrl+Down</kbd> | `Vue` | Déplace l'étape sélectionnée vers le bas dans le DAG | `pipelines.move_step_down` |
| **Supprimer l'étape ciblée** | <kbd>Delete</kbd> *(touche nue)* | `Widget` | Supprime l'étape actuellement sélectionnée dans le workflow | `pipelines.delete_step` |

### Laboratoire A/B

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Échantillon A précédent** | <kbd>Alt+Up</kbd> | `Vue` | Affiche la carte précédente générée par la branche A | `ab.sample_a_prev` |
| **Échantillon A suivant** | <kbd>Alt+Down</kbd> | `Vue` | Affiche la carte suivante générée par la branche A | `ab.sample_a_next` |
| **Échantillon B précédent** | <kbd>Alt+Left</kbd> | `Vue` | Affiche la carte précédente générée par la branche B | `ab.sample_b_prev` |
| **Échantillon B suivant** | <kbd>Alt+Right</kbd> | `Vue` | Affiche la carte suivante générée par la branche B | `ab.sample_b_next` |

### Smart Merge

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Conflit précédent** | <kbd>Alt+Left</kbd> | `Dialogue` | Navigue vers le conflit d'importation précédent | `merge.prev_conflict` |
| **Conflit suivant** | <kbd>Alt+Right</kbd> | `Dialogue` | Navigue vers le conflit d'importation suivant | `merge.next_conflict` |
| **Tout garder Local** | <kbd>Ctrl+Alt+Left</kbd> | `Dialogue` | Conserve toutes les valeurs locales de la carte en conflit | `merge.keep_all_local` |
| **Tout garder Entrant** | <kbd>Ctrl+Alt+Right</kbd> | `Dialogue` | Remplace toutes les valeurs par la version entrante | `merge.keep_all_incoming` |
| **Valider la fusion** | <kbd>Ctrl+Return</kbd> | `Dialogue` | Valide les arbitrages et applique la fusion | `merge.confirm` |

### Outillage & Debug

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Capture d'écran debug** | <kbd>Ctrl+F12</kbd> | `Application` | Enregistre un instantané de l'interface pour diagnostic | `app.debug_screenshot` |
| **Galerie des dialogues (Dev)** | <kbd>Ctrl+Alt+D</kbd> | `Application` | Affiche la vitrine des boîtes de dialogue en mode développement | `app.debug_gallery` |

### Dialogues

| Action | Séquence par défaut | Portée | Description | Identifiant |
| :--- | :--- | :--- | :--- | :--- |
| **Fermer la boîte de dialogue** | <kbd>Escape</kbd> | `Dialogue` | Ferme la boîte de dialogue active sans valider | `dialog.close` |
| **Valider la boîte de dialogue** | <kbd>Return</kbd> | `Dialogue` | Confirme et valide la sélection de la boîte de dialogue | `dialog.confirm` |
| **Appliquer les modifications** | <kbd>Ctrl+Return</kbd> | `Dialogue` | Valide ou applique les modifications sans fermer la boîte de dialogue | `dialog.apply` |
| **Nouveau paquet** | <kbd>Ctrl+N</kbd> | `Dialogue` | Ouvre la création d'un nouveau paquet dans le sélecteur | `dialog.new_deck` |
| **Élément précédent** | <kbd>Up</kbd> *(touche nue)* | `Widget` | Sélectionne l'élément précédent dans la liste du dialogue | `dialog.prev_item` |
| **Élément suivant** | <kbd>Down</kbd> *(touche nue)* | `Widget` | Sélectionne l'élément suivant dans la liste du dialogue | `dialog.next_item` |
