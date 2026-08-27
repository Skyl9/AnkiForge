"""
Schémas de validation et modèles de données pour les addons AnkiForge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator
import re


class AddonStatus(str, Enum):
    """Statut d'un addon dans le gestionnaire."""

    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    INCOMPATIBLE = "incompatible"


class AddonManifest(BaseModel):
    """
    Schéma de validation strict pour le fichier manifest.json d'un addon.
    """

    id: str = Field(..., description="Identifiant unique en minuscules (ex: elevenlabs_tts)")
    name: str = Field(..., description="Nom d'affichage lisible pour l'humain")
    version: str = Field(default="1.0.0", description="Version sémantique de l'addon (ex: 1.2.0)")
    author: str = Field(default="Anonyme", description="Auteur ou organisation")
    description: str = Field(default="", description="Description courte de l'addon")
    min_ankiforge_version: Optional[str] = Field(default=None, description="Version minimale d'AnkiForge requise")
    max_ankiforge_version: Optional[str] = Field(default=None, description="Version maximale d'AnkiForge supportée")
    entry_point: str = Field(default="__init__.py", description="Fichier Python point d'entrée")
    homepage: Optional[str] = Field(default=None, description="URL de documentation ou GitHub")

    @field_validator("id")
    @classmethod
    def validate_addon_id(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(f"L'identifiant d'addon '{v}' est invalide. Utilisez uniquement des lettres, chiffres, tirets et underscores.")
        return v.lower()


@dataclass
class AddonInfo:
    """
    Représente les métadonnées et l'état d'exécution d'un addon chargé en mémoire.
    """

    manifest: AddonManifest
    folder_path: Path
    status: AddonStatus = AddonStatus.DISABLED
    is_enabled: bool = True
    error_message: Optional[str] = None
    config_schema: Dict[str, Any] = field(default_factory=dict)
    has_documentation: bool = False
    doc_markdown: str = ""

    @property
    def id(self) -> str:
        return self.manifest.id

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    @property
    def author(self) -> str:
        return self.manifest.author

    @property
    def description(self) -> str:
        return self.manifest.description
