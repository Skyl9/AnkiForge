import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.settings_service import SettingsService

logger = logging.getLogger(__name__)


@dataclass
class VisionCategory:
    """Représente une catégorie d'analyse visuelle et de reconnaissance d'image."""

    id: str
    name: str
    description: str
    icon: str
    provider: str  # "anthropic", "gemini", "ollama", "openai", "native"
    model_id: str  # "claude-3-7-sonnet-20250219", "gemini-2.5-flash", "qwen2.5-vl:7b", "apple_vision"
    thinking_budget: int = 0  # 0 pour désactivé, > 0 pour les modèles à raisonnement (Claude 3.7)
    temperature: float = 0.2
    custom_instructions: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convertit l'instance en dictionnaire JSON-sérialisable."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VisionCategory":
        """Instancie une VisionCategory depuis un dictionnaire de données."""
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "Catégorie")),
            description=str(data.get("description", "")),
            icon=str(data.get("icon", "ph.sparkle")),
            provider=str(data.get("provider", "ollama")),
            model_id=str(data.get("model_id", "qwen2.5-vl:7b")),
            thinking_budget=int(data.get("thinking_budget", 0)),
            temperature=float(data.get("temperature", 0.2)),
            custom_instructions=str(data.get("custom_instructions", "")),
        )


