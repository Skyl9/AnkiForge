import ast
import contextvars
import dataclasses
import json
import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, TypeVar, cast, get_args, get_origin

from PySide6.QtCore import QCoreApplication, QTimer

from ankiforge.database.models import LLMConfigModel, TokenUsageModel
from ankiforge.utils.jinja_sandbox import create_prompt_environment

logger = logging.getLogger(__name__)

# Environnement Jinja2 sandboxé (partagé) pour l'interpolation des prompts.
_PROMPT_ENV = create_prompt_environment()

# Gabarit du bloc « MODÈLES DE CARTES AUTORISÉS » pour la balise {{ available_card_models }}.
_CARD_MODELS_PROMPT_TEMPLATE = (
    "### 📋 MODÈLES DE CARTES AUTORISÉS & DIRECTIVES DE SÉLECTION :\n"
    "Pour chaque notion ou concept extrait, CHOISIS le modèle de carte le plus pertinent parmi les modèles autorisés ci-dessous :\n"
    "{% for m in models %}\n"
    '{{ loop.index }}. Modèle : "{{ m.name }}"{% if m.desc %}\n'
    "   - Rôle & Heuristique : {{ m.desc }}{% endif %}\n"
    "   - Champs attendus : {{ m.fields_text }}\n"
    "{% endfor %}\n"
    "### 📦 FORMAT JSON DE SORTIE :\n"
    'Retourne un objet JSON avec la clé "notes" contenant la liste des cartes avec la clé "model" et leurs champs respectifs :\n'
    "{\n"
    '  "notes": [\n'
    "    {\n"
    '      "model": "<Nom du Modèle>",\n'
    '      "fields": {\n'
    '        "<Champ 1>": "...",\n'
    '        "<Champ 2>": "..."\n'
    "      }\n"
    "    }\n"
    "  ]\n"
    "}"
)

# --- Contexte de télémétrie (propagé par pipeline, persona et test A/B) ---
_telemetry_pipeline_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("ankiforge_pipeline_id", default=None)
_telemetry_persona_id: contextvars.ContextVar[int | None] = contextvars.ContextVar("ankiforge_persona_id", default=None)
_telemetry_ab_run_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("ankiforge_ab_run_id", default=None)


@contextmanager
def telemetry_context(
    *,
    pipeline_id: int | None = None,
    persona_id: int | None = None,
    ab_run_id: str | None = None,
) -> Iterator[None]:
    """Associe un contexte de télémétrie aux appels LLM du thread courant (pipeline, persona, test A/B)."""
    token_pipeline = _telemetry_pipeline_id.set(pipeline_id)
    token_persona = _telemetry_persona_id.set(persona_id)
    token_ab = _telemetry_ab_run_id.set(ab_run_id)
    try:
        yield
    finally:
        _telemetry_pipeline_id.reset(token_pipeline)
        _telemetry_persona_id.reset(token_persona)
        _telemetry_ab_run_id.reset(token_ab)


def _db_log_token_usage(
    provider: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    task_type: str,
    pipeline_id: int | None = None,
    persona_id: int | None = None,
    ab_run_id: str | None = None,
) -> None:
    """Fonction interne qui écrit réellement dans la BDD (strictement sur le Main Thread)."""
    cost = 0.0

    # On cherche la config du modèle pour obtenir les tarifs dynamiques de manière déterministe
    config = LLMConfigModel.select().where(LLMConfigModel.model_id == model_id).order_by(LLMConfigModel.sort_order.asc(), LLMConfigModel.id.asc()).first()
    if config:
        cost = 0.0 if getattr(config, "is_free", False) else prompt_tokens / 1000000 * config.prompt_pricing + completion_tokens / 1000000 * config.completion_pricing

    TokenUsageModel.create(
        provider=provider,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=cost,
        task_type=task_type,
        pipeline_id=pipeline_id,
        persona_id=persona_id,
        ab_run_id=ab_run_id,
    )
    logger.debug(
        "Télémétrie Tokens BDD : %s (%s) - Prompt: %d, Completion: %d (Coût: $%.5f, Tâche: '%s', Pipeline: %s, Persona: %s, A/B: %s)",
        provider,
        model_id,
        prompt_tokens,
        completion_tokens,
        cost,
        task_type,
        pipeline_id,
        persona_id,
        ab_run_id,
    )


