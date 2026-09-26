"""
Tests headless PySide6 pour MCP-ADV-05 : EmbeddedCardTableWidget et EmbeddedCardPreviewWidget.
Vérifie l'insertion dans le layout de chat, la mise à jour des données, le basculement en mode figé,
la propagation des signaux et la conformité des thèmes DesignTokens.
"""

from __future__ import annotations

from typing import Any

from ankiforge.ui.views.consultant_view.widgets.chat_message_widget import ChatMessageWidget
from ankiforge.ui.views.consultant_view.widgets.embedded_card_preview_widget import EmbeddedCardPreviewWidget
from ankiforge.ui.views.consultant_view.widgets.embedded_card_table_widget import EmbeddedCardTableWidget

# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

SAMPLE_ROWS: list[dict[str, Any]] = [
    {"id": 1, "model": "Basique", "front": "Qu'est-ce que le SRS ?", "back": "Spaced Repetition System."},
    {"id": 2, "model": "Cloze", "front": "Python est un langage {{c1::interprété}}", "back": "Python est un langage interprété"},
    {"id": 3, "model": "Basique", "front": "Formule $E=mc^2$", "back": "Énergie-masse."},
]

SAMPLE_FIELDS: dict[str, str] = {
    "Front": "Qu'est-ce que le SRS ?",
    "Back": "Spaced Repetition System.",
}


# ===========================================================================
# EmbeddedCardTableWidget
# ===========================================================================


class TestEmbeddedCardTableWidget:
    """Tests pour EmbeddedCardTableWidget."""

    def test_creation_with_rows(self, qtbot: Any) -> None:
        """Le widget s'initialise correctement avec une liste de cartes."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        assert w.table.rowCount() == 3
        assert not w.is_frozen

    def test_creation_with_empty_rows(self, qtbot: Any) -> None:
        """Le widget accepte une liste vide sans erreur."""
        w = EmbeddedCardTableWidget([])
        qtbot.addWidget(w)
        assert w.table.rowCount() == 0

    def test_title_displayed(self, qtbot: Any) -> None:
        """Le titre personnalisé est affiché dans l'en-tête."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS, title="Résultats de diagnostic")
        qtbot.addWidget(w)
        assert "Résultats de diagnostic" in w.lbl_title.text()

    def test_count_label(self, qtbot: Any) -> None:
        """Le badge de count indique le nombre correct de cartes."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        assert "3" in w.lbl_count.text()

    def test_count_label_singular(self, qtbot: Any) -> None:
        """Le badge de count utilise le singulier pour une seule carte."""
        w = EmbeddedCardTableWidget([SAMPLE_ROWS[0]])
        qtbot.addWidget(w)
        assert "1 carte" in w.lbl_count.text()
        assert "cartes" not in w.lbl_count.text()

    def test_columns(self, qtbot: Any) -> None:
        """Le tableau a bien 5 colonnes (ID, Modèle, Recto, Verso, Action)."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        assert w.table.columnCount() == 5

    def test_note_id_data_role(self, qtbot: Any) -> None:
        """La colonne ID stocke bien l'ID en UserRole pour un accès programmatique."""
        from PySide6.QtCore import Qt

        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        item = w.table.item(0, 0)
        assert item is not None
        assert item.data(Qt.ItemDataRole.UserRole) == 1

    def test_open_editor_signal_emitted(self, qtbot: Any) -> None:
        """Le signal open_editor_requested est émis avec le bon note_id au clic."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        received: list[int] = []
        w.open_editor_requested.connect(received.append)

        # Simule le clic sur le bouton ↗ de la première ligne
        from PySide6.QtWidgets import QPushButton

        cell = w.table.cellWidget(0, 4)
        assert cell is not None
        btn = cell.findChild(QPushButton)
        assert btn is not None
        btn.click()

        assert received == [1]

    def test_update_rows(self, qtbot: Any) -> None:
        """update_rows met à jour les données sans erreur."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        new_rows = [{"id": 99, "model": "Nouveau", "front": "F", "back": "B"}]
        w.update_rows(new_rows)
        assert w.table.rowCount() == 1

    def test_freeze_disables_buttons(self, qtbot: Any) -> None:
        """freeze() désactive les boutons ↗ de toutes les lignes."""
        from PySide6.QtWidgets import QPushButton

        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        w.freeze(timestamp="2026-09-26")
        assert w.is_frozen

        for row_idx in range(w.table.rowCount()):
            cell = w.table.cellWidget(row_idx, 4)
            if cell:
                for btn in cell.findChildren(QPushButton):
                    assert not btn.isEnabled()

    def test_freeze_shows_badge(self, qtbot: Any) -> None:
        """freeze() affiche le badge de statut figé dans l'en-tête."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        w.freeze(timestamp="T+0")
        # En mode headless, on teste que le badge n'est pas explicitement caché
        assert not w.lbl_frozen_badge.isHidden()
        assert "Figé" in w.lbl_frozen_badge.text()

    def test_freeze_prevents_update_rows(self, qtbot: Any) -> None:
        """update_rows est ignoré après freeze()."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        w.freeze()
        w.update_rows([])  # Doit être ignoré
        assert w.table.rowCount() == 3  # Toujours les données initiales

    def test_freeze_idempotent(self, qtbot: Any) -> None:
        """Appeler freeze() deux fois ne cause pas d'erreur."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        w.freeze()
        w.freeze()  # Doit être un no-op
        assert w.is_frozen

    def test_truncate_short_text(self) -> None:
        """_truncate retourne le texte intact si plus court que max_len."""
        result = EmbeddedCardTableWidget._truncate("Bonjour", 60)
        assert result == "Bonjour"

    def test_truncate_long_text(self) -> None:
        """_truncate tronque et ajoute '…' pour les textes longs."""
        long_text = "A" * 80
        result = EmbeddedCardTableWidget._truncate(long_text, 60)
        assert result.endswith("…")
        assert len(result) == 61  # 60 + '…'

    def test_truncate_removes_html_tags(self) -> None:
        """_truncate supprime les balises HTML pour la prévisualisation."""
        html_text = "<b>Bonjour</b> monde"
        result = EmbeddedCardTableWidget._truncate(html_text, 60)
        assert "<b>" not in result
        assert "Bonjour monde" in result

    def test_refresh_theme_no_error(self, qtbot: Any) -> None:
        """refresh_theme() s'exécute sans erreur."""
        w = EmbeddedCardTableWidget(SAMPLE_ROWS)
        qtbot.addWidget(w)
        w.refresh_theme()  # Doit finir sans exception


