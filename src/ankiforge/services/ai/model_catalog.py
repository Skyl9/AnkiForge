"""
Catalogue et registre des spécifications et capacités des modèles LLM pour AnkiForge.

Fournit une base de connaissances exhaustive des capacités réelles (Vision, Thinking,
Contexte, Vitesse, Coût, Recommandations) et l'auto-détection pour les modèles locaux Ollama.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """Spécifications et capacités détaillées d'un modèle d'IA."""

    provider: str  # "gemini", "openai", "anthropic", "groq", "ollama"
    model_id: str
    display_name: str
    context_window: int = 128000
    max_tokens: int = 16384
    supports_vision: bool = False
    supports_thinking: bool = False
    supports_json: bool = True
    speed_rating: str = "fast"  # "ultra-fast", "fast", "moderate", "deliberate"
    quality_tier: str = "balanced"  # "flagship", "balanced", "economy", "reasoning"
    is_free: bool = False
    prompt_pricing: float = 0.0  # $ / 1M tokens
    completion_pricing: float = 0.0  # $ / 1M tokens
    recommended_tasks: list[str] = field(default_factory=list)
    ankiforge_use_case: str = ""
    description: str = ""

    @property
    def formatted_context_window(self) -> str:
        """Retourne la taille de contexte lisible (ex: '128k', '1M', '2M')."""
        if self.context_window >= 1_000_000:
            val = self.context_window / 1_000_000
            return f"{val:.1f}M" if val % 1 else f"{int(val)}M"
        if self.context_window >= 1_000:
            return f"{self.context_window // 1_000}k"
        return str(self.context_window)

    @property
    def formatted_pricing(self) -> str:
        """Retourne une étiquette de tarification lisible."""
        if self.is_free or self.provider == "ollama":
            return "100% Gratuit"
        if self.prompt_pricing == 0.0 and self.completion_pricing == 0.0:
            return "Tier Gratuit"
        return f"${self.prompt_pricing:.2f} / ${self.completion_pricing:.2f} (1M)"

    @property
    def speed_label(self) -> str:
        """Label en français pour la vitesse d'inférence."""
        labels = {
            "ultra-fast": "Ultra-rapide (>150 t/s)",
            "fast": "Rapide (~70-100 t/s)",
            "moderate": "Modéré (~30-50 t/s)",
            "deliberate": "Raisonnement approfondi (CoT)",
        }
        return labels.get(self.speed_rating, "Standard")

    @property
    def quality_label(self) -> str:
        """Label de qualité globale."""
        labels = {
            "flagship": "Modèle Phare",
            "balanced": "Équilibré",
            "economy": "Économique / Léger",
            "reasoning": "Raisonnement Complexe",
        }
        return labels.get(self.quality_tier, "Standard")


