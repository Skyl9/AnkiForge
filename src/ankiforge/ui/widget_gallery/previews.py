"""Aperçus observationnels partagés par les familles non visuelles de la galerie.

Quatre familles n'exposent pas de widget autonome :

* les **layouts** sont des coquilles qui attendent un ``QStackedWidget`` et un registre
  de vues ;
* les **viewmodels** sont des ``QObject`` sans représentation graphique ;
* les **modèles Qt** et leurs **délégués** ne s'expriment que dans une vue ;
* la famille **shell** ne peut pas instancier la vraie fenêtre principale.

Ce module fournit les conteneurs d'aperçu génériques qui rendent ces objets observables
sans dupliquer leur logique : inspection des signaux pour les ``QObject``, tableau ou
liste liés au modèle pour les ``QAbstractItemModel``, vue porteuse pour les délégués et
recomposition inerte de la coquille applicative.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from PySide6.QtCore import QAbstractItemModel, QMetaMethod, QObject, Qt
from PySide6.QtGui import QCloseEvent, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListView,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QStyledItemDelegate,
    QTableView,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ankiforge.ui.layouts.base_layout import BaseLayout
from ankiforge.ui.layouts.layout_manager import LayoutManager
from ankiforge.ui.theme import DesignTokens
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)

#: Signaux techniques de ``QObject`` qui n'ont pas de sens dans un journal d'aperçu.
_IGNORED_SIGNALS = frozenset({"destroyed", "objectNameChanged"})

#: Hauteur d'une ligne peinte par un délégué dans son aperçu.
_PREVIEW_ROW_HEIGHT = 40
#: Gouttière interne des conteneurs d'aperçu.
_PREVIEW_PADDING = 12


def _title_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setStyleSheet(f"color: {DesignTokens.TEXT_PRIMARY}; font-size: {DesignTokens.FONT_SIZE_BASE}px; font-weight: 600;")
    return label


def _caption_label(text: str, parent: QWidget | None = None) -> QLabel:
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: {DesignTokens.FONT_SIZE_SM}px;")
    return label


class ObjectPreview(QWidget):
    """Aperçu d'un objet Qt non visuel : identité, signaux et journal des émissions.

    Les signaux de l'objet sont connectés à un journal borné, ce qui rend observable le
    comportement d'un ViewModel sans écrire de scénario spécifique. Les objets exposant
    ``dispose()`` (contrat :class:`BaseViewModel`) sont libérés à la fermeture, afin
    qu'aucun abonnement au bus d'événements ne survive à l'aperçu.
    """

    def __init__(
        self,
        target: QObject,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._signal_items: dict[str, QTreeWidgetItem] = {}
        self._signal_counts: dict[str, int] = {}
        self._subscriptions: list[tuple[Callable[..., Any], Callable[..., Any]]] = []
        self._disposed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PREVIEW_PADDING, _PREVIEW_PADDING, _PREVIEW_PADDING, _PREVIEW_PADDING)
        layout.setSpacing(8)
        layout.addWidget(_title_label(title, self))
        if subtitle:
            layout.addWidget(_caption_label(subtitle, self))

        self.signal_tree = QTreeWidget(self)
        self.signal_tree.setHeaderLabels([tr("Signal"), tr("Émissions")])
        self.signal_tree.setColumnWidth(0, 240)
        self.signal_tree.setRootIsDecorated(False)
        self.signal_tree.setMaximumHeight(180)
        layout.addWidget(self.signal_tree)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(200)
        self.log_view.setPlaceholderText(tr("Les émissions de signaux apparaîtront ici."))
        self.log_view.setMaximumHeight(140)
        layout.addWidget(self.log_view)

        self._actions = QHBoxLayout()
        self._build_actions()
        self._actions.addStretch()
        layout.addLayout(self._actions)
        layout.addStretch()

        self._connect_signals()

    @property
    def target(self) -> QObject:
        """Objet Qt observé par cet aperçu."""
        return self._target

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_actions(self) -> None:
        set_busy = getattr(self._target, "set_busy", None)
        if callable(set_busy):
            self._busy_button = QPushButton(tr("Basculer l'occupation"), self)
            self._busy_button.clicked.connect(self._toggle_busy)
            self._actions.addWidget(self._busy_button)

        emit_message = getattr(self._target, "emit_message", None)
        if callable(emit_message):
            self._message_button = QPushButton(tr("Émettre un message de démonstration"), self)
            self._message_button.clicked.connect(self._emit_demo_message)
            self._actions.addWidget(self._message_button)

        set_error = getattr(self._target, "set_error", None)
        if callable(set_error):
            self._error_button = QPushButton(tr("Simuler une erreur"), self)
            self._error_button.clicked.connect(self._simulate_error)
            self._actions.addWidget(self._error_button)

    def _connect_signals(self) -> None:
        meta_object = self._target.metaObject()
        for index in range(meta_object.methodCount()):
            method = meta_object.method(index)
            if method.methodType() != QMetaMethod.MethodType.Signal:
                continue
            name = method.name().data().decode("utf-8", errors="replace")
            if name in _IGNORED_SIGNALS:
                continue
            signal = getattr(self._target, name, None)
            if signal is None:
                continue
            item = QTreeWidgetItem([name, "0"])
            self.signal_tree.addTopLevelItem(item)
            self._signal_items[name] = item
            self._signal_counts[name] = 0
            slot = self._make_signal_slot(name)
            signal.connect(slot)
            self._subscriptions.append((signal, slot))

    def _make_signal_slot(self, name: str) -> Callable[..., None]:
        """Fabrique un récepteur borné au nom du signal (les lambdas de boucle fuient la variable)."""

        def _slot(*args: Any) -> None:
            self._record_signal(name, args)

        return _slot

    # ── Interactions ──────────────────────────────────────────────────────────

    def _toggle_busy(self) -> None:
        set_busy = getattr(self._target, "set_busy", None)
        if not callable(set_busy):
            return
        is_busy = bool(getattr(self._target, "is_busy", False))
        set_busy(not is_busy)
        self._busy_button.setText(tr("Repasser au repos") if not is_busy else tr("Basculer l'occupation"))

    def _emit_demo_message(self) -> None:
        emit_message = getattr(self._target, "emit_message", None)
        if callable(emit_message):
            emit_message(tr("Message de démonstration émis depuis la galerie."))

    def _simulate_error(self) -> None:
        set_error = getattr(self._target, "set_error", None)
        if callable(set_error):
            set_error(tr("Erreur de démonstration simulée par la galerie."))

    def _record_signal(self, name: str, args: tuple[Any, ...]) -> None:
        if self._disposed:
            return
        count = self._signal_counts.get(name, 0) + 1
        self._signal_counts[name] = count
        item = self._signal_items.get(name)
        if item is not None:
            item.setText(1, str(count))
        rendered = ", ".join(repr(arg)[:60] for arg in args if not isinstance(arg, QObject))
        self.log_view.appendPlainText(f"{name}({rendered})" if rendered else f"{name}()")

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._disposed:
            super().closeEvent(event)
            return
        self._disposed = True
        for signal, slot in self._subscriptions:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                logger.debug("Signal déjà déconnecté pour l'aperçu « %s »", type(self._target).__name__)
        self._subscriptions.clear()

        dispose = getattr(self._target, "dispose", None)
        if callable(dispose):
            try:
                dispose()
            except Exception:
                logger.exception("Échec de la libération de l'aperçu « %s »", type(self._target).__name__)
        super().closeEvent(event)


class ItemModelPreview(QWidget):
    """Aperçu d'un modèle de données Qt dans une liste ou un tableau lié."""

    def __init__(
        self,
        model: QAbstractItemModel,
        title: str,
        list_mode: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self._list_mode = list_mode

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PREVIEW_PADDING, _PREVIEW_PADDING, _PREVIEW_PADDING, _PREVIEW_PADDING)
        layout.setSpacing(8)
        layout.addWidget(_title_label(title, self))
        self.metrics_label = _caption_label(self._metrics_text(), self)
        layout.addWidget(self.metrics_label)

        view: QAbstractItemView = QListView(self) if list_mode else QTableView(self)
        view.setModel(model)
        view.setAlternatingRowColors(True)
        if isinstance(view, QTableView):
            header = view.horizontalHeader()
            header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setStretchLastSection(True)
        layout.addWidget(view, 1)

        # Le compteur doit suivre les chargements différés (fetchMore) et les resets.
        model.rowsInserted.connect(self._refresh_metrics)
        model.rowsRemoved.connect(self._refresh_metrics)
        model.modelReset.connect(self._refresh_metrics)
        model.layoutChanged.connect(self._refresh_metrics)

    def _metrics_text(self) -> str:
        columns = 1 if self._list_mode else self.model.columnCount()
        return tr("%1 ligne(s) × %2 colonne(s)", self.model.rowCount(), columns)

    def _refresh_metrics(self, *_args: object) -> None:
        self.metrics_label.setText(self._metrics_text())


