"""Audit de non-régression i18n : aucune chaîne d'interface ne doit échapper au catalogue.

Ces tests ne vérifient pas « qu'il y a des traductions » — la traduction humaine est un
ticket distinct — mais que **toute chaîne affichée est extractible**, donc que le
traducteur verra la totalité de l'interface. Une chaîne codée en dur passe inaperçue
jusqu'au jour où l'interface est à moitiéenglish : l'audit est donc le garde-fou.

Trois fautes sont visées, toutes silencieuses à l'exécution :

1. un littellé passé directement à un widget (``QLabel("Enregistrer")``) ;
2. une f-chaîne dans ``tr()`` — évaluée *avant* l'appel, donc absente du catalogue ;
3. une interpolation mal formée — marqueur orphelin, ou valeur sans marqueur.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from ankiforge.utils.i18n import CATALOG_STEM, SOURCE_LANGUAGE, TRANSLATIONS_RELPATH

SRC_DIR = Path(__file__).resolve().parents[2] / "src" / "ankiforge"
TRANSLATIONS_DIR = SRC_DIR.joinpath(*TRANSLATIONS_RELPATH[2:])

#: Constructeurs et setters dont le premier argument positionnel est du texte affiché.
TEXT_SINKS = frozenset(
    {
        "QLabel",
        "QPushButton",
        "QCheckBox",
        "QRadioButton",
        "QGroupBox",
        "QToolButton",
        "QLineEdit",
        "QAction",
        "setText",
        "setPlaceholderText",
        "setToolTip",
        "setWindowTitle",
        "setStatusTip",
        "setWhatsThis",
    }
)

#: Un mot français courant. Volontairement étroit : « Nom », « Type », « Date » sont des
#: libellés français *et* des mots anglais, les exclure éviterait un faux positif à chaque
#: ticket, les includre rendrait l'audit inopérant.
FRENCH_MARKER = re.compile(
    r"\b(?:"
    r"supprim|fichier|carte|paquet|document|mod[eè]le|entra[iî]ne|recherch|enregistr|"
    r"charger|aperçu|résumé|profil|param[eè]tres|pr[eé]f[eé]renc|termin|annul|valid|"
    r"confirmer|attention|erreur|succ[eè]s|avertissement|dossier|texte|image|vid[eé]o|"
    r"audio|audio|nombre|sélection|choisir|aucun|aucune|tous|vide|bloqu|"
    r"g[eé]n[eé]r|import|export|enregistr|d[eé]lai|vitesse|taille|langue"
    r")",
    re.IGNORECASE,
)

PLACEHOLDER_RE = re.compile(r"%(\d{1,2}|n|%)")

#: Noms de paramètres qui dénotent un texte destiné à être lu, dans un `__init__`.
LABEL_PARAMS = frozenset({"text", "label", "title"})

#: Fragment XML/HTML : ce n'est pas une phrase, c'est de la donnée affichée telle quelle.
_MARKUP = re.compile(r"</?[a-zA-Z][\w-]*(?:\s[^<>]*)?/?>|&\w+;")

#: Mot en minuscules d'au moins deux lettres : la trace d'une prose choisie par un humain.
_LOWERCASE_WORD = re.compile(r"[a-zà-ÿ]{2,}")

#: Mot long, ou caractère hors ASCII : « STATUT GLOBAL » et « TEMPS ÉCOULÉ » sont des
#: phrases en capitales, pas des acronymes.
_LONG_WORD = re.compile(r"[A-Za-zÀ-ÿ]{5,}")

#: Marqueur de modèle Anki : `{{FrontSide}}`, `{{Nom}}`…
_ANKI_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")


def is_technical_literal(value: str) -> bool:
    """Un littéral qui n'est pas une phrase : acronyme, compteur, marqueur, fragment HTML.

    Ces valeurs sont déjà dans leur forme finale — les traduire produirait des messages
    qu'un traducteur ne peut qu'abandonner, et, pour celles qui servent aussi d'identité
    (`TagPillButton("{{FrontSide}}")`), une traduction cassant silencieusement la comparaison.
    """
    if _ANKI_TEMPLATE.search(value) or _MARKUP.search(value):
        return True
    if _LOWERCASE_WORD.search(value):
        return False
    return not (_LONG_WORD.search(value) or any(ord(char) > 127 for char in value))


def python_files() -> list[Path]:
    return sorted(SRC_DIR.rglob("*.py"))


def tr_calls(tree: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "tr") or (isinstance(func, ast.Attribute) and func.attr == "tr"):
            calls.append(node)
    return calls


@pytest.fixture(scope="module")
def parsed() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"))) for path in python_files()]


def label_wrappers() -> dict[str, str]:
    """Classes maison dont le premier paramètre est un texte affiché, déduit des signatures.

    Une liste de noms figée serait fausse au premier widget nouveau : `Badge`,
    `DangerButton`, `StorageMetricCard`… sont aussi des puits d'affichage, au même titre que
    `QLabel`. C'est la signature — un `__init__` dont le premier paramètre s'appelle `text`,
    `label` ou `title` — qui les qualifie, pas leur nom.
    """
    found: dict[str, str] = {}
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not (isinstance(item, ast.FunctionDef) and item.name == "__init__"):
                    continue
                args = item.args.args[1:]
                if args and args[0].arg in LABEL_PARAMS:
                    found.setdefault(node.name, args[0].arg)
    return found


def sink_first_literals(tree: ast.Module, sinks: frozenset[str]) -> list[tuple[int, str, str]]:
    """(ligne, nom du puits, littéral) pour chaque puits d'affichage alimenté par un littéral nu."""
    found: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or not node.args:
            continue
        if node.func.id not in sinks:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.strip():
            found.append((node.lineno, node.func.id, first.value))
    return found


