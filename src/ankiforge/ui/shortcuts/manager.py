"""Manager central de liaison et de résolution des raccourcis clavier AnkiForge.

Assure l'activation des bindings par vue affichée, la résolution hiérarchique
(Dialogue > Widget > Vue > Application) et la priorité absolue de la saisie de texte.
Conforme à l'ADR 0032.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
)

from ankiforge.ui.shortcuts.catalog import get_shortcut_catalog, get_shortcut_sequence
from ankiforge.ui.shortcuts.models import (
    ShortcutDefinition,
    ShortcutId,
    ShortcutScope,
    is_reserved_sequence,
    normalize_sequence_text,
)

logger = logging.getLogger(__name__)


def is_text_input_focused() -> bool:
    """Indique si le widget actuellement focalisé est un champ de saisie de texte."""
    focus_widget = QApplication.focusWidget()
    if focus_widget is None:
        return False
    return isinstance(focus_widget, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox))


@dataclass
class BindingRecord:
    """Enregistrement interne d'un raccourci lié à un widget."""

    id: ShortcutId
    scope: ShortcutScope
    sequence: str
    target: QWidget
    shortcut: QShortcut
    handler: Callable[[], None]
    is_bare: bool


class ShortcutManager(QObject):
    """Manager unique liant le catalogue déclaratif aux widgets de l'application."""

    def __init__(self, parent: QObject | None = None, settings_service: Any = None) -> None:
        super().__init__(parent)
        self._settings_service = settings_service
        self._bindings: list[BindingRecord] = []
        self._active_view: QWidget | None = None
        self._active_dialog: QWidget | None = None

    @property
    def active_view(self) -> QWidget | None:
        """Vue actuellement affichée."""
        return self._active_view

    @property
    def active_dialog(self) -> QWidget | None:
        """Boîte de dialogue modale actuellement active."""
        return self._active_dialog

    def set_active_view(self, view: QWidget | None) -> None:
        """Définit la vue affichée et met à jour l'activation des bindings."""
        if self._active_view is not view:
            self._active_view = view
            self._recompute_active_bindings()

    def set_active_dialog(self, dialog: QWidget | None) -> None:
        """Définit le dialogue actif et met à jour l'activation des bindings."""
        if self._active_dialog is not dialog:
            self._active_dialog = dialog
            self._recompute_active_bindings()

    def bind(
        self,
        target: QWidget,
        bindings: dict[ShortcutId, Callable[[], None]],
        scope: ShortcutScope | None = None,
        custom_definitions: dict[ShortcutId, ShortcutDefinition] | None = None,
    ) -> list[QShortcut]:
        """Lie un ensemble d'actions du catalogue à des fonctions de rappel sur un widget.

        Args:
            target: Le widget récepteur auquel attacher les raccourcis.
            bindings: Dictionnaire associant chaque ShortcutId à son handler.
            scope: Surcharge optionnelle de la portée déclarative.
            custom_definitions: Dictionnaire optionnel pour définitions de test/locales.

        Returns:
            La liste des instances QShortcut créées.
        """
        created_shortcuts: list[QShortcut] = []

        catalog = get_shortcut_catalog()
        for sc_id, handler in bindings.items():
            if custom_definitions and sc_id in custom_definitions:
                definition = custom_definitions[sc_id]
            elif sc_id in catalog:
                definition = catalog[sc_id]
            else:
                raise KeyError(f"ShortcutId non répertorié : {sc_id}")

            effective_scope = scope if scope is not None else definition.scope
            sequence_str = definition.default_sequence if custom_definitions and sc_id in custom_definitions else get_shortcut_sequence(sc_id, self._settings_service)

            # Vérification des séquences réservées
            if is_reserved_sequence(sequence_str):
                raise ValueError(f"Impossible de lier la séquence réservée '{sequence_str}' pour '{sc_id}'")

            # Vérification des touches nues
            is_bare = definition.allow_bare_key or (len(sequence_str) == 1 and not any(mod in sequence_str for mod in ("Ctrl", "Alt", "Shift", "Meta")))
            if is_bare and effective_scope != ShortcutScope.WIDGET:
                raise ValueError(f"La touche nue '{sequence_str}' pour '{sc_id}' ne peut être liée qu'en portée WIDGET (portée demandée : {effective_scope.name}).")

            # Règle du texte prioritaire : la saisie absorbe les touches nues
            def make_wrapped_handler(h: Callable[[], None], bare: bool, seq: str) -> Callable[[], None]:
                def wrapped() -> None:
                    if bare and is_text_input_focused():
                        logger.debug("Touche nue '%s' absorbée par la saisie de texte focalisée", seq)
                        return
                    h()

                return wrapped

            wrapped_cb = make_wrapped_handler(handler, is_bare, sequence_str)

            # Création du QShortcut Qt
            shortcut = QShortcut(QKeySequence(sequence_str), target)
            if effective_scope == ShortcutScope.WIDGET:
                shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            else:
                shortcut.setContext(Qt.ShortcutContext.WindowShortcut)

            shortcut.activated.connect(wrapped_cb)
            created_shortcuts.append(shortcut)

            record = BindingRecord(
                id=sc_id,
                scope=effective_scope,
                sequence=sequence_str,
                target=target,
                shortcut=shortcut,
                handler=handler,
                is_bare=is_bare,
            )
            self._bindings.append(record)

        # Nettoyage automatique à la destruction du widget
        target.destroyed.connect(lambda: self.unbind(target))

        self._recompute_active_bindings()
        return created_shortcuts

    def unbind(self, target: QWidget) -> None:
        """Supprime tous les bindings associés à un widget cible."""
        surviving: list[BindingRecord] = []
        for rec in self._bindings:
            if rec.target is target:
                try:
                    rec.shortcut.setEnabled(False)
                    rec.shortcut.setParent(None)
                    rec.shortcut.deleteLater()
                except RuntimeError:
                    pass
            else:
                surviving.append(rec)
        self._bindings = surviving
        self._recompute_active_bindings()

    def _is_descendant_of(self, child: QObject, ancestor: QObject) -> bool:
        """Vérifie si un QObject est un descendant d'un ancêtre donné."""
        current = child.parent()
        while current is not None:
            if current is ancestor:
                return True
            current = current.parent()
        return False

    def _recompute_active_bindings(self) -> None:
        """Recalcule l'état actif/inactif de chaque binding selon la vue courante et la priorité hiérarchique."""
        eligible_records: list[BindingRecord] = []

        for rec in self._bindings:
            try:
                # Vérifier si le widget cible existe toujours
                _ = rec.target.parent()
            except RuntimeError:
                continue

            is_eligible = False
            if rec.scope == ShortcutScope.APPLICATION:
                is_eligible = True
            elif rec.scope == ShortcutScope.VUE:
                if self._active_view is not None:
                    is_eligible = rec.target is self._active_view or self._is_descendant_of(rec.target, self._active_view)
            elif rec.scope == ShortcutScope.DIALOGUE:
                is_eligible = (rec.target is self._active_dialog or self._is_descendant_of(rec.target, self._active_dialog)) if self._active_dialog is not None else True
            elif rec.scope == ShortcutScope.WIDGET:
                # En portée WIDGET, éligible si dans la vue active ou si aucune vue n'est définie
                is_eligible = (rec.target is self._active_view or self._is_descendant_of(rec.target, self._active_view)) if self._active_view is not None else True

            if is_eligible:
                eligible_records.append(rec)
            else:
                rec.shortcut.setEnabled(False)

        # Résolution des priorités hiérarchiques : à séquence égale, la portée la plus spécifique gagne
        by_sequence: dict[str, list[BindingRecord]] = {}
        for rec in eligible_records:
            norm_seq = normalize_sequence_text(rec.sequence).upper()
            by_sequence.setdefault(norm_seq, []).append(rec)

        for _norm_seq, records in by_sequence.items():
            max_scope = max(r.scope for r in records)
            for r in records:
                r.shortcut.setEnabled(r.scope == max_scope)
