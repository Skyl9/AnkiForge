from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class PipelineRunState:
    """
    L'objet de Contexte (State) qui voyage d'étape en étape dans le DAG (Moteur d'Orchestration IA).
    Au lieu de passer de simples strings, chaque étape enrichit ou lit cet état.
    """

    # Identifiants de contexte de base
    document_id: Optional[int] = None
    initial_prompt: str = ""

    # Contexte RAG (Retrieval-Augmented Generation)
    retrieved_chunks: List[str] = field(default_factory=list)

    # Variables dynamiques stockées par les étapes (ex: plan_du_cours, cartes_generees)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Historique de la conversation pour les agents conversationnels (ReAct)
    messages: List[Dict[str, str]] = field(default_factory=list)

    # État de l'exécution
    errors: List[str] = field(default_factory=list)
    is_paused_for_human: bool = False
    current_step_id: Optional[int] = None

    def add_error(self, error_message: str) -> None:
        """Ajoute une erreur à l'état."""
        self.errors.append(error_message)

    def set_variable(self, key: str, value: Any) -> None:
        """Définit une variable dans l'état partagé."""
        self.variables[key] = value

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Récupère une variable de l'état partagé."""
        return self.variables.get(key, default)