def log_token_usage(
    provider: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    task_type: str = "1. Reformulation & Génération Wozniak",
    *,
    pipeline_id: int | None = None,
    persona_id: int | None = None,
    ab_run_id: str | None = None,
) -> None:
    """
    Enregistre la consommation de jetons (tokens) en base de données et calcule le coût estimé.

    Args:
        provider (str): Nom du fournisseur d'IA (ex: 'openai', 'gemini').
        model_id (str): Identifiant du modèle utilisé.
        prompt_tokens (int): Nombre de jetons envoyés en entrée.
        completion_tokens (int): Nombre de jetons générés en sortie.
        task_type (str): Type de tâche IA pour répartition dans le suivi.
        pipeline_id (int | None): Pipeline DAG émetteur (défaut: contexte de télémétrie).
        persona_id (int | None): Persona/agent émetteur (défaut: contexte de télémétrie).
        ab_run_id (str | None): Identifiant d'exécution du test A/B (défaut: contexte de télémétrie).
    """
    eff_pipeline = pipeline_id if pipeline_id is not None else _telemetry_pipeline_id.get()
    eff_persona = persona_id if persona_id is not None else _telemetry_persona_id.get()
    eff_ab_run = ab_run_id if ab_run_id is not None else _telemetry_ab_run_id.get()

    logger.info(
        "Consommation tokens : %s / %s - %d tokens (tâche: '%s')",
        provider,
        model_id,
        prompt_tokens + completion_tokens,
        task_type,
    )
    app = QCoreApplication.instance()
    if app:
        # Téléportation vers l'Event Loop du thread principal de l'UI
        QTimer.singleShot(
            0,
            app,
            lambda: _db_log_token_usage(provider, model_id, prompt_tokens, completion_tokens, task_type, eff_pipeline, eff_persona, eff_ab_run),
        )
    else:
        # Fallback si pas d'interface graphique (ex: pendant les tests unitaires via pytest)
        _db_log_token_usage(provider, model_id, prompt_tokens, completion_tokens, task_type, eff_pipeline, eff_persona, eff_ab_run)


T = TypeVar("T")