class DelegatePreview(QWidget):
    """Aperçu d'un délégué de rendu appliqué à quelques lignes représentatives."""

    def __init__(
        self,
        delegate: QStyledItemDelegate,
        title: str,
        rows: Sequence[tuple[str, dict[int, Any]]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row_height = _PREVIEW_ROW_HEIGHT
        self._model = QStandardItemModel(self)
        for label, roles in rows:
            item = QStandardItem(label)
            item.setEditable(False)
            for role, value in roles.items():
                item.setData(value, role)
            self._model.appendRow(item)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(_PREVIEW_PADDING, _PREVIEW_PADDING, _PREVIEW_PADDING, _PREVIEW_PADDING)
        layout.setSpacing(8)
        layout.addWidget(_title_label(title, self))

        self.table_view = QTableView(self)
        self.table_view.setModel(self._model)
        self.table_view.setItemDelegate(delegate)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table_view.setShowGrid(False)
        self.table_view.verticalHeader().hide()
        self.table_view.horizontalHeader().hide()
        self.table_view.setMinimumHeight(row_height * max(1, len(rows)) + 8)
        layout.addWidget(self.table_view, 1)


class ShellPreviewWindow(QMainWindow):
    """Aperçu inerte de la coquille applicative, sans instancier les vues réelles.

    La fenêtre compose les **vrais** layouts et le **vrai** registre de vues de
    :meth:`MainWindow.view_registry`, mais remplace chaque vue par un substitut textuel.
    Aucun worker, timer réseau ni démon MCP n'est donc démarré : l'aperçu est purement
    observationnel, conformément au hors-périmètre de la galerie.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("[Galerie Dev] Coquille de la fenêtre principale"))
        self._registry = self._main_window_registry()
        self._current_layout: BaseLayout | None = None
        self._stacked: QStackedWidget | None = None

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        selector_bar = QWidget(central)
        selector_layout = QHBoxLayout(selector_bar)
        selector_layout.setContentsMargins(8, 6, 8, 6)
        selector_layout.addWidget(_caption_label(tr("Disposition :"), selector_bar))
        self.layout_combo = QComboBox(selector_bar)
        for metadata in LayoutManager.get_available_layouts():
            self.layout_combo.addItem(metadata["name"], metadata["id"])
        self.layout_combo.currentIndexChanged.connect(self._on_layout_changed)
        selector_layout.addWidget(self.layout_combo)
        selector_layout.addStretch()
        layout.addWidget(selector_bar)

        self._host = QWidget(central)
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(0, 0, 0, 0)
        self._host_layout.setSpacing(0)
        layout.addWidget(self._host, 1)

        self.setCentralWidget(central)
        self._apply_layout("ide")

    # ── API d'observation ─────────────────────────────────────────────────────

    def navigation_ids(self) -> list[str]:
        """Identifiants de vues rendus par la coquille, dans l'ordre du registre réel."""
        return list(self._registry)

    @property
    def current_layout(self) -> BaseLayout | None:
        return self._current_layout

    # ── Construction de la coquille ───────────────────────────────────────────

    @staticmethod
    def _main_window_registry() -> dict[str, tuple[str, str, str, type[QWidget]]]:
        from ankiforge.ui.main_window import MainWindow

        try:
            return MainWindow.view_registry()
        except Exception:
            logger.exception("Registre des vues indisponible pour l'aperçu de la coquille")
            return {}

    def _apply_layout(self, layout_id: str) -> None:
        if self._current_layout is not None:
            self._current_layout.hide()
            self._host_layout.removeWidget(self._current_layout)
            self._current_layout.deleteLater()
            self._current_layout = None
        if self._stacked is not None:
            self._stacked.deleteLater()
            self._stacked = None

        self._stacked = QStackedWidget(self._host)
        for _view_id, (_category, _icon, title, _cls) in self._registry.items():
            placeholder = QLabel(tr("Aperçu de la vue « %1 » (non instanciée).", title), self._stacked)
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: {DesignTokens.FONT_SIZE_BASE}px;")
            self._stacked.addWidget(placeholder)

        layout = LayoutManager.create_layout(layout_id, profile_name="galerie")
        layout.populate_navigation(self._registry)
        layout.set_stacked_widget(self._stacked)
        active_view = "dashboard" if "dashboard" in self._registry else next(iter(self._registry), None)
        if active_view is not None:
            layout.set_active_view(active_view)
        layout.view_selected.connect(self._on_view_selected)
        self._current_layout = layout
        self._host_layout.addWidget(layout)

    def set_layout(self, layout_id: str) -> None:
        """Bascule la coquille vers une disposition, en synchronisant le sélecteur local."""
        resolved = LayoutManager.resolve_layout_id(layout_id)
        if self._current_layout is not None and self._current_layout.get_layout_id() == resolved:
            return
        for index in range(self.layout_combo.count()):
            if self.layout_combo.itemData(index) == resolved:
                self.layout_combo.blockSignals(True)
                self.layout_combo.setCurrentIndex(index)
                self.layout_combo.blockSignals(False)
                break
        self._apply_layout(resolved)

    def _on_view_selected(self, view_id: str, _data: object = None) -> None:
        if self._stacked is None:
            return
        for index, known_id in enumerate(self._registry):
            if known_id == view_id:
                self._stacked.setCurrentIndex(index)
                break

    def _on_layout_changed(self, index: int) -> None:
        layout_id = self.layout_combo.itemData(index)
        if layout_id:
            self._apply_layout(str(layout_id))
