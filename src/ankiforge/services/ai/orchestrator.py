import concurrent.futures
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from jinja2 import Template
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ankiforge.database.models import LLMConfigModel, PipelineStepModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import AIReponseParser

logger = logging.getLogger(__name__)


class PipelineWorkerSignals(QObject):
    """Signaux Qt émis par le Worker (Orchestrateur DAG) vers l'UI."""

    step_started = Signal(int, str)  # step_order, description
    step_progress = Signal(int, int, str)  # current_item, total_items, detail
    step_completed = Signal(int, object)  # step_order, state (PipelineRunState)
    human_validation_required = Signal(object)  # state pour l'UI (Copilote)
    pipeline_finished = Signal(object)  # state final
    error_occurred = Signal(str)
    cancelled = Signal()


class PipelineOrchestrator(QRunnable):
    """
    Cœur du Moteur d'Orchestration en Graphe Orienté Acyclique (DAG).
    Exécute les étapes du pipeline de manière asynchrone (QRunnable / QThreadPool)
    avec support du RAG, Map-Reduce, outils Python et points d'arrêt pour validation humaine.
    """

    def __init__(
        self,
        pipeline_id: Optional[int] = None,
        initial_state: Optional[PipelineRunState] = None,
        steps: Optional[List[PipelineStepModel]] = None,
        ai_provider: Optional[LLMProvider] = None,
        tool_registry: Optional[Dict[str, Callable[[PipelineRunState], Any]]] = None,
        max_steps: int = 50,
        max_map_workers: int = 4,
    ) -> None:
        super().__init__()
        self.pipeline_id = pipeline_id
        self.state: PipelineRunState = initial_state if initial_state is not None else PipelineRunState()
        self._steps_override = steps
        self._ai_provider = ai_provider
        self.tool_registry: Dict[str, Callable[[PipelineRunState], Any]] = tool_registry or {}
        self.max_steps = max_steps
        self.max_map_workers = max_map_workers

        self.signals = PipelineWorkerSignals()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Initialisé à l'état actif (non en pause)
        self._is_cancelled = False

    @property
    def ai_provider(self) -> LLMProvider:
        """Fournisseur LLM actif avec fallback paresseux."""
        if self._ai_provider is None:
            try:
                config = LLMConfigModel.select().first()
                if config:
                    self._ai_provider = AIManager.create_provider_from_config(config)
                else:
                    self._ai_provider = MockProvider()
            except Exception as e:
                logger.warning(f"Impossible d'instancier le provider LLM, fallback Mock: {e}")
                self._ai_provider = MockProvider()
        return self._ai_provider

    def _load_steps(self) -> List[PipelineStepModel]:
        """Charge la liste ordonnée des étapes du pipeline."""
        if self._steps_override is not None:
            return list(self._steps_override)

        if self.pipeline_id is None:
            return []

        steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == self.pipeline_id).order_by(PipelineStepModel.step_order.asc()))
        return steps

    def _render_prompt_template(self, template_str: str, extra_context: Optional[Dict[str, Any]] = None) -> str:
        """Rend une chaîne de template Jinja2 avec le contexte partagé de l'état."""
        if not template_str:
            return ""

        context: Dict[str, Any] = {
            "state": self.state,
            "variables": self.state.variables,
            "retrieved_chunks": self.state.retrieved_chunks,
            "initial_prompt": self.state.initial_prompt,
            "document_id": self.state.document_id,
            "text_source": self.state.get_variable("text_source", ""),
            "last_output": self.state.get_variable("last_output", ""),
            "fields": self.state.get_variable("fields", ["Front", "Back"]),
        }
        if extra_context:
            context.update(extra_context)

        try:
            template = Template(template_str)
            return template.render(**context)
        except Exception as e:
            logger.warning(f"Erreur de rendu Jinja2 sur prompt: {e}. Utilisation du texte brut.")
            return template_str

    @Slot()
    def run(self) -> None:
        """Point d'entrée de l'exécution asynchrone du DAG."""
        logger.info(f"[Orchestrateur DAG] Démarrage du pipeline (id={self.pipeline_id})")
        steps = self._load_steps()
        if not steps:
            msg = f"Le pipeline {self.pipeline_id} ne contient aucune étape à exécuter."
            logger.warning(msg)
            self.state.add_error(msg)
            self.signals.error_occurred.emit(msg)
            return

        # Indexer les étapes par id et par ordre pour transitions rapides
        steps_by_order: Dict[int, PipelineStepModel] = {s.step_order: s for s in steps}
        steps_by_id: Dict[int, PipelineStepModel] = {s.id: s for s in steps if s.id is not None}

        # Déterminer la première étape (step_order le plus bas)
        first_step = min(steps, key=lambda s: s.step_order)
        current_step: Optional[PipelineStepModel] = first_step

        executed_count = 0

        try:
            while current_step is not None and not self._is_cancelled:
                if executed_count >= self.max_steps:
                    raise RuntimeError(f"Limite de sécurité atteinte ({self.max_steps} étapes exécutées). Boucle infinie détectée dans le DAG.")

                executed_count += 1
                step_order = current_step.step_order
                step_type = (current_step.step_type or "LLM_PROMPT").upper()
                persona_name = current_step.persona.name if current_step.persona else "Action Système"
                desc = f"Étape {step_order} [{step_type}] : {persona_name}"

                logger.info(f"[Orchestrateur DAG] Exécution de {desc}")
                self.signals.step_started.emit(step_order, desc)

                self.state.current_step_id = current_step.id
                self.state.current_step_order = step_order
                t_start = time.perf_counter()

                step_succeeded = True
                step_error_msg = ""

                try:
                    # ==========================================
                    # ROUTEUR D'EXÉCUTION DES ÉTAPES DU DAG
                    # ==========================================
                    if step_type == "LLM_PROMPT":
                        self._execute_llm_prompt(current_step)

                    elif step_type == "RAG_RETRIEVAL":
                        self._execute_rag_retrieval(current_step)

                    elif step_type == "MAP_REDUCE":
                        self._execute_map_reduce(current_step)

                    elif step_type == "HUMAN_VALIDATION":
                        self._execute_human_validation(current_step)

                    elif step_type == "PYTHON_TOOL":
                        self._execute_python_tool(current_step)

                    else:
                        logger.warning(f"Type d'étape inconnu '{step_type}', exécution standard LLM.")
                        self._execute_llm_prompt(current_step)

                except Exception as ex:
                    step_succeeded = False
                    step_error_msg = str(ex)
                    logger.exception(f"Erreur lors de l'exécution de l'étape {step_order}: {ex}")
                    self.state.add_error(f"Étape {step_order} ({step_type}): {step_error_msg}")

                duration = time.perf_counter() - t_start

                if self._is_cancelled:
                    logger.info("[Orchestrateur DAG] Pipeline annulé par l'utilisateur.")
                    self.signals.cancelled.emit()
                    return

                # Log de l'étape dans l'historique de l'état
                status_str = "SUCCESS" if step_succeeded else "FAILED"
                self.state.log_step_execution(
                    step_order=step_order,
                    step_type=step_type,
                    status=status_str,
                    duration_sec=duration,
                    details=step_error_msg if not step_succeeded else None,
                )

                self.signals.step_completed.emit(step_order, self.state)

                # ==========================================
                # GESTION DES TRANSITIONS ET BRANCHEMENTS DU DAG
                # ==========================================
                if step_succeeded:
                    if current_step.on_success_step:
                        # Si l'objet est déjà chargé ou présent dans notre index
                        target_id = getattr(current_step.on_success_step, "id", current_step.on_success_step)
                        current_step = steps_by_id.get(target_id, current_step.on_success_step)
                    else:
                        # Avancement séquentiel vers la prochaine étape par step_order croissant
                        next_orders = [o for o in steps_by_order.keys() if o > step_order]
                        if next_orders:
                            current_step = steps_by_order[min(next_orders)]
                        else:
                            current_step = None  # Fin normale du DAG
                else:
                    # Gestion des échecs selon failure_behavior
                    behavior = (current_step.failure_behavior or "stop").lower()
                    if behavior == "goto_failure_step" and current_step.on_failure_step:
                        target_id = getattr(current_step.on_failure_step, "id", current_step.on_failure_step)
                        current_step = steps_by_id.get(target_id, current_step.on_failure_step)
                    elif behavior == "continue":
                        next_orders = [o for o in steps_by_order.keys() if o > step_order]
                        current_step = steps_by_order[min(next_orders)] if next_orders else None
                    else:
                        # "stop" par défaut
                        self.signals.error_occurred.emit(step_error_msg)
                        return

            if not self._is_cancelled:
                logger.info("[Orchestrateur DAG] Pipeline terminé avec succès.")
                self.signals.pipeline_finished.emit(self.state)

        except Exception as e:
            logger.exception(f"[Orchestrateur DAG Fatal Error] {e}")
            self.state.add_error(str(e))
            self.signals.error_occurred.emit(str(e))

    # ==========================================
    # MÉTHODES DE TRAITEMENT SPÉCIFIQUES
    # ==========================================

    def _execute_llm_prompt(self, step: PipelineStepModel) -> None:
        """Exécute un prompt LLM standard en interpolant les templates Jinja2."""
        cfg: Dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(step.config_data)
            except Exception:
                cfg = {}

        raw_system_prompt = cfg.get("prompt_override") or (step.persona.system_prompt if step.persona else "")
        rendered_sys = self._render_prompt_template(raw_system_prompt)

        # Préparation du prompt utilisateur à partir du contexte courant
        input_var = cfg.get("input_variable")
        if input_var:
            user_input = self.state.get_variable(input_var)
        else:
            user_input = self.state.get_variable("last_output") or self.state.get_variable("text_source") or self.state.initial_prompt or "Analyser et générer les flashcards correspondantes."

        if isinstance(user_input, (dict, list)):
            user_input = json.dumps(user_input, ensure_ascii=False, indent=2)

        output_format = str(cfg.get("output_format") or (getattr(step.persona, "output_format", "json") if step.persona else "json"))

        # Provider override si configuré
        provider = self.ai_provider
        if cfg.get("llm_config_id"):
            override_cfg = LLMConfigModel.get_or_none(LLMConfigModel.id == cfg["llm_config_id"])
            if override_cfg:
                try:
                    provider = AIManager.create_provider_from_config(override_cfg)
                except Exception as e:
                    logger.warning("Impossible d'instancier le provider dédié: %s", e)

        response_text = provider.generate(
            system_prompt=rendered_sys,
            user_prompt=user_input,
            response_format=output_format,
        )

        parsed_output: Any = response_text
        if output_format == "json":
            try:
                parsed_output = AIReponseParser.parse(response_text)
            except Exception as e:
                logger.warning(f"Parsing JSON impossible pour l'étape {step.step_order}, conservation du brut: {e}")
                parsed_output = response_text

        # Mise à jour des variables de l'état partagé
        out_var = cfg.get("output_variable")
        if out_var:
            self.state.set_variable(out_var, parsed_output)
        self.state.set_variable(f"result_step_{step.step_order}", parsed_output)
        self.state.set_variable("last_output", parsed_output)

        # Si l'étape a généré des cartes, on les extrait dans generated_cards
        if isinstance(parsed_output, dict) and "cards" in parsed_output and isinstance(parsed_output["cards"], list):
            self.state.set_variable("generated_cards", parsed_output["cards"])
        elif isinstance(parsed_output, list) and len(parsed_output) > 0 and isinstance(parsed_output[0], dict):
            self.state.set_variable("generated_cards", parsed_output)

    def _execute_rag_retrieval(self, step: PipelineStepModel) -> None:
        """Interroge l'index vectoriel ou effectue une recherche sémantique locale."""
        cfg: Dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(step.config_data)
            except Exception:
                cfg = {}

        top_k = int(cfg.get("top_k", 5))
        query = (
            cfg.get("rag_query_template")
            or self.state.get_variable("rag_query")
            or (step.persona.system_prompt if step.persona else None)
            or self.state.initial_prompt
            or "Concepts clés et définitions"
        )
        rendered_query = self._render_prompt_template(query)

        doc_id = str(self.state.document_id) if self.state.document_id else "default_doc"
        retrieved: List[str] = []

        try:
            llm_config = LLMConfigModel.select().first()
            if llm_config:
                rag = RAGService(llm_config)
                rag_results = rag.search(doc_id, rendered_query, top_k=top_k)
                retrieved = [r.get("content", "") if isinstance(r, dict) else str(r) for r in rag_results]
        except Exception as e:
            logger.warning(f"Recherche RAG FAISS non disponible: {e}. Utilisation du fallback mémoire.")

        # Fallback en mémoire si aucun chunk FAISS n'est retourné
        if not retrieved:
            text_source = self.state.get_variable("text_source") or self.state.initial_prompt
            if text_source:
                # Découpage basique par paragraphes
                paras = [p.strip() for p in text_source.split("\n\n") if p.strip()]
                retrieved = paras[:top_k]

        out_var = cfg.get("output_variable") or "retrieved_chunks"
        self.state.set_variable(out_var, retrieved)
        self.state.add_retrieved_chunks(retrieved)
        self.state.set_variable("last_output", "\n\n".join(retrieved))

    def _execute_map_reduce(self, step: PipelineStepModel) -> None:
        """
        Découpe une liste d'éléments (chunks de documents, liste de cartes)
        et applique la Persona sur chaque élément en parallèle (Map) puis fusionne (Reduce).
        """
        # Trouver la liste d'éléments à mapper
        items = self.state.get_variable("map_items") or self.state.get_variable("chunks") or self.state.get_variable("cards") or self.state.retrieved_chunks

        if isinstance(items, str):
            items = [p.strip() for p in items.split("\n\n") if p.strip()]

        if not items or not isinstance(items, list):
            logger.info("Aucun élément trouvé pour l'étape MAP_REDUCE. Étape ignorée.")
            return

        total_items = len(items)
        raw_system_prompt = step.persona.system_prompt if step.persona else "Analyser et traiter le contenu."
        output_format = getattr(step.persona, "output_format", "json") if step.persona else "json"

        results: List[Any] = []
        completed_count = 0

        def _process_item(index: int, item_content: Any) -> Any:
            nonlocal completed_count
            if self._is_cancelled:
                return None

            item_str = json.dumps(item_content, ensure_ascii=False) if isinstance(item_content, (dict, list)) else str(item_content)
            rendered_sys = self._render_prompt_template(raw_system_prompt, extra_context={"item": item_content, "index": index})

            response = self.ai_provider.generate(
                system_prompt=rendered_sys,
                user_prompt=item_str,
                response_format=output_format,
            )

            parsed = response
            if output_format == "json":
                try:
                    parsed = AIReponseParser.parse(response)
                except Exception:
                    parsed = response

            completed_count += 1
            self.signals.step_progress.emit(
                completed_count,
                total_items,
                f"Génération Parallèle : {completed_count}/{total_items}",
            )
            return parsed

        # Exécution parallèle avec ThreadPoolExecutor
        workers = min(self.max_map_workers, max(1, total_items))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_index = {executor.submit(_process_item, i, item): i for i, item in enumerate(items)}
            ordered_results: Dict[int, Any] = {}
            for future in concurrent.futures.as_completed(future_to_index):
                if self._is_cancelled:
                    break
                idx = future_to_index[future]
                try:
                    res = future.result()
                    if res is not None:
                        ordered_results[idx] = res
                except Exception as e:
                    logger.error(f"Erreur sur l'élément {idx} en Map-Reduce: {e}")

        # Recomposer les résultats dans l'ordre
        for i in range(total_items):
            if i in ordered_results:
                results.append(ordered_results[i])

        # Phase de Réduction : fusionner les listes ou dictionnaires
        aggregated_cards: List[dict] = []
        for r in results:
            if isinstance(r, dict) and "cards" in r and isinstance(r["cards"], list):
                aggregated_cards.extend(r["cards"])
            elif isinstance(r, list):
                for sub in r:
                    if isinstance(sub, dict):
                        aggregated_cards.append(sub)
            elif isinstance(r, dict):
                aggregated_cards.append(r)

        self.state.set_variable("map_reduce_results", results)
        if aggregated_cards:
            self.state.set_variable("generated_cards", aggregated_cards)
        self.state.set_variable("last_output", aggregated_cards if aggregated_cards else results)

    def _execute_human_validation(self, step: PipelineStepModel) -> None:
        """Met le DAG en pause et attend l'interaction de l'utilisateur sur l'UI."""
        logger.info(f"[Orchestrateur DAG] Pause pour validation humaine (étape {step.step_order})")
        cfg: Dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(step.config_data)
            except Exception:
                cfg = {}
        self.state.set_variable("human_validation_config", cfg)
        self.state.is_paused_for_human = True
        self._pause_event.clear()

        # Émettre le signal pour ouvrir la modale / débloquer l'IHM
        self.signals.human_validation_required.emit(self.state)

        # Attente propre et non-bloquante pour la boucle Qt (bloque seulement ce thread de travail)
        self._pause_event.wait()
        self.state.is_paused_for_human = False

    def _execute_python_tool(self, step: PipelineStepModel) -> None:
        """Exécute un outil Python (natif ou script personnalisé BDD) sur l'état partagé."""
        cfg: Dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(step.config_data)
            except Exception:
                cfg = {}

        tool_name = cfg.get("tool_name") or (step.persona.name if step.persona else "clean_html_latex")

        # 1. Vérifier si un callback est surchargé dans tool_registry en mémoire
        if tool_name in self.tool_registry:
            tool_fn = self.tool_registry[tool_name]
            result = tool_fn(self.state)
        else:
            from ankiforge.services.tools.tool_service import ToolService

            result = ToolService.execute_tool(tool_name, self.state, cfg.get("tool_args"))

        out_var = cfg.get("output_variable") or f"result_tool_{step.step_order}"
        self.state.set_variable(out_var, result)
        self.state.set_variable(f"result_tool_{step.step_order}", result)

    # ==========================================
    # CONTRÔLES EXTERNES (THREAD-SAFE / APPELÉS PAR L'UI)
    # ==========================================

    def resume(self, modified_state: Optional[PipelineRunState] = None) -> None:
        """Reprend l'exécution du DAG après validation humaine."""
        if modified_state is not None:
            self.state = modified_state
        self.state.is_paused_for_human = False
        self._pause_event.set()
        logger.info("[Orchestrateur DAG] Signal de reprise (resume) reçu.")

    def cancel(self) -> None:
        """Demande l'arrêt immédiat et définitif du pipeline."""
        self._is_cancelled = True
        self.state.is_paused_for_human = False
        self._pause_event.set()
        logger.info("[Orchestrateur DAG] Signal d'annulation (cancel) reçu.")
