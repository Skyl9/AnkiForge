"""Service d'exportation rapide des cartes et notes en texte, JSON, JSONL et Markdown.

Permet l'analyse hors-ligne rapide (doublons, champs vides, tags, traçabilité RAG)
sans nécessiter l'ouverture d'un fichier .apkg dans Anki Desktop.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ankiforge.database.models import (
    NoteChunkLinkModel,
    NoteModel,
    NoteVersionModel,
)
from ankiforge.utils.tags import parse_note_tags

logger = logging.getLogger(__name__)


class CardExportService:
    """Gestionnaire d'extraction et de sérialisation des cartes au format JSON, JSONL, Texte ou Markdown."""

    def extract_export_data(
        self,
        notes: Sequence[NoteModel | int],
        include_ids: bool = True,
    ) -> list[dict[str, Any]]:
        """Extrait les données structurées des notes spécifiées pour l'export.

        Args:
            notes: Séquence d'instances NoteModel ou d'identifiants de note.
            include_ids: Si True, inclut les identifiants techniques (id, guid, chunk_id).
                         Si False, produit une structure déterministe / anonymisée.

        Returns:
            Liste ordonnée de dictionnaires représentant chaque carte.
        """
        resolved_notes: list[NoteModel] = []
        for item in notes:
            if isinstance(item, int):
                n = NoteModel.get_or_none(NoteModel.id == item)
                if n is not None:
                    resolved_notes.append(n)
            elif isinstance(item, NoteModel):
                resolved_notes.append(item)

        results: list[dict[str, Any]] = []

        for note in resolved_notes:
            model_name = note.note_type.name if note.note_type else "Inconnu"

            fields_dict: dict[str, str] = {}
            active_version = note.versions.where(NoteVersionModel.is_active == True).first()  # noqa: E712
            if active_version and active_version.content:
                try:
                    loaded = json.loads(active_version.content)
                    if isinstance(loaded, dict):
                        fields_dict = {str(k): str(v) for k, v in loaded.items()}
                except (json.JSONDecodeError, TypeError) as err:
                    logger.debug("Erreur décodage JSON pour la note #%s: %s", getattr(note, "id", "?"), err)

            first_card = note.cards.first()
            deck_name = first_card.deck.name if first_card and first_card.deck else "Par défaut"
            card_flags = int(getattr(first_card, "flags", 0) or 0) if first_card else 0
            is_suspended = bool(getattr(first_card, "is_suspended", False)) if first_card else False

            tags_list = parse_note_tags(note.tags)

            prov_tags = [t for t in tags_list if t.startswith(("doc:", "source:", "section:", "page:", "chunk:"))]
            linked_sources: list[dict[str, Any]] = []

            try:
                chunk_links = list(NoteChunkLinkModel.select(NoteChunkLinkModel).where(NoteChunkLinkModel.note == note))
                for link in chunk_links:
                    chunk = link.chunk
                    if chunk is not None:
                        doc = chunk.document
                        src_dict: dict[str, Any] = {
                            "document_title": doc.title if doc else "",
                            "heading_path": chunk.heading_path or "",
                            "page_number": chunk.page_number,
                            "resolution": link.resolution or "unknown",
                        }
                        if include_ids:
                            src_dict["document_id"] = doc.id if doc else None
                            src_dict["chunk_id"] = chunk.id
                        linked_sources.append(src_dict)
            except Exception as e:
                logger.debug("Remarque lecture chunk_links note #%s: %s", getattr(note, "id", "?"), e)

            card_entry: dict[str, Any] = {
                "deck": deck_name,
                "model": model_name,
                "fields": fields_dict,
                "tags": tags_list,
                "provenance": {
                    "tags": prov_tags,
                    "sources": linked_sources,
                },
                "status": note.status or "new",
                "flags": card_flags,
                "is_suspended": is_suspended,
            }

            if include_ids:
                card_entry["id"] = note.id
                card_entry["guid"] = note.guid

            results.append(card_entry)

        return results

    def format_json(self, data: list[dict[str, Any]], indent: int = 2) -> str:
        """Sérialise les données en JSON formatté lisible."""
        return json.dumps(data, indent=indent, ensure_ascii=False)

    def format_jsonl(self, data: list[dict[str, Any]]) -> str:
        """Sérialise les données en format JSON Lines (1 ligne par carte)."""
        lines = [json.dumps(card, ensure_ascii=False) for card in data]
        return "\n".join(lines) + ("\n" if lines else "")

    def format_text(self, data: list[dict[str, Any]]) -> str:
        """Sérialise les cartes en format texte lisible humain, une carte par bloc délimité."""
        blocks: list[str] = []
        for idx, card in enumerate(data, 1):
            lines: list[str] = []
            lines.append("=" * 80)
            card_id_str = f" #{card['id']}" if "id" in card else f" #{idx}"
            lines.append(f"CARTE{card_id_str} — Paquet : {card.get('deck', 'N/A')} | Modèle : {card.get('model', 'N/A')}")

            status_str = f"Statut : {card.get('status', 'new')} | Drapeaux : {card.get('flags', 0)} | Suspendue : {'Oui' if card.get('is_suspended') else 'Non'}"
            lines.append(status_str)

            tags_str = ", ".join(card.get("tags", [])) if card.get("tags") else "Aucun"
            lines.append(f"Tags : {tags_str}")

            prov = card.get("provenance", {})
            prov_tags = prov.get("tags", [])
            sources = prov.get("sources", [])
            if prov_tags or sources:
                prov_summary_parts = []
                if prov_tags:
                    prov_summary_parts.append(f"Tags : {', '.join(prov_tags)}")
                if sources:
                    for src in sources:
                        doc_title = src.get("document_title", "")
                        page = src.get("page_number")
                        page_str = f" (p. {page})" if page is not None else ""
                        heading = src.get("heading_path", "")
                        res = src.get("resolution", "")
                        res_str = f" [{res}]" if res else ""
                        prov_summary_parts.append(f"Source : {doc_title}{page_str} > {heading}{res_str}")
                lines.append(f"Provenance : {' | '.join(prov_summary_parts)}")

            lines.append("-" * 80)

            fields = card.get("fields", {})
            if fields:
                for fname, fval in fields.items():
                    lines.append(f"[{fname}]")
                    lines.append(fval.strip())
                    lines.append("")
            else:
                lines.append("(Aucun champ renseigné)")
                lines.append("")

            lines.append("=" * 80)
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    def format_markdown(self, data: list[dict[str, Any]]) -> str:
        """Sérialise les cartes en format Markdown structuré."""
        blocks: list[str] = []
        for idx, card in enumerate(data, 1):
            lines: list[str] = []
            card_id_str = f" #{card['id']}" if "id" in card else f" #{idx}"
            lines.append(f"### Carte{card_id_str}")
            lines.append("")
            lines.append(f"- **Paquet :** {card.get('deck', 'N/A')}")
            lines.append(f"- **Modèle :** {card.get('model', 'N/A')}")
            lines.append(f"- **Statut :** `{card.get('status', 'new')}` | **Drapeau :** {card.get('flags', 0)} | **Suspendue :** {'Oui' if card.get('is_suspended') else 'Non'}")

            tags = card.get("tags", [])
            tags_str = ", ".join(f"`{t}`" for t in tags) if tags else "*Aucun*"
            lines.append(f"- **Tags :** {tags_str}")

            prov = card.get("provenance", {})
            sources = prov.get("sources", [])
            if sources:
                lines.append("- **Provenance :**")
                for src in sources:
                    doc = src.get("document_title", "")
                    page = src.get("page_number")
                    heading = src.get("heading_path", "")
                    p_str = f" (page {page})" if page is not None else ""
                    res = src.get("resolution", "")
                    lines.append(f"  - {doc}{p_str} > {heading} *({res})*")
            elif prov.get("tags"):
                lines.append(f"- **Provenance (tags) :** {', '.join(prov.get('tags', []))}")

            lines.append("")
            lines.append("#### Champs")
            fields = card.get("fields", {})
            if fields:
                for fname, fval in fields.items():
                    lines.append(f"**{fname}** :")
                    lines.append("> " + fval.replace("\n", "\n> "))
                    lines.append("")
            else:
                lines.append("*(Aucun champ)*")
                lines.append("")

            lines.append("---")
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)

    def export_to_file(
        self,
        notes: Sequence[NoteModel | int],
        output_path: str | Path,
        format_type: str = "json",
        include_ids: bool = True,
    ) -> int:
        """Exporte une collection de notes vers un fichier unique.

        Args:
            notes: Notes à exporter.
            output_path: Chemin du fichier de destination.
            format_type: 'json', 'jsonl', 'text' / 'txt', 'markdown' / 'md'.
            include_ids: Si True, inclut les identifiants techniques.

        Returns:
            Nombre de cartes exportées.
        """
        data = self.extract_export_data(notes, include_ids=include_ids)
        fmt = format_type.lower().strip()

        if fmt in ("json", "application/json"):
            content = self.format_json(data)
        elif fmt in ("jsonl", "ndjson"):
            content = self.format_jsonl(data)
        elif fmt in ("markdown", "md"):
            content = self.format_markdown(data)
        else:
            content = self.format_text(data)

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")
        logger.info("Exportation rapide de %d cartes vers '%s' (format: %s)", len(data), out_path.name, fmt)
        return len(data)

    def export_to_directory(
        self,
        notes: Sequence[NoteModel | int],
        output_dir: str | Path,
        format_type: str = "json",
        include_ids: bool = True,
    ) -> int:
        """Exporte les notes sous forme d'un dossier avec un fichier par carte.

        Args:
            notes: Notes à exporter.
            output_dir: Dossier de destination.
            format_type: 'json', 'text' / 'txt', 'markdown' / 'md'.
            include_ids: Si True, inclut les identifiants techniques.

        Returns:
            Nombre de cartes exportées.
        """
        data = self.extract_export_data(notes, include_ids=include_ids)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        fmt = format_type.lower().strip()
        ext = ".json" if fmt in ("json", "application/json", "jsonl") else (".md" if fmt in ("markdown", "md") else ".txt")

        for idx, card in enumerate(data, 1):
            card_id_str = f"card_{card['id']}" if "id" in card else f"card_{idx:04d}"
            target_file = out_dir / f"{card_id_str}{ext}"

            if fmt in ("json", "application/json"):
                file_content = json.dumps(card, indent=2, ensure_ascii=False)
            elif fmt in ("markdown", "md"):
                file_content = self.format_markdown([card])
            else:
                file_content = self.format_text([card])

            target_file.write_text(file_content, encoding="utf-8")

        logger.info("Exportation rapide de %d cartes dans le dossier '%s'", len(data), out_dir)
        return len(data)
