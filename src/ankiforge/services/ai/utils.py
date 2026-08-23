import ast
import dataclasses
import json
import re
from typing import Any, Type, TypeVar, cast, get_args, get_origin

from jinja2 import Template
from PySide6.QtCore import QCoreApplication, QTimer

from ankiforge.database.models import LLMConfigModel, TokenUsageModel


def _db_log_token_usage(provider: str, model_id: str, prompt_tokens: int, completion_tokens: int, task_type: str) -> None:
    """Fonction interne qui écrit réellement dans la BDD (strictement sur le Main Thread)."""
    cost = 0.0

    # On cherche la config du modèle pour obtenir les tarifs dynamiques
    config = LLMConfigModel.get_or_none(LLMConfigModel.model_id == model_id)
    if config:
        if getattr(config, "is_free", False):
            cost = 0.0
        else:
            cost = (prompt_tokens / 1_000_000 * config.prompt_pricing) + (completion_tokens / 1_000_000 * config.completion_pricing)

    TokenUsageModel.create(
        provider=provider,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=cost,
        task_type=task_type,
    )


def log_token_usage(provider: str, model_id: str, prompt_tokens: int, completion_tokens: int, task_type: str = "1. Reformulation & Génération Wozniak") -> None:
    """
    Enregistre la consommation de jetons (tokens) en base de données et calcule le coût estimé.

    Args:
        provider (str): Nom du fournisseur d'IA (ex: 'openai', 'gemini').
        model_id (str): Identifiant du modèle utilisé.
        prompt_tokens (int): Nombre de jetons envoyés en entrée.
        completion_tokens (int): Nombre de jetons générés en sortie.
        task_type (str): Type de tâche IA pour répartition dans le suivi.
    """
    app = QCoreApplication.instance()
    if app:
        # Téléportation vers l'Event Loop du thread principal de l'UI
        QTimer.singleShot(0, app, lambda: _db_log_token_usage(provider, model_id, prompt_tokens, completion_tokens, task_type))
    else:
        # Fallback si pas d'interface graphique (ex: pendant les tests unitaires via pytest)
        _db_log_token_usage(provider, model_id, prompt_tokens, completion_tokens, task_type)


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
            if fallback_match:
                cleaned_text = fallback_match.group(1).strip()
            else:
                cleaned_text = response_text.strip()

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
    def parse(cls, response_text: str, target_model: Type[T] | None = None) -> T | Any:
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
    def _validate(cls, data: Any, target_model: Type[T]) -> T:
        origin = get_origin(target_model)
        if origin is list:
            args = get_args(target_model)
            if not isinstance(data, list):
                raise ValueError("L'IA n'a pas renvoyé une liste JSON.")
            if args and dataclasses.is_dataclass(args[0]):
                item_type = args[0]
                return [cls._instantiate_dataclass(item, item_type) for item in data]  # type: ignore
            return data  # type: ignore

        elif dataclasses.is_dataclass(target_model):
            if not isinstance(data, dict):
                raise ValueError(f"L'IA n'a pas renvoyé un objet JSON compatible avec {target_model.__name__}.")
            return cast(T, cls._instantiate_dataclass(data, target_model))

        return data

    @classmethod
    def _instantiate_dataclass(cls, data: dict, target_model: Type[T]) -> T:
        if not isinstance(data, dict):
            raise ValueError(f"Données invalides pour instancier {target_model.__name__}. Un dictionnaire était attendu.")

        init_kwargs = {}
        for field in dataclasses.fields(target_model):  # type: ignore
            if field.name in data:
                val = data[field.name]
                field_origin = get_origin(field.type)
                field_args = get_args(field.type)

                if field_origin is list and field_args and dataclasses.is_dataclass(field_args[0]):
                    if not isinstance(val, list):
                        raise ValueError(f"Le champ '{field.name}' doit être une liste.")
                    init_kwargs[field.name] = [cls._instantiate_dataclass(item, cast(Type[T], field_args[0])) for item in val]
                elif dataclasses.is_dataclass(field.type):
                    init_kwargs[field.name] = cls._instantiate_dataclass(val, cast(Type[T], field.type))  # type: ignore
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

    jinja_template = Template(system_prompt_template)
    return jinja_template.render(
        fields_str=fields_str,
        first_field=first_field,
        second_field=second_field,
    )


def extract_cards_from_data(data: Any) -> list[dict[str, Any]]:
    """
    Extrait universellement une liste de dictionnaires représentant des cartes / notes
    depuis n'importe quelle structure (dict avec 'notes'/'cards'/'flashcards', list, ou string JSON).
    """
    if isinstance(data, str):
        try:
            data = AIReponseParser.parse(data)
        except Exception:
            return []

    if isinstance(data, dict):
        for key in ("notes", "cards", "flashcards", "data", "result", "items", "output"):
            if key in data and isinstance(data[key], list):
                return [c for c in data[key] if isinstance(c, dict)]
        if any(k.lower() in ("front", "recto", "question") for k in data.keys()):
            return [data]
        return []

    if isinstance(data, list):
        return [c for c in data if isinstance(c, dict)]

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