class VisionCategoryService:
    """Service de gestion et de persistance des catégories d'IA de vision par profil."""

    SETTINGS_KEY = "ai/vision_categories"

    @staticmethod
    def get_default_categories() -> list[VisionCategory]:
        """Retourne les 4 catégories d'analyse visuelle standardisées (Standards 2025-2026)."""
        return [
            VisionCategory(
                id="reasoning",
                name="Raisonnement Visuel Complexe",
                description="Formules mathématiques, diagrammes scientifiques, graphes d'ingénierie et manuscrits denses avec réflexion pas-à-pas.",
                icon="ph.brain",
                provider="anthropic",
                model_id="claude-3-7-sonnet-20250219",
                thinking_budget=2048,
                temperature=0.2,
                custom_instructions="Analyse rigoureusement la structure logique, les équations et les légendes. Détaille les étapes de raisonnement avant de conclure.",
            ),
            VisionCategory(
                id="massive",
                name="Ingestion Massive & Rapide",
                description="Traitement haute vitesse pour de grands volumes de pages scannées, polycopiés et manuels entiers (contexte étendu).",
                icon="ph.lightning",
                provider="gemini",
                model_id="gemini-2.5-flash",
                thinking_budget=0,
                temperature=0.2,
                custom_instructions="Synthétise et transcris fidèlement le contenu textuel et conceptuel de cette page en minimisant la latence.",
            ),
            VisionCategory(
                id="structured",
                name="OCR Structuré & Tableaux",
                description="Reconnaissance précise de la mise en page, extraction des tableaux denses en HTML/Markdown et équations LaTeX.",
                icon="ph.table",
                provider="ollama",
                model_id="qwen2.5-vl:7b",
                thinking_budget=0,
                temperature=0.1,
                custom_instructions="Transcris le contenu au format Markdown propre. Convertis tous les tableaux en syntaxe Markdown ou HTML <table> et les formules en LaTeX ($...$ ou $$...$$).",
            ),
            VisionCategory(
                id="hardware",
                name="Transcription Locale & Matérielle",
                description="Extraction locale instantanée sans VRAM (Apple Vision Framework sous macOS avec Neural Engine, Tesseract sous Linux/Win).",
                icon="ph.cpu",
                provider="native",
                model_id="apple_vision",
                thinking_budget=0,
                temperature=0.0,
                custom_instructions="",
            ),
        ]

    @classmethod
    def get_visual_rag_category(cls) -> VisionCategory:
        """Retourne la catégorie dédiée au RAG Visuel et à l'indexation dense."""
        for cat in cls.get_categories():
            if cat.id == "visual_rag":
                return cat
        return VisionCategory(
            id="visual_rag",
            name="RAG Visuel & Indexation Dense",
            description="Indexation sémantique des diagrammes, schémas, cartes et planches anatomiques par description visuelle dense.",
            icon="ph.eye",
            provider="gemini",
            model_id="gemini-2.5-flash",
            thinking_budget=0,
            temperature=0.2,
            custom_instructions=(
                "Tu es un analyste visuel pour un système de recherche documentaire et de mémorisation (Visual RAG). "
                "Analyse minutieusement cette image/page (diagramme, schéma, carte, planche anatomique ou document). "
                "Produis une description sémantique visuelle dense comprenant : "
                "1. Titre et sujet principal du visuel. "
                "2. Entités et concepts visibles. "
                "3. Relations spatiales, flèches, flux et causalités. "
                "4. Textes, étiquettes et légendes explicites. "
                "5. Formules ou données chiffrées éventuelles. "
                "Formate la réponse en Markdown clair et dense."
            ),
        )

    @classmethod
    def get_categories(cls) -> list[VisionCategory]:
        """Récupère la liste des catégories configurées en base, avec repli sur les valeurs par défaut."""
        raw_val = SettingsService.get(cls.SETTINGS_KEY, default=None)
        if raw_val is None:
            defaults = cls.get_default_categories()
            cls.save_all_categories(defaults)
            return defaults

        try:
            if isinstance(raw_val, str):
                data_list = json.loads(raw_val)
            elif isinstance(raw_val, list):
                data_list = raw_val
            else:
                data_list = []

            categories = [VisionCategory.from_dict(item) for item in data_list if isinstance(item, dict)]
            return categories if categories else cls.get_default_categories()
        except Exception as e:
            logger.warning("Erreur lors de la lecture des catégories de vision : %s. Utilisation des valeurs par défaut.", e)
            return cls.get_default_categories()

    @classmethod
    def save_all_categories(cls, categories: list[VisionCategory]) -> None:
        """Persiste l'ensemble des catégories en base de données."""
        data_to_store = [cat.to_dict() for cat in categories]
        SettingsService.set(cls.SETTINGS_KEY, data_to_store, category="ai")
        logger.info("Catégories de vision sauvegardées (%d catégories)", len(categories))

    @classmethod
    def get_category_by_id(cls, cat_id: str) -> VisionCategory | None:
        """Recherche une catégorie par son identifiant unique."""
        for cat in cls.get_categories():
            if cat.id == cat_id:
                return cat
        if cat_id == "visual_rag":
            return cls.get_visual_rag_category()
        return None

    @classmethod
    def save_category(cls, category: VisionCategory) -> None:
        """Ajoute ou met à jour une catégorie de vision."""
        categories = cls.get_categories()
        updated = False
        for i, existing in enumerate(categories):
            if existing.id == category.id:
                categories[i] = category
                updated = True
                break

        if not updated:
            categories.append(category)

        cls.save_all_categories(categories)
        logger.info("Catégorie de vision '%s' (ID: %s) mise à jour.", category.name, category.id)

    @classmethod
    def delete_category(cls, cat_id: str) -> bool:
        """Supprime une catégorie par son ID."""
        categories = cls.get_categories()
        filtered = [c for c in categories if c.id != cat_id]
        if len(filtered) < len(categories):
            cls.save_all_categories(filtered)
            logger.info("Catégorie de vision ID '%s' supprimée.", cat_id)
            return True
        return False

    @classmethod
    def reset_to_defaults(cls) -> list[VisionCategory]:
        """Rétablit les 4 catégories par défaut d'AnkiForge."""
        defaults = cls.get_default_categories()
        cls.save_all_categories(defaults)
        logger.info("Catégories de vision réinitialisées aux préréglages d'usine.")
        return defaults

    @classmethod
    def resolve_provider_for_category(cls, category: VisionCategory) -> LLMProvider | str:
        """
        Instancie le LLMProvider correspondant à la catégorie, ou retourne 'native' pour l'OCR matériel.
        Injecte automatiquement la clé API stockée pour ce fournisseur.
        """
        if category.provider == "native":
            return "native"

        try:
            from ankiforge.services.ai.flexible_service import AIManager

            key = str(SettingsService.get(f"keys/{category.provider.lower()}", ""))
            return AIManager.create_provider(
                provider_name=category.provider,
                model_id=category.model_id,
                api_key=key if key else None,
                thinking_budget=category.thinking_budget,
            )
        except Exception as err:
            logger.error("Impossible de résoudre le provider pour la catégorie %s : %s", category.name, err)
            return MockProvider()
