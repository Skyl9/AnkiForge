import json
import re

from PySide6.QtCore import QCoreApplication, QTimer
from jinja2 import Template

from ankiforge.database.models import TokenUsageModel, LLMConfigModel


def _db_log_token_usage(provider: str, model_id: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Fonction interne qui écrit réellement dans la BDD (strictement sur le Main Thread)."""
    cost = 0.0

    # On cherche la config du modèle pour obtenir les tarifs dynamiques
    config = LLMConfigModel.get_or_none(LLMConfigModel.model_id == model_id)
    if config:
        cost = (prompt_tokens / 1_000_000 * config.prompt_pricing) + (completion_tokens / 1_000_000 * config.completion_pricing)

    TokenUsageModel.create(
        provider=provider,
        model_id=model_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        estimated_cost_usd=cost,
    )


def log_token_usage(provider: str, model_id: str, prompt_tokens: int, completion_tokens: int) -> None:
    """
    Enregistre la consommation de jetons (tokens) en base de données et calcule le coût estimé.

    Args:
        provider (str): Nom du fournisseur d'IA (ex: 'openai', 'gemini').
        model_id (str): Identifiant du modèle utilisé.
        prompt_tokens (int): Nombre de jetons envoyés en entrée.
        completion_tokens (int): Nombre de jetons générés en sortie.
    """
    app = QCoreApplication.instance()
    if app:
        # Téléportation vers l'Event Loop du thread principal de l'UI
        QTimer.singleShot(0, app, lambda: _db_log_token_usage(provider, model_id, prompt_tokens, completion_tokens))
    else:
        # Fallback si pas d'interface graphique (ex: pendant les tests unitaires via pytest)
        _db_log_token_usage(provider, model_id, prompt_tokens, completion_tokens)


def parse_ai_json_response(response_text: str):
    """
    Nettoie et convertit la réponse de l'IA en objet Python (dict ou list).
    Extrait intelligemment le bloc JSON même s'il y a du texte autour.
    """
    try:
        backticks = "`" * 3
        # 1. On cherche d'abord proprement un bloc de code markdown
        pattern = backticks + r"(?:json)?\s*(.*?)" + backticks
        match = re.search(pattern, response_text, re.DOTALL)

        if match:
            cleaned_text = match.group(1).strip()
        else:
            # 2. FALLBACK ULTIME : L'IA a oublié les backticks
            fallback_match = re.search(r"(\{.*}|\[.*])", response_text, re.DOTALL)
            if fallback_match:
                cleaned_text = fallback_match.group(1).strip()
            else:
                cleaned_text = response_text.strip()

        # 👇 3. LE BOUCLIER ANTI-CRASH (Version Définitive & Infaillible) 👇
        def escape_latex(m):
            char = m.group(1)
            # Si le backslash protège un caractère JSON valide (ex: \n, \", \\)
            if char in '"\\/bfnrtu':
                return "\\" + char
            # Sinon, c'est du LaTeX rebelle (ex: \(, \[), on double le backslash !
            else:
                return "\\\\" + char

        # On intercepte chaque backslash suivi d'un caractère et on le filtre
        cleaned_text = re.sub(r"\\(.)", escape_latex, cleaned_text)

        return json.loads(cleaned_text)

    except json.JSONDecodeError as e:
        raise ValueError(f"L'IA a généré un format invalide. Impossible de lire le JSON.\nDétail: {e}") from e


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
