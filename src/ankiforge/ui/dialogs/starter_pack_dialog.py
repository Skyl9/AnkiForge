"""Dialogue de Sélection et d'Installation des Modèles Communautaires Préconfigurés (Starter Pack)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ankiforge.database.models import NoteTypeModel
from ankiforge.services.cards.card_model_io import CardModelIO
from ankiforge.ui.components.badges import Badge
from ankiforge.ui.components.buttons import FilterChipButton, PrimaryButton, SecondaryButton
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widgets.toast import show_toast
from ankiforge.utils.i18n import tr
from ankiforge.utils.icon_loader import load_on_accent_icon, load_phosphor_icon


class StarterModelCardWidget(QFrame):
    """Carte graphique représentant un modèle communautaire du starter pack."""

    def __init__(
        self,
        pack: dict[str, Any],
        on_install_callback: Any,
        is_installed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.pack = pack
        self.on_install_callback = on_install_callback
        self.is_installed = is_installed

        self.setObjectName("StarterModelCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if self.is_installed:
            self.setProperty("installed", "true")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Ligne du haut : Badge Catégorie + Version + Badge d'état d'installation
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        cat_badge = Badge(
            pack.get("category", self.tr("Général")),
            variant="status",
            color=DesignTokens.ACCENT_PRIMARY,
        )
        top_row.addWidget(cat_badge)
        top_row.addStretch()

        ver_lbl = QLabel(tr("v%1", pack.get("version", "1.0.0")))
        ver_lbl.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px;")
        top_row.addWidget(ver_lbl)

        if is_installed:
            installed_badge = Badge(self.tr("Installé"), variant="success")
            top_row.addWidget(installed_badge)
        layout.addLayout(top_row)

        # Titre & Auteur
        title_lbl = QLabel(pack.get("name", self.tr("Type de note")))
        title_lbl.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        layout.addWidget(title_lbl)

        author_lbl = QLabel(tr("Par : %1", pack.get("author", "AnkiForge")))
        author_lbl.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_MUTED};")
        layout.addWidget(author_lbl)

        # Description
        desc_lbl = QLabel(pack.get("description", ""))
        desc_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_SECONDARY}; line-height: 1.4;")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Champs requis encadrés dans un bloc StarterFieldsBox
        fields = pack.get("fields_schema", [])
        fields_str = ", ".join(fields)
        fields_frame = QFrame()
        fields_frame.setObjectName("StarterFieldsBox")
        fields_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        fields_layout = QHBoxLayout(fields_frame)
        fields_layout.setContentsMargins(10, 6, 10, 6)
        fields_layout.setSpacing(6)

        fields_lbl_title = QLabel(self.tr("Champs :"))
        fields_lbl_title.setStyleSheet(f"font-size: 11px; font-weight: bold; color: {DesignTokens.TEXT_MUTED};")
        fields_layout.addWidget(fields_lbl_title)

        fields_lbl_content = QLabel(fields_str)
        fields_lbl_content.setStyleSheet(f"font-size: 11px; color: {DesignTokens.TEXT_SECONDARY};")
        fields_lbl_content.setWordWrap(True)
        fields_layout.addWidget(fields_lbl_content, 1)

        layout.addWidget(fields_frame)

        layout.addStretch()

        # Bouton Installer ou bandeau "Déjà installé"
        if is_installed:
            state_banner = QFrame()
            state_banner.setObjectName("StarterInstalledBanner")
            state_banner.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            state_banner.setFixedHeight(36)
            state_layout = QHBoxLayout(state_banner)
            state_layout.setContentsMargins(12, 0, 12, 0)
            state_layout.setSpacing(6)

            icon_lbl = QLabel()
            icon_lbl.setPixmap(load_phosphor_icon("ph.check-circle", color=DesignTokens.COLOR_GREEN).pixmap(15, 15))
            state_layout.addWidget(icon_lbl)

            state_lbl = QLabel(self.tr("Déjà installé dans ce profil"))
            state_lbl.setStyleSheet(f"color: {DesignTokens.COLOR_GREEN_TEXT}; font-size: 11px; font-weight: bold;")
            state_layout.addWidget(state_lbl)
            state_layout.addStretch()

            layout.addWidget(state_banner)
        else:
            btn_install = PrimaryButton(self.tr("Installer ce type de note"))
            btn_install.setIcon(load_on_accent_icon("ph.plus-circle"))
            btn_install.clicked.connect(lambda: self.on_install_callback(self.pack))
            layout.addWidget(btn_install)


class StarterPackDialog(QDialog):
    """Dialogue modal de catalogue de styles communautaires intégrés."""

    model_installed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StarterPackDialog")
        self.setWindowTitle(self.tr("Catalogue de Types de Note Communautaires (Starter Pack)"))
        self.setMinimumSize(850, 600)
        self.resize(920, 650)
        self.setModal(True)
        self._cards: list[tuple[StarterModelCardWidget, dict[str, Any]]] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 18)
        layout.setSpacing(14)

        # En-tête
        header = QHBoxLayout()
        icon_lbl = QLabel()
        icon_lbl.setPixmap(load_phosphor_icon("ph.sparkle", color=DesignTokens.ACCENT_PRIMARY).pixmap(26, 26))
        header.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_lbl = QLabel(self.tr("Types de note communautaires et professionnels prêts à l'emploi"))
        title_lbl.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {DesignTokens.TEXT_PRIMARY};")
        subtitle_lbl = QLabel(self.tr("Installez en un clic des gabarits pour la médecine, le code, les maths et les langues, ou activez la mémorisation par texte à trous (Cloze)."))
        subtitle_lbl.setStyleSheet(f"font-size: 12px; color: {DesignTokens.TEXT_MUTED};")
        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        header.addLayout(title_box, 1)

        layout.addLayout(header)

        # Barre de filtres par catégorie
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(0, 0, 0, 2)

        lbl_filter = QLabel(self.tr("Catégorie :"))
        lbl_filter.setStyleSheet(f"color: {DesignTokens.TEXT_MUTED}; font-size: 11px; font-weight: bold;")
        filter_row.addWidget(lbl_filter)

        packs = CardModelIO.get_starter_pack_models()
        self._packs_by_category: dict[str, list[dict[str, Any]]] = {}
        for pack in packs:
            cat = str(pack.get("category", "Général"))
            self._packs_by_category.setdefault(cat, []).append(pack)

        self._btn_tous = FilterChipButton(self.tr("Tous"))
        self._btn_tous.setChecked(True)
        self._btn_tous.toggled.connect(self._on_category_toggled)
        filter_row.addWidget(self._btn_tous)

        self._category_buttons: list[FilterChipButton] = []
        for cat in sorted(self._packs_by_category):
            btn = FilterChipButton(cat)
            btn.toggled.connect(self._on_category_toggled)
            filter_row.addWidget(btn)
            self._category_buttons.append(btn)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        # Grille de modèles
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        grid_layout = QGridLayout(scroll_content)
        grid_layout.setContentsMargins(0, 2, 8, 8)
        grid_layout.setSpacing(14)
        grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        installed_names = {str(m.name) for m in NoteTypeModel.select(NoteTypeModel.name)}

        for idx, pack in enumerate(packs):
            is_installed = str(pack.get("name", "")) in installed_names
            card = StarterModelCardWidget(
                pack,
                on_install_callback=self._on_install_pack,
                is_installed=is_installed,
            )
            row = idx // 2
            col = idx % 2
            grid_layout.addWidget(card, row, col)
            self._cards.append((card, pack))

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # Footer
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 6, 0, 0)
        btn_close = SecondaryButton(self.tr("Fermer"))
        btn_close.clicked.connect(self.accept)
        footer.addStretch()
        footer.addWidget(btn_close)
        layout.addLayout(footer)

    def _on_category_toggled(self, _checked: bool) -> None:
        sender = self.sender()
        if not isinstance(sender, FilterChipButton):
            return
        if sender is self._btn_tous:
            if sender.isChecked():
                for btn in self._category_buttons:
                    btn.setChecked(False)
        else:
            if sender.isChecked():
                self._btn_tous.setChecked(False)
                for btn in self._category_buttons:
                    if btn is not sender:
                        btn.setChecked(False)
        self._apply_category_filter()

    def _apply_category_filter(self) -> None:
        selected: str | None = None
        if not self._btn_tous.isChecked():
            for btn in self._category_buttons:
                if btn.isChecked():
                    selected = btn.text()
                    break
        for card, pack in self._cards:
            cat = str(pack.get("category", "Général"))
            card.setHidden(selected is not None and cat != selected)

    def _on_install_pack(self, pack: dict[str, Any]) -> None:
        name = pack.get("name", self.tr("Type de note"))
        exists = NoteTypeModel.get_or_none(NoteTypeModel.name == name) is not None

        overwrite = False
        if exists:
            res = QMessageBox.question(
                self,
                self.tr("Type de note existant"),
                tr("Le type de note '%1' est déjà présent dans votre collection.\n\nVoulez-vous le dupliquer (Non) ou écraser sa configuration (Oui) ?", name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if res == QMessageBox.StandardButton.Cancel:
                return
            overwrite = res == QMessageBox.StandardButton.Yes

        try:
            model_inst, _ = CardModelIO.save_model_to_db(pack, overwrite_existing=overwrite)
            show_toast(self, tr("Type de note '%1' installé avec succès !", model_inst.name))
            self.model_installed.emit(model_inst.id)
        except Exception as e:
            QMessageBox.critical(self, self.tr("Erreur"), tr("Échec de l'installation : %1", str(e)))
