"""
Gestionnaire d'autocomplétion des mentions inline (@deck:, @doc:, @model:, @card:)
et des commandes rapides Slash (/clear, /undo, /compact, /panorama, /deepscan, /help) pour le Consultant IA.
"""

from __future__ import annotations

import json
import logging

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import QCompleter, QWidget

from ankiforge.database.models import DeckModel, DocumentModel, NoteModel, NoteTypeModel
from ankiforge.ui.theme import DesignTokens

logger = logging.getLogger(__name__)

SLASH_COMMANDS: list[tuple[str, str, str]] = [
    ("/clear", "slash", "Effacer l'historique et la mémoire de la session"),
    ("/compact", "slash", "Compacter le contexte actif et libérer des tokens"),
    ("/undo", "slash", "Annuler la dernière modification de carte via Time Machine"),
    ("/panorama", "slash", "Lancer un panorama 360° global de la collection"),
    ("/deepscan", "slash", "Lancer un scan approfondi du paquet actif"),
    ("/help", "slash", "Afficher la documentation des outils et commandes"),
]


class MentionCompleter(QCompleter):
    """Compléteur intelligent pour les mentions (@) et les commandes slash (/)."""

    mention_selected = Signal(str, str)  # type (ex: "deck", "slash"), identifier/command

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parent is not None:
            self.setWidget(parent)

        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.list_model = QStringListModel(self)
        self.setModel(self.list_model)
        self._current_items: list[tuple[str, str, str]] = []  # (display, type, identifier)
        self.activated.connect(self._on_activated)

        popup = self.popup()
        if popup is not None:
            popup.setStyleSheet(f"""
                QListView {{
                    background-color: {DesignTokens.BG_PANEL};
                    color: {DesignTokens.TEXT_PRIMARY};
                    border: 1px solid {DesignTokens.ACCENT_PRIMARY};
                    border-radius: {DesignTokens.RADIUS_SM}px;
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
            """)

    def update_completions(self, text_prefix: str, trigger_char: str = "@") -> None:
        """Met à jour les options selon le caractère déclencheur (@ ou /)."""
        self._current_items.clear()

        if trigger_char == "/":
            # Commandes Slash
            clean_prefix = text_prefix.strip().lower()
            for cmd, _c_type, desc in SLASH_COMMANDS:
                if clean_prefix == "" or cmd.lower().startswith("/" + clean_prefix) or clean_prefix in cmd.lower():
                    self._current_items.append((f"{cmd}  —  {desc}", "slash", cmd))
        else:
            # Mentions (@)
            try:
                clean_filter = text_prefix.replace("@", "").strip().lower()

                # 1. Paquets (@deck:)
                for d in DeckModel.select().limit(30):
                    if not clean_filter or clean_filter in d.name.lower() or "deck" in clean_filter:
                        self._current_items.append((f"@deck:{d.name}", "deck", str(d.id)))

                # 2. Documents (@doc:)
                for doc in DocumentModel.select().limit(30):
                    if not clean_filter or clean_filter in doc.title.lower() or "doc" in clean_filter:
                        self._current_items.append((f"@doc:{doc.title}", "doc", str(doc.id)))

                # 3. Modèles de cartes (@model:)
                for nt in NoteTypeModel.select().limit(25):
                    fields_repr = ""
                    if nt.fields_schema:
                        try:
                            f_list = json.loads(nt.fields_schema)
                            if isinstance(f_list, list):
                                fields_repr = f" — [{', '.join(f_list[:4])}{'...' if len(f_list) > 4 else ''}]"
                        except Exception:
                            pass
                    display_text = f"@model:{nt.name}{fields_repr}"
                    if not clean_filter or clean_filter in nt.name.lower() or "model" in clean_filter:
                        self._current_items.append((display_text, "model", str(nt.name)))

                # 4. Notes / Cartes (@card:) avec aperçu de la question
                from ankiforge.database.models import NoteVersionModel

                query_notes = NoteModel.select().order_by(NoteModel.id.desc()).limit(35)
                for n in query_notes:
                    active_v = n.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
                    snippet = ""
                    if active_v and active_v.content:
                        try:
                            d_parsed = json.loads(active_v.content)
                            snippet = d_parsed.get("Front", d_parsed.get("Recto", active_v.content))
                        except Exception:
                            snippet = active_v.content

                    snippet_clean = str(snippet).replace("\n", " ").strip()
                    short_snippet = snippet_clean[:38] + ("..." if len(snippet_clean) > 38 else "")
                    display_text = f"@card:{n.id} — {short_snippet}" if short_snippet else f"@card:{n.id}"

                    if not clean_filter or str(n.id) in clean_filter or clean_filter in snippet_clean.lower() or "card" in clean_filter or "note" in clean_filter:
                        self._current_items.append((display_text, "card", str(n.id)))

            except Exception as e:
                logger.debug("Erreur lors de la récupération des mentions : %s", e)

        display_list = [item[0] for item in self._current_items]
        self.list_model.setStringList(display_list)

    def _on_activated(self, text: str) -> None:
        for display, m_type, m_id in self._current_items:
            if text == display:
                self.mention_selected.emit(m_type, m_id)
                break
