"""Conteneur d'aperçu pour un widget de la galerie."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ankiforge.ui.widget_gallery.registry import GalleryEntry

logger = logging.getLogger(__name__)


class PreviewContainer(QWidget):
    """Instancie un widget de la galerie avec gestion d'erreurs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._current: QWidget | None = None
        self._error_label = QLabel(self)
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        self._layout.addWidget(self._error_label)

    def set_entry(self, entry: GalleryEntry | None) -> None:
        self.clear()
        if entry is None:
            return
        try:
            widget = entry.factory()
            self._current = widget
            self._layout.addWidget(widget)
        except Exception as exc:
            logger.exception("Échec d'instanciation du widget %s", entry.name)
            self._error_label.setText(f"Erreur : {exc}")
            self._error_label.show()

    def clear(self) -> None:
        """Libère l'aperçu courant, y compris quand la fenêtre hôte se ferme.

        Un widget enfant ne reçoit pas de ``QCloseEvent`` lorsque son parent top-level se
        ferme : la libération doit donc être déclenchée explicitement par l'appelant.
        """
        if self._current is not None:
            self._layout.removeWidget(self._current)
            # Fermer avant de supprimer libère les abonnements (bus d'événements) des
            # composants qui ne se désabonnent que dans ``closeEvent``.
            self._current.close()
            self._current.deleteLater()
            self._current = None
        self._error_label.hide()

    @property
    def current_widget(self) -> QWidget | None:
        """Widget actuellement affiché dans l'aperçu, ou ``None``."""
        return self._current
