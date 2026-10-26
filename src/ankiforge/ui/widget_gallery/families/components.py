"""Famille « components » de la galerie : composants atomiques de ``ui/components``.

Chaque factory instancie un composant réel alimenté par les charges utiles
déterministes de :mod:`ankiforge.dev.fake_data`, sans appel réseau. Les composants
adossés à SQLite lisent le profil de développement ; seul l'atelier des règles y
amorce ses règles par défaut, de façon idempotente. Les composants dont la
construction exige un parent fonctionnel (gouttière, barre d'état du linter,
emplacement et voile de panneau) reçoivent une instance réelle construite à la
volée : leur libellé de galerie assume cette vue en situation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtWidgets import QHBoxLayout, QTableWidgetItem, QVBoxLayout, QWidget

from ankiforge.dev.fake_data import (
    make_fake_linter_comparison,
    make_fake_model_spec,
    make_fake_snippet,
    make_fake_source_diagnostic,
    make_fake_wozniak_item,
)
from ankiforge.ui.components.badges import Badge, StatusBadge, TagButton
from ankiforge.ui.components.buttons import (
    ActionButton,
    DangerButton,
    FilterChipButton,
    IconButton,
    PremiumActionCard,
    PrimaryButton,
    SecondaryButton,
)
from ankiforge.ui.components.code_editor.widgets.composite_editor import CodeEditorWithGutter
from ankiforge.ui.components.code_editor.widgets.native_editor import NativeCodeEditor
from ankiforge.ui.components.code_editor.widgets.status_bar import LintStatusBar
from ankiforge.ui.components.deck_select_window import DeckSelectWindow
from ankiforge.ui.components.document_picker_button import DocumentPickerButton
from ankiforge.ui.components.document_select_window import DocumentSelectWindow
from ankiforge.ui.components.duplicate_widgets import DuplicateMatrixTable, DuplicateMergeInspector
from ankiforge.ui.components.elided_label import ElidedLabel
from ankiforge.ui.components.flow_layout import FlowWidget
from ankiforge.ui.components.hierarchy_breadcrumb_bar import BreadcrumbSegmentButton, HierarchyBreadcrumbBar
from ankiforge.ui.components.inputs import (
    AutoExpandingTextEdit,
    DBComboBox,
    GlowLineEdit,
    OptionToggleRow,
    StyledComboBox,
    StyledLineEdit,
    StyledTextEdit,
    ToggleSwitch,
)
from ankiforge.ui.components.linter_rules_dialog import LinterRulesManagerDialog
from ankiforge.ui.components.linter_widgets import (
    FieldInspectorWidget,
    KatexLivePreviewWidget,
    SourceDiagnosticCardWidget,
    WozniakCardItemWidget,
    WozniakHubWidget,
    WozniakKpiCard,
)
from ankiforge.ui.components.lists import ActivityItem, ContextItem, DocTreeItem, StyledListItem, VirtualListView
from ankiforge.ui.components.misc import DaemonStatusWidget, StyledToolbar, UserAvatar
from ankiforge.ui.components.modal_field import ModalField
from ankiforge.ui.components.model_select_window import ModelSelectWindow
from ankiforge.ui.components.model_selector.badges import CapabilityPill, ModelCapabilityBadgesWidget
from ankiforge.ui.components.model_selector.dialog import ModelCardWidget, ModelDiscoveryDialog
from ankiforge.ui.components.model_selector.selector import ModelComboBox, ModelSelectorWidget
from ankiforge.ui.components.nav_badge import NavBadgeButton
from ankiforge.ui.components.panels import (
    EmptyStateWidget,
    GlassPanel,
    IdePanel,
    MetricCard,
    PanelDragOverlay,
    PanelPlaceholderWidget,
    StatCard,
)
from ankiforge.ui.components.persona_select_window import PersonaSelectWindow
from ankiforge.ui.components.pipeline_select_window import PipelineSelectWindow
from ankiforge.ui.components.sidebar import ClickableLabel, Sidebar, SidebarItem, SidebarProfileItem
from ankiforge.ui.components.snippet_drawer import SnippetCardWidget, SnippetLibraryDrawer
from ankiforge.ui.components.tables import CicdTable, StyledTableWidget, VirtualTableView
from ankiforge.ui.components.tabs.bars.ide_bar import IdeTabBar
from ankiforge.ui.components.tabs.bars.pill_bar import PillTabBar
from ankiforge.ui.components.tabs.bars.scrollable_bar import ScrollableTabBarWidget
from ankiforge.ui.components.tabs.bars.settings_bar import SettingsTabBar
from ankiforge.ui.components.tabs.floating_dock import FloatingDockWindow
from ankiforge.ui.components.tabs.segmented_tab_bar import SegmentedTabBar, SegmentedTabButton, SubTabButton
from ankiforge.ui.components.tabs.tab_button import TabButton
from ankiforge.ui.components.tabs.tab_container import TabContainer
from ankiforge.ui.components.tag_completer import TagCompleterItemWidget, TagCompleterPopup
from ankiforge.ui.components.tag_select_window import TagSelectWindow
from ankiforge.ui.components.title_bar import GlobalTitleBar
from ankiforge.ui.components.topbar import ClickableLabel as TopBarClickableLabel
from ankiforge.ui.components.topbar import TopBar
from ankiforge.ui.components.vision_capability import VisionCapabilityBadge, VisionCapabilityNotice
from ankiforge.ui.theme import DesignTokens
from ankiforge.ui.widget_gallery.registry import gallery_widget
from ankiforge.utils.i18n import tr

logger = logging.getLogger(__name__)


def _make_badge() -> QWidget:
    return Badge(tr("Nouveau"), variant="filled", color=DesignTokens.COLOR_BLUE)


def _make_status_badge() -> QWidget:
    return StatusBadge(tr("Validé"), icon_name="ph.check-circle", variant="success")


def _make_tag_button() -> QWidget:
    return TagButton(tr("biologie"), removable=True)


def _make_action_button() -> QWidget:
    return ActionButton(tr("Lancer l'analyse"))


def _make_danger_button() -> QWidget:
    return DangerButton(tr("Supprimer la carte"), tooltip=tr("Action irréversible"))


def _make_filter_chip_button() -> QWidget:
    return FilterChipButton(tr("Cartes à revoir"), icon_name="ph.funnel")


def _make_icon_button() -> QWidget:
    return IconButton("ph.pencil", tooltip=tr("Éditer la carte"), size=32)


def _make_premium_action_card() -> QWidget:
    return PremiumActionCard(
        icon_name="ph.sparkle",
        title=tr("Génération assistée"),
        description=tr("Forgez un lot de cartes à partir d'un document indexé."),
    )


def _make_primary_button() -> QWidget:
    return PrimaryButton(tr("Enregistrer"))


def _make_secondary_button() -> QWidget:
    return SecondaryButton(tr("Annuler"))


def _make_code_editor_with_gutter() -> QWidget:
    return CodeEditorWithGutter(placeholder=tr("Saisissez le gabarit HTML..."), mode="html")


def _make_line_number_area() -> QWidget:
    # L'éditeur natif instancie lui-même sa gouttière : l'aperçu la montre en situation.
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.addWidget(NativeCodeEditor(mode="html", parent=container))
    return container


def _make_native_code_editor() -> QWidget:
    return NativeCodeEditor(mode="css", placeholder=tr("Sélecteur CSS..."))


def _make_lint_status_bar() -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    editor = NativeCodeEditor(mode="html", parent=container)
    layout.addWidget(editor)
    layout.addWidget(LintStatusBar(editor, parent=container))
    return container


def _make_deck_select_window() -> QWidget:
    return DeckSelectWindow(title=tr("Sélectionner un paquet"), allow_all=True)


def _make_document_picker_button() -> QWidget:
    return DocumentPickerButton(allow_clear=True)


def _make_document_select_window() -> QWidget:
    return DocumentSelectWindow(title=tr("Sélectionner un cours"))


def _make_duplicate_matrix_table() -> QWidget:
    return DuplicateMatrixTable()


def _make_duplicate_merge_inspector() -> QWidget:
    return DuplicateMergeInspector()


def _make_elided_label() -> QWidget:
    return ElidedLabel(tr("Un titre de document volontairement très long pour éprouver la troncature"))


def _make_flow_widget() -> QWidget:
    flow = FlowWidget()
    for label in (tr("Gras"), tr("Italique"), tr("Souligné"), tr("Code")):
        flow.addWidget(Badge(label, variant="outline"))
    return flow


def _make_breadcrumb_segment_button() -> QWidget:
    return BreadcrumbSegmentButton(tr("Biologie"), "Biologie", True)


def _make_hierarchy_breadcrumb_bar() -> QWidget:
    return HierarchyBreadcrumbBar(
        initial_path="Biologie::Cellule::Mitose",
        existing_paths=["Biologie", "Biologie::Cellule", "Biologie::Cellule::Mitose"],
    )


def _make_auto_expanding_text_edit() -> QWidget:
    return AutoExpandingTextEdit(placeholder=tr("Décrivez le concept à forger..."), min_height=48, max_height=160)


def _make_db_combo_box() -> QWidget:
    return DBComboBox()


def _make_glow_line_edit() -> QWidget:
    return GlowLineEdit(placeholder=tr("Rechercher une carte..."))


def _make_option_toggle_row() -> QWidget:
    return OptionToggleRow(
        title=tr("Occulter automatiquement les champs vides"),
        icon_name="ph.eye",
        checked=True,
        tooltip=tr("Masque les champs non renseignés à la génération."),
    )


def _make_styled_combo_box() -> QWidget:
    combo = StyledComboBox()
    combo.addItems([tr("Tous les paquets"), tr("Biologie::Cellule")])
    return combo


def _make_styled_line_edit() -> QWidget:
    return StyledLineEdit(icon_name="ph.magnifying-glass", placeholder=tr("Filtrer les cartes..."))


def _make_styled_text_edit() -> QWidget:
    return StyledTextEdit()


def _make_toggle_switch() -> QWidget:
    return ToggleSwitch()


def _make_linter_rules_dialog() -> QWidget:
    return LinterRulesManagerDialog()


def _make_field_inspector() -> QWidget:
    original, proposal = make_fake_linter_comparison()
    return FieldInspectorWidget(original_data=original, proposal_data=proposal)


def _make_katex_preview() -> QWidget:
    return KatexLivePreviewWidget(initial_formula="\\int_{-\\infty}^{\\infty} |f(t)|^2\\,dt")


def _make_source_diagnostic_card() -> QWidget:
    return SourceDiagnosticCardWidget(make_fake_source_diagnostic())


def _make_wozniak_card_item() -> QWidget:
    return WozniakCardItemWidget(make_fake_wozniak_item())


def _make_wozniak_hub() -> QWidget:
    return WozniakHubWidget()


def _make_wozniak_kpi_card() -> QWidget:
    return WozniakKpiCard(
        cat_id="atomicity",
        title=tr("Atomicité"),
        pct=72,
        subtitle=tr("18 cartes à scinder"),
        color=DesignTokens.COLOR_RED,
        icon_name="ph.cube",
        is_pending=False,
    )


def _make_activity_item() -> QWidget:
    return ActivityItem(
        icon_name="ph.plus",
        title=tr("Lot de 12 cartes généré"),
        subtitle=tr("Biologie::Cellule"),
        timestamp=tr("il y a 4 min"),
    )


def _make_context_item() -> QWidget:
    return ContextItem(tr("Note"), tr("Qu'est-ce que la mitose ?"))


def _make_doc_tree_item() -> QWidget:
    return DocTreeItem(tr("Chapitre 1 — Introduction"), is_dir=False)


def _make_styled_list_item() -> QWidget:
    return StyledListItem()


def _make_virtual_list_view() -> QWidget:
    return VirtualListView()


def _make_daemon_status_widget() -> QWidget:
    return DaemonStatusWidget()


def _make_styled_toolbar() -> QWidget:
    return StyledToolbar()


def _make_user_avatar() -> QWidget:
    return UserAvatar(initials="TR", size=32)


def _make_modal_field() -> QWidget:
    return ModalField(placeholder=tr("Sélectionner un paquet..."))


def _make_model_select_window() -> QWidget:
    return ModelSelectWindow(title=tr("Sélectionner un type de note"))


def _make_capability_pill() -> QWidget:
    return CapabilityPill(
        icon_name="ph.eye",
        text=tr("Vision"),
        accent_color=DesignTokens.COLOR_BLUE,
        tooltip=tr("Ce modèle accepte les images en entrée."),
    )


def _make_model_capability_badges() -> QWidget:
    badges = ModelCapabilityBadgesWidget(compact=False)
    badges.set_model(make_fake_model_spec())
    return badges


def _make_model_card() -> QWidget:
    return ModelCardWidget(make_fake_model_spec(), is_installed=True, is_current=True)


def _make_model_discovery_dialog() -> QWidget:
    return ModelDiscoveryDialog()


def _make_model_combo_box() -> QWidget:
    return ModelComboBox()


def _make_model_selector() -> QWidget:
    return ModelSelectorWidget(allow_inherit=True, show_badges=True)


def _make_nav_badge_button() -> QWidget:
    return NavBadgeButton("documents", "ph.file-text", tr("Documents"))


def _make_empty_state_widget() -> QWidget:
    return EmptyStateWidget(
        icon_name="ph.ghost",
        title=tr("Aucune carte sélectionnée"),
        description=tr("Choisissez un paquet pour afficher ses cartes."),
    )


def _make_glass_panel() -> QWidget:
    return GlassPanel()


def _make_ide_panel() -> QWidget:
    return IdePanel(title=tr("Aperçu"), detachable=True)


def _make_metric_card() -> QWidget:
    return MetricCard(
        label=tr("Cartes révisées"),
        value="1 248",
        icon_name="ph.squares-four",
        trend="+12 %",
        trend_positive=True,
    )


def _make_panel_drag_overlay() -> QWidget:
    container = QWidget()
    layout = QVBoxLayout(container)
    panel = IdePanel(title=tr("Panneau source"), parent=container)
    layout.addWidget(panel)
    overlay = PanelDragOverlay(panel)
    overlay.setGeometry(panel.rect())
    overlay.show()
    return container


def _make_panel_placeholder() -> QWidget:
    return PanelPlaceholderWidget(IdePanel(title=tr("Panneau libre")))


def _make_stat_card() -> QWidget:
    return StatCard(label=tr("Cartes"), value="3 512")


def _make_persona_select_window() -> QWidget:
    return PersonaSelectWindow(title=tr("Sélectionner un agent"))


def _make_pipeline_select_window() -> QWidget:
    return PipelineSelectWindow(title=tr("Sélectionner un pipeline"))


def _make_clickable_label() -> QWidget:
    return ClickableLabel(tr("Lien de navigation"))


def _make_sidebar() -> QWidget:
    return Sidebar(profile_name="default")


def _make_sidebar_item() -> QWidget:
    return SidebarItem("documents", "ph.file-text", tr("Documents"))


def _make_sidebar_profile_item() -> QWidget:
    return SidebarProfileItem(profile_name="recherche")


def _make_top_bar_clickable_label() -> QWidget:
    return TopBarClickableLabel(tr("Lien de navigation"))


def _make_snippet_card() -> QWidget:
    return SnippetCardWidget(make_fake_snippet())


def _make_snippet_library_drawer() -> QWidget:
    return SnippetLibraryDrawer()


def _make_cicd_table() -> QWidget:
    table = CicdTable([tr("Étape"), tr("Statut"), tr("Durée")])
    rows = (("Ruff", tr("Succès"), "1,2 s"), ("Pytest", tr("Succès"), "8,4 s"))
    table.setRowCount(len(rows))
    for row_index, row_values in enumerate(rows):
        for column_index, value in enumerate(row_values):
            table.setItem(row_index, column_index, QTableWidgetItem(value))
    return table


def _make_styled_table() -> QWidget:
    table = StyledTableWidget([tr("Recto"), tr("Verso"), tr("Paquet")])
    rows = (
        (tr("Qu'est-ce que la mitose ?"), tr("Une division cellulaire."), "Biologie::Cellule"),
        (tr("Quelles sont les phases de la mitose ?"), tr("Prophase, métaphase, anaphase, télophase."), "Biologie::Cellule"),
    )
    table.setRowCount(len(rows))
    for row_index, row_values in enumerate(rows):
        for column_index, value in enumerate(row_values):
            table.setItem(row_index, column_index, QTableWidgetItem(value))
    return table


def _make_virtual_table_view() -> QWidget:
    return VirtualTableView()


def _make_ide_tab_bar() -> QWidget:
    return IdeTabBar()


def _make_pill_tab_bar() -> QWidget:
    return PillTabBar()


def _make_scrollable_tab_bar() -> QWidget:
    return ScrollableTabBarWidget(variant="ide")


def _make_settings_tab_bar() -> QWidget:
    return SettingsTabBar()


def _make_floating_dock() -> QWidget:
    return FloatingDockWindow()


def _make_segmented_tab_bar() -> QWidget:
    return SegmentedTabBar()


def _make_segmented_tab_button() -> QWidget:
    return SegmentedTabButton("apercu", tr("Aperçu"), icon_name="ph.eye", badge_text="3")


def _make_sub_tab_button() -> QWidget:
    return SubTabButton(tr("Brouillon"), icon_name="ph.pencil", is_active=True)


def _make_tab_button() -> QWidget:
    return TabButton(tr("Nouvelle carte"), icon_name="ph.plus", closable=True)


def _make_tab_container() -> QWidget:
    return TabContainer()


def _make_tag_completer_item() -> QWidget:
    return TagCompleterItemWidget("biologie", 8)


def _make_tag_completer_popup() -> QWidget:
    return TagCompleterPopup()


def _make_tag_select_window() -> QWidget:
    return TagSelectWindow(title=tr("Sélectionner des tags"))


def _make_global_title_bar() -> QWidget:
    return GlobalTitleBar()


def _make_top_bar() -> QWidget:
    return TopBar()


def _make_vision_capability_badge() -> QWidget:
    return VisionCapabilityBadge()


def _make_vision_capability_notice() -> QWidget:
    notice = VisionCapabilityNotice()
    notice.set_support_status(False)
    return notice


#: Correspondance clé de galerie → factory, source unique de la couverture.
COMPONENT_FACTORIES: dict[str, Callable[[], QWidget]] = {
    "ActionButton": _make_action_button,
    "ActivityItem": _make_activity_item,
    "AutoExpandingTextEdit": _make_auto_expanding_text_edit,
    "Badge": _make_badge,
    "BreadcrumbSegmentButton": _make_breadcrumb_segment_button,
    "CapabilityPill": _make_capability_pill,
    "CicdTable": _make_cicd_table,
    "ClickableLabel": _make_clickable_label,
    "ClickableLabel (topbar)": _make_top_bar_clickable_label,
    "CodeEditorWithGutter": _make_code_editor_with_gutter,
    "ContextItem": _make_context_item,
    "DBComboBox": _make_db_combo_box,
    "DaemonStatusWidget": _make_daemon_status_widget,
    "DangerButton": _make_danger_button,
    "DeckSelectWindow": _make_deck_select_window,
    "DocTreeItem": _make_doc_tree_item,
    "DocumentPickerButton": _make_document_picker_button,
    "DocumentSelectWindow": _make_document_select_window,
    "DuplicateMatrixTable": _make_duplicate_matrix_table,
    "DuplicateMergeInspector": _make_duplicate_merge_inspector,
    "ElidedLabel": _make_elided_label,
    "EmptyStateWidget": _make_empty_state_widget,
    "FieldInspectorWidget": _make_field_inspector,
    "FilterChipButton": _make_filter_chip_button,
    "FloatingDockWindow": _make_floating_dock,
    "FlowWidget": _make_flow_widget,
    "GlassPanel": _make_glass_panel,
    "GlobalTitleBar": _make_global_title_bar,
    "GlowLineEdit": _make_glow_line_edit,
    "HierarchyBreadcrumbBar": _make_hierarchy_breadcrumb_bar,
    "IconButton": _make_icon_button,
    "IdePanel": _make_ide_panel,
    "IdeTabBar": _make_ide_tab_bar,
    "KatexLivePreviewWidget": _make_katex_preview,
    "LineNumberArea": _make_line_number_area,
    "LintStatusBar": _make_lint_status_bar,
    "LinterRulesManagerDialog": _make_linter_rules_dialog,
    "MetricCard": _make_metric_card,
    "ModalField": _make_modal_field,
    "ModelCapabilityBadgesWidget": _make_model_capability_badges,
    "ModelCardWidget": _make_model_card,
    "ModelComboBox": _make_model_combo_box,
    "ModelDiscoveryDialog": _make_model_discovery_dialog,
    "ModelSelectWindow": _make_model_select_window,
    "ModelSelectorWidget": _make_model_selector,
    "NativeCodeEditor": _make_native_code_editor,
    "NavBadgeButton": _make_nav_badge_button,
    "OptionToggleRow": _make_option_toggle_row,
    "PanelDragOverlay": _make_panel_drag_overlay,
    "PanelPlaceholderWidget": _make_panel_placeholder,
    "PersonaSelectWindow": _make_persona_select_window,
    "PillTabBar": _make_pill_tab_bar,
    "PipelineSelectWindow": _make_pipeline_select_window,
    "PremiumActionCard": _make_premium_action_card,
    "PrimaryButton": _make_primary_button,
    "ScrollableTabBarWidget": _make_scrollable_tab_bar,
    "SecondaryButton": _make_secondary_button,
    "SegmentedTabBar": _make_segmented_tab_bar,
    "SegmentedTabButton": _make_segmented_tab_button,
    "SettingsTabBar": _make_settings_tab_bar,
    "Sidebar": _make_sidebar,
    "SidebarItem": _make_sidebar_item,
    "SidebarProfileItem": _make_sidebar_profile_item,
    "SnippetCardWidget": _make_snippet_card,
    "SnippetLibraryDrawer": _make_snippet_library_drawer,
    "SourceDiagnosticCardWidget": _make_source_diagnostic_card,
    "StatCard": _make_stat_card,
    "StatusBadge": _make_status_badge,
    "StyledComboBox": _make_styled_combo_box,
    "StyledLineEdit": _make_styled_line_edit,
    "StyledListItem": _make_styled_list_item,
    "StyledTableWidget": _make_styled_table,
    "StyledTextEdit": _make_styled_text_edit,
    "StyledToolbar": _make_styled_toolbar,
    "SubTabButton": _make_sub_tab_button,
    "TabButton": _make_tab_button,
    "TabContainer": _make_tab_container,
    "TagButton": _make_tag_button,
    "TagCompleterItemWidget": _make_tag_completer_item,
    "TagCompleterPopup": _make_tag_completer_popup,
    "TagSelectWindow": _make_tag_select_window,
    "ToggleSwitch": _make_toggle_switch,
    "TopBar": _make_top_bar,
    "UserAvatar": _make_user_avatar,
    "VirtualListView": _make_virtual_list_view,
    "VirtualTableView": _make_virtual_table_view,
    "VisionCapabilityBadge": _make_vision_capability_badge,
    "VisionCapabilityNotice": _make_vision_capability_notice,
    "WozniakCardItemWidget": _make_wozniak_card_item,
    "WozniakHubWidget": _make_wozniak_hub,
    "WozniakKpiCard": _make_wozniak_kpi_card,
}

#: Identifiants des classes incarnées par chaque entrée. La valeur est le nom
#: simple de la classe ; les homonymes inter-modules sont qualifiés par leur module
#: afin que les deux ``ClickableLabel`` restent contrôlés séparément.
_CLASS_ID_OVERRIDES: dict[str, str] = {
    "ClickableLabel": "ankiforge.ui.components.sidebar.ClickableLabel",
    "ClickableLabel (topbar)": "ankiforge.ui.components.topbar.ClickableLabel",
}

#: Identifiant de classe déclaré par chaque entrée (les homonymes restent traçables).
COMPONENT_CLASS_IDS: dict[str, str] = {key: _CLASS_ID_OVERRIDES.get(key, key) for key in COMPONENT_FACTORIES}


def component_labels() -> dict[str, str]:
    """Libellés français affichés dans l'arbre de la galerie (extractibles par lupdate)."""
    return {
        "ActionButton": tr("Bouton d'action"),
        "ActivityItem": tr("Élément d'activité"),
        "AutoExpandingTextEdit": tr("Zone de texte auto-extensible"),
        "Badge": tr("Badge"),
        "BreadcrumbSegmentButton": tr("Segment de fil d'Ariane"),
        "CapabilityPill": tr("Pastille de capacité"),
        "CicdTable": tr("Tableau CI/CD"),
        "ClickableLabel": tr("Libellé cliquable"),
        "ClickableLabel (topbar)": tr("Libellé cliquable (barre supérieure)"),
        "CodeEditorWithGutter": tr("Éditeur de code avec gouttière"),
        "ContextItem": tr("Élément de contexte"),
        "DBComboBox": tr("Liste déroulante liée à la base"),
        "DaemonStatusWidget": tr("État du démon"),
        "DangerButton": tr("Bouton destructif"),
        "DeckSelectWindow": tr("Sélection de paquet"),
        "DocTreeItem": tr("Élément d'arborescence documentaire"),
        "DocumentPickerButton": tr("Bouton de sélection de document"),
        "DocumentSelectWindow": tr("Sélection de document"),
        "DuplicateMatrixTable": tr("Matrice des doublons"),
        "DuplicateMergeInspector": tr("Inspecteur de fusion des doublons"),
        "ElidedLabel": tr("Libellé tronqué"),
        "EmptyStateWidget": tr("État vide"),
        "FieldInspectorWidget": tr("Inspecteur de champs"),
        "FilterChipButton": tr("Puce de filtre"),
        "FloatingDockWindow": tr("Fenêtre de dock flottante"),
        "FlowWidget": tr("Conteneur fluide"),
        "GlassPanel": tr("Panneau vitré"),
        "GlobalTitleBar": tr("Barre de titre globale"),
        "GlowLineEdit": tr("Champ de recherche lumineux"),
        "HierarchyBreadcrumbBar": tr("Fil d'Ariane hiérarchique"),
        "IconButton": tr("Bouton icône"),
        "IdePanel": tr("Panneau IDE"),
        "IdeTabBar": tr("Barre d'onglets IDE"),
        "KatexLivePreviewWidget": tr("Aperçu KaTeX en direct"),
        "LineNumberArea": tr("Gouttière de numéros de ligne (dans l'éditeur)"),
        "LintStatusBar": tr("Barre d'état du linter (sous l'éditeur)"),
        "LinterRulesManagerDialog": tr("Gestionnaire des règles du linter"),
        "MetricCard": tr("Carte de métrique"),
        "ModalField": tr("Champ modal"),
        "ModelCapabilityBadgesWidget": tr("Badges de capacités du modèle"),
        "ModelCardWidget": tr("Carte de modèle IA"),
        "ModelComboBox": tr("Liste déroulante de modèles"),
        "ModelDiscoveryDialog": tr("Exploration des modèles IA"),
        "ModelSelectWindow": tr("Sélection de type de note"),
        "ModelSelectorWidget": tr("Sélecteur de modèle"),
        "NativeCodeEditor": tr("Éditeur de code natif"),
        "NavBadgeButton": tr("Bouton de navigation avec badge"),
        "OptionToggleRow": tr("Ligne d'option à bascule"),
        "PanelDragOverlay": tr("Superposition de glissement de panneau"),
        "PanelPlaceholderWidget": tr("Emplacement de panneau"),
        "PersonaSelectWindow": tr("Sélection d'agent"),
        "PillTabBar": tr("Barre d'onglets pastilles"),
        "PipelineSelectWindow": tr("Sélection de pipeline"),
        "PremiumActionCard": tr("Carte d'action premium"),
        "PrimaryButton": tr("Bouton principal"),
        "ScrollableTabBarWidget": tr("Barre d'onglets défilante"),
        "SecondaryButton": tr("Bouton secondaire"),
        "SegmentedTabBar": tr("Barre d'onglets segmentée"),
        "SegmentedTabButton": tr("Bouton d'onglet segmenté"),
        "SettingsTabBar": tr("Barre d'onglets de réglages"),
        "Sidebar": tr("Barre latérale"),
        "SidebarItem": tr("Élément de barre latérale"),
        "SidebarProfileItem": tr("Élément de profil de barre latérale"),
        "SnippetCardWidget": tr("Carte de snippet"),
        "SnippetLibraryDrawer": tr("Bibliothèque de snippets"),
        "SourceDiagnosticCardWidget": tr("Carte de diagnostic de source"),
        "StatCard": tr("Carte de statistique"),
        "StatusBadge": tr("Badge d'état avec icône"),
        "StyledComboBox": tr("Liste déroulante stylisée"),
        "StyledLineEdit": tr("Champ de saisie stylisé"),
        "StyledListItem": tr("Élément de liste stylisé"),
        "StyledTableWidget": tr("Tableau stylisé"),
        "StyledTextEdit": tr("Zone de texte stylisée"),
        "StyledToolbar": tr("Barre d'outils stylisée"),
        "SubTabButton": tr("Sous-onglet"),
        "TabButton": tr("Bouton d'onglet"),
        "TabContainer": tr("Conteneur d'onglets"),
        "TagButton": tr("Puce de tag"),
        "TagCompleterItemWidget": tr("Élément d'autocomplétion de tag"),
        "TagCompleterPopup": tr("Pop-up d'autocomplétion de tags"),
        "TagSelectWindow": tr("Sélection de tags"),
        "ToggleSwitch": tr("Interrupteur"),
        "TopBar": tr("Barre supérieure"),
        "UserAvatar": tr("Avatar utilisateur"),
        "VirtualListView": tr("Liste virtuelle"),
        "VirtualTableView": tr("Tableau virtuel"),
        "VisionCapabilityBadge": tr("Badge de capacité visuelle"),
        "VisionCapabilityNotice": tr("Avis de capacité visuelle"),
        "WozniakCardItemWidget": tr("Carte problème Wozniak"),
        "WozniakHubWidget": tr("Hub d'audit Wozniak"),
        "WozniakKpiCard": tr("Carte KPI Wozniak"),
    }


def register() -> None:
    """Enregistre les composants dans la galerie (idempotent)."""
    labels = component_labels()
    for key, factory in COMPONENT_FACTORIES.items():
        label = labels.get(key)
        if label is None:
            logger.warning("Libellé de galerie manquant pour le composant « %s »", key)
            label = key
        gallery_widget(family="components", name=label)(factory)
