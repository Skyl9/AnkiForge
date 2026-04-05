import ctypes
import os
import platform

from ankiforge.utils.paths import get_project_root

base_dir = get_project_root()
ext = "dll" if platform.system() == "Windows" else "so"
lib_path = base_dir/"src" / "ankiforge" / "c_ext" / f"levenshtein_distance.{ext}"

try:
    _matcher_lib = ctypes.CDLL(lib_path)

    _matcher_lib.calculate_similarity.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    _matcher_lib.calculate_similarity.restype = ctypes.c_double

    C_MATCHER_LOADED = True
except Exception as e:
    print(f"⚠️ Librairie C non trouvée, fallback sur Python. Erreur: {e}")
    C_MATCHER_LOADED = False


def get_similarity(text1: str, text2: str) -> float:
    """Appelle la fonction C ultra-rapide si disponible, sinon fallback sur difflib."""
    if C_MATCHER_LOADED:
        # En C, les chaînes doivent être encodées en bytes
        return _matcher_lib.calculate_similarity(text1.encode('utf-8'), text2.encode('utf-8'))
    else:
        import difflib
        return difflib.SequenceMatcher(None, text1, text2).ratio()