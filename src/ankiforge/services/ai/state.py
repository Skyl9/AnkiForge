import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunState:
    """
    Objet de Contexte (State) partagé voyageant d'étape en étape dans le DAG (Moteur d'Orchestration IA).
    Chaque étape lit et enrichit cet état de façon dynamique.
    """

    # Identifiants de contexte et données sources
    document_id: Optional[int] = None
    initial_prompt: str = ""

    # Contexte RAG (Retrieval-Augmented Generation)
    retrieved_chunks: List[str] = field(default_factory=list)

    # Variables dynamiques stockées par les étapes (ex: plan_du_cours, generated_cards, map_reduce_results)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Historique de conversation / messages pour les agents (ReAct / Chat)
    messages: List[Dict[str, str]] = field(default_factory=list)

    # Suivi d'exécution
    errors: List[str] = field(default_factory=list)
    is_paused_for_human: bool = False
    current_step_id: Optional[int] = None
    current_step_order: Optional[int] = None
    execution_history: List[Dict[str, Any]] = field(default_factory=list)

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

    def add_retrieved_chunks(self, chunks: List[str]) -> None:
        """Ajoute des morceaux de texte récupérés par le RAG."""
        self.retrieved_chunks.extend(chunks)
        self.variables["retrieved_chunks"] = self.retrieved_chunks

    def log_step_execution(
        self,
        step_order: int,
        step_type: str,
        status: str,
        duration_sec: float = 0.0,
        details: Optional[str] = None,
    ) -> None:
        """Enregistre l'exécution d'une étape dans l'historique."""
        self.execution_history.append(
            {
                "step_order": step_order,
                "step_type": step_type,
                "status": status,
                "duration_sec": round(duration_sec, 3),
                "details": details,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
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
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineRunState":
        """Reconstruit un PipelineRunState depuis un dictionnaire sérialisé."""
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
        )