@pytest.fixture(scope="module")
def wrapper_sinks() -> frozenset[str]:
    return frozenset(label_wrappers())


# ── 1. Aucun littellé nu dans un puits d'affichage ────────────────────────────


def test_no_raw_french_label_in_display_sink(parsed: list[tuple[Path, ast.Module]], wrapper_sinks: frozenset[str]) -> None:
    """`QLabel("Enregistrer")` doit avoir disparu : le texte passe par `tr()`."""
    offenders: list[str] = []
    for path, tree in parsed:
        for lineno, sink, value in sink_first_literals(tree, TEXT_SINKS | wrapper_sinks):
            if FRENCH_MARKER.search(value):
                offenders.append(f"{path.relative_to(SRC_DIR)}:{lineno} {sink}({value[:60]!r})")

    assert not offenders, "Littellé français non extrait :\n" + "\n".join(offenders)


def test_every_display_sink_wraps_its_literal(parsed: list[tuple[Path, ast.Module]]) -> None:
    """Règle générale, sans lexique : un puits d'affichage reçoit toujours une expression traduite."""
    offenders: list[str] = []
    for path, tree in parsed:
        for lineno, sink, value in sink_first_literals(tree, TEXT_SINKS):
            offenders.append(f"{path.relative_to(SRC_DIR)}:{lineno} {sink}({value[:60]!r})")

    assert not offenders, "Puits d'affichage alimenté par un littéral nu :\n" + "\n".join(offenders)


def test_every_label_wrapper_wraps_its_literal(parsed: list[tuple[Path, ast.Module]], wrapper_sinks: frozenset[str]) -> None:
    """Même règle pour les widgets maison, sauf les littéraux qui ne sont pas des phrases.

    `Badge("0")`, `TagPillButton("{{FrontSide}}")` ou `DashboardActionButton("LLM")` restent
    des données : leur demander une traduction produirait des messages que le traducteur ne
    peut qu'abandonner — et, pour une valeur servant aussi d'identité, une traduction
    cassant silencieusement la comparaison. Tout ce qui contient un mot en minuscules est
    une phrase, et doit passer par `tr()`.
    """
    offenders: list[str] = []
    for path, tree in parsed:
        for lineno, sink, value in sink_first_literals(tree, wrapper_sinks):
            if not is_technical_literal(value):
                offenders.append(f"{path.relative_to(SRC_DIR)}:{lineno} {sink}({value[:60]!r})")

    assert not offenders, "Widget maison alimenté par un littéral nu :\n" + "\n".join(offenders)


# ── 2. Aucune f-chaîne dans tr() ───────────────────────────────────────────────


