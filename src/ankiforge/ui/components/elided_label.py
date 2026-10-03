"""
Composant QLabel avec élision dynamique de texte (ElidedLabel).
Permet au texte d'être tronqué proprement avec des points de suspension (...) selon la largeur disponible,
sans imposer de largeur minimale au layout conteneur.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtGui import QFontMetrics, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    """
    QLabel qui élide dynamiquement son texte avec des points de suspension (...)
    selon la largeur allouée par le layout, tout en conservant le texte intégral
    accessible via ``text()`` et en garantissant une taille minimale nulle (width=0).
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setText(text)

    def setText(self, text: str) -> None:
        """Définit le texte complet et recalcule l'élision immédiatement."""
        self._full_text = text
        self._update_elided_text()

    def text(self) -> str:
        """Retourne le texte intégral original (sémantique inchangée)."""
        return self._full_text

    def full_text(self) -> str:
        """Alias explicite pour récupérer le texte complet sans élision."""
        return self._full_text

    def elided_text(self) -> str:
        """Retourne le texte actuellement affiché à l'écran après élision."""
        return super().text()

    def minimumSizeHint(self) -> QSize:
        """Autorise le rétrécissement horizontal jusqu'à 0 sans forcer le parent."""
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        """Ne revendique pas de largeur minimale arbitraire."""
        return QSize(0, super().sizeHint().height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        """Recalcule l'élision à chaque redimensionnement du widget."""
        super().resizeEvent(event)
        self._update_elided_text()

    def changeEvent(self, event: QEvent) -> None:
        """Met à jour l'affichage si la police ou le style changent."""
        if event.type() in (QEvent.Type.FontChange, QEvent.Type.StyleChange):
            self._update_elided_text()
        super().changeEvent(event)

    def _update_elided_text(self) -> None:
        """Calcule le texte élidé selon la largeur courante et l'assigne au QLabel."""
        if not self._full_text:
            super().setText("")
            return

        w = self.width()
        if w > 0:
            fm = QFontMetrics(self.font())
            elided = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight, w)
            super().setText(elided)
        else:
            super().setText(self._full_text)
