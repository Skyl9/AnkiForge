"""Catalogue central déclaratif des raccourcis clavier d'AnkiForge.

Unique source de vérité pour tous les bindings, libellés et documentations.
Conforme à l'ADR 0013 (zéro tr() à l'import, résolution paresseuse) et à l'ADR 0032.
"""

from typing import Any

from ankiforge.ui.shortcuts.models import (
    ShortcutCategory,
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
    is_reserved_sequence,
)
from ankiforge.utils.i18n import tr


def build_shortcut_catalog() -> dict[ShortcutId, ShortcutDefinition]:
    """Construit et retourne le catalogue exhaustif déclaratif des raccourcis.

    Encapsulé dans une fonction pour garantir zéro évaluation de tr() au chargement du module.
    """
    return {
        # Actions d'application
        ShortcutId.APP_COMMAND_PALETTE: ShortcutDefinition(
            id=ShortcutId.APP_COMMAND_PALETTE,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+K",
            title_getter=lambda: tr("Palette de commandes"),
            description_getter=lambda: tr("Ouvre la palette de commandes globale omnibox"),
        ),
        ShortcutId.APP_SETTINGS: ShortcutDefinition(
            id=ShortcutId.APP_SETTINGS,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+,",
            title_getter=lambda: tr("Paramètres"),
            description_getter=lambda: tr("Ouvre la boîte de dialogue des paramètres"),
        ),
        ShortcutId.APP_SAVE: ShortcutDefinition(
            id=ShortcutId.APP_SAVE,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+S",
            title_getter=lambda: tr("Enregistrer"),
            description_getter=lambda: tr("Routeur unique d'enregistrement dans la vue active"),
        ),
        ShortcutId.APP_RUN_PRIMARY: ShortcutDefinition(
            id=ShortcutId.APP_RUN_PRIMARY,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Return",
            title_getter=lambda: tr("Action primaire de la vue"),
            description_getter=lambda: tr("Déclenche l'action principale de la vue active (génération, exécution)"),
        ),
        ShortcutId.APP_FIND: ShortcutDefinition(
            id=ShortcutId.APP_FIND,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+F",
            title_getter=lambda: tr("Rechercher"),
            description_getter=lambda: tr("Active le champ de recherche de la vue active"),
        ),
        ShortcutId.APP_IMPORT: ShortcutDefinition(
            id=ShortcutId.APP_IMPORT,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Shift+I",
            title_getter=lambda: tr("Importer un paquet Anki (.apkg)"),
            description_getter=lambda: tr("Ouvre l'assistant d'importation de collection ou de paquet"),
        ),
        ShortcutId.APP_EXPORT: ShortcutDefinition(
            id=ShortcutId.APP_EXPORT,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Alt+E",
            title_getter=lambda: tr("Exporter des cartes Anki (.apkg)"),
            description_getter=lambda: tr("Ouvre la boîte de dialogue d'export de cartes"),
        ),
        ShortcutId.APP_TOUR: ShortcutDefinition(
            id=ShortcutId.APP_TOUR,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="F1",
            title_getter=lambda: tr("Visite guidée d'AnkiForge"),
            description_getter=lambda: tr("Lance la visite interactive des fonctionnalités"),
        ),
        ShortcutId.APP_DEBUG_SCREENSHOT: ShortcutDefinition(
            id=ShortcutId.APP_DEBUG_SCREENSHOT,
            category=ShortcutCategory.OUTILLAGE,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+F12",
            title_getter=lambda: tr("Capture d'écran debug"),
            description_getter=lambda: tr("Enregistre un instantané de l'interface pour diagnostic"),
        ),
        ShortcutId.APP_DEBUG_GALLERY: ShortcutDefinition(
            id=ShortcutId.APP_DEBUG_GALLERY,
            category=ShortcutCategory.OUTILLAGE,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Alt+D",
            title_getter=lambda: tr("Galerie des dialogues (Dev)"),
            description_getter=lambda: tr("Affiche la vitrine des boîtes de dialogue en mode développement"),
        ),
        # Navigation entre les vues
        ShortcutId.NAV_VIEW_1: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_1,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+1",
            title_getter=lambda: tr("Aller à la vue 1"),
        ),
        ShortcutId.NAV_VIEW_2: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_2,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+2",
            title_getter=lambda: tr("Aller à la vue 2"),
        ),
        ShortcutId.NAV_VIEW_3: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_3,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+3",
            title_getter=lambda: tr("Aller à la vue 3"),
        ),
        ShortcutId.NAV_VIEW_4: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_4,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+4",
            title_getter=lambda: tr("Aller à la vue 4"),
        ),
        ShortcutId.NAV_VIEW_5: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_5,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+5",
            title_getter=lambda: tr("Aller à la vue 5"),
        ),
        ShortcutId.NAV_VIEW_6: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_6,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+6",
            title_getter=lambda: tr("Aller à la vue 6"),
        ),
        ShortcutId.NAV_VIEW_7: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_7,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+7",
            title_getter=lambda: tr("Aller à la vue 7"),
        ),
        ShortcutId.NAV_VIEW_8: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_8,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+8",
            title_getter=lambda: tr("Aller à la vue 8"),
        ),
        ShortcutId.NAV_VIEW_9: ShortcutDefinition(
            id=ShortcutId.NAV_VIEW_9,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Alt+9",
            title_getter=lambda: tr("Aller à la vue 9"),
        ),
        ShortcutId.NAV_NEXT_VIEW: ShortcutDefinition(
            id=ShortcutId.NAV_NEXT_VIEW,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Tab",
            title_getter=lambda: tr("Vue suivante"),
        ),
        ShortcutId.NAV_PREV_VIEW: ShortcutDefinition(
            id=ShortcutId.NAV_PREV_VIEW,
            category=ShortcutCategory.NAVIGATION,
            scope=ShortcutScope.APPLICATION,
            default_sequence="Ctrl+Shift+Tab",
            title_getter=lambda: tr("Vue précédente"),
        ),
        # Invariants transverses
        ShortcutId.VIEW_HISTORY: ShortcutDefinition(
            id=ShortcutId.VIEW_HISTORY,
            category=ShortcutCategory.APPLICATION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+H",
            title_getter=lambda: tr("Historique des versions"),
            description_getter=lambda: tr("Affiche la machine à remonter le temps et les versions antérieures"),
        ),
        # Actions Édition & Navigateur (T2)
        ShortcutId.EDITION_MOVE_TO_DECK: ShortcutDefinition(
            id=ShortcutId.EDITION_MOVE_TO_DECK,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+D",
            title_getter=lambda: tr("Déplacer vers un paquet…"),
            description_getter=lambda: tr("Déplace les cartes ou notes sélectionnées vers un autre paquet"),
        ),
        ShortcutId.EDITION_NEW_DECK: ShortcutDefinition(
            id=ShortcutId.EDITION_NEW_DECK,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouveau paquet…"),
            description_getter=lambda: tr("Crée un nouveau paquet de cartes"),
        ),
        ShortcutId.EDITION_DESELECT_ALL: ShortcutDefinition(
            id=ShortcutId.EDITION_DESELECT_ALL,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+A",
            title_getter=lambda: tr("Tout décocher"),
            description_getter=lambda: tr("Décoche et désélectionne toutes les cartes de la vue"),
        ),
        ShortcutId.EDITION_EDIT_NOTE: ShortcutDefinition(
            id=ShortcutId.EDITION_EDIT_NOTE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+E",
            title_getter=lambda: tr("Éditer la note ciblée"),
            description_getter=lambda: tr("Active l'éditeur de champs pour la note sélectionnée"),
        ),
        ShortcutId.EDITION_EDIT_NOTE_BARE: ShortcutDefinition(
            id=ShortcutId.EDITION_EDIT_NOTE_BARE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.WIDGET,
            default_sequence="E",
            allow_bare_key=True,
            title_getter=lambda: tr("Éditer la note ciblée (touche rapide)"),
            description_getter=lambda: tr("Active l'éditeur depuis la table des cartes"),
        ),
        ShortcutId.EDITION_CHANGE_MODEL: ShortcutDefinition(
            id=ShortcutId.EDITION_CHANGE_MODEL,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+M",
            title_getter=lambda: tr("Changer le type de note…"),
            description_getter=lambda: tr("Modifie le type de note du lot sélectionné"),
        ),
        ShortcutId.EDITION_TOGGLE_DISPLAY_MODE: ShortcutDefinition(
            id=ShortcutId.EDITION_TOGGLE_DISPLAY_MODE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+T",
            title_getter=lambda: tr("Basculer Cartes / Notes"),
            description_getter=lambda: tr("Alterne l'affichage entre les cartes unitaires et les notes parentes"),
        ),
        ShortcutId.EDITION_FIND_REPLACE: ShortcutDefinition(
            id=ShortcutId.EDITION_FIND_REPLACE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+F",
            title_getter=lambda: tr("Rechercher / remplacer ciblé…"),
            description_getter=lambda: tr("Ouvre l'édition groupée pré-armée sur Rechercher et Remplacer"),
        ),
        ShortcutId.EDITION_DELETE: ShortcutDefinition(
            id=ShortcutId.EDITION_DELETE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Delete",
            title_getter=lambda: tr("Supprimer la sélection"),
            description_getter=lambda: tr("Supprime définitivement les cartes ou notes sélectionnées"),
        ),
        ShortcutId.EDITION_SUSPEND: ShortcutDefinition(
            id=ShortcutId.EDITION_SUSPEND,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+J",
            title_getter=lambda: tr("Suspendre / réactiver"),
            description_getter=lambda: tr("Bascule l'état suspendu des cartes ou notes sélectionnées"),
        ),
        ShortcutId.EDITION_SUSPEND_BARE: ShortcutDefinition(
            id=ShortcutId.EDITION_SUSPEND_BARE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.WIDGET,
            default_sequence="!",
            allow_bare_key=True,
            title_getter=lambda: tr("Suspendre / réactiver (table)"),
            description_getter=lambda: tr("Bascule l'état suspendu depuis la table focalisée"),
        ),
        ShortcutId.EDITION_GROUP_EDIT: ShortcutDefinition(
            id=ShortcutId.EDITION_GROUP_EDIT,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+E",
            title_getter=lambda: tr("Édition groupée…"),
            description_getter=lambda: tr("Ouvre la boîte de dialogue d'édition groupée de cartes"),
        ),
        ShortcutId.EDITION_TOGGLE_PREVIEW: ShortcutDefinition(
            id=ShortcutId.EDITION_TOGGLE_PREVIEW,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+P",
            title_getter=lambda: tr("Afficher / Masquer l'aperçu"),
            description_getter=lambda: tr("Bascule le volet latéral d'aperçu de la carte"),
        ),
        ShortcutId.EDITION_TOGGLE_TABLE: ShortcutDefinition(
            id=ShortcutId.EDITION_TOGGLE_TABLE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+T",
            title_getter=lambda: tr("Replier / déplier la liste des cartes"),
            description_getter=lambda: tr("Replie ou déplie le panneau tabulaire des cartes"),
        ),
        ShortcutId.EDITION_PREV_CARD: ShortcutDefinition(
            id=ShortcutId.EDITION_PREV_CARD,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Alt+Up",
            title_getter=lambda: tr("Carte précédente"),
            description_getter=lambda: tr("Sélectionne la carte précédente dans la table"),
        ),
        ShortcutId.EDITION_NEXT_CARD: ShortcutDefinition(
            id=ShortcutId.EDITION_NEXT_CARD,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Alt+Down",
            title_getter=lambda: tr("Carte suivante"),
            description_getter=lambda: tr("Sélectionne la carte suivante dans la table"),
        ),
        ShortcutId.EDITION_FLAG_0: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_0,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+0",
            title_getter=lambda: tr("Aucun drapeau"),
            description_getter=lambda: tr("Retire tout drapeau des cartes sélectionnées"),
        ),
        ShortcutId.EDITION_FLAG_1: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_1,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+1",
            title_getter=lambda: tr("Drapeau 1 (Rouge)"),
        ),
        ShortcutId.EDITION_FLAG_2: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_2,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+2",
            title_getter=lambda: tr("Drapeau 2 (Orange)"),
        ),
        ShortcutId.EDITION_FLAG_3: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_3,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+3",
            title_getter=lambda: tr("Drapeau 3 (Vert)"),
        ),
        ShortcutId.EDITION_FLAG_4: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_4,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+4",
            title_getter=lambda: tr("Drapeau 4 (Bleu)"),
        ),
        ShortcutId.EDITION_FLAG_5: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_5,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+5",
            title_getter=lambda: tr("Drapeau 5 (Rose)"),
        ),
        ShortcutId.EDITION_FLAG_6: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_6,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+6",
            title_getter=lambda: tr("Drapeau 6 (Turquoise)"),
        ),
        ShortcutId.EDITION_FLAG_7: ShortcutDefinition(
            id=ShortcutId.EDITION_FLAG_7,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+7",
            title_getter=lambda: tr("Drapeau 7 (Violet)"),
        ),
        ShortcutId.EDITION_FORMAT_BOLD: ShortcutDefinition(
            id=ShortcutId.EDITION_FORMAT_BOLD,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+B",
            title_getter=lambda: tr("Gras"),
            description_getter=lambda: tr("Applique la mise en gras au texte sélectionné"),
        ),
        ShortcutId.EDITION_FORMAT_ITALIC: ShortcutDefinition(
            id=ShortcutId.EDITION_FORMAT_ITALIC,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+I",
            title_getter=lambda: tr("Italique"),
            description_getter=lambda: tr("Applique l'italique au texte sélectionné"),
        ),
        ShortcutId.EDITION_FORMAT_UNDERLINE: ShortcutDefinition(
            id=ShortcutId.EDITION_FORMAT_UNDERLINE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+U",
            title_getter=lambda: tr("Souligné"),
            description_getter=lambda: tr("Applique le soulignement au texte sélectionné"),
        ),
        ShortcutId.EDITION_FORMAT_CLOZE: ShortcutDefinition(
            id=ShortcutId.EDITION_FORMAT_CLOZE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+C",
            title_getter=lambda: tr("Trou Cloze"),
            description_getter=lambda: tr("Insère une suppression masquée Anki"),
        ),
        ShortcutId.EDITION_FORMAT_MATH: ShortcutDefinition(
            id=ShortcutId.EDITION_FORMAT_MATH,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+M",
            title_getter=lambda: tr("Formule KaTeX"),
            description_getter=lambda: tr("Insère un bloc ou une formule mathématique KaTeX"),
        ),
        # Studio de Création & Batch Factory (T3)
        ShortcutId.CREATION_NEW_INPUT: ShortcutDefinition(
            id=ShortcutId.CREATION_NEW_INPUT,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouvelle saisie"),
            description_getter=lambda: tr("Ouvre un nouvel onglet de saisie libre dans le Studio de Création"),
        ),
        ShortcutId.BATCH_COMPOSE: ShortcutDefinition(
            id=ShortcutId.BATCH_COMPOSE,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Composer le lot…"),
            description_getter=lambda: tr("Ouvre le dialogue de composition et de découpage de lot"),
        ),
        # Revue de cartes (Portée WIDGET partagée Studio & Batch)
        ShortcutId.REVIEW_VALIDATE_SPACE: ShortcutDefinition(
            id=ShortcutId.REVIEW_VALIDATE_SPACE,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Space",
            allow_bare_key=True,
            title_getter=lambda: tr("Valider la carte (Espace)"),
            description_getter=lambda: tr("Marque la carte ciblée comme validée"),
        ),
        ShortcutId.REVIEW_VALIDATE_V: ShortcutDefinition(
            id=ShortcutId.REVIEW_VALIDATE_V,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="V",
            allow_bare_key=True,
            title_getter=lambda: tr("Valider la carte (V)"),
            description_getter=lambda: tr("Marque la carte ciblée comme validée"),
        ),
        ShortcutId.REVIEW_REJECT_DELETE: ShortcutDefinition(
            id=ShortcutId.REVIEW_REJECT_DELETE,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Delete",
            allow_bare_key=True,
            title_getter=lambda: tr("Rejeter la carte (Suppr)"),
            description_getter=lambda: tr("Rejette la carte ciblée"),
        ),
        ShortcutId.REVIEW_REJECT_BACKSPACE: ShortcutDefinition(
            id=ShortcutId.REVIEW_REJECT_BACKSPACE,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Backspace",
            allow_bare_key=True,
            title_getter=lambda: tr("Rejeter la carte (Retour)"),
            description_getter=lambda: tr("Rejette la carte ciblée"),
        ),
        ShortcutId.REVIEW_REJECT_R: ShortcutDefinition(
            id=ShortcutId.REVIEW_REJECT_R,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="R",
            allow_bare_key=True,
            title_getter=lambda: tr("Rejeter la carte (R)"),
            description_getter=lambda: tr("Rejette la carte ciblée"),
        ),
        ShortcutId.REVIEW_EDIT: ShortcutDefinition(
            id=ShortcutId.REVIEW_EDIT,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="E",
            allow_bare_key=True,
            title_getter=lambda: tr("Éditer la carte"),
            description_getter=lambda: tr("Active l'édition de la carte ciblée"),
        ),
        ShortcutId.REVIEW_PREV_CARD: ShortcutDefinition(
            id=ShortcutId.REVIEW_PREV_CARD,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Alt+Left",
            title_getter=lambda: tr("Carte précédente"),
            description_getter=lambda: tr("Sélectionne la carte précédente dans la table de revue"),
        ),
        ShortcutId.REVIEW_NEXT_CARD: ShortcutDefinition(
            id=ShortcutId.REVIEW_NEXT_CARD,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Alt+Right",
            title_getter=lambda: tr("Carte suivante"),
            description_getter=lambda: tr("Sélectionne la carte suivante dans la table de revue"),
        ),
        ShortcutId.REVIEW_PREV_TASK: ShortcutDefinition(
            id=ShortcutId.REVIEW_PREV_TASK,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Alt+Up",
            title_getter=lambda: tr("Tranche précédente"),
            description_getter=lambda: tr("Bascule vers la tâche ou tranche précédente dans la revue du lot"),
        ),
        ShortcutId.REVIEW_NEXT_TASK: ShortcutDefinition(
            id=ShortcutId.REVIEW_NEXT_TASK,
            category=ShortcutCategory.STUDIO,
            scope=ShortcutScope.WIDGET,
            default_sequence="Alt+Down",
            title_getter=lambda: tr("Tranche suivante"),
            description_getter=lambda: tr("Bascule vers la tâche ou tranche suivante dans la revue du lot"),
        ),
        # Documents (T4)
        ShortcutId.DOCUMENTS_IMPORT_FILE: ShortcutDefinition(
            id=ShortcutId.DOCUMENTS_IMPORT_FILE,
            category=ShortcutCategory.DOCUMENTS,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+O",
            title_getter=lambda: tr("Importer un document"),
            description_getter=lambda: tr("Ouvre l'explorateur pour importer un fichier ou cours"),
        ),
        ShortcutId.DOCUMENTS_NEW_ALBUM: ShortcutDefinition(
            id=ShortcutId.DOCUMENTS_NEW_ALBUM,
            category=ShortcutCategory.DOCUMENTS,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouvel album…"),
            description_getter=lambda: tr("Crée un nouvel album documentaire d'images"),
        ),
        ShortcutId.DOCUMENTS_DELIMIT_SCOPE: ShortcutDefinition(
            id=ShortcutId.DOCUMENTS_DELIMIT_SCOPE,
            category=ShortcutCategory.DOCUMENTS,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+P",
            title_getter=lambda: tr("Délimiter la portée…"),
            description_getter=lambda: tr("Ouvre la boîte de délimitation de portée du document"),
        ),
        ShortcutId.DOCUMENTS_VECTORIZE: ShortcutDefinition(
            id=ShortcutId.DOCUMENTS_VECTORIZE,
            category=ShortcutCategory.DOCUMENTS,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+R",
            title_getter=lambda: tr("Vectoriser dans le RAG"),
            description_getter=lambda: tr("Lance l'indexation vectorielle du document actif pour la recherche sémantique"),
        ),
        ShortcutId.DOCUMENTS_TOGGLE_COVERAGE: ShortcutDefinition(
            id=ShortcutId.DOCUMENTS_TOGGLE_COVERAGE,
            category=ShortcutCategory.DOCUMENTS,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+C",
            title_getter=lambda: tr("Afficher / masquer la couverture"),
            description_getter=lambda: tr("Bascule l'affichage du panneau d'inspection de couverture et de structure"),
        ),
        # Analyse & Audit IA (T4)
        ShortcutId.ANALYSIS_REINDEX: ShortcutDefinition(
            id=ShortcutId.ANALYSIS_REINDEX,
            category=ShortcutCategory.ANALYSE,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+R",
            title_getter=lambda: tr("Réindexer les sources"),
            description_getter=lambda: tr("Réindexe la matière ou le document ciblé dans l'analyse"),
        ),
        ShortcutId.ANALYSIS_ALIGN_SOURCES: ShortcutDefinition(
            id=ShortcutId.ANALYSIS_ALIGN_SOURCES,
            category=ShortcutCategory.ANALYSE,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+A",
            title_getter=lambda: tr("Aligner les sources"),
            description_getter=lambda: tr("Synchronise et aligne les cartes Anki aux sections sources"),
        ),
        ShortcutId.ANALYSIS_FORGE_FRAGMENT: ShortcutDefinition(
            id=ShortcutId.ANALYSIS_FORGE_FRAGMENT,
            category=ShortcutCategory.ANALYSE,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+F",
            title_getter=lambda: tr("Forger le fragment ciblé"),
            description_getter=lambda: tr("Ouvre le Studio de Création sur la section orpheline ciblée"),
        ),
        # Modèles de cartes (T4)
        ShortcutId.MODELS_NEW_TYPE: ShortcutDefinition(
            id=ShortcutId.MODELS_NEW_TYPE,
            category=ShortcutCategory.MODELES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouveau type de note"),
            description_getter=lambda: tr("Crée un nouveau modèle de carte"),
        ),
        ShortcutId.MODELS_DUPLICATE: ShortcutDefinition(
            id=ShortcutId.MODELS_DUPLICATE,
            category=ShortcutCategory.MODELES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+D",
            title_getter=lambda: tr("Dupliquer le type de note"),
            description_getter=lambda: tr("Duplique le modèle de carte actuellement sélectionné"),
        ),
        ShortcutId.MODELS_IMPORT_JSON: ShortcutDefinition(
            id=ShortcutId.MODELS_IMPORT_JSON,
            category=ShortcutCategory.MODELES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+O",
            title_getter=lambda: tr("Importer un type de note (JSON)…"),
            description_getter=lambda: tr("Importe une définition de type de note depuis un fichier JSON"),
        ),
        ShortcutId.MODELS_EXPORT_JSON: ShortcutDefinition(
            id=ShortcutId.MODELS_EXPORT_JSON,
            category=ShortcutCategory.MODELES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+E",
            title_getter=lambda: tr("Exporter le type de note (JSON)…"),
            description_getter=lambda: tr("Exporte le modèle de carte sélectionné au format JSON"),
        ),
        # Agents IA (T5)
        ShortcutId.AGENTS_NEW: ShortcutDefinition(
            id=ShortcutId.AGENTS_NEW,
            category=ShortcutCategory.PIPELINES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouvel agent"),
            description_getter=lambda: tr("Crée un nouvel agent IA dans l'atelier"),
        ),
        ShortcutId.AGENTS_DUPLICATE: ShortcutDefinition(
            id=ShortcutId.AGENTS_DUPLICATE,
            category=ShortcutCategory.PIPELINES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Shift+D",
            title_getter=lambda: tr("Dupliquer l'agent"),
            description_getter=lambda: tr("Clone l'agent IA sélectionné"),
        ),
        # Pipelines DAG (T5)
        ShortcutId.PIPELINES_NEW: ShortcutDefinition(
            id=ShortcutId.PIPELINES_NEW,
            category=ShortcutCategory.PIPELINES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouveau pipeline"),
            description_getter=lambda: tr("Crée un nouveau pipeline DAG"),
        ),
        ShortcutId.PIPELINES_MOVE_STEP_UP: ShortcutDefinition(
            id=ShortcutId.PIPELINES_MOVE_STEP_UP,
            category=ShortcutCategory.PIPELINES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Up",
            title_getter=lambda: tr("Monter l'étape"),
            description_getter=lambda: tr("Déplace l'étape sélectionnée vers le haut dans le DAG"),
        ),
        ShortcutId.PIPELINES_MOVE_STEP_DOWN: ShortcutDefinition(
            id=ShortcutId.PIPELINES_MOVE_STEP_DOWN,
            category=ShortcutCategory.PIPELINES,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Down",
            title_getter=lambda: tr("Descendre l'étape"),
            description_getter=lambda: tr("Déplace l'étape sélectionnée vers le bas dans le DAG"),
        ),
        ShortcutId.PIPELINES_DELETE_STEP: ShortcutDefinition(
            id=ShortcutId.PIPELINES_DELETE_STEP,
            category=ShortcutCategory.PIPELINES,
            scope=ShortcutScope.WIDGET,
            default_sequence="Delete",
            allow_bare_key=True,
            title_getter=lambda: tr("Supprimer l'étape ciblée"),
            description_getter=lambda: tr("Supprime l'étape actuellement sélectionnée dans le workflow"),
        ),
        # Consultant IA (T5)
        ShortcutId.CONSULTANT_NEW_CHAT: ShortcutDefinition(
            id=ShortcutId.CONSULTANT_NEW_CHAT,
            category=ShortcutCategory.CONSULTANT,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouvelle discussion"),
            description_getter=lambda: tr("Démarre une nouvelle session de chat avec le consultant IA"),
        ),
        ShortcutId.CONSULTANT_EXPORT_SESSION: ShortcutDefinition(
            id=ShortcutId.CONSULTANT_EXPORT_SESSION,
            category=ShortcutCategory.CONSULTANT,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+E",
            title_getter=lambda: tr("Exporter la session"),
            description_getter=lambda: tr("Exporte l'historique de la discussion courante en Markdown"),
        ),
        ShortcutId.CONSULTANT_TOGGLE_SIDEBAR: ShortcutDefinition(
            id=ShortcutId.CONSULTANT_TOGGLE_SIDEBAR,
            category=ShortcutCategory.CONSULTANT,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+B",
            title_getter=lambda: tr("Barre latérale des sessions"),
            description_getter=lambda: tr("Affiche ou masque l'arborescence des discussions antérieures"),
        ),
        ShortcutId.CONSULTANT_TOGGLE_INSPECTOR: ShortcutDefinition(
            id=ShortcutId.CONSULTANT_TOGGLE_INSPECTOR,
            category=ShortcutCategory.CONSULTANT,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+Alt+I",
            title_getter=lambda: tr("Inspecteur d'activité"),
            description_getter=lambda: tr("Affiche ou masque le volet d'inspection MCP et télémétrie"),
        ),
        # Laboratoire A/B (T5)
        ShortcutId.AB_SAMPLE_A_PREV: ShortcutDefinition(
            id=ShortcutId.AB_SAMPLE_A_PREV,
            category=ShortcutCategory.AB_TEST,
            scope=ShortcutScope.VUE,
            default_sequence="Alt+Up",
            title_getter=lambda: tr("Échantillon A précédent"),
            description_getter=lambda: tr("Affiche la carte précédente générée par la branche A"),
        ),
        ShortcutId.AB_SAMPLE_A_NEXT: ShortcutDefinition(
            id=ShortcutId.AB_SAMPLE_A_NEXT,
            category=ShortcutCategory.AB_TEST,
            scope=ShortcutScope.VUE,
            default_sequence="Alt+Down",
            title_getter=lambda: tr("Échantillon A suivant"),
            description_getter=lambda: tr("Affiche la carte suivante générée par la branche A"),
        ),
        ShortcutId.AB_SAMPLE_B_PREV: ShortcutDefinition(
            id=ShortcutId.AB_SAMPLE_B_PREV,
            category=ShortcutCategory.AB_TEST,
            scope=ShortcutScope.VUE,
            default_sequence="Alt+Left",
            title_getter=lambda: tr("Échantillon B précédent"),
            description_getter=lambda: tr("Affiche la carte précédente générée par la branche B"),
        ),
        ShortcutId.AB_SAMPLE_B_NEXT: ShortcutDefinition(
            id=ShortcutId.AB_SAMPLE_B_NEXT,
            category=ShortcutCategory.AB_TEST,
            scope=ShortcutScope.VUE,
            default_sequence="Alt+Right",
            title_getter=lambda: tr("Échantillon B suivant"),
            description_getter=lambda: tr("Affiche la carte suivante générée par la branche B"),
        ),
        # Smart Merge (T5)
        ShortcutId.MERGE_PREV_CONFLICT: ShortcutDefinition(
            id=ShortcutId.MERGE_PREV_CONFLICT,
            category=ShortcutCategory.MERGE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Alt+Left",
            title_getter=lambda: tr("Conflit précédent"),
            description_getter=lambda: tr("Navigue vers le conflit d'importation précédent"),
        ),
        ShortcutId.MERGE_NEXT_CONFLICT: ShortcutDefinition(
            id=ShortcutId.MERGE_NEXT_CONFLICT,
            category=ShortcutCategory.MERGE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Alt+Right",
            title_getter=lambda: tr("Conflit suivant"),
            description_getter=lambda: tr("Navigue vers le conflit d'importation suivant"),
        ),
        ShortcutId.MERGE_KEEP_ALL_LOCAL: ShortcutDefinition(
            id=ShortcutId.MERGE_KEEP_ALL_LOCAL,
            category=ShortcutCategory.MERGE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Ctrl+Alt+Left",
            title_getter=lambda: tr("Tout garder Local"),
            description_getter=lambda: tr("Conserve toutes les valeurs locales de la carte en conflit"),
        ),
        ShortcutId.MERGE_KEEP_ALL_INCOMING: ShortcutDefinition(
            id=ShortcutId.MERGE_KEEP_ALL_INCOMING,
            category=ShortcutCategory.MERGE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Ctrl+Alt+Right",
            title_getter=lambda: tr("Tout garder Entrant"),
            description_getter=lambda: tr("Remplace toutes les valeurs par la version entrante"),
        ),
        ShortcutId.MERGE_CONFIRM: ShortcutDefinition(
            id=ShortcutId.MERGE_CONFIRM,
            category=ShortcutCategory.MERGE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Ctrl+Return",
            title_getter=lambda: tr("Valider la fusion"),
            description_getter=lambda: tr("Valide les arbitrages et applique la fusion"),
        ),
        # Dialogues modaux & Sélecteurs (T6)
        ShortcutId.DIALOG_CLOSE: ShortcutDefinition(
            id=ShortcutId.DIALOG_CLOSE,
            category=ShortcutCategory.DIALOGUE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Escape",
            title_getter=lambda: tr("Fermer la boîte de dialogue"),
            description_getter=lambda: tr("Ferme la boîte de dialogue active sans valider"),
        ),
        ShortcutId.DIALOG_CONFIRM: ShortcutDefinition(
            id=ShortcutId.DIALOG_CONFIRM,
            category=ShortcutCategory.DIALOGUE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Return",
            title_getter=lambda: tr("Valider la boîte de dialogue"),
            description_getter=lambda: tr("Confirme et valide la sélection de la boîte de dialogue"),
        ),
        ShortcutId.DIALOG_APPLY: ShortcutDefinition(
            id=ShortcutId.DIALOG_APPLY,
            category=ShortcutCategory.DIALOGUE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Ctrl+Return",
            title_getter=lambda: tr("Appliquer les modifications"),
            description_getter=lambda: tr("Valide ou applique les modifications sans fermer la boîte de dialogue"),
        ),
        ShortcutId.DIALOG_NEW_DECK: ShortcutDefinition(
            id=ShortcutId.DIALOG_NEW_DECK,
            category=ShortcutCategory.DIALOGUE,
            scope=ShortcutScope.DIALOGUE,
            default_sequence="Ctrl+N",
            title_getter=lambda: tr("Nouveau paquet"),
            description_getter=lambda: tr("Ouvre la création d'un nouveau paquet dans le sélecteur"),
        ),
        ShortcutId.DIALOG_PREV_ITEM: ShortcutDefinition(
            id=ShortcutId.DIALOG_PREV_ITEM,
            category=ShortcutCategory.DIALOGUE,
            scope=ShortcutScope.WIDGET,
            default_sequence="Up",
            allow_bare_key=True,
            title_getter=lambda: tr("Élément précédent"),
            description_getter=lambda: tr("Sélectionne l'élément précédent dans la liste du dialogue"),
        ),
        ShortcutId.DIALOG_NEXT_ITEM: ShortcutDefinition(
            id=ShortcutId.DIALOG_NEXT_ITEM,
            category=ShortcutCategory.DIALOGUE,
            scope=ShortcutScope.WIDGET,
            default_sequence="Down",
            allow_bare_key=True,
            title_getter=lambda: tr("Élément suivant"),
            description_getter=lambda: tr("Sélectionne l'élément suivant dans la liste du dialogue"),
        ),
        # Édition & Formatage inline (T6)
        ShortcutId.EDITION_FORMAT_CODE: ShortcutDefinition(
            id=ShortcutId.EDITION_FORMAT_CODE,
            category=ShortcutCategory.EDITION,
            scope=ShortcutScope.VUE,
            default_sequence="Ctrl+K",
            title_getter=lambda: tr("Code inline"),
            description_getter=lambda: tr("Enveloppe le texte sélectionné dans des balises de code"),
        ),
        # Modèles de cartes & Éditeur de code (T6)
        ShortcutId.CODE_FORMAT: ShortcutDefinition(
            id=ShortcutId.CODE_FORMAT,
            category=ShortcutCategory.MODELES,
            scope=ShortcutScope.WIDGET,
            default_sequence="Ctrl+Alt+L",
            title_getter=lambda: tr("Formater le document"),
            description_getter=lambda: tr("Réindente et nettoie le code HTML ou CSS dans l'éditeur"),
        ),
    }