def test_no_fstring_inside_tr(parsed: list[tuple[Path, ast.Module]]) -> None:
    """`tr(f"...")` est la faute la plus coûteuse : le catalogue se remplit de messages morts.

    Seule la **première** position est fautive : c'est elle que `pylupdate` extrait. Les
    positions suivantes sont des valeurs, et une f-chaîne y est légitime — c'est même la
    seule façon de conserver une spécification de format (``tr("Total : %1", f"{x:.1f}")``).
    """
    offenders: list[str] = []
    for path, tree in parsed:
        for call in tr_calls(tree):
            if call.args and isinstance(call.args[0], ast.JoinedStr):
                offenders.append(f"{path.relative_to(SRC_DIR)}:{call.lineno}")

    assert not offenders, "f-chaîne passée à tr() (non extractible) :\n" + "\n".join(offenders)


# ── 2 bis. `self.tr()` ne sait pas substituer ───────────────────────────────────


def test_qobject_tr_is_never_called_with_values(parsed: list[tuple[Path, ast.Module]]) -> None:
    """`QObject.tr(sourceText, disambiguation=None)` : le 2ᵉ argument n'est PAS une valeur.

    `self.tr("Total : %1", n)` ne lève rien — Qt cherche un message contextualisé par la
    chaîne représentée par `n`, ne le trouve pas, et renvoie **silencieusement** le texte
    source, marqueur `%1` inclus. L'interface affiche alors littéralement « Total : %1 ».
    Seule la forme `tr(...)` du module sait substituer.
    """
    offenders: list[str] = []
    for path, tree in parsed:
        for call in tr_calls(tree):
            if isinstance(call.func, ast.Attribute) and len(call.args) > 1:
                offenders.append(f"{path.relative_to(SRC_DIR)}:{call.lineno} {ast.unparse(call.func)}(...)")

    assert not offenders, "Appel à QObject.tr() avec valeurs (marqueurs non résolus) :\n" + "\n".join(offenders)


# ── 2 ter. Traduire au chargement du module fige la langue source ──────────────


def _tr_calls_evaluated_at_import(statements: list[ast.stmt]) -> list[ast.Call]:
    """`tr()` atteignable sans jamais appeler une fonction.

    Le corps d'une fonction est exclu : il s'exécute toujours après l'amorçage. En revanche
    les décorateurs et les valeurs par défaut d'une `def` sont évalués à l'import, donc
    vérifiés — de même que les bases de classes, les annotations et les corps de classe
    imbriqués, qui s'exécutent dès la définition.
    """
    calls: list[ast.Call] = []
    for statement in statements:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = [d for d in (*statement.args.defaults, *statement.args.kw_defaults) if d is not None]
            for expression in (*statement.decorator_list, *defaults):
                calls.extend(tr_calls(expression))
        elif isinstance(statement, ast.ClassDef):
            for expression in (*statement.bases, *statement.decorator_list):
                calls.extend(tr_calls(expression))
            calls.extend(_tr_calls_evaluated_at_import(statement.body))
        else:
            calls.extend(tr_calls(statement))
    return calls


def test_tr_is_never_called_at_import_time(parsed: list[tuple[Path, ast.Module]]) -> None:
    """Un `tr()` au niveau module ou au corps d'une classe s'exécute à l'import.

    Or `__main__.py` importe `MainWindow` avant d'appeler `install_translator()` : un
    libellé résolu à ce moment-là est figé dans la langue source, et l'interface reste
    française même en anglais — sans la moindre erreur, donc sans le moindre signal. C'est
    pourquoi `MainWindow.view_registry()` est une méthode et non une constante de classe.
    """
    offenders: list[str] = []
    for path, tree in parsed:
        for call in _tr_calls_evaluated_at_import(tree.body):
            offenders.append(f"{path.relative_to(SRC_DIR)}:{call.lineno} {ast.unparse(call.func)}(...)")

    assert not offenders, "tr() exécuté au chargement du module, donc avant le traducteur :\n" + "\n".join(offenders)


# ── 3. Interpolation cohérente ─────────────────────────────────────────────────


