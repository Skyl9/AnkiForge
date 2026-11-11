"""Migration 053 : Ajout des champs LaTeX aux modèles de notes (NoteTypeModel).

Ajoute sur NoteTypeModel :
- latex_pre : préambule LaTeX (\\documentclass, \\usepackage, macros personnalisées)
- latex_post : postambule LaTeX (\\end{document})
- latex_svg : booléen forçant la génération SVG vectorielle (dvisvgm) au lieu de PNG
"""

from peewee import BooleanField, TextField
from peewee_migrate import Migrator


def migrate(migrator: Migrator, database, fake=False, **kwargs):
    """Ajoute les colonnes LaTeX à la table notetypemodel."""
    migrator.add_fields(
        "notetypemodel",
        latex_pre=TextField(
            default=r"""\documentclass[12pt]{article}
\special{papersize=3in,5in}
\usepackage[utf8]{inputenc}
\usepackage{amssymb,amsmath}
\pagestyle{empty}
\setlength{\parindent}{0in}
\begin{document}
"""
        ),
        latex_post=TextField(default=r"\end{document}"),
        latex_svg=BooleanField(default=True),
    )


def rollback(migrator: Migrator, database, fake=False, **kwargs):
    """Supprime les colonnes LaTeX."""
    migrator.remove_fields(
        "notetypemodel",
        "latex_pre",
        "latex_post",
        "latex_svg",
    )
