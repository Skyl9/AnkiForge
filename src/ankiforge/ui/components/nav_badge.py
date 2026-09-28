"""
Pastille d'état partagée par les boutons de navigation d'AnkiForge.

Les quatre layouts (`ide`, `macos`, `dashboard`, `glassmorphism`) déclarent leurs
boutons de navigation via des classes distinctes. Elles héritent toutes de
`NavBadgeButton` pour offrir le même contrat : une pastille discrète affichée en
coin de l'icône, qui rappelle à l'utilisateur qu'un travail est en cours dans la
vue (cartes générées, file d'attente batch, revue ouverte) sans jamais bloquer la
navigation.

Le style (`QLabel#NavBadge`) est déclaré dans le QSS global de `StyleEngine` :
aucune couleur ni aucun style n'est codé en dur ici (Règle d'or DESIGN.md).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QLabel, QPushButton, QSizePolicy, QWidget

MAX_BADGE_TEXT = 99

# Ancrage vertical : 1/6 de la hauteur du bouton, soit une pastille posée sur le
# bandeau supérieur plutôt qu'au centre exact.
BADGE_VERTICAL_DIVISOR = 6

# Marge intérieure de la pastille, en px (largeur minimale du badge).
BADGE_MIN_WIDTH = 12


class NavBadgeButton(QPushButton):
    """Bouton de navigation portant une pastille « travail en cours » optionnelle."""

    def __init__(self, view_id: str, icon_name: str, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view_id = view_id
        self.icon_name = icon_name
        self.title = title

        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        self._nav_badge_label: QLabel | None = None
        self._nav_badge_count: int | None = None

        # La sélection peut changer la largeur du bouton : la pastille suit d'elle-même.
        self.toggled.connect(lambda _checked: self._reposition_nav_badge())

    def nav_badge_count(self) -> int | None:
        """Nombre d'éléments de travail signalés, ou None si la vue est au repos."""
        return self._nav_badge_count

    def nav_badge_label(self) -> QLabel:
        """Pastille du bouton (créée paresseusement) — toujours parentingée au bouton."""
        if self._nav_badge_label is None:
            label = QLabel(self)
            label.setObjectName("NavBadge")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            # La pastille est purement décorative : elle ne doit jamais capter la souris.
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            label.hide()
            self._nav_badge_label = label
        return self._nav_badge_label

    def set_nav_badge(self, count: int | None) -> None:
        """Affiche (ou masque) la pastille. Un compte nul ou négatif équivaut à l'absence."""
        normalized = count if count is not None and count > 0 else None
        if normalized == self._nav_badge_count:
            return
        self._nav_badge_count = normalized
        label = self.nav_badge_label()
        if normalized is None:
            label.hide()
            return
        label.setText(f"{MAX_BADGE_TEXT}+" if normalized > MAX_BADGE_TEXT else str(normalized))
        label.setToolTip(f"{self.title} — {normalized} élément{'s' if normalized > 1 else ''} en cours")
        label.setAccessibleName(label.toolTip())
        self._reposition_nav_badge()
        label.show()
        label.raise_()

    def _reposition_nav_badge(self) -> None:
        """Ancre la pastille dans le coin supérieur droit, sans débordement."""
        if self._nav_badge_label is None:
            return
        label = self._nav_badge_label
        label.adjustSize()
        label.setFixedWidth(max(BADGE_MIN_WIDTH, label.sizeHint().width() + 2))
        label.move(max(0, self.width() - label.width()), max(0, (self.height() - label.height()) // BADGE_VERTICAL_DIVISOR))

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._reposition_nav_badge()
        super().resizeEvent(event)