class AIReponseParser:
    """
    Classe utilitaire pour nettoyer, parser et valider les réponses JSON des LLMs.
    Utilise les dataclasses Python pour une validation rigoureuse des structures.
    """

    @staticmethod
    def _extract_json_string(response_text: str) -> str:
        backticks = "`" * 3
        # 1. On cherche d'abord proprement un bloc de code markdown
        pattern = backticks + r"(?:json)?\s*(.*?)" + backticks
        match = re.search(pattern, response_text, re.DOTALL)

        if match:
            cleaned_text = match.group(1).strip()
        else:
            # 2. FALLBACK ULTIME : L'IA a oublié les backticks
            fallback_match = re.search(r"(\{.*\}|\[.*\])", response_text, re.DOTALL)
            cleaned_text = fallback_match.group(1).strip() if fallback_match else response_text.strip()

        # 3. Normalisation des attributs HTML avec guillemets doubles non échappés
        def fix_html_attrs(m: re.Match) -> str:
            tag = m.group(0)
            tag = re.sub(r'([\w-]+)="([^"]*)"', r"\1='\2'", tag)
            tag = re.sub(r'([\w-]+)=\\"([^\\"]*)\\"', r"\1='\2'", tag)
            return tag

        cleaned_text = re.sub(r"<[^>]+>", fix_html_attrs, cleaned_text)

        # 4. Suppression des virgules traînantes (trailing commas)
        cleaned_text = re.sub(r",\s*([\]\}])", r"\1", cleaned_text)

        # 5. BOUCLIER ANTI-CRASH LATEX
        def escape_latex(m: re.Match) -> str:
            char = m.group(1)
            # Si le backslash protège un caractère JSON valide (ex: \n, \", \\)
            if char in '"\\/bfnrtu':
                return "\\" + char
            # Sinon, c'est du LaTeX rebelle (ex: \(, \[), on double le backslash !
            else:
                return "\\\\" + char

        # On intercepte chaque backslash suivi d'un caractère et on le filtre
        cleaned_text = re.sub(r"\\(.)", escape_latex, cleaned_text)
        return cleaned_text

    @classmethod
    def parse(cls, response_text: str, target_model: type[T] | None = None) -> T | Any:
        """
        Nettoie et convertit la réponse de l'IA en objet Python avec résilience / self-healing.
        Si une dataclass (target_model) est fournie, le JSON sera validé et instancié.
        Sinon, retourne un dictionnaire ou une liste native.
        """
        cleaned_text = cls._extract_json_string(response_text)
        data: Any = None

        try:
            data = json.loads(cleaned_text)
        except json.JSONDecodeError:
            # Fallback 1 : structure dictionnaire Python native
            if len(cleaned_text) > 100_000:
                data = None
            else:
                try:
                    data = ast.literal_eval(cleaned_text)
                except (ValueError, SyntaxError, TypeError, MemoryError):
                    data = None

        if data is None:
            # Fallback 2 : Extraction individuelle d'objets {...} pour JSON partiel
            individual_objects = []
            for obj_match in re.finditer(r"\{[^{}]+\}", response_text):
                try:
                    o_clean = cls._extract_json_string(obj_match.group(0))
                    loaded_obj = json.loads(o_clean)
                    if isinstance(loaded_obj, dict):
                        individual_objects.append(loaded_obj)
                except (json.JSONDecodeError, ValueError):
                    pass

            if individual_objects:
                data = {"notes": individual_objects}

        if data is None:
            try:
                data = json.loads(cleaned_text)
            except json.JSONDecodeError as e:
                raise ValueError(f"L'IA a généré un format invalide. Impossible de lire le JSON.\nDétail: {e}") from e

        if target_model is not None:
            return cls._validate(data, target_model)

        return data

    @classmethod
    def _validate(cls, data: Any, target_model: type[T]) -> T:
        origin = get_origin(target_model)
        if origin is list:
            args = get_args(target_model)
            if not isinstance(data, list):
                raise ValueError("L'IA n'a pas renvoyé une liste JSON.")
            if args and dataclasses.is_dataclass(args[0]):
                item_type = cast(type[T], args[0])
                return cast(T, [cls._instantiate_dataclass(item, item_type) for item in data])
            return cast(T, data)

        elif dataclasses.is_dataclass(target_model):
            if not isinstance(data, dict):
                raise ValueError(f"L'IA n'a pas renvoyé un objet JSON compatible avec {target_model.__name__}.")
            return cast(T, cls._instantiate_dataclass(data, target_model))

        return data

    @classmethod
    def _instantiate_dataclass(cls, data: dict, target_model: type[T]) -> T:
        if not isinstance(data, dict):
            raise ValueError(f"Données invalides pour instancier {target_model.__name__}. Un dictionnaire était attendu.")

        init_kwargs = {}
        for field in dataclasses.fields(cast(Any, target_model)):
            if field.name in data:
                val = data[field.name]
                field_origin = get_origin(field.type)
                field_args = get_args(field.type)

                if field_origin is list and field_args and dataclasses.is_dataclass(field_args[0]):
                    if not isinstance(val, list):
                        raise ValueError(f"Le champ '{field.name}' doit être une liste.")
                    init_kwargs[field.name] = [cls._instantiate_dataclass(item, cast(type[T], field_args[0])) for item in val]
                elif dataclasses.is_dataclass(field.type):
                    init_kwargs[field.name] = cls._instantiate_dataclass(val, cast(type[T], field.type))  # type: ignore
                else:
                    init_kwargs[field.name] = val
            elif field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                field_args = get_args(field.type)
                if type(None) in field_args:
                    init_kwargs[field.name] = None  # type: ignore
                else:
                    raise ValueError(f"Clé manquante dans le JSON pour le champ requis: '{field.name}'")

        try:
            return target_model(**init_kwargs)
        except Exception as e:
            raise ValueError(f"Erreur de validation lors de la création de {target_model.__name__} : {e}") from e