# ===========================================================================
# EmbeddedCardPreviewWidget
# ===========================================================================


class TestEmbeddedCardPreviewWidget:
    """Tests pour EmbeddedCardPreviewWidget."""

    def test_creation_no_note_type(self, qtbot: Any) -> None:
        """Le widget s'initialise sans modèle de note, en mode fallback générique."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        assert not w.is_frozen
        assert w._is_recto

    def test_side_badge_initial_recto(self, qtbot: Any) -> None:
        """Le badge de côté affiche RECTO par défaut."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        assert "RECTO" in w.lbl_side_badge.text()

    def test_flip_toggles_side(self, qtbot: Any) -> None:
        """_on_flip bascule le flag _is_recto et met à jour le badge et le bouton."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        assert w._is_recto

        w._on_flip()
        assert not w._is_recto
        assert "VERSO" in w.lbl_side_badge.text()
        assert "Recto" in w.btn_flip.text()

        w._on_flip()
        assert w._is_recto
        assert "RECTO" in w.lbl_side_badge.text()

    def test_freeze_disables_flip_button(self, qtbot: Any) -> None:
        """freeze() désactive le bouton Recto/Verso."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        w.freeze()
        assert not w.btn_flip.isEnabled()

    def test_freeze_shows_badge(self, qtbot: Any) -> None:
        """freeze() affiche le badge de statut figé."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        w.freeze(timestamp="2026-09-26T10:00")
        # En mode headless, on teste que le badge n'est pas explicitement caché
        assert not w.lbl_frozen_badge.isHidden()
        assert "Figé" in w.lbl_frozen_badge.text()

    def test_freeze_prevents_flip(self, qtbot: Any) -> None:
        """Le flip est ignoré après freeze()."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        w.freeze()
        w._on_flip()  # Doit être ignoré
        assert w._is_recto  # Toujours sur le Recto

    def test_freeze_idempotent(self, qtbot: Any) -> None:
        """Appeler freeze() deux fois ne cause pas d'erreur."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        w.freeze()
        w.freeze()
        assert w.is_frozen

    def test_freeze_prevents_update_fields(self, qtbot: Any) -> None:
        """update_fields est ignoré après freeze()."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        w.freeze()
        original_fields = dict(w._fields)
        w.update_fields({"Front": "Nouveau texte", "Back": "Nouveau dos"})
        assert w._fields == original_fields

    def test_update_fields_before_freeze(self, qtbot: Any) -> None:
        """update_fields met à jour les données avant le freeze."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        new_fields = {"Front": "Nouveau", "Back": "Dos nouveau"}
        w.update_fields(new_fields)
        assert w._fields == new_fields

    def test_open_editor_signal_emitted(self, qtbot: Any) -> None:
        """open_editor_requested est émis avec le bon note_id via le bouton ↗."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS, note_id=42)
        qtbot.addWidget(w)
        received: list[int] = []
        w.open_editor_requested.connect(received.append)
        assert hasattr(w, "btn_open")
        w.btn_open.click()
        assert received == [42]

    def test_no_open_button_without_note_id(self, qtbot: Any) -> None:
        """Aucun bouton Ouvrir dans l'Éditeur si note_id est None."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS, note_id=None)
        qtbot.addWidget(w)
        assert not hasattr(w, "btn_open")

    def test_fallback_label_used_in_headless(self, qtbot: Any) -> None:
        """En mode headless sans WebEngine, le fallback QLabel est utilisé."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        # En mode headless, SafeWebEngineView peut être créée ou non selon l'env
        # L'important est qu'au moins l'un des deux modes (web/fallback) soit actif
        has_rendering = w._web_view is not None or w._fallback_lbl is not None
        assert has_rendering

    def test_refresh_theme_no_error(self, qtbot: Any) -> None:
        """refresh_theme() s'exécute sans erreur."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS)
        qtbot.addWidget(w)
        w.refresh_theme()

    def test_title_displayed(self, qtbot: Any) -> None:
        """Le titre personnalisé est affiché dans l'en-tête."""
        w = EmbeddedCardPreviewWidget(SAMPLE_FIELDS, title="Aperçu KaTeX")
        qtbot.addWidget(w)
        assert "Aperçu KaTeX" in w.lbl_title.text()


