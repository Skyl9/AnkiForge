"""
ThemeProfile definition for AnkiForge Style Engine.
Représente la structure complète et typée d'un profil de thème visuel.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeProfile:
    """Structure de données immuable décrivant l'ensemble des tokens visuels d'un thème."""

    id: str
    name: str
    description: str

    # Backgrounds
    bg_main: str
    bg_sidebar: str
    bg_panel: str
    bg_input: str
    bg_hover: str
    bg_active: str

    # Accents
    accent_primary: str
    accent_hover: str
    accent_glow: str

    # Textes
    text_primary: str
    text_secondary: str
    text_muted: str

    # Bordures
    border_color: str
    border_light: str
    border_focus: str

    # Semantics
    color_blue: str
    color_green: str
    color_yellow: str
    color_red: str
    color_purple: str

    # Radius
    radius_sm: int  # buttons, inputs
    radius_md: int  # cards, panels
    radius_lg: int  # modals, banners

    # Typography & Mode (with defaults)
    is_dark: bool = True
    font_main: str = ".AppleSystemUIFont"
    font_code: str = "Menlo"
    font_size_base: int = 13
    font_size_sm: int = 11
