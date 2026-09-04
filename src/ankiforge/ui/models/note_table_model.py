"""
Modèle de tableau virtuel paginé pour l'explorateur de notes et la vue d'Édition (AnkiForge).
Fournit un rendu instantané, un préchargement par lot (Batch Prefetch) des versions actives
et une virtualisation totale compatible 100 000+ cartes à 60 FPS.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import peewee
from PySide6.QtCore import QModelIndex, QPersistentModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from ankiforge.database.models import CardModel, DeckModel, NoteModel, NoteVersionModel
from ankiforge.ui.models.delegates import (
    BADGE_BG_COLOR_ROLE,
    BADGE_TEXT_COLOR_ROLE,
    FLAG_ROLE,
    IS_INVALID_CARD_ROLE,
    NOTE_ID_ROLE,
    RAW_CONTENT_ROLE,
    TAGS_LIST_ROLE,
)
from ankiforge.ui.models.paginated_model import BasePaginatedPeeweeModel
from ankiforge.ui.theme import DesignTokens

logger = logging.getLogger(__name__)
_ROOT_INDEX = QModelIndex()

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: Any) -> str:
    """Épure le HTML brut d'une chaîne de caractères pour affichage compact."""
    if text is None:
        return ""
    s = str(text)
    s = _HTML_TAG_RE.sub("", s)
    return s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").strip()


@dataclass
class NoteRowData:
    """Représentation aplatie et optimisée en mémoire d'une ligne de note."""

    note_id: int
    guid: str
    checked: bool = False
    flag: int = 0
    recto: str = ""
    verso: str = ""
    fields_dict: dict[str, str] = field(default_factory=dict)
    model_name: str = "Inconnu"
    deck_name: str = "Par défaut"
    tags_list: list[str] = field(default_factory=list)
    tags_display: str = ""
    version_num: int = 1
    is_invalid: bool = False
    raw_note: NoteModel | None = None


