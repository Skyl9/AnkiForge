"""
Service d'Exportation et d'Importation JSON de Modèles de Cartes AnkiForge.
Format standardisé compatible avec la communauté et l'archivage de gabarits.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ankiforge.database.models import NoteTypeModel


SCHEMA_VERSION = "1.0"


class CardModelIO:
    """Gestionnaire d'import / export JSON pour les modèles de cartes (NoteTypeModel)."""

    @classmethod
    def export_to_dict(cls, model: NoteTypeModel, author: str = "AnkiForge User", tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Convertit un NoteTypeModel en dictionnaire standardisé AnkiForge."""
        try:
            fields = json.loads(model.fields_schema) if model.fields_schema else ["Front", "Back"]
        except Exception:
            fields = ["Front", "Back"]

        try:
            templates = json.loads(model.templates) if model.templates else []
        except Exception:
            templates = []

        return {
            "ankiforge_schema_version": SCHEMA_VERSION,
            "metadata": {
                "name": model.name,
                "author": author,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "tags": tags or ["ankiforge", "card-model"],
            },
            "fields_schema": fields,
            "templates": templates,
            "css_style": model.css_style or "",
        }

    @classmethod
    def export_to_json(cls, model: NoteTypeModel, author: str = "AnkiForge User", tags: Optional[List[str]] = None) -> str:
        """Sérialise un modèle de carte en JSON formaté."""
        data = cls.export_to_dict(model, author=author, tags=tags)
        return json.dumps(data, indent=2, ensure_ascii=False)

    @classmethod
    def validate_and_parse_json(cls, json_str: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Valide la structure d'un modèle JSON AnkiForge.
        Retourne (is_valid, parsed_data, error_message).
        """
        try:
            data = json.loads(json_str)
        except Exception as e:
            return False, None, f"JSON invalide : {str(e)}"

        if not isinstance(data, dict):
            return False, None, "Le contenu doit être un objet JSON valide."

        # Vérification du nom
        name = ""
        if "metadata" in data and isinstance(data["metadata"], dict) and "name" in data["metadata"]:
            name = str(data["metadata"]["name"]).strip()
        elif "name" in data:
            name = str(data["name"]).strip()

        if not name:
            return False, None, "Nom du modèle manquant dans le fichier JSON."

        # Vérification des champs
        fields = data.get("fields_schema", [])
        if not isinstance(fields, list) or not fields:
            # Fallback
            fields = ["Front", "Back"]

        # Vérification des templates
        templates = data.get("templates", [])
        if not isinstance(templates, list) or not templates:
            templates = [{"name": "Carte 1", "qfmt": "{{Front}}", "afmt": "{{FrontSide}}<hr id='answer'>{{Back}}"}]

        css_style = data.get("css_style", "")

        normalized_data = {
            "name": name,
            "fields_schema": fields,
            "templates": templates,
            "css_style": css_style,
            "metadata": data.get("metadata", {}),
        }

        return True, normalized_data, ""

    @classmethod
    def save_model_to_db(
        cls,
        model_data: Dict[str, Any],
        overwrite_existing: bool = False,
        new_name: Optional[str] = None,
    ) -> Tuple[NoteTypeModel, bool]:
        """
        Enregistre les données du modèle en base SQLite Peewee.
        Retourne (model_instance, is_created).
        """
        name = (new_name or model_data["name"]).strip()
        fields_json = json.dumps(model_data["fields_schema"], ensure_ascii=False)
        templates_json = json.dumps(model_data["templates"], ensure_ascii=False)
        css_style = model_data.get("css_style", "")

        existing = NoteTypeModel.get_or_none(NoteTypeModel.name == name)

        if existing:
            if overwrite_existing:
                existing.fields_schema = fields_json
                existing.templates = templates_json
                existing.css_style = css_style
                existing.save()
                return existing, False
            else:
                # Générer un nom unique si on n'écrase pas
                idx = 2
                while NoteTypeModel.get_or_none(NoteTypeModel.name == f"{name} ({idx})"):
                    idx += 1
                name = f"{name} ({idx})"

        created = NoteTypeModel.create(
            name=name,
            fields_schema=fields_json,
            templates=templates_json,
            css_style=css_style,
        )
        return created, True
