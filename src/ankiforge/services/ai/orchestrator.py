import concurrent.futures
import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from jinja2 import Template
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from ankiforge.database.models import LLMConfigModel, PipelineStepModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.rag_service import RAGService
from ankiforge.services.ai.state import PipelineRunState
from ankiforge.services.ai.utils import (
    AIReponseParser,
    extract_cards_from_data,
    format_available_card_models_prompt,
)
from ankiforge.services.plugins.api import PipelineHooksAPI
from ankiforge.services.plugins.event_bus import event_bus

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
        pipeline_id: int | None = None,
        initial_state: PipelineRunState | None = None,
        steps: list[PipelineStepModel] | None = None,
        ai_provider: LLMProvider | None = None,
        tool_registry: dict[str, Callable[[PipelineRunState], Any]] | None = None,
        max_steps: int = 50,
        max_map_workers: int = 4,
    ) -> None:
        super().__init__()
        self.pipeline_id = pipeline_id
        self.state: PipelineRunState = initial_state if initial_state is not None else PipelineRunState()
        self._steps_override = steps
        self._ai_provider = ai_provider
        self.tool_registry: dict[str, Callable[[PipelineRunState], Any]] = tool_registry or {}
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
                logger.warning("Impossible d'instancier le provider LLM, fallback Mock: %s", e)
                self._ai_provider = MockProvider()
        return self._ai_provider

    def _load_steps(self) -> list[PipelineStepModel]:
        """Charge la liste ordonnée des étapes du pipeline."""
        if self._steps_override is not None:
            return list(self._steps_override)

        if self.pipeline_id is None:
            return []

        steps = list(PipelineStepModel.select().where(PipelineStepModel.pipeline == self.pipeline_id).order_by(PipelineStepModel.step_order.asc()))
        return steps

    def _render_prompt_template(self, template_str: str, extra_context: dict[str, Any] | None = None) -> str:
        """Rend une chaîne de template Jinja2 avec le contexte partagé de l'état."""
        if not template_str:
            return ""

        fields_list = self.state.get_variable("fields", ["Front", "Back"])
        if isinstance(fields_list, str):
            try:
                fields_list = json.loads(fields_list)
            except Exception:
                fields_list = ["Front", "Back"]
        if not isinstance(fields_list, list) or not fields_list:
            fields_list = ["Front", "Back"]

        first_field = fields_list[0] if len(fields_list) > 0 else "Front"
        second_field = fields_list[1] if len(fields_list) > 1 else "Back"
        fields_str = ", ".join([f'"{f}"' for f in fields_list])

        selected_models = self.state.get_variable("selected_models", None)
        models_catalog_str = format_available_card_models_prompt(selected_models)

        context: dict[str, Any] = {
            "state": self.state,
            "variables": self.state.variables,
            "retrieved_chunks": self.state.retrieved_chunks,
            "initial_prompt": self.state.initial_prompt,
            "document_id": self.state.document_id,
            "text_source": self.state.get_variable("text_source", ""),
            "last_output": self.state.get_variable("last_output", ""),
            "fields": fields_list,
            "fields_str": fields_str,
            "first_field": first_field,
            "second_field": second_field,
            "available_card_models": models_catalog_str,
            "card_models_catalog": models_catalog_str,
            "card_models": models_catalog_str,
            "document_chunk": self.state.get_variable("document_chunk", "") or self.state.get_variable("text_source", ""),
            "target_deck": self.state.get_variable("target_deck", "Default"),
            "note_type": self.state.get_variable("note_type", "Basique"),
        }
        if extra_context:
            context.update(extra_context)

        try:
            template = Template(template_str)
            return template.render(**context)
        except Exception as e:
            logger.warning("Erreur de rendu Jinja2 sur prompt: %s. Utilisation du texte brut.", e)
            return template_str

    @Slot()
    def run(self) -> None:
        """Point d'entrée de l'exécution asynchrone du DAG."""
        logger.info("[Orchestrateur DAG] Démarrage du pipeline (id=%s)", self.pipeline_id)
        steps = self._load_steps()
        if not steps:
            msg = f"Le pipeline {self.pipeline_id} ne contient aucune étape à exécuter."
            logger.warning(msg)
            self.state.add_error(msg)
            self.signals.error_occurred.emit(msg)
            return

        # Indexer les étapes par id et par ordre pour transitions rapides
        steps_by_order: dict[int, PipelineStepModel] = {int(getattr(s, "step_order", 0)): s for s in steps}
        steps_by_id: dict[int, PipelineStepModel] = {int(getattr(s, "id", 0)): s for s in steps if getattr(s, "id", None) is not None}

        # Déterminer la première étape (step_order le plus bas)
        first_step = min(steps, key=lambda s: int(getattr(s, "step_order", 0)))
        current_step: PipelineStepModel | None = first_step

        executed_count = 0
        event_bus.emit("pipeline_started", self.pipeline_id, self.state)

        try:
            while current_step is not None and not self._is_cancelled:
                if executed_count >= self.max_steps:
                    raise RuntimeError(f"Limite de sécurité atteinte ({self.max_steps} étapes exécutées). Boucle infinie détectée dans le DAG.")

                executed_count += 1
                step_order = int(getattr(current_step, "step_order", 0))
                step_type = str(current_step.step_type or "LLM_PROMPT").upper()
                persona_name = current_step.persona.name if current_step.persona else "Action Système"
                desc = f"Étape {step_order} [{step_type}] : {persona_name}"

                logger.info("[Orchestrateur DAG] Exécution de %s", desc)
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
                    custom_steps = PipelineHooksAPI.get_registered_steps()
                    if step_type in custom_steps:
                        custom_executor = custom_steps[step_type]
                        custom_executor(self, current_step, self.state)

                    elif step_type == "LLM_PROMPT":
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
                        logger.warning("Type d'étape inconnu '%s', exécution standard LLM.", step_type)
                        self._execute_llm_prompt(current_step)

                except Exception as ex:
                    step_succeeded = False
                    step_error_msg = str(ex)
                    logger.exception("Erreur lors de l'exécution de l'étape %d: %s", step_order, ex)
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
                        current_step = steps_by_id.get(int(target_id)) if target_id is not None else None
                    else:
                        # Avancement séquentiel vers la prochaine étape par step_order croissant
                        next_orders = [o for o in steps_by_order if o > step_order]
                        current_step = steps_by_order[min(next_orders)] if next_orders else None  # Fin normale du DAG

                else:
                    # Gestion des échecs selon failure_behavior
                    behavior = str(current_step.failure_behavior or "stop").lower()
                    if behavior == "goto_failure_step" and current_step.on_failure_step:
                        target_id = getattr(current_step.on_failure_step, "id", current_step.on_failure_step)
                        current_step = steps_by_id.get(int(target_id)) if target_id is not None else None
                    elif behavior == "continue":
                        next_orders = [o for o in steps_by_order if o > step_order]
                        current_step = steps_by_order[min(next_orders)] if next_orders else None

                    else:
                        # "stop" par défaut
                        self.signals.error_occurred.emit(step_error_msg)
                        return

            if not self._is_cancelled:
                logger.info("[Orchestrateur DAG] Pipeline terminé avec succès.")
                event_bus.emit("pipeline_finished", self.state)
                self.signals.pipeline_finished.emit(self.state)

        except Exception as e:
            logger.exception("[Orchestrateur DAG Fatal Error] %s", e)
            self.state.add_error(str(e))
            self.signals.error_occurred.emit(str(e))

    # ==========================================
    # MÉTHODES DE TRAITEMENT SPÉCIFIQUES
    # ==========================================

    def _execute_llm_prompt(self, step: PipelineStepModel) -> None:
        """Exécute un prompt LLM standard en interpolant les templates Jinja2."""
        cfg: dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(str(step.config_data))
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
                logger.warning("Parsing JSON impossible pour l'étape %d, conservation du brut: %s", step.step_order, e)
                parsed_output = response_text

        # Mise à jour des variables de l'état partagé
        out_var = cfg.get("output_variable")
        if out_var:
            self.state.set_variable(out_var, parsed_output)
        self.state.set_variable(f"result_step_{step.step_order}", parsed_output)
        self.state.set_variable("last_output", parsed_output)

        # Si l'étape a généré des cartes, on les extrait dans generated_cards
        extracted_cards = extract_cards_from_data(parsed_output)
        if extracted_cards:
            self.state.set_variable("generated_cards", extracted_cards)

    def _execute_rag_retrieval(self, step: PipelineStepModel) -> None:
        """Interroge l'index vectoriel ou effectue une recherche sémantique locale."""
        cfg: dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(str(step.config_data))
            except Exception:
                cfg = {}

        top_k = int(cfg.get("top_k", 5))
        mode = str(cfg.get("retrieval_mode", "hybrid"))
        w_dense = float(cfg.get("w_dense", 0.6))
        w_sparse = float(cfg.get("w_sparse", 0.4))
        rrf_k = int(cfg.get("rrf_k", 60))

        query = (
            cfg.get("rag_query_template")
            or self.state.get_variable("rag_query")
            or (step.persona.system_prompt if step.persona else None)
            or self.state.initial_prompt
            or "Concepts clés et définitions"
        )
        rendered_query = self._render_prompt_template(query)

        doc_id = str(self.state.document_id) if self.state.document_id else "default_doc"
        retrieved: list[str] = []
        rag_results: list[dict[str, Any]] = []

        try:
            llm_config = LLMConfigModel.select().first()
            rag = RAGService(llm_config)
            rag_results = rag.search(
                doc_id=doc_id,
                query=rendered_query,
                top_k=top_k,
                mode=mode,
                w_dense=w_dense,
                w_sparse=w_sparse,
                rrf_k=rrf_k,
            )
            retrieved = [r.get("content", "") if isinstance(r, dict) else str(r) for r in rag_results]
        except Exception as e:
            logger.warning("Recherche RAG Hybride FAISS/BM25 non disponible: %s. Utilisation du fallback mémoire.", e)

        # Fallback en mémoire si aucun chunk FAISS n'est retourné
        if not retrieved:
            text_source = self.state.get_variable("text_source") or self.state.initial_prompt
            if text_source:
                # Découpage basique par paragraphes
                paras = [p.strip() for p in text_source.split("\n\n") if p.strip()]
                retrieved = paras[:top_k]

        out_var = cfg.get("output_variable") or "retrieved_chunks"
        self.state.set_variable(out_var, retrieved)
        self.state.set_variable(f"{out_var}_details", rag_results)
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

        results: list[Any] = []
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
            ordered_results: dict[int, Any] = {}
            for future in concurrent.futures.as_completed(future_to_index):
                if self._is_cancelled:
                    break
                idx = future_to_index[future]
                try:
                    res = future.result()
                    if res is not None:
                        ordered_results[idx] = res
                except Exception as e:
                    logger.error("Erreur sur l'élément %d en Map-Reduce: %s", idx, e)

        # Recomposer les résultats dans l'ordre
        for i in range(total_items):
            if i in ordered_results:
                results.append(ordered_results[i])

        # Phase de Réduction : fusionner les listes ou dictionnaires
        aggregated_cards: list[dict] = []
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
        logger.info("[Orchestrateur DAG] Pause pour validation humaine (étape %d)", step.step_order)
        cfg: dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(str(step.config_data))
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
        cfg: dict[str, Any] = {}
        if step.config_data:
            try:
                cfg = json.loads(str(step.config_data))
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

    def resume(self, modified_state: PipelineRunState | None = None) -> None:
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
