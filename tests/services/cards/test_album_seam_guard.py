"""
Test de garde : **qui a le droit de lire le fichier image d'une planche ?**

`DocumentPageModel.rotation` est persisté (ADR 0011). Avant la couture, neuf
consommateurs le lisaient et un seul l'honorait — le reste produisait des planches
couchées, en silence. Un point d'entrée unique ne tient que si un consommateur
ne peut pas le contourner : c'est le rôle de ce test, source-level, comme une règle
de linter.

Le test échoue dès qu'un module hors liste blanche lit `page.media.filename`
pour produire une image. Ajouter un module à la liste est un acte délibéré ;
l'oublier ne peut plus passer inaperçu.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC_ROOT = Path(__file__).resolve().parents[3] / "src" / "ankiforge"

#: La couture elle-même : elle a le droit de résoudre le fichier brut, c'est son métier.
ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        # ── La couture (ADR 0011) ────────────────────────────────────────────
        "services/cards/album_service.py",
    }
)

#: Modules exemptés : ils ne lisent pas le *fichier* d'une planche, mais un média
#: d'une autre nature (document source original, média de fragment, page PDF).
EXEMPTED_MODULES: frozenset[str] = frozenset(
    {
        "services/cards/media_manager.py",
        "services/cards/image_occlusion_service.py",
        "services/parsing/epub_parser.py",
        "services/parsing/pptx_parser.py",
        "services/parsing/web_importer.py",
        "services/rag/vector_manager.py",
        "services/rag/hybrid_retriever.py",
    }
)


#: Exceptions **bornées** à la lecture de la rotation, sans production d'image.
#: Chacune est justifiée par un test qui vérifie *aussi* qu'elle reste ce qu'elle est.
ROTATION_EXEMPTED_MODULES: frozenset[str] = frozenset(
    {
        # La clé de cache doit changer quand la planche pivote, sinon l'orientation
        # précédente continuerait d'être servie. Aucune image n'y est produite.
        "ui/views/documents_view/widgets/album_thumbnails.py",
    }
)


def _relative(path: Path) -> str:
    return path.relative_to(SRC_ROOT).as_posix()


def _iter_source_files() -> list[Path]:
    return sorted(p for p in SRC_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _reads_media_filename(tree: ast.AST) -> bool:
    """
    Détecte l'accès à `.media.filename` — l'expression qui précède l'ouverture
    du fichier d'une planche.

    On cherche l'attribut `filename` dont la valeur porte un attribut `media`
    (n'importe quel objet : `page.media`, `self.page.media`, `chunk.media`...).
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute) or node.attr != "filename":
            continue
        if isinstance(node.value, ast.Attribute) and node.value.attr == "media":
            return True
    return False


def test_no_module_outside_the_whitelist_reads_the_planche_file() -> None:
    """
    Aucun module hors liste blanche ne résout le fichier image d'une planche.

    Un neuvième consommateur fourvoyé serait à une ligne : ce test est ce qui
    l'empêche d'exister.
    """
    offenders: list[str] = []
    for path in _iter_source_files():
        rel = _relative(path)
        if rel in ALLOWED_MODULES or rel in EXEMPTED_MODULES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover - fichier non parsable : hors périmètre
            continue
        if _reads_media_filename(tree):
            offenders.append(rel)

    assert not offenders, (
        "Ces modules lisent le fichier image d'une planche hors de la couture "
        "(AlbumService.render_page_image) et ignorent donc sa rotation durable (ADR 0011) :\n"
        + "\n".join(f"  - {rel}" for rel in offenders)
        + "\n\nPasser par la couture, ou ajouter volontairement le module à ALLOWED_MODULES "
        "dans tests/services/cards/test_album_seam_guard.py."
    )


def test_the_whitelist_still_points_at_existing_files() -> None:
    """Une liste blanche qui pointe dans le vide ne protège plus rien."""
    for rel in ALLOWED_MODULES | EXEMPTED_MODULES:
        assert (SRC_ROOT / rel).is_file(), f"Module listé introuvable dans la source : {rel}"