def format_system_prompt(system_prompt_template: str, fields_schema_json: str | None) -> str:
    """
    Remplit dynamiquement un prompt système Jinja2 avec les champs Anki cibles.

    Args:
        system_prompt_template (str): Le prompt système brut contenant les variables Jinja2.
        fields_schema_json (str | None): Le schéma JSON des champs du modèle de note.

    Returns:
        str: Le prompt système final prêt à être envoyé à l'IA.
    """
    fields = json.loads(fields_schema_json) if fields_schema_json else ["Front", "Back"]
    fields_str = '", "'.join(fields)

    first_field = fields[0] if len(fields) > 0 else "Field1"
    second_field = fields[1] if len(fields) > 1 else "Field2"

    jinja_template = _PROMPT_ENV.from_string(system_prompt_template)
    return jinja_template.render(
        fields_str=fields_str,
        first_field=first_field,
        second_field=second_field,
    )


def format_available_card_models_prompt(models: list[Any] | None = None) -> str:
    """
    Génère un bloc de directives sémantiques et de schémas JSON pour la balise {{ available_card_models }}.
    """
    if not models:
        try:
            from ankiforge.database.models import NoteTypeModel

            models = list(NoteTypeModel.select())
        except Exception:
            models = []

    if not models:
        return ""

    model_entries = []
    for m in models:
        if isinstance(m, dict):
            name = m.get("name", "")
            desc = m.get("description", "")
            fields_schema = m.get("fields_schema", '["Front", "Back"]')
        else:
            name = getattr(m, "name", "")
            desc = getattr(m, "description", "")
            fields_schema = getattr(m, "fields_schema", '["Front", "Back"]')

        if isinstance(fields_schema, str):
            try:
                fields_list = json.loads(fields_schema)
            except json.JSONDecodeError:
                fields_list = ["Front", "Back"]
        elif isinstance(fields_schema, list):
            fields_list = fields_schema
        else:
            fields_list = ["Front", "Back"]

        fields_sample = ", ".join([f'"{f}": "..."' for f in fields_list])
        model_entries.append({"name": name, "desc": desc, "fields_text": "{" + fields_sample + "}"})

    return _PROMPT_ENV.from_string(_CARD_MODELS_PROMPT_TEMPLATE).render(models=model_entries)


def _normalize_card_item(item: dict[str, Any]) -> dict[str, Any]:
    """Aplatit les structures {"model": "...", "fields": {...}} en conservant l'annotation de modèle."""
    res = dict(item)
    if "fields" in res and isinstance(res["fields"], dict):
        inner_fields = res.pop("fields")
        for k, v in inner_fields.items():
            if k not in res:
                res[k] = v
    if "note_type" in res and "model" not in res:
        res["model"] = res.pop("note_type")
    return res


def normalize_card_fields(cards: list[dict[str, Any]], expected_fields: list[str]) -> list[dict[str, Any]]:
    """Normalise des dictionnaires de cartes pour correspondre strictement aux champs attendus."""
    prepared: list[dict[str, Any]] = []
    for card_data in cards:
        if not isinstance(card_data, dict):
            continue

        cleaned: dict[str, str] = {}
        lower_card = {str(k).lower().strip(): v for k, v in card_data.items()}
        raw_vals = list(card_data.values())

        for i, f in enumerate(expected_fields):
            f_lower = f.lower().strip()
            if f_lower in lower_card:
                val = lower_card[f_lower]
            elif i < len(raw_vals):
                val = raw_vals[i]
            else:
                val = ""

            if isinstance(val, list):
                val_str = "<br>".join(str(item) for item in val)
            elif val is not None:
                val_str = str(val)
            else:
                val_str = ""

            cleaned[f] = val_str

        prepared.append(cleaned)
    return prepared


