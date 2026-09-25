"""Configuration de mise en page pour dmgbuild (Packaging macOS DMG AnkiForge)."""

import os

_this_file = globals().get("__file__")
if _this_file:
    _this_dir = os.path.dirname(os.path.abspath(_this_file))
elif os.path.isdir("build_script"):
    _this_dir = os.path.abspath("build_script")
elif os.path.basename(os.getcwd()) == "build_script":
    _this_dir = os.getcwd()
else:
    _this_dir = os.path.abspath(".")

_repo_root = _this_dir if os.path.isfile(os.path.join(_this_dir, "pyproject.toml")) else os.path.dirname(_this_dir)

# Récupération des variables passées en ligne de commande (-D nom=valeur) si présentes
_defines = globals().get("defines") or {}

# Nom de volume affiché dans le Finder et format de compression
volume_name = "AnkiForge"
format = "UDZO"

# Contenu à intégrer dans l'image disque
app_path = _defines.get("app_path", os.path.join(_repo_root, "dist_prod", "AnkiForge.app"))
files = [(app_path, "AnkiForge.app")]
symlinks = {"Applications": "/Applications"}

# Géométrie de la fenêtre DMG (position initiale (x, y) et dimensions (largeur, hauteur))
window_rect = ((200, 140), (640, 420))
default_view = "icon-view"

# Mise en page des icônes
icon_size = 120
text_size = 13
icon_locations = {
    "AnkiForge.app": (160, 205),
    "Applications": (480, 205),
}

# Barres d'interface macOS masquées pour un rendu minimaliste épuré
show_status_bar = False
show_toolbar = False
show_pathbar = False
show_sidebar = False

# Arrière-plan Retina (dmgbuild compile automatiquement dmg_background.png et dmg_background@2x.png via tiffutil)
background = os.path.join(_this_dir, "assets", "dmg_background.png")

# Icône du volume monté
icon = os.path.join(_repo_root, "src", "ressources", "icons", "ankiforge.icns")