_catalog_cache: dict[ShortcutId, ShortcutDefinition] | None = None


def get_shortcut_catalog() -> dict[ShortcutId, ShortcutDefinition]:
    """Renvoie le catalogue central des raccourcis clavier déclaratifs."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = build_shortcut_catalog()
    return _catalog_cache


def __getattr__(name: str) -> Any:
    """Accès paresseux à SHORTCUT_CATALOG pour éviter tout appel tr() au chargement de module."""
    if name == "SHORTCUT_CATALOG":
        return get_shortcut_catalog()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def get_shortcut_definition(shortcut_id: ShortcutId) -> ShortcutDefinition:
    """Récupère la définition immuable d'un raccourci dans le catalogue."""
    catalog = get_shortcut_catalog()
    try:
        return catalog[shortcut_id]
    except KeyError:
        raise KeyError(f"Identifiant de raccourci non répertorié au catalogue : {shortcut_id}") from None


def get_shortcut_sequence(shortcut_id: ShortcutId, settings_service: Any = None) -> str:
    """Récupère la séquence effective d'un raccourci (en tenant compte d'une éventuelle surcharge)."""
    if settings_service is not None and hasattr(settings_service, "get_shortcut_override"):
        override = settings_service.get_shortcut_override(shortcut_id.value)
        if isinstance(override, str) and override.strip():
            return override.strip()

    definition = get_shortcut_definition(shortcut_id)
    return definition.default_sequence


