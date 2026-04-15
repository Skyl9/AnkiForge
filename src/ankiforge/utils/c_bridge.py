import ctypes
import logging
import platform

from ankiforge.utils.paths import get_project_root

logger = logging.getLogger(__name__)

base_dir = get_project_root()
ext = "dll" if platform.system() == "Windows" else "so"
lib_path = base_dir / "src" / "ankiforge" / "c_ext" / f"levenshtein_distance.{ext}"

try:
    _matcher_lib = ctypes.CDLL(str(lib_path))

    _matcher_lib.calculate_similarity.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _matcher_lib.calculate_similarity.restype = ctypes.c_double

    C_MATCHER_LOADED = True
except Exception as e:
    logger.warning(f"⚠️ Librairie C non trouvée, fallback sur Python. Erreur: {e}")
    C_MATCHER_LOADED = False


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
    if C_MATCHER_LOADED:
        # En C, les chaînes doivent être encodées en bytes
        return _matcher_lib.calculate_similarity(text1.encode("utf-8"), text2.encode("utf-8"))
    else:
        import difflib

        return difflib.SequenceMatcher(None, text1, text2).ratio()