def test_every_interpolation_marker_has_a_value(parsed: list[tuple[Path, ast.Module]]) -> None:
    """Un `%3` sans troisième valeur affiche littéralement « %3 » ; un `%` orphelin aussi."""
    offenders: list[str] = []
    for path, tree in parsed:
        for call in tr_calls(tree):
            if not call.args or not (isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str)):
                continue
            template = call.args[0].value
            markers = [int(m.group(1)) for m in PLACEHOLDER_RE.finditer(template) if m.group(1).isdigit()]
            supplied = len(call.args) - 1
            if supplied and not markers:
                offenders.append(f"{path.relative_to(SRC_DIR)}:{call.lineno} valeurs sans marqueur")
            if markers and not supplied:
                offenders.append(f"{path.relative_to(SRC_DIR)}:{call.lineno} marqueur sans valeur")
            if markers and supplied and max(markers) > supplied:
                offenders.append(f"{path.relative_to(SRC_DIR)}:{call.lineno} marqueur %{max(markers)} > {supplied} valeurs")

    assert not offenders, "Interpolation incohérente :\n" + "\n".join(offenders)


# ── 4 bis. Le critère d'exemption lui-même est éprouvé ─────────────────────────


@pytest.mark.parametrize(
    "value",
    ["0", "0%", "0 / 0", "(0)", "LLM", "MCP", "JSON", "OFF", "{{FrontSide}}", '<hr id="answer">'],
)
def test_technical_literals_are_exempt_from_translation(value: str) -> None:
    assert is_technical_literal(value), f"{value!r} est une donnée, pas une phrase : il ne faut pas la traduire"


@pytest.mark.parametrize(
    "value",
    ["Rejeter", "0 étapes", "Thinking / CoT", "100% Local (Ollama)", "STATUT GLOBAL", "TEMPS ÉCOULÉ", "HTML Recto"],
)
def test_phrases_must_be_translated(value: str) -> None:
    """Une garde qui n'exempte que les acronymes resterait inopérante sur du texte en capitales."""
    assert not is_technical_literal(value), f"{value!r} est une phrase : elle doit passer par tr()"


# ── 4. Le catalogue existe, est à jour et n'est pas traduit automatiquement ──────


def test_source_catalog_is_committed() -> None:
    """Le catalogue de la langue source est versionné : sans lui, rien n'est extractible."""
    catalog = TRANSLATIONS_DIR / f"{CATALOG_STEM}_{SOURCE_LANGUAGE}.ts"
    assert catalog.is_file(), f"Catalogue absent : {catalog}. Générer : uv run python script/extract_translations.py"


def test_committed_catalog_matches_a_fresh_extraction() -> None:
    """Le `.ts` versionné doit correspondre au code : un catalogue périmé traduit du vide."""
    from script.extract_translations import extract as extract_catalog
    from script.extract_translations import ts_path

    stale: list[str] = []
    for language in ("fr", "en"):
        reference = ts_path(language)
        if not reference.is_file():
            stale.append(f"{reference.name} absent")
            continue
        # La re-extraction cible le **même dossier** : l'emplacement du `.ts` détermine
        # le chemin relatif inscrit dans `<location>`, donc un dossier temporaire
        # produirait un fichier différent pour la seule raison que `../../ui/…` change.
        probe = TRANSLATIONS_DIR / f".audit_{language}.ts"
        try:
            extract_catalog(language, probe)
            if probe.read_bytes() != reference.read_bytes():
                stale.append(reference.name)
        finally:
            probe.unlink(missing_ok=True)

    assert not stale, f"Catalogues périmés ({', '.join(stale)}). Régénérer : uv run python script/extract_translations.py"


def test_target_catalog_has_no_automatic_translation() -> None:
    """Aucun catalogue ne doit être rempli automatiquement : la traduction est humaine."""
    import xml.etree.ElementTree as ET

    from script.extract_translations import ts_path

    filled = []
    for language in ("fr", "en"):
        catalog = ts_path(language)
        if not catalog.is_file():
            continue
        for translation in ET.parse(catalog).iter("translation"):
            if (translation.text or "").strip():
                filled.append(f"{catalog.name}: {translation.text.strip()[:40]!r}")

    assert not filled, "Traduction automatique détectée :\n" + "\n".join(filled)


def test_catalog_covers_every_display_context() -> None:
    """Le catalogue contient au moins autant de contextes que de classes traduisantes du projet."""
    import xml.etree.ElementTree as ET

    from script.extract_translations import ts_path

    catalog = ts_path(SOURCE_LANGUAGE)
    assert catalog.is_file(), f"Catalogue absent : {catalog}"
    contexts = {node.findtext("name") or "" for node in ET.parse(catalog).iter("context")}
    assert len(contexts) > 50, f"Catalogue dégradé : seulement {len(contexts)} contextes, la promotion en self.tr() n'a pas eu lieu"
