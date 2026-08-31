"""AnkiForge - Advanced AI-driven Anki Card Forge & Studio."""

import sys
from pathlib import Path

# Support pour les bundles macOS .app (Contents/Resources sur sys.path pour les métadonnées dist-info)
if sys.platform == "darwin":
    _exe_res = Path(sys.executable).parent.parent / "Resources"
    if _exe_res.exists() and str(_exe_res) not in sys.path:
        sys.path.insert(0, str(_exe_res))
    try:
        _mod_res = Path(__file__).resolve().parent.parent.parent / "Resources"
        if _mod_res.exists() and str(_mod_res) not in sys.path:
            sys.path.insert(0, str(_mod_res))
    except Exception:
        pass

__version__ = "0.2.0"