def extract_cards_from_data(data: Any) -> list[dict[str, Any]]:
    """
    Extrait universellement une liste de dictionnaires représentant des cartes / notes
    depuis n'importe quelle structure via validation Pydantic et auto-réparation (Self-Healing).
    Supporte les formats multi-modèles structurés {"model": "...", "fields": {...}}.
    """
    try:
        from ankiforge.services.ai.schemas import GeneratedCardsContainerSchema, SelfHealingValidator

        container = SelfHealingValidator.parse_and_validate(data, GeneratedCardsContainerSchema)
        if container and container.notes:
            result: list[dict[str, Any]] = []
            for n in container.notes:
                card_dict: dict[str, Any] = dict(n.fields)
                if n.model:
                    card_dict["model"] = n.model
                if n.tags:
                    card_dict["tags"] = n.tags
                result.append(card_dict)
            if result:
                return result
    except Exception as err:
        logger.debug("Parsing du schéma de cartes générées ignoré : %s", err)

    if isinstance(data, str):
        try:
            data = AIReponseParser.parse(data)
        except Exception:
            return []

    if isinstance(data, dict):
        for key in ("notes", "cards", "flashcards", "data", "result", "items", "output"):
            if key in data and isinstance(data[key], list):
                return [_normalize_card_item(c) for c in data[key] if isinstance(c, dict)]
        if any(k.lower() in ("front", "recto", "question") for k in data):
            return [_normalize_card_item(data)]
        return []

    if isinstance(data, list):
        return [_normalize_card_item(c) for c in data if isinstance(c, dict)]

    return []


def get_human_readable_api_error(error: Exception) -> str:
    """
    Traduit les erreurs techniques d'API (OpenAI, Gemini, requêtes locales)
    en messages compréhensibles et orientés action pour l'utilisateur.
    """
    error_str = str(error).lower()

    # 1. Erreurs de Quotas et Surcharge (429)
    if any(k in error_str for k in ["429", "quota", "resource exhausted", "rate limit", "too many requests"]):
        return "Vous avez dépassé votre quota d'utilisation ou le service est actuellement surchargé. Veuillez patienter un moment ou vérifier votre facturation API."

    # 2. Erreurs d'Authentification (401 / 403)
    if any(k in error_str for k in ["401", "403", "unauthorized", "api_key_invalid", "api key", "authentication"]):
        return "La clé API fournie est invalide, expirée ou manquante. Veuillez vérifier vos paramètres d'authentification IA."

    # 3. Timeout et Connexion Perdue
    if any(k in error_str for k in ["timeout", "timed out", "read timeout"]):
        return "La connexion au service IA a expiré (Timeout). Le modèle est peut-être surchargé ou votre connexion internet est instable."

    # 4. Connexion refusée (Typique de Ollama éteint)
    if any(k in error_str for k in ["connection refused", "failed to establish", "connrefused", "target machine actively refused"]):
        return "Impossible de se connecter au service. Si vous utilisez Ollama en local, vérifiez que le logiciel est bien lancé en arrière-plan."

    # 5. Dépassement de contexte
    if any(k in error_str for k in ["context length", "maximum context", "token limit"]):
        return "Le document fourni est trop long pour la capacité de mémoire de ce modèle. Essayez de réduire la taille du découpage (Chunking) ou utilisez un modèle avec un plus grand contexte."

    # 6. Erreur serveur générique (500)
    if any(k in error_str for k in ["500", "502", "503", "internal server error", "bad gateway"]):
        return "Le serveur du fournisseur IA a rencontré une erreur interne. Veuillez réessayer plus tard."

    # Fallback : on renvoie l'erreur brute mais encapsulée proprement
    return f"Une erreur technique est survenue : {str(error)}"
