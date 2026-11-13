import json
import re
from typing import Any


def strip_html_tags(text: str) -> str:
    """Nettoie les balises HTML et décode les entités basiques pour un aperçu fluide dans le tableau."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = clean.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", clean).strip()


def format_tags_display(tags_raw: Any) -> str:
    """Formate les tags pour éviter l'affichage de chaînes Python brutes comme '[]'."""
    if not tags_raw:
        return ""
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            if isinstance(parsed, list):
                tags_raw = parsed
            elif tags_raw.strip() in ("[]", ""):
                return ""
        except Exception:
            if tags_raw.strip() in ("[]", ""):
                return ""
    if isinstance(tags_raw, list):
        clean_list = [str(t).strip() for t in tags_raw if str(t).strip()]
        return "  ".join(f"#{t}" for t in clean_list)
    return str(tags_raw).strip()