# Dictionnaire de référence des modèles majeurs 2025-2026
CURATED_MODELS: dict[str, ModelSpec] = {
    # ── GOOGLE GEMINI ──
    "gemini:gemini-3.5-flash-lite": ModelSpec(
        provider="gemini",
        model_id="gemini-3.5-flash-lite",
        display_name="Google Gemini 3.5 Flash Lite",
        context_window=1048576,
        max_tokens=65536,
        supports_vision=True,
        supports_thinking=False,
        supports_json=True,
        speed_rating="ultra-fast",
        quality_tier="economy",
        is_free=True,
        prompt_pricing=0.0,
        completion_pricing=0.0,
        recommended_tasks=["flashcards", "batch", "vision"],
        ankiforge_use_case="Le moteur par défaut ultra-rapide et gratuit d'AnkiForge. Idéal pour la création massive de flashcards et le découpage RAG.",
        description="Modèle ultra-léger de Google avec fenêtre de 1M tokens, gratuit sur l'API AI Studio.",
    ),
    "gemini:gemini-2.0-flash": ModelSpec(
        provider="gemini",
        model_id="gemini-2.0-flash",
        display_name="Google Gemini 2.0 Flash",
        context_window=1048576,
        max_tokens=65536,
        supports_vision=True,
        supports_thinking=False,
        supports_json=True,
        speed_rating="ultra-fast",
        quality_tier="balanced",
        is_free=True,
        prompt_pricing=0.10,
        completion_pricing=0.40,
        recommended_tasks=["flashcards", "vision", "long_docs", "batch"],
        ankiforge_use_case="Vitesse fulgurante avec vision multimodale native. Excellent pour traiter de gros polycopiés et analyser des schémas.",
        description="Génération multimodale temps réel avec support JSON strict et fenêtre de 1M tokens.",
    ),
    "gemini:gemini-1.5-pro": ModelSpec(
        provider="gemini",
        model_id="gemini-1.5-pro",
        display_name="Google Gemini 1.5 Pro",
        context_window=2097152,
        max_tokens=65536,
        supports_vision=True,
        supports_thinking=False,
        supports_json=True,
        speed_rating="moderate",
        quality_tier="flagship",
        is_free=False,
        prompt_pricing=1.25,
        completion_pricing=5.00,
        recommended_tasks=["long_docs", "vision", "audit"],
        ankiforge_use_case="Contexte colossal de 2M tokens capable d'ingérer des manuels entiers sans découpage et d'analyser des planches anatomiques complexes.",
        description="Modèle phare de Google pour les contextes ultra-longs et l'analyse documentaire approfondie.",
    ),
    # ── OPENAI ──
    "openai:gpt-4o": ModelSpec(
        provider="openai",
        model_id="gpt-4o",
        display_name="GPT-4o (OpenAI)",
        context_window=128000,
        max_tokens=16384,
        supports_vision=True,
        supports_thinking=False,
        supports_json=True,
        speed_rating="fast",
        quality_tier="flagship",
        is_free=False,
        prompt_pricing=2.50,
        completion_pricing=10.00,
        recommended_tasks=["flashcards", "audit", "vision"],
        ankiforge_use_case="Référence polyvalente pour la formulation de flashcards de haute précision et l'audit chirurgical des règles Wozniak.",
        description="Modèle omni d'OpenAI combinant intelligence supérieure, rapidité et vision haute définition.",
    ),
    "openai:gpt-4o-mini": ModelSpec(
        provider="openai",
        model_id="gpt-4o-mini",
        display_name="GPT-4o Mini (OpenAI)",
        context_window=128000,
        max_tokens=16384,
        supports_vision=True,
        supports_thinking=False,
        supports_json=True,
        speed_rating="ultra-fast",
        quality_tier="economy",
        is_free=False,
        prompt_pricing=0.15,
        completion_pricing=0.60,
        recommended_tasks=["flashcards", "batch", "vision"],
        ankiforge_use_case="Rapport qualité/prix imbattable chez OpenAI pour les gros volumes de cartes et le traitement par lots.",
        description="Modèle compact et économique surpassant GPT-3.5 avec vision native.",
    ),
    "openai:o3-mini": ModelSpec(
        provider="openai",
        model_id="o3-mini",
        display_name="o3-mini (OpenAI Reasoning)",
        context_window=200000,
        max_tokens=100000,
        supports_vision=False,
        supports_thinking=True,
        supports_json=True,
        speed_rating="fast",
        quality_tier="reasoning",
        is_free=False,
        prompt_pricing=1.10,
        completion_pricing=4.40,
        recommended_tasks=["audit", "reasoning"],
        ankiforge_use_case="Spécialiste du raisonnement logique et scientifique (maths, code, médecine). Parfait pour auditer les cartes ambiguës et déjouer les pièges conceptuels.",
        description="Modèle de raisonnement CoT rapide et économique d'OpenAI pour la logique complexe.",
    ),
    "openai:o1": ModelSpec(
        provider="openai",
        model_id="o1",
        display_name="o1 (OpenAI Flagship Reasoning)",
        context_window=200000,
        max_tokens=100000,
        supports_vision=True,
        supports_thinking=True,
        supports_json=True,
        speed_rating="deliberate",
        quality_tier="flagship",
        is_free=False,
        prompt_pricing=15.00,
        completion_pricing=60.00,
        recommended_tasks=["audit", "reasoning", "vision"],
        ankiforge_use_case="Le sommet du raisonnement formel avec vision pour les problèmes scientifiques, diagnostics médicaux et synthèses complexes.",
        description="Modèle phare de réflexion approfondie d'OpenAI avec chaîne de pensée complète.",
    ),
    # ── ANTHROPIC ──
    "anthropic:claude-3-7-sonnet-20250219": ModelSpec(
        provider="anthropic",
        model_id="claude-3-7-sonnet-20250219",
        display_name="Claude 3.7 Sonnet (Anthropic)",
        context_window=200000,
        max_tokens=64000,
        supports_vision=True,
        supports_thinking=True,
        supports_json=True,
        speed_rating="fast",
        quality_tier="flagship",
        is_free=False,
        prompt_pricing=3.00,
        completion_pricing=15.00,
        recommended_tasks=["flashcards", "audit", "reasoning", "vision"],
        ankiforge_use_case="Le modèle le plus polyvalent et puissant : dispose du mode hybride Extended Thinking pour alterner entre réponse instantanée et raisonnement approfondi.",
        description="Premier modèle hybride d'Anthropic alliant réflexion continue paramétrable et vision de classe mondiale.",
    ),
    "anthropic:claude-3-5-sonnet-20241022": ModelSpec(
        provider="anthropic",
        model_id="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet (Anthropic)",
        context_window=200000,
        max_tokens=8192,
        supports_vision=True,
        supports_thinking=False,
        supports_json=True,
        speed_rating="fast",
        quality_tier="flagship",
        is_free=False,
        prompt_pricing=3.00,
        completion_pricing=15.00,
        recommended_tasks=["flashcards", "audit", "vision"],
        ankiforge_use_case="Style de rédaction et clarté pédagogique incomparables pour reformuler des concepts littéraires, médicaux et juridiques.",
        description="Modèle de référence d'Anthropic pour la nuance d'écriture, l'analyse de code et la vision.",
    ),
    "anthropic:claude-3-5-haiku-20241022": ModelSpec(
        provider="anthropic",
        model_id="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku (Anthropic)",
        context_window=200000,
        max_tokens=8192,
        supports_vision=False,
        supports_thinking=False,
        supports_json=True,
        speed_rating="ultra-fast",
        quality_tier="economy",
        is_free=False,
        prompt_pricing=0.80,
        completion_pricing=4.00,
        recommended_tasks=["flashcards", "batch"],
        ankiforge_use_case="Vitesse d'exécution exceptionnelle avec une excellente compréhension des consignes complexes pour la génération rapide.",
        description="Modèle ultra-rapide d'Anthropic égalant les performances de Claude 3 Opus sur de nombreux benchmarks.",
    ),
    # ── GROQ LPU ──
    "groq:llama-3.3-70b-versatile": ModelSpec(
        provider="groq",
        model_id="llama-3.3-70b-versatile",
        display_name="Llama 3.3 70B (Groq LPU)",
        context_window=128000,
        max_tokens=32768,
        supports_vision=False,
        supports_thinking=False,
        supports_json=True,
        speed_rating="ultra-fast",
        quality_tier="balanced",
        is_free=False,
        prompt_pricing=0.59,
        completion_pricing=0.79,
        recommended_tasks=["flashcards", "batch"],
        ankiforge_use_case="Inférence LPU fulgurante à plus de 300 tokens/seconde avec le meilleur modèle open-source 70B.",
        description="Propulsé par le matériel LPU de Groq pour une latence quasi-nulle sur Llama 3.3.",
    ),
    "groq:deepseek-r1-distill-llama-70b": ModelSpec(
        provider="groq",
        model_id="deepseek-r1-distill-llama-70b",
        display_name="DeepSeek-R1 70B (Groq LPU)",
        context_window=128000,
        max_tokens=32768,
        supports_vision=False,
        supports_thinking=True,
        supports_json=True,
        speed_rating="fast",
        quality_tier="reasoning",
        is_free=False,
        prompt_pricing=0.75,
        completion_pricing=0.99,
        recommended_tasks=["audit", "reasoning"],
        ankiforge_use_case="Raisonnement DeepSeek-R1 accéléré par Groq pour auditer vos collections et déceler les interférences sans attente.",
        description="Distillation de DeepSeek-R1 dans Llama-70B exécutée à haute vitesse sur Groq.",
    ),
}

