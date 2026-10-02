from PySide6.QtCore import QMimeData
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtWidgets import QLabel


def local_file_paths(mime_data: QMimeData) -> list[str]:
    """Extrait les chemins de fichiers locaux d'un glisser-déposer du système."""
    return [url.toLocalFile() for url in mime_data.urls() if url.isLocalFile()]


class FileDropMixin:
    """Cible de dépôt de fichiers locaux partagée par la vue et l'arbre des documents.

    Doit précéder la classe QWidget/QTreeWidget dans l'ordre de résolution des méthodes :
    les drops internes (non-fichiers) sont confiés à ``handle_internal_drop``, qui délègue
    par défaut au ``dropEvent`` natif de Qt.
    """

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accepte les fichiers externes en plus du comportement natif de la classe hôte."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)  # type: ignore[misc]

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Maintient l'acceptation du survol pour les fichiers externes."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)  # type: ignore[misc]

    def dropEvent(self, event: QDropEvent) -> None:
        """Route les fichiers déposés vers ``handle_files_dropped``, sinon vers le dépôt interne."""
        if not event.mimeData().hasUrls():
            self.handle_internal_drop(event)
            return
        paths = local_file_paths(event.mimeData())
        event.acceptProposedAction()
        if paths:
            self.handle_files_dropped(paths)

    def handle_files_dropped(self, paths: list[str]) -> None:
        """Point d'extension obligatoire : reçoit les chemins de fichiers déposés."""
        raise NotImplementedError

    def handle_internal_drop(self, event: QDropEvent) -> None:
        """Dépôt sans fichier externe (déplacement interne d'items) : comportement Qt par défaut."""
        super().dropEvent(event)  # type: ignore[misc]


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    if len(hex_c) == 6:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    else:
        r, g, b = 100, 116, 139
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.35);
            border-radius: 9999px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)
