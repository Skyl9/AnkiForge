import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunState:
    """
    Objet de Contexte (State) partagé voyageant d'étape en étape dans le DAG (Moteur d'Orchestration IA).
    Chaque étape lit et enrichit cet état de façon dynamique.
    """

    # Identifiants de contexte et données sources
    document_id: int | None = None
    initial_prompt: str = ""

    # Contexte RAG (Retrieval-Augmented Generation)
    retrieved_chunks: list[str] = field(default_factory=list)

    # Variables dynamiques stockées par les étapes (ex: plan_du_cours, generated_cards, map_reduce_results)
    variables: dict[str, Any] = field(default_factory=dict)

    # Historique de conversation / messages pour les agents (ReAct / Chat)
    messages: list[dict[str, str]] = field(default_factory=list)

    # Suivi d'exécution et budgets
    errors: list[str] = field(default_factory=list)
    is_paused_for_human: bool = False
    current_step_id: int | None = None
    current_step_order: int | None = None
    execution_history: list[dict[str, Any]] = field(default_factory=list)
    step_execution_counts: dict[int, int] = field(default_factory=dict)
    step_token_usage: dict[int, int] = field(default_factory=dict)
    total_tokens: int = 0

    def add_error(self, error_message: str) -> None:
        """Enregistre une erreur dans l'état."""
        logger.error(f"[PipelineRunState Error] {error_message}")
        self.errors.append(error_message)

    def set_variable(self, key: str, value: Any) -> None:
        """Définit une variable dans le contexte partagé."""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Récupère une variable du contexte partagé."""
        return self.variables.get(key, default)

    def add_retrieved_chunks(self, chunks: list[str]) -> None:
        """Ajoute des morceaux de texte récupérés par le RAG."""
        self.retrieved_chunks.extend(chunks)
        self.variables["retrieved_chunks"] = self.retrieved_chunks

    def record_step_execution(self, step_order: int) -> int:
        """Incrémente et retourne le nombre d'exécutions d'une étape (garde anti-cycle)."""
        count = self.step_execution_counts.get(step_order, 0) + 1
        self.step_execution_counts[step_order] = count
        return count

    def get_step_execution_count(self, step_order: int) -> int:
        """Retourne le nombre d'exécutions d'une étape."""
        return self.step_execution_counts.get(step_order, 0)

    def record_tokens(self, step_order: int, prompt_tokens: int, completion_tokens: int) -> None:
        """Comptabilise les tokens consommés par une étape et au niveau global."""
        tokens = max(0, prompt_tokens + completion_tokens)
        self.step_token_usage[step_order] = self.step_token_usage.get(step_order, 0) + tokens
        self.total_tokens += tokens

    def get_step_tokens(self, step_order: int) -> int:
        """Retourne les tokens cumulés consommés par une étape."""
        return self.step_token_usage.get(step_order, 0)

    def log_step_execution(
        self,
        step_order: int,
        step_type: str,
        status: str,
        duration_sec: float = 0.0,
        details: str | None = None,
        tokens_used: int | None = None,
        thought: str | None = None,
    ) -> None:
        """Enregistre l'exécution d'une étape dans l'historique."""
        self.execution_history.append(
            {
                "step_order": step_order,
                "step_type": step_type,
                "status": status,
                "duration_sec": round(duration_sec, 3),
                "details": details,
                "tokens_used": tokens_used if tokens_used is not None else self.get_step_tokens(step_order),
                "thought": thought,
            }
        )

    def get_step_thought(self, step_order: int) -> str | None:
        """Retourne la chaîne de réflexion (thought/CoT) enregistrée pour une étape donnée."""
        for entry in reversed(self.execution_history):
            if entry.get("step_order") == step_order:
                val = entry.get("thought")
                return str(val) if val else None
        return None

    def to_dict(self) -> dict[str, Any]:
        """Sérialise l'état pour la persistance ou l'envoi vers l'UI."""
        return {
            "document_id": self.document_id,
            "initial_prompt": self.initial_prompt,
            "retrieved_chunks": list(self.retrieved_chunks),
            "variables": dict(self.variables),
            "messages": list(self.messages),
            "errors": list(self.errors),
            "is_paused_for_human": self.is_paused_for_human,
            "current_step_id": self.current_step_id,
            "current_step_order": self.current_step_order,
            "execution_history": list(self.execution_history),
            "step_execution_counts": {str(k): v for k, v in self.step_execution_counts.items()},
            "step_token_usage": {str(k): v for k, v in self.step_token_usage.items()},
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PipelineRunState":
        """Reconstruit un PipelineRunState depuis un dictionnaire sérialisé."""
        raw_counts = data.get("step_execution_counts", {})
        counts: dict[int, int] = {int(k): int(v) for k, v in raw_counts.items() if str(k).isdigit()}

        raw_usage = data.get("step_token_usage", {})
        usage: dict[int, int] = {int(k): int(v) for k, v in raw_usage.items() if str(k).isdigit()}

        return cls(
            document_id=data.get("document_id"),
            initial_prompt=data.get("initial_prompt", ""),
            retrieved_chunks=data.get("retrieved_chunks", []),
            variables=data.get("variables", {}),
            messages=data.get("messages", []),
            errors=data.get("errors", []),
            is_paused_for_human=data.get("is_paused_for_human", False),
            current_step_id=data.get("current_step_id"),
            current_step_order=data.get("current_step_order"),
            execution_history=data.get("execution_history", []),
            step_execution_counts=counts,
            step_token_usage=usage,
            total_tokens=int(data.get("total_tokens", 0)),
        )
