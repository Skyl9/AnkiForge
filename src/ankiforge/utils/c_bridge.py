import ctypes
import logging
import platform
from pathlib import Path

from ankiforge.utils.paths import get_resource_path

logger = logging.getLogger(__name__)

ext = "dll" if platform.system() == "Windows" else "so"
_candidates = [
    get_resource_path("c_ext", f"levenshtein_distance.{ext}"),
    get_resource_path("src", "c_ext", f"levenshtein_distance.{ext}"),
    get_resource_path(f"levenshtein_distance.{ext}"),
    get_resource_path("src", "ankiforge", "c_ext", f"levenshtein_distance.{ext}"),
    get_resource_path("ankiforge", "c_ext", f"levenshtein_distance.{ext}"),
]
lib_path: Path = next((p for p in _candidates if p.exists()), _candidates[0])

_matcher_lib: ctypes.CDLL | None = None
C_MATCHER_LOADED = False


def init_c_matcher(custom_path: Path | None = None) -> bool:
    """
    Initialise la librairie C native Levenshtein.

    Si la librairie est absente ou si son chargement échoue, émet un avertissement explicite
    et bascule sur le repli pur Python difflib (performances réduites).
    """
    global _matcher_lib, C_MATCHER_LOADED
    target = custom_path if custom_path is not None else lib_path
    try:
        if target.exists():
            _matcher_lib = ctypes.CDLL(str(target))
            _matcher_lib.calculate_similarity.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            _matcher_lib.calculate_similarity.restype = ctypes.c_double
            C_MATCHER_LOADED = True
            logger.info("Extension C Levenshtein chargée avec succès depuis %s", target)
            return True
        else:
            logger.warning(
                "Extension C Levenshtein non trouvée à %s, repli transparent sur difflib (performances réduites).",
                target,
            )
            _matcher_lib = None
            C_MATCHER_LOADED = False
            return False
    except Exception as e:
        logger.warning("Erreur lors du chargement de l'extension C (%s) : %s. Repli sur difflib.", target, e)
        _matcher_lib = None
        C_MATCHER_LOADED = False
        return False


C_MATCHER_LOADED = init_c_matcher()


def get_similarity(text1: str, text2: str) -> float:
    """
    Calcule le taux de similarité sémantique entre deux textes.

    Tente d'utiliser l'extension C ultra-rapide (Levenshtein) si compilée,
    sinon utilise difflib en Python pur comme solution de secours.

    Args:
        text1 (str): Premier texte à comparer.
        text2 (str): Second texte à comparer.

    Returns:
        float: Indice de similarité entre 0.0 (totalement différent) et 1.0 (identique).
    """
    if C_MATCHER_LOADED and _matcher_lib is not None:
        try:
            # En C, les chaînes doivent être encodées en bytes
            return float(_matcher_lib.calculate_similarity(text1.encode("utf-8"), text2.encode("utf-8")))
        except Exception as exec_err:
            logger.warning("Erreur à l'exécution de l'extension C Levenshtein : %s. Repli sur difflib.", exec_err)

    import difflib

    return float(difflib.SequenceMatcher(None, text1, text2).ratio())
