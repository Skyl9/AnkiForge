from typing import List, Tuple
from PySide6.QtWidgets import QLabel


def apply_pill_style(badge: QLabel, color_hex: str) -> None:
    """Applique un style de capsule/pill parfaitement arrondie avec fond translucide et bordure assortie."""
    hex_c = color_hex.lstrip("#")
    try:
        r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    except Exception:
        r, g, b = 99, 102, 241
    badge.setStyleSheet(f"""
        QLabel {{
            background-color: rgba({r}, {g}, {b}, 0.15) !important;
            color: {color_hex};
            border: 1px solid rgba({r}, {g}, {b}, 0.40);
            border-radius: 9999px;
            padding: 2px 10px;
            font-size: 10.5px;
            font-weight: bold;
            letter-spacing: 0.5px;
        }}
    """)


PRESET_SAMPLES: List[Tuple[str, str, str]] = [
    (
        "Cas Médical",
        (
            "L'insuffisance cardiaque droite est caractérisée par l'incapacité du ventricule droit "
            "à assurer un débit sanguin pulmonaire suffisant. Les signes cliniques prédominants "
            "associent turgescence jugulaire, reflux hépato-jugulaire, hépatomégalie douloureuse "
            "et œdèmes des membres inférieurs."
        ),
        "field",
    ),
    (
        "Maths (Algèbre)",
        (
            "Soit E un espace vectoriel de dimension finie n et u un endomorphisme de E. "
            "u est diagonalisable si et seulement si son polynôme caractéristique est scindé sur K "
            "et si pour toute valeur propre λ, la dimension du sous-espace propre associé "
            "Ker(u - λ·id) est égale à la multiplicité algébrique de λ."
        ),
        "cloze",
    ),
    (
        "Droit Civil",
        (
            "Selon l'article 1101 du Code civil, le contrat est une convention par laquelle une ou "
            "plusieurs personnes s'obligent envers d'autres à donner, à faire ou à ne pas faire quelque "
            "chose. Sa validité requiert le consentement libre et éclairé, la capacité juridique et un "
            "contenu licite et certain."
        ),
        "warning",
    ),
    (
        "Anglais (Idiomes)",
        ("A blessing in disguise is an apparent misfortune that eventually results in something good happening. To bite the bullet means to face a difficult situation with courage and fortitude."),
        "info",
    ),
]
