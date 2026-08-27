"""
Pydantic Schemas and Self-Healing Validation Engine for AnkiForge AI Outputs.
Provides strict type contracts, sanitization and automated self-healing.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Type, TypeVar
from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeneratedCardSchema(BaseModel):
    """Schéma d'une flashcard générée par l'IA."""

    model: Optional[str] = Field(default=None, description="Nom du modèle de carte Anki cible")
    fields: Dict[str, str] = Field(default_factory=dict, description="Dictionnaire des champs {nom_champ: valeur}")
    tags: List[str] = Field(default_factory=list, description="Liste des étiquettes / tags associés")

    @model_validator(mode="before")
    @classmethod
    def _normalize_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            res = dict(data)
            # Normaliser tags
            tags_val = res.get("tags", [])
            if isinstance(tags_val, str):
                res["tags"] = [t.strip() for t in tags_val.split() if t.strip()]
            elif not isinstance(tags_val, list):
                res["tags"] = []

            # Si les champs sont directement au premier niveau (ex: {"Front": "...", "Back": "..."})
            if "fields" not in res or not isinstance(res["fields"], dict):
                fields: Dict[str, str] = {}
                model = res.get("model") or res.get("note_type")
                for k, v in res.items():
                    if k in ("model", "note_type", "tags", "fields"):
                        continue
                    fields[str(k)] = str(v)
                res["fields"] = fields
                if model:
                    res["model"] = str(model)
            return res
        return data

    @field_validator("fields")
    @classmethod
    def _validate_fields(cls, v: Dict[str, str]) -> Dict[str, str]:
        if not v:
            raise ValueError("Une carte doit contenir au moins un champ non vide.")
        return {str(k): str(val) for k, val in v.items()}


class GeneratedCardsContainerSchema(BaseModel):
    """Conteneur racine pour la liste des flashcards extraites."""

    notes: List[GeneratedCardSchema] = Field(default_factory=list, description="Liste des flashcards générées")

    @model_validator(mode="before")
    @classmethod
    def _normalize_container(cls, data: Any) -> Any:
        if isinstance(data, list):
            return {"notes": data}
        if isinstance(data, dict):
            for key in ("notes", "cards", "flashcards", "data", "result", "items", "output"):
                if key in data and isinstance(data[key], list):
                    return {"notes": data[key]}
            # Cas d'un objet unique
            if any(k.lower() in ("front", "recto", "question", "fields") for k in data.keys()):
                return {"notes": [data]}
        return data


class WozniakAuditViolationSchema(BaseModel):
    """Schéma d'une violation de règle détectée par l'audit Wozniak."""

    rule_name: str = Field(description="Nom ou identifiant de la règle violée")
    reason: str = Field(description="Explication pédagogique de la violation")
    suggestion: Optional[Dict[str, str]] = Field(default=None, description="Proposition de carte corrigée")


class WozniakAuditResultSchema(BaseModel):
    """Résultat de l'audit de conformité d'une flashcard."""

    is_compliant: bool = Field(default=True, description="Vrai si la carte respecte tous les principes")
    violations: List[WozniakAuditViolationSchema] = Field(default_factory=list, description="Liste des anomalies")
    global_score: Optional[int] = Field(default=None, description="Score global sur 100")


class ExtractedConceptSchema(BaseModel):
    """Schéma pour les étapes d'extraction de connaissances brutes."""

    concept_name: str = Field(description="Titre de la notion ou concept extrait")
    summary: str = Field(description="Synthèse atomique du concept")
    recommended_model: Optional[str] = Field(default=None, description="Modèle de carte préconisé")


class SelfHealingValidator:
    """Moteur de validation et d'auto-réparation pour les sorties LLM structurées."""

    @staticmethod
    def clean_json_string(raw: str) -> str:
        """Nettoie les balises markdown ```json et extrait le JSON valide."""
        text = raw.strip()
        # Supprimer les balises de code Markdown
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # Isoler le premier bloc { ... } ou [ ... ]
        start_brace = text.find("{")
        start_bracket = text.find("[")

        if start_brace != -1 and (start_bracket == -1 or start_brace < start_bracket):
            end_brace = text.rfind("}")
            if end_brace != -1:
                text = text[start_brace : end_brace + 1]
        elif start_bracket != -1:
            end_bracket = text.rfind("]")
            if end_bracket != -1:
                text = text[start_bracket : end_bracket + 1]

        # Supprimer les virgules traînantes (trailing commas) avant } ou ]
        text = re.sub(r",\s*([\]}])", r"\1", text)
        return text

    @classmethod
    def parse_and_validate(
        cls,
        raw_output: Any,
        schema_cls: Type[T],
    ) -> T:
        """
        Valide une sortie brute contre un schéma Pydantic avec nettoyage automatique.
        Lève ValidationError si irréparable.
        """
        if isinstance(raw_output, schema_cls):
            return raw_output

        parsed_data = raw_output
        if isinstance(raw_output, str):
            cleaned = cls.clean_json_string(raw_output)
            try:
                parsed_data = json.loads(cleaned)
            except Exception as e:
                # Tente une réparation des guillemets simples en doubles
                try:
                    repaired = re.sub(r"'([^']*)'", r'"\1"', cleaned)
                    parsed_data = json.loads(repaired)
                except Exception:
                    raise ValueError(f"JSON syntaxiquement invalide pour {schema_cls.__name__}: {e}") from e

        return schema_cls.model_validate(parsed_data)
