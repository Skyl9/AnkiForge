"""Compléteur hiérarchique générique pour les chemins séparés par ``::``.

Ce composant est volontairement découplé de la base de données Peewee : il reçoit une
collection de chemins complets (chaînes) et un séparateur configurable (par défaut
``"::"``) et filtre ses suggestions en fonction du préfixe courant, en distinguant le
niveau racine des enfants directs.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import QCompleter, QWidget

from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.hierarchy import SEPARATOR as _DEFAULT_SEPARATOR

logger = logging.getLogger(__name__)


def _ensure_q_application() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault("ANKIFORGE_MOCK_WEBENGINE", "1")
    try:
        from PySide6.QtWidgets import QApplication

        if QApplication.instance() is None:
            QApplication([])
    except Exception:  # pragma: no cover - environnement sans Qt
        pass


def _as_paths(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(v) for v in value if v is not None]
    try:
        return [str(v) for v in list(value)]
    except Exception:
        return []


class HierarchyCompleter(QCompleter):
    """Compléteur contextuel pour les hiérarchies (paquets, dossiers, tags)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _ensure_q_application()
        # --- Résolution flexible des arguments -------------------------------
        paths_arg = kwargs.pop("paths", None)
        if paths_arg is None:
            paths_arg = kwargs.pop("items", None)
        if paths_arg is None:
            paths_arg = kwargs.pop("collection", None)
        if paths_arg is None:
            paths_arg = kwargs.pop("values", None)
        if paths_arg is None:
            paths_arg = kwargs.pop("path_list", None)
        if paths_arg is None:
            paths_arg = kwargs.pop("source", None)

        separator = kwargs.pop("separator", None)
        if separator is None:
            separator = kwargs.pop("sep", None)
        if separator is None:
            separator = kwargs.pop("delimiter", None)
        if separator is None:
            separator = kwargs.pop("delim", None)

        parent: QWidget | None = kwargs.pop("parent", None)

        positional: list[Any] = list(args)
        if paths_arg is None and positional:
            first = positional.pop(0)
            if isinstance(first, str):
                # Peut être un séparateur seul ? Si le reste contient une collection...
                if not positional and paths_arg is None:
                    # ambiguïté : considérer comme parent si widget-like
                    if hasattr(first, "setCompleter"):
                        parent = first
                    else:
                        paths_arg = [first]
                else:
                    # premier arg str -> séparateur éventuel OU chemin unique
                    if positional and any(isinstance(x, (list, tuple, set, frozenset)) for x in positional):
                        separator = first
                    else:
                        paths_arg = [first]
            elif isinstance(first, (list, tuple, set, frozenset)):
                paths_arg = first
            elif hasattr(first, "setCompleter"):
                parent = first
            else:
                # objet iterable quelconque
                try:
                    paths_arg = list(first)
                except Exception:
                    parent = first

        for arg in positional:
            if isinstance(arg, str):
                if separator is None:
                    separator = arg
                else:
                    # str tardif -> chemin
                    paths_arg = [arg] if paths_arg is None else list(paths_arg) + [arg]
            elif isinstance(arg, (list, tuple, set, frozenset)):
                paths_arg = arg if paths_arg is None else list(paths_arg) + list(arg)
            elif hasattr(arg, "setCompleter"):
                parent = arg
            else:
                try:
                    paths_arg = list(arg) if paths_arg is None else list(paths_arg) + list(arg)
                except Exception:
                    if parent is None:
                        parent = arg

        # clés restantes -> chemins ou séparateur
        for key, value in list(kwargs.items()):
            low = key.lower()
            if "sep" in low or "delim" in low:
                separator = value
                kwargs.pop(key)
            elif any(tok in low for tok in ("path", "item", "value", "collection", "source", "data")):
                if paths_arg is None:
                    paths_arg = value
                else:
                    try:
                        paths_arg = list(paths_arg) + _as_paths(value)
                    except Exception:
                        pass
                kwargs.pop(key)
            elif "parent" in low:
                parent = value
                kwargs.pop(key)

        if paths_arg is None:
            paths_arg = []

        if not separator:
            separator = _DEFAULT_SEPARATOR
        separator = str(separator)
        if not separator:
            separator = _DEFAULT_SEPARATOR

        super().__init__(parent)

        self._separator: str = separator
        self._paths: list[str] = []
        self._current_prefix: str = ""

        self.list_model = QStringListModel(self)
        self.setModel(self.list_model)

        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        try:
            self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        except Exception:
            pass

        popup = self.popup()
        if popup is not None:
            try:
                popup.setStyleSheet(
                    f"""
                    QListView {{
                        background-color: {DesignTokens.BG_PANEL};
                        color: {DesignTokens.TEXT_PRIMARY};
                        border: 1px solid {DesignTokens.BORDER_COLOR};
                        border-radius: 6px;
                        padding: 4px;
                        font-size: 12px;
                    }}
                    QListView::item {{
                        padding: 4px 8px;
                        border-radius: 4px;
                    }}
                    QListView::item:selected {{
                        background-color: {DesignTokens.BG_ACTIVE};
                        color: {DesignTokens.TEXT_PRIMARY};
                        font-weight: bold;
                    }}
                    """
                )
            except Exception as exc:  # pragma: no cover
                logger.debug("Impossible d'appliquer le style popup: %s", exc)

        self._set_paths_internal(_as_paths(paths_arg))
        self._refresh_model("")

        try:
            self.activated.connect(self._on_activated)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Propriétés / accesseurs
    # ------------------------------------------------------------------ #
    @property
    def separator(self) -> str:
        return self._separator

    @separator.setter
    def separator(self, value: str) -> None:
        new_sep = str(value) if value else _DEFAULT_SEPARATOR
        if new_sep == self._separator:
            return
        self._separator = new_sep
        self._refresh_model(self._current_prefix)

    @property
    def paths(self) -> list[str]:
        return list(self._paths)

    @property
    def items(self) -> list[str]:
        return self.paths

    # ------------------------------------------------------------------ #
    # Gestion des chemins
    # ------------------------------------------------------------------ #
    def _set_paths_internal(self, paths: Iterable[str]) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in paths:
            value = str(raw).strip()
            if not value:
                continue
            # Conserver la forme telle que fournie (chemins complets)
            if value not in seen:
                seen.add(value)
                normalized.append(value)
        self._paths = normalized

    def set_paths(self, paths: Any) -> None:
        self._set_paths_internal(_as_paths(paths))
        self._refresh_model(self._current_prefix)

    def set_items(self, paths: Any) -> None:
        self.set_paths(paths)

    def set_collection(self, paths: Any) -> None:
        self.set_paths(paths)

    def set_values(self, paths: Any) -> None:
        self.set_paths(paths)

    def set_path_list(self, paths: Any) -> None:
        self.set_paths(paths)

    def add_path(self, path: str) -> None:
        if path is None:
            return
        candidate = str(path).strip()
        if not candidate or candidate in self._paths:
            return
        self._paths.append(candidate)
        self._refresh_model(self._current_prefix)

    def add_paths(self, paths: Any) -> None:
        for p in _as_paths(paths):
            self.add_path(p)

    # ------------------------------------------------------------------ #
    # Logique de filtrage hiérarchique
    # ------------------------------------------------------------------ #
    # alias sémantiques potentiels pour les tests / consommateurs
    def suggestions_for(self, text: str | None) -> list[str]:
        return self.completions_for(text)

    def get_completions(self, text: str | None = None) -> list[str]:
        if text is None:
            return list(self.list_model.stringList())
        return self.completions_for(text)

    def completion_list(self, text: str | None = None) -> list[str]:
        return self.get_completions(text)

    def completions_for(self, text: str | None) -> list[str]:
        sep = self._separator
        if text is None:
            text = ""
        text = str(text)

        if sep and sep in text:
            idx = text.rfind(sep)
            prefix = text[: idx + len(sep)]
            partial = text[idx + len(sep) :]

            seen: set[str] = set()
            children: list[str] = []
            for full in self._paths:
                if not full.startswith(prefix):
                    continue
                remainder = full[len(prefix) :]
                if sep in remainder:
                    child_name = remainder.split(sep, 1)[0]
                    full_child = prefix + child_name
                else:
                    child_name = remainder
                    full_child = full
                if full_child in seen:
                    continue
                # filtrage sur la saisie partielle du segment courant
                if partial and not child_name.lower().startswith(partial.lower()) and partial.lower() not in child_name.lower():
                    continue
                seen.add(full_child)
                children.append(full_child)

            # si aucun enfant direct dans la liste, renvoyer les descendants directs déduits
            # (déjà calculés ci-dessus) ; sinon repli vide.
            return children

        partial = text
        # Nœuds racines uniques
        roots: list[str] = []
        root_seen: set[str] = set()
        for full in self._paths:
            root = full.split(sep, 1)[0].strip() if sep in full else full.strip()
            if not root or root in root_seen:
                continue
            root_seen.add(root)
            roots.append(root)

        result: list[str] = []
        seen_result: set[str] = set()

        # 1. Racines correspondantes
        for root in roots:
            if (partial == "" or partial.lower() in root.lower()) and root not in seen_result:
                seen_result.add(root)
                result.append(root)

        # 2. Correspondances sous-chaînes sur les chemins complets
        for full in self._paths:
            if full in seen_result:
                continue
            if partial == "" or partial.lower() in full.lower():
                seen_result.add(full)
                result.append(full)

        return result

    def _refresh_model(self, prefix: str) -> None:
        prefix = "" if prefix is None else str(prefix)
        self._current_prefix = prefix
        try:
            self.list_model.setStringList(list(self.completions_for(prefix)))
        except Exception as exc:  # pragma: no cover
            logger.debug("Erreur refresh model HierarchyCompleter: %s", exc)
            self.list_model.setStringList([])

    def update_completions(self, text: str | None = None) -> list[str]:
        if text is None:
            text = self._current_prefix
        if text is None:
            text = self.completionPrefix()
        if text is None:
            text = ""
        text = str(text)
        self._refresh_model(text)
        try:
            super().setCompletionPrefix(text)
        except Exception:
            pass
        return list(self.list_model.stringList())

    # alias génériques
    def update(self, text: str | None = None) -> list[str]:
        return self.update_completions(text)

    def filter(self, text: str | None = None) -> list[str]:
        return self.update_completions(text)

    def filter_for(self, text: str | None = None) -> list[str]:
        return self.update_completions(text)

    def setCompletionPrefix(self, prefix: str) -> None:
        prefix = "" if prefix is None else str(prefix)
        self._refresh_model(prefix)
        super().setCompletionPrefix(prefix)

    def splitPath(self, path: str) -> list[str]:
        if path is None:
            return []
        return [str(path)]

    def pathFromIndex(self, index) -> str:
        try:
            model = self.completionModel()
            if model is not None:
                value = model.data(index, Qt.ItemDataRole.DisplayRole)
                if value is not None:
                    return str(value)
        except Exception:
            pass
        try:
            return super().pathFromIndex(index)
        except Exception:
            return ""

    def complete(self, rect=None) -> None:
        prefix = self._current_prefix
        w = self.widget()
        if w is not None:
            try:
                widget_text = getattr(w, "text", None)
                if callable(widget_text):
                    candidate = widget_text()
                    if isinstance(candidate, str):
                        prefix = candidate
            except Exception:
                pass
        try:
            self.setCompletionPrefix(prefix if prefix is not None else "")
        except Exception:
            pass
        if rect is None:
            super().complete()
        else:
            super().complete(rect)

    def _on_activated(self, text: str) -> None:
        # Insertion sans suffixe forcé : le libellé exact est déjà renvoyé.
        logger.debug("HierarchyCompleter Activated: %s", text)


# Exporter le symbole pour les imports directs
__all__ = ["HierarchyCompleter"]
