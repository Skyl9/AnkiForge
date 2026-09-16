"""
Utilitaires de dispatch Qt thread-safe pour les rafraîchissements d'interface.

Permet d'exécuter une mise à jour d'UI déclenchée depuis un worker (QThread)
sur le thread d'affinité du widget cible (en général le thread GUI).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer


def run_on_owner_thread(receiver: QObject, callback: Callable[[], Any]) -> None:
    """Exécute `callback` sur le thread d'affinité de `receiver`.

    Si la fonction est déjà appelée depuis ce thread, l'exécution est immédiate.
    Sinon, elle est rapatriée via une connexion différée pour rester thread-safe.
    """
    if QThread.currentThread() is receiver.thread():
        callback()
    else:
        QTimer.singleShot(0, receiver, callback)
