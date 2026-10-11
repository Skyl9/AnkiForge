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
            if hasattr(_matcher_lib, "calculate_levenshtein_distance"):
                _matcher_lib.calculate_levenshtein_distance.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                _matcher_lib.calculate_levenshtein_distance.restype = ctypes.c_int
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


def levenshtein_distance(text1: str, text2: str) -> int:
    """Calcule la distance d'édition de Levenshtein entre deux chaînes de caractères.

    Prend en compte fidèlement les caractères Unicode (points de code).
    Utilise l'extension C si disponible et que les deux chaînes sont en pur ASCII,
    sinon utilise l'algorithme dynamique optimisé en Python pur.

    Args:
        text1: Première chaîne.
        text2: Seconde chaîne.

    Returns:
        int: Nombre minimal d'insertions, suppressions ou substitutions.
    """
    if text1 == text2:
        return 0
    len1 = len(text1)
    len2 = len(text2)
    if len1 == 0:
        return len2
    if len2 == 0:
        return len1

    # Tenter l'extension C rapide si pur ASCII
    if C_MATCHER_LOADED and _matcher_lib is not None and hasattr(_matcher_lib, "calculate_levenshtein_distance"):
        try:
            b1 = text1.encode("ascii")
            b2 = text2.encode("ascii")
            dist = int(_matcher_lib.calculate_levenshtein_distance(b1, b2))
            if dist >= 0:
                return dist
        except (UnicodeEncodeError, Exception):
            pass

    # Algorithme dynamique à 2 lignes en Python pur (Unicode codepoints)
    s1, s2 = text1, text2
    if len1 > len2:
        s1, s2 = s2, s1
        len1, len2 = len2, len1

    current_row = list(range(len1 + 1))
    for i, c2 in enumerate(s2):
        next_row = [i + 1] * (len1 + 1)
        for j, c1 in enumerate(s1):
            cost = 0 if c1 == c2 else 1
            next_row[j + 1] = min(
                next_row[j] + 1,
                current_row[j + 1] + 1,
                current_row[j] + cost,
            )
        current_row = next_row

    return current_row[len1]