class NoteVirtualTableModel(BasePaginatedPeeweeModel[NoteRowData]):
    """
    Modèle de tableau virtuel paginé pour NoteModel.
    Gère les colonnes génériques (Checkbox / Drapeau / Recto / Autres / Modèle / Deck / Tags)
    ou dynamiques (quand un modèle de note spécifique est sélectionné).
    """

    def __init__(
        self,
        query: peewee.Query | None = None,
        total_count: int | None = None,
        active_model_fields: list[str] | None = None,
        chunk_size: int = 100,
        parent: Any | None = None,
    ) -> None:
        self._active_model_fields: list[str] | None = active_model_fields
        self._checked_note_ids: set[int] = set()
        self._all_checked_mode: bool = False
        self._unchecked_note_ids: set[int] = set()
        self._headers: list[str] = []
        self._update_headers()
        super().__init__(query=query, total_count=total_count, chunk_size=chunk_size, parent=parent)

    # --- Configuration des En-têtes & Colonnes ---

    def _update_headers(self) -> None:
        if self._active_model_fields:
            self._headers = ["", ""] + list(self._active_model_fields) + ["Deck", "Tags"]
        else:
            self._headers = ["", "", "Recto (Tri)", "Autres champs", "Modèle", "Deck", "Tags"]

    def set_active_model_fields(self, fields: list[str] | None) -> None:
        """Change le schéma des colonnes affichées."""
        self.beginResetModel()
        self._active_model_fields = fields
        self._update_headers()
        self.endResetModel()

    def set_filter_query(
        self,
        query: peewee.Query,
        total_count: int | None = None,
        active_model_fields: list[str] | None = None,
    ) -> None:
        """Met à jour la requête de filtrage et recharge le premier lot."""
        self.beginResetModel()
        self._base_query = query
        self._loaded_rows.clear()
        self._checked_note_ids.clear()
        self._all_checked_mode = False
        self._unchecked_note_ids.clear()
        self._active_model_fields = active_model_fields
        self._update_headers()
        try:
            self._total_count = total_count if total_count is not None else query.count()
        except Exception as e:
            logger.warning("Erreur calcul total_count dans NoteVirtualTableModel: %s", e)
            self._total_count = 0
        self.endResetModel()

        if self._total_count > 0:
            self._load_initial_batch()

    # --- Contrat Qt AbstractTableModel ---

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = _ROOT_INDEX) -> int:
        if parent.isValid():
            return 0
        return len(self._headers)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if orientation == Qt.Orientation.Horizontal:
            if role == Qt.ItemDataRole.DisplayRole and 0 <= section < len(self._headers):
                return self._headers[section]
            if role == Qt.ItemDataRole.TextAlignmentRole:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index: QModelIndex | QPersistentModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        base_flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            return base_flags | Qt.ItemFlag.ItemIsUserCheckable
        return base_flags

    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or index.row() >= len(self._loaded_rows):
            return None

        row_data = self._loaded_rows[index.row()]
        col = index.column()

        # ── Rôles Spéciaux Universels ──
        if role == NOTE_ID_ROLE:
            return row_data.note_id
        if role == RAW_CONTENT_ROLE:
            return row_data.fields_dict
        if role == Qt.ItemDataRole.UserRole:
            return row_data.raw_note

        # ── Colonne 0 : Case à Cocher ──
        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                is_checked = row_data.note_id not in self._unchecked_note_ids if self._all_checked_mode else row_data.note_id in self._checked_note_ids
                return Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            return None

        # ── Colonne 1 : Drapeau Anki ──
        if col == 1:
            if role == FLAG_ROLE:
                return row_data.flag
            if role == Qt.ItemDataRole.ToolTipRole:
                flag_name = DesignTokens.FLAG_NAMES.get(row_data.flag, "Aucun")
                return f"Drapeau : {flag_name}" if row_data.flag > 0 else "Définir un drapeau"
            if role == Qt.ItemDataRole.DisplayRole:
                return ""
            return None

        # ── Mode Dynamique (Modèle Unique Sélectionné) ──
        if self._active_model_fields:
            num_fields = len(self._active_model_fields)
            deck_col = 2 + num_fields
            tags_col = deck_col + 1

            if 2 <= col <= 1 + num_fields:
                field_name = self._active_model_fields[col - 2]
                val = row_data.fields_dict.get(field_name, "")
                if role == Qt.ItemDataRole.DisplayRole:
                    return val[:120]
                if role == Qt.ItemDataRole.FontRole and col == 2:
                    return QFont(DesignTokens.FONT_CODE, 10)
                if role == Qt.ItemDataRole.ForegroundRole and col > 2:
                    return QColor(DesignTokens.TEXT_SECONDARY)
                if role == IS_INVALID_CARD_ROLE and col == 2:
                    return row_data.is_invalid

            elif col == deck_col:
                if role == Qt.ItemDataRole.DisplayRole:
                    return row_data.deck_name
                if role == BADGE_BG_COLOR_ROLE:
                    return "rgba(99, 102, 241, 0.15)"
                if role == BADGE_TEXT_COLOR_ROLE:
                    return DesignTokens.ACCENT_PRIMARY

            elif col == tags_col:
                if role == Qt.ItemDataRole.DisplayRole:
                    return row_data.tags_display
                if role == TAGS_LIST_ROLE:
                    return row_data.tags_list

            return None

        # ── Mode Standard (Tous les Modèles / Mixte) ──
        # Headers: ["", "", "Recto (Tri)", "Autres champs", "Modèle", "Deck", "Tags"]
        if col == 2:  # Recto
            if role == Qt.ItemDataRole.DisplayRole:
                return row_data.recto[:120]
            if role == Qt.ItemDataRole.FontRole:
                return QFont(DesignTokens.FONT_CODE, 10)
            if role == IS_INVALID_CARD_ROLE:
                return row_data.is_invalid
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(DesignTokens.COLOR_RED) if row_data.is_invalid else QColor(DesignTokens.TEXT_PRIMARY)

        elif col == 3:  # Verso / Autres champs
            if role == Qt.ItemDataRole.DisplayRole:
                return row_data.verso[:120]
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(DesignTokens.TEXT_SECONDARY)

        elif col == 4:  # Modèle
            if role == Qt.ItemDataRole.DisplayRole:
                return row_data.model_name
            if role == BADGE_BG_COLOR_ROLE:
                return DesignTokens.BG_INPUT
            if role == BADGE_TEXT_COLOR_ROLE:
                return DesignTokens.TEXT_MUTED

        elif col == 5:  # Deck
            if role == Qt.ItemDataRole.DisplayRole:
                return row_data.deck_name
            if role == BADGE_BG_COLOR_ROLE:
                return "rgba(99, 102, 241, 0.15)"
            if role == BADGE_TEXT_COLOR_ROLE:
                return DesignTokens.ACCENT_PRIMARY

        elif col == 6:  # Tags
            if role == Qt.ItemDataRole.DisplayRole:
                return row_data.tags_display
            if role == TAGS_LIST_ROLE:
                return row_data.tags_list

        return None

    def setData(self, index: QModelIndex | QPersistentModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if not index.isValid() or index.row() >= len(self._loaded_rows):
            return False

        row_data = self._loaded_rows[index.row()]
        if index.column() == 1 and role == FLAG_ROLE:
            row_data.flag = int(value or 0)
            self.dataChanged.emit(index, index, [FLAG_ROLE, Qt.ItemDataRole.ToolTipRole])
            return True

        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            checked = value == Qt.CheckState.Checked
            row_data.checked = checked
            if self._all_checked_mode:
                if checked:
                    self._unchecked_note_ids.discard(row_data.note_id)
                else:
                    self._unchecked_note_ids.add(row_data.note_id)
            else:
                if checked:
                    self._checked_note_ids.add(row_data.note_id)
                else:
                    self._checked_note_ids.discard(row_data.note_id)

            self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
            return True

        return False

    # --- Traitement Haute Performance par Lot (Batch Prefetch) ---

    def _process_batch(self, raw_items: list[Any]) -> list[NoteRowData]:
        if not raw_items:
            return []

        note_ids = [n.id for n in raw_items if n and n.id]
        if not note_ids:
            return []

        # 1. Requête groupée des versions actives en 1 aller-retour SQL
        content_by_note_id: dict[int, dict[str, str]] = {}
        version_num_by_note_id: dict[int, int] = {}
        try:
            active_versions = NoteVersionModel.select().where(
                (NoteVersionModel.note.in_(note_ids)) & (NoteVersionModel.is_active == True)  # noqa: E712
            )
            for v in active_versions:
                if v.content:
                    try:
                        parsed = json.loads(v.content)
                        if isinstance(parsed, dict):
                            content_by_note_id[v.note_id] = {str(k): strip_html(val) for k, val in parsed.items()}
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                version_num_by_note_id[v.note_id] = getattr(v, "version_number", 1)
        except Exception as e:
            logger.warning("Erreur préchargement NoteVersionModel: %s", e)

        # 2. Requête groupée des paquets et drapeaux (CardModel ➔ DeckModel)
        deck_by_note_id: dict[int, str] = {}
        flag_by_note_id: dict[int, int] = {}
        try:
            cards = CardModel.select(CardModel.note, CardModel.flags, DeckModel.name).join(DeckModel).where(CardModel.note.in_(note_ids))
            for c in cards:
                if c.note_id not in deck_by_note_id and c.deck:
                    deck_by_note_id[c.note_id] = c.deck.name
                c_flag = int(getattr(c, "flags", 0) or 0)
                if c_flag > 0:
                    flag_by_note_id[c.note_id] = max(flag_by_note_id.get(c.note_id, 0), c_flag)
        except Exception as e:
            logger.warning("Erreur préchargement DeckModel et drapeaux: %s", e)

        # 3. Assemblage vectorisé des structures NoteRowData
        results: list[NoteRowData] = []
        for note in raw_items:
            nid = note.id
            fields_data = content_by_note_id.get(nid, {})
            if not fields_data:
                # Repli dynamique si aucune version active trouvée
                fields_data = self._extract_fallback_content(note)

            vals = list(fields_data.values())
            recto = vals[0] if len(vals) > 0 else ""
            verso = " | ".join(vals[1:]) if len(vals) > 1 else ""

            is_invalid = not recto.strip()
            if is_invalid:
                recto = "⚠️ CARTE INVALIDE (Recto vide)"

            # Nom du modèle
            nt_name = note.note_type.name if (note.note_type and hasattr(note.note_type, "name")) else "Inconnu"

            # Nom du dossier / paquet
            folder_name = getattr(note, "_deck_name", None) or deck_by_note_id.get(nid, "Par défaut")

            # Parsing des tags
            tags_list = self._parse_tags(note.tags)
            tags_display = "  ".join(f"#{t}" for t in tags_list) if tags_list else ""

            row_obj = NoteRowData(
                note_id=nid,
                guid=str(getattr(note, "guid", "")),
                checked=(nid not in self._unchecked_note_ids if self._all_checked_mode else nid in self._checked_note_ids),
                flag=flag_by_note_id.get(nid, 0),
                recto=recto,
                verso=verso,
                fields_dict=fields_data,
                model_name=nt_name,
                deck_name=folder_name,
                tags_list=tags_list,
                tags_display=tags_display,
                version_num=version_num_by_note_id.get(nid, 1),
                is_invalid=is_invalid,
                raw_note=note,
            )
            results.append(row_obj)

        return results

    def _extract_fallback_content(self, note: NoteModel) -> dict[str, str]:
        """Extrait le contenu depuis la dernière version si aucune active."""
        data = {}
        try:
            v = NoteVersionModel.select().where(NoteVersionModel.note == note).order_by(NoteVersionModel.version_number.desc()).first()
            if v and v.content:
                parsed = json.loads(v.content)
                if isinstance(parsed, dict):
                    data = {str(k): strip_html(val) for k, val in parsed.items()}
        except (json.JSONDecodeError, ValueError, TypeError, peewee.PeeweeException):
            pass
        return data

    def _parse_tags(self, tags_raw: Any) -> list[str]:
        """Convertit la chaîne JSON ou la liste de tags en liste Python propre."""
        if not tags_raw:
            return []
        if isinstance(tags_raw, list):
            return [str(t).strip() for t in tags_raw if str(t).strip()]
        try:
            parsed = json.loads(str(tags_raw))
            if isinstance(parsed, list):
                return [str(t).strip() for t in parsed if str(t).strip()]
            if isinstance(parsed, str) and parsed.strip():
                return [parsed.strip()]
        except Exception:
            if isinstance(tags_raw, str) and tags_raw.strip():
                return [tags_raw.strip()]
        return []

    # --- Opérations Métier & Mises à Jour en Direct ---

    def get_note_at(self, row: int) -> NoteModel | None:
        """Retourne l'objet NoteModel à l'indice de ligne donné."""
        if 0 <= row < len(self._loaded_rows):
            return self._loaded_rows[row].raw_note
        return None

    def get_note_data_at(self, row: int) -> NoteRowData | None:
        """Retourne l'objet NoteRowData à l'indice de ligne donné."""
        if 0 <= row < len(self._loaded_rows):
            return self._loaded_rows[row]
        return None

    def find_row_by_note_id(self, note_id: int) -> int:
        """Trouve la ligne d'une note déjà chargée en mémoire, ou -1."""
        for idx, row in enumerate(self._loaded_rows):
            if row.note_id == note_id:
                return idx
        return -1

    def update_note_content(self, note_id: int, new_content: dict[str, str]) -> None:
        """Met à jour instantanément les champs d'une note dans le modèle virtuel."""
        row_idx = self.find_row_by_note_id(note_id)
        if row_idx < 0:
            return

        row_data = self._loaded_rows[row_idx]
        cleaned_content = {str(k): strip_html(v) for k, v in new_content.items()}
        row_data.fields_dict = cleaned_content

        vals = list(cleaned_content.values())
        row_data.recto = vals[0] if len(vals) > 0 else ""
        row_data.verso = " | ".join(vals[1:]) if len(vals) > 1 else ""
        row_data.is_invalid = not row_data.recto.strip()
        if row_data.is_invalid:
            row_data.recto = "⚠️ CARTE INVALIDE (Recto vide)"

        top_left = self.index(row_idx, 0)
        bottom_right = self.index(row_idx, self.columnCount() - 1)
        self.dataChanged.emit(top_left, bottom_right)

    def update_note_flag(self, note_id: int, flag: int) -> None:
        """Met à jour instantanément le drapeau d'une note dans le modèle virtuel."""
        row_idx = self.find_row_by_note_id(note_id)
        if row_idx < 0:
            return
        self._loaded_rows[row_idx].flag = flag
        flag_idx = self.index(row_idx, 1)
        self.dataChanged.emit(flag_idx, flag_idx, [FLAG_ROLE, Qt.ItemDataRole.ToolTipRole])

    def prepend_note(self, note: NoteModel) -> None:
        """Insère une note nouvellement forgée tout en haut de la table."""
        processed = self._process_batch([note])
        if processed:
            self.beginInsertRows(QModelIndex(), 0, 0)
            self._loaded_rows.insert(0, processed[0])
            self._total_count += 1
            self.endInsertRows()

    def remove_notes_by_ids(self, note_ids: list[int]) -> None:
        """Supprime une liste de notes du modèle virtuel."""
        ids_to_remove = set(note_ids)
        for idx in range(len(self._loaded_rows) - 1, -1, -1):
            if self._loaded_rows[idx].note_id in ids_to_remove:
                self.beginRemoveRows(QModelIndex(), idx, idx)
                self._loaded_rows.pop(idx)
                self._total_count = max(0, self._total_count - 1)
                self.endRemoveRows()

        self._checked_note_ids.difference_update(ids_to_remove)
        self._unchecked_note_ids.difference_update(ids_to_remove)

    def set_all_checked(self, checked: bool) -> None:
        """Sélectionne ou désélectionne l'ensemble des cartes (O(1) complexité)."""
        self._all_checked_mode = checked
        self._checked_note_ids.clear()
        self._unchecked_note_ids.clear()
        if len(self._loaded_rows) > 0:
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._loaded_rows) - 1, 0)
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.CheckStateRole])

    def get_checked_note_ids(self) -> list[int]:
        """Retourne la liste complète des IDs de notes cochées."""
        if self._all_checked_mode:
            if self._base_query is not None:
                try:
                    all_ids = [n.id for n in self._base_query.select(NoteModel.id)]
                    return [nid for nid in all_ids if nid not in self._unchecked_note_ids]
                except Exception as e:
                    logger.warning("Erreur get_checked_note_ids all_mode: %s", e)
            return [r.note_id for r in self._loaded_rows if r.note_id not in self._unchecked_note_ids]

        return list(self._checked_note_ids)