# Tâches AnkiForge et leurs métadonnées
ANKIFORGE_TASKS: dict[str, dict[str, str]] = {
    "flashcards": {
        "label": "Génération Flashcards",
        "description": "Formulation de questions/réponses atomiques, claires et respectueuses de la mémoire.",
        "icon": "ph.cards",
    },
    "audit": {
        "label": "Audit Wozniak & Linter",
        "description": "Vérification des 20 règles de mémorisation, détection d'interférences et scission de cartes denses.",
        "icon": "ph.check-circle",
    },
    "long_docs": {
        "label": "Documents Denses & RAG",
        "description": "Ingestion de cours volumineux, thèses, polycopiés et manuels de plusieurs centaines de pages.",
        "icon": "ph.files",
    },
    "vision": {
        "label": "Schémas & Vision d'Image",
        "description": "Analyse de planches anatomiques, graphiques, figures scientifiques et OCR manuscrit.",
        "icon": "ph.eye",
    },
    "reasoning": {
        "label": "Raisonnement & Sciences",
        "description": "Mécanismes physiologiques, démonstrations mathématiques et cas cliniques complexes.",
        "icon": "ph.brain",
    },
    "batch": {
        "label": "Traitement par Lots (Batch)",
        "description": "Exécution rapide et économique de pipelines à grande échelle sans latence.",
        "icon": "ph.lightning",
    },
}