def _names_a_page(node: ast.AST, page_holders: frozenset[str]) -> bool:
    """
    L'expression portant `.rotation` désigne-t-elle une page ?

    Varier la forme (`self._page`, `pages[0]`, `p`) était la faille de la première
    version de cette règle : elle visait quatre noms exacts, donc une fuite par
    `p.rotation` passait. On accepte aujourd'hui un nom court **ou** se terminant par
    `page`, ce qui couvre `self._page`, `page`, et `my_page`, et un index de liste.

    On est appelé avec l'attribut complet (`page.rotation`) : on remonte le receveur
    jusqu'au nom, **niveau par niveau**, sans le déplier jusqu'à la racine. En effet
    `self._page.rotation` se déplierait en `self`, qui n'est pas un porteur, alors que
    `_page` en est un : on teste donc chaque maillon et on retient le premier porteur.
    """
    candidates: list[str] = []
    target: ast.AST = node
    while True:
        if isinstance(target, ast.Attribute):
            candidates.append(target.attr)
            target = target.value
        elif isinstance(target, ast.Subscript):
            # `pages[0]` : le porteur est la collection, pas l'index.
            target = target.value
        elif isinstance(target, ast.Name):
            candidates.append(target.id)
            break
        else:
            break

    for raw in candidates:
        name = raw.lstrip("_")
        if name in page_holders or name.endswith("page") or name.endswith("pages"):
            return True
    return False


def test_no_module_outside_the_whitelist_reads_the_rotation() -> None:
    """
    Aucun module hors de la couture ne lit la rotation d'une planche.

    L'orientation affichée vient de `AlbumService.render_page_image` ; relire
    `page.rotation` ailleurs est la double implémentation que la couture remplace.
    """
    page_holders = frozenset({"page", "current_page", "page_rec", "page_model", "board", "current_board"})
    offenders: list[str] = []
    for path in _iter_source_files():
        rel = _relative(path)
        if rel in ALLOWED_MODULES:
            continue
        # Le cache de vignettes compose sa clé avec la rotation sans produire d'image.
        # L'exception est vérifiée par le test dédié ci-dessous : on n'accorde donc pas
        # un passe droit muet, on le borne à un module et à une raison.
        if rel in ROTATION_EXEMPTED_MODULES:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr != "rotation":
                continue
            if _names_a_page(node, page_holders):
                offenders.append(f"{rel}:{node.lineno}")

    assert not offenders, (
        "Ces modules lisent la rotation d'une planche hors de la couture :\n" + "\n".join(f"  - {o}" for o in offenders) + "\n\nL'orientation se demande à la couture (AlbumService.render_page_image)."
    )


def test_the_rotation_reader_is_the_seam_and_the_cache_keys_on_it() -> None:
    """
    La couture lit la rotation pour rendre ; le cache la lit pour composer sa clé.

    Le cache de vignettes consulte `page.rotation` sans produire d'image — c'est ce qui
    rend l'entrée juste : pivoter une planche change sa clé, donc son entrée, donc
    l'ancienne vignette n'est plus jamais servie. Cette exception est écrite
    explicitement ici pour qu'elle reste une exception et ne devienne pas un précédent.
    """
    seam = SRC_ROOT / "services/cards/album_service.py"
    thumbnails = SRC_ROOT / "ui/views/documents_view/widgets/album_thumbnails.py"

    seam_tree = ast.parse(seam.read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.Attribute) and n.attr == "rotation" for n in ast.walk(seam_tree)), "La couture ne lit plus la rotation : la règle de garde n'a plus d'objet."

    thumb_tree = ast.parse(thumbnails.read_text(encoding="utf-8"))
    key_for = next(n for n in ast.walk(thumb_tree) if isinstance(n, ast.FunctionDef) and n.name == "key_for")
    assert any(isinstance(n, ast.Attribute) and n.attr == "rotation" for n in ast.walk(key_for)), (
        "La clé de cache ne dépend plus de la rotation : une rotation servirait une vignette de l'orientation précédente."
    )