def get_shortcut_label(shortcut_id: ShortcutId) -> str:
    """Renvoie le libellé traduit du raccourci."""
    return get_shortcut_definition(shortcut_id).title


def validate_catalog(catalog: dict[ShortcutId, ShortcutDefinition] | None = None) -> None:
    """Valide la cohérence interne du catalogue de raccourcis.

    Vérifie l'absence de séquences réservées, l'unicité des séquences en portée
    APPLICATION et la stricte isolation des touches nues à la portée WIDGET.
    """
    effective_catalog = catalog if catalog is not None else get_shortcut_catalog()
    seen_app_sequences: dict[str, ShortcutId] = {}

    for sc_id, definition in effective_catalog.items():
        seq = definition.default_sequence

        # 1. Vérification liste noire réservée
        if is_reserved_sequence(seq):
            raise ValueError(f"Le raccourci {sc_id} utilise une séquence réservée interdite : '{seq}'")

        # 2. Vérification unicité en portée APPLICATION
        if definition.scope == ShortcutScope.APPLICATION:
            norm_seq = seq.upper()
            if norm_seq in seen_app_sequences:
                existing_id = seen_app_sequences[norm_seq]
                raise ValueError(f"Collision de séquence en portée APPLICATION : '{seq}' est attribuée à '{existing_id}' et '{sc_id}'")
            seen_app_sequences[norm_seq] = sc_id

        # 3. Vérification des touches nues (admises uniquement en portée WIDGET)
        is_bare = definition.allow_bare_key or len(seq) == 1
        if is_bare:
            if definition.scope != ShortcutScope.WIDGET:
                raise ValueError(f"Touche nue '{seq}' interdite pour le raccourci '{sc_id}' : seule la portée WIDGET est autorisée.")
            if not definition.allow_bare_key:
                raise ValueError(f"Touche nue '{seq}' détectée pour '{sc_id}' sans allow_bare_key=True.")

        # 4. Vérification de la validité du libellé (ADR 0013)
        if not callable(definition.title_getter):
            raise ValueError(f"title_getter du raccourci {sc_id} n'est pas un appelable.")
        title = definition.title
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Le titre du raccourci {sc_id} ne renvoie pas une chaîne valide.")