class ModelCatalog:
    """Gestionnaire central de découverte et de recommandation des modèles LLM."""

    @classmethod
    def get_model_spec(cls, provider: str, model_id: str) -> ModelSpec:
        """Retourne la spécification d'un modèle depuis le catalogue ou l'infère si inconnu."""
        key = f"{provider.lower()}:{model_id.lower()}"
        if key in CURATED_MODELS:
            return CURATED_MODELS[key]

        # Recherche approximative par model_id seul
        for m_key, spec in CURATED_MODELS.items():
            if m_key.endswith(f":{model_id.lower()}"):
                return spec
            if spec.model_id.lower() in model_id.lower() or model_id.lower() in spec.model_id.lower():
                return spec

        # Modèle inconnu / personnalisé : inférence intelligente basée sur le nom
        m_id_low = model_id.lower()
        p_low = provider.lower()

        is_vision = any(v in m_id_low for v in ("vision", "llava", "4o", "gemini", "claude-3", "sonnet"))
        is_thinking = any(t in m_id_low for t in ("r1", "o1", "o3", "thinking", "reasoning", "qwq"))
        is_local = p_low == "ollama" or "localhost" in p_low
        is_free = is_local or ("flash-lite" in m_id_low and p_low == "gemini")

        context = 128000
        if "gemini" in m_id_low or "gemini" in p_low:
            context = 1048576
        elif "claude" in m_id_low:
            context = 200000
        elif "32k" in m_id_low:
            context = 32768
        elif "8k" in m_id_low:
            context = 8192

        tasks: list[str] = ["flashcards"]
        if is_vision:
            tasks.append("vision")
        if is_thinking:
            tasks.extend(["audit", "reasoning"])
        if context >= 500000:
            tasks.append("long_docs")

        return ModelSpec(
            provider=provider,
            model_id=model_id,
            display_name=f"{model_id} ({provider})",
            context_window=context,
            max_tokens=16384,
            supports_vision=is_vision,
            supports_thinking=is_thinking,
            supports_json=True,
            speed_rating="fast" if not is_thinking else "deliberate",
            quality_tier="reasoning" if is_thinking else ("flagship" if is_vision else "balanced"),
            is_free=is_free,
            prompt_pricing=0.0 if is_free else 1.0,
            completion_pricing=0.0 if is_free else 3.0,
            recommended_tasks=tasks,
            ankiforge_use_case="Modèle configuré par l'utilisateur.",
            description=f"Modèle personnalisé {model_id} hébergé sur {provider}.",
        )

    @classmethod
    def get_curated_catalog(cls) -> list[ModelSpec]:
        """Retourne la liste ordonnée de tous les modèles du catalogue officiel."""
        return list(CURATED_MODELS.values())

    @classmethod
    def recommend_models_for_task(cls, task_key: str) -> list[ModelSpec]:
        """Retourne les meilleurs modèles recommandés pour une tâche donnée."""
        matching = [spec for spec in CURATED_MODELS.values() if task_key in spec.recommended_tasks]
        # Trier : modèles gratuits/légers d'abord pour flashcards/batch, modèles phares pour audit/reasoning
        if task_key in ("audit", "reasoning"):
            return sorted(matching, key=lambda s: 0 if s.supports_thinking else 1)
        if task_key == "vision":
            return sorted(matching, key=lambda s: 0 if s.supports_vision else 1)
        return sorted(matching, key=lambda s: 0 if s.is_free else 1)

    @classmethod
    def detect_ollama_model_capabilities(cls, base_url: str, model_name: str) -> ModelSpec:
        """
        Interroge l'API Ollama locale POST /api/show pour inspecter les capacités réelles.
        Détecte la vision (projecteur CLIP), la réflexion (<think>) et la fenêtre de contexte.
        """
        url = f"{base_url.rstrip('/')}/api/show"
        payload = json.dumps({"name": model_name}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})

        supports_vision = False
        supports_thinking = False
        context_len = 8192

        m_name_low = model_name.lower()
        if any(v in m_name_low for v in ("llava", "vision", "bakllava", "llama3.2-vision", "minicpm")):
            supports_vision = True
        if any(t in m_name_low for t in ("r1", "reasoning", "qwq", "think")):
            supports_thinking = True

        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:  # nosec B310
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    model_info = data.get("model_info", {})
                    # Recherche du projecteur vision
                    for k in model_info:
                        if "clip" in k.lower() or "projector" in k.lower():
                            supports_vision = True
                        if "context_length" in k.lower():
                            try:
                                context_len = int(model_info[k])
                            except (ValueError, TypeError):
                                pass

                    # Vérification du template pour la balise <think>
                    template = str(data.get("template", ""))
                    if "<think>" in template or "thought" in template:
                        supports_thinking = True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, Exception) as e:
            logger.debug("Détection Ollama show impossible pour %s (%s), repli heuristique", model_name, e)

        tasks: list[str] = ["flashcards"]
        if supports_vision:
            tasks.append("vision")
        if supports_thinking:
            tasks.extend(["audit", "reasoning"])
        if context_len >= 32000:
            tasks.append("long_docs")

        return ModelSpec(
            provider="ollama",
            model_id=model_name,
            display_name=f"{model_name} (Ollama Local)",
            context_window=context_len,
            max_tokens=min(16384, context_len),
            supports_vision=supports_vision,
            supports_thinking=supports_thinking,
            supports_json=True,
            speed_rating="fast" if not supports_thinking else "moderate",
            quality_tier="reasoning" if supports_thinking else "balanced",
            is_free=True,
            prompt_pricing=0.0,
            completion_pricing=0.0,
            recommended_tasks=tasks,
            ankiforge_use_case="Modèle 100% local hébergé sur votre machine via Ollama. Zéro fuite de données et coût nul.",
            description=f"Modèle local {model_name} exécuté sur votre matériel.",
        )


__all__ = ["ANKIFORGE_TASKS", "CURATED_MODELS", "ModelCatalog", "ModelSpec"]