# ===========================================================================
# ChatMessageWidget — Injection des composants riches
# ===========================================================================


class TestChatMessageWidgetRichComponents:
    """Vérifie l'injection des composants riches dans ChatMessageWidget."""

    def test_add_card_table_creates_widget(self, qtbot: Any) -> None:
        """add_card_table() insère un EmbeddedCardTableWidget dans le layout de contenu."""
        msg = ChatMessageWidget("AnkiForge AI", "", is_user=False)
        qtbot.addWidget(msg)

        table_w = msg.add_card_table(SAMPLE_ROWS)
        assert isinstance(table_w, EmbeddedCardTableWidget)
        assert table_w.table.rowCount() == 3

    def test_add_card_table_connects_open_editor(self, qtbot: Any) -> None:
        """open_editor_requested de EmbeddedCardTableWidget est relié à celui de ChatMessageWidget."""
        msg = ChatMessageWidget("AnkiForge AI", "", is_user=False)
        qtbot.addWidget(msg)
        received: list[int] = []
        msg.open_editor_requested.connect(received.append)

        table_w = msg.add_card_table(SAMPLE_ROWS)

        from PySide6.QtWidgets import QPushButton

        cell = table_w.table.cellWidget(0, 4)
        assert cell is not None
        btn = cell.findChild(QPushButton)
        assert btn is not None
        btn.click()

        assert received == [1]

    def test_add_card_preview_creates_widget(self, qtbot: Any) -> None:
        """add_card_preview() insère un EmbeddedCardPreviewWidget dans le layout de contenu."""
        msg = ChatMessageWidget("AnkiForge AI", "", is_user=False)
        qtbot.addWidget(msg)

        preview_w = msg.add_card_preview(SAMPLE_FIELDS)
        assert isinstance(preview_w, EmbeddedCardPreviewWidget)
        assert not preview_w.is_frozen

    def test_add_card_preview_with_note_id_connects_signal(self, qtbot: Any) -> None:
        """Le signal open_editor_requested est relié quand note_id est fourni."""
        msg = ChatMessageWidget("AnkiForge AI", "", is_user=False)
        qtbot.addWidget(msg)
        received: list[int] = []
        msg.open_editor_requested.connect(received.append)

        preview_w = msg.add_card_preview(SAMPLE_FIELDS, note_id=7)
        assert hasattr(preview_w, "btn_open")
        preview_w.btn_open.click()

        assert received == [7]

    def test_multiple_rich_components_coexist(self, qtbot: Any) -> None:
        """Plusieurs composants riches (table + preview) peuvent coexister dans une même bulle."""
        msg = ChatMessageWidget("AnkiForge AI", "", is_user=False)
        qtbot.addWidget(msg)

        table_w = msg.add_card_table(SAMPLE_ROWS, title="Table 1")
        preview_w = msg.add_card_preview(SAMPLE_FIELDS, title="Preview 1")

        assert isinstance(table_w, EmbeddedCardTableWidget)
        assert isinstance(preview_w, EmbeddedCardPreviewWidget)
        # Les deux doivent être dans le layout content
        found_table = found_preview = False
        for i in range(msg.content_layout.count()):
            item = msg.content_layout.itemAt(i)
            if item and isinstance(item.widget(), EmbeddedCardTableWidget):
                found_table = True
            if item and isinstance(item.widget(), EmbeddedCardPreviewWidget):
                found_preview = True
        assert found_table
        assert found_preview
