#!/usr/bin/env python3
"""Calculateur de scores CRAP (Change Risk Anti-Patterns) pour AnkiForge.

Croise la Complexité Cyclomatique de McCabe (CC) extraite via l'AST Python
avec la couverture de tests (LCOV / pytest-cov) selon la formule canonique :
    CRAP = CC² × (1 − coverage)³ + CC

Utilisation :
    uv run python script/crap.py                         # Analyse tout src/ankidraft/
    uv run python script/crap.py --changed               # Analyse uniquement le diff Git
    uv run python script/crap.py --threshold 25          # Exit code 2 si le seuil est dépassé
    uv run python script/crap.py --top 15                # Affiche le top 15 des fonctions à risque
    uv run python script/crap.py --no-coverage           # Complexité cyclomatique seule
    uv run python script/crap.py --lcov coverage/lcov.info # Spécifie le rapport LCOV
    uv run python script/crap.py src/ankidraft/utils/    # Analyse un fichier ou dossier spécifique
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TextIO

# Répertoires à exclure systématiquement de l'analyse
SKIP_DIRS = {
    ".git",
    ".idea",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "crapper-master",
}

# Répertoires contenant les tests (exclus de la mesure métier sauf demande explicite)
TEST_DIRS = {"tests", "test"}


@dataclass(frozen=True)
class FunctionMetric:
    """Représentation immuable d'une unité de code analysée."""

    name: str
    namespace: str
    complexity: int
    start_line: int
    end_line: int
    path: str
    coverage: float | None = None
    crap: float | None = None

    @property
    def status_label(self) -> str:
        """Indicateur textuel du niveau de risque."""
        if self.crap is None:
            return "N/A"
        if self.crap <= 5.0:
            return "FAIBLE"
        if self.crap <= 25.0:
            return "ACCEPTABLE"
        if self.crap <= 30.0:
            return "ATTENTION"
        return "CRITIQUE"


class CoverageReport:
    """Index de couverture ligne par ligne et branche par branche extrait d'un fichier LCOV."""

    def __init__(self) -> None:
        """Initialise un rapport de couverture vide."""
        # path normalisé -> {line_number: (covered, total)}
        self.lines: dict[str, dict[int, tuple[int, int]]] = {}
        # path normalisé -> {line_number: (covered_branches, total_branches)}
        self.branches: dict[str, dict[int, tuple[int, int]]] = {}

    def add_line(self, path: str, line_num: int, hits: int) -> None:
        """Enregistre le passage sur une ligne de code."""
        norm = normalize_path(path)
        file_lines = self.lines.setdefault(norm, {})
        file_lines[line_num] = (1 if hits > 0 else 0, 1)

    def add_branch(self, path: str, line_num: int, taken: str) -> None:
        """Enregistre le passage sur une branche d'exécution."""
        norm = normalize_path(path)
        file_branches = self.branches.setdefault(norm, {})
        covered, total = file_branches.get(line_num, (0, 0))
        hit = 1 if taken.isdigit() and int(taken) > 0 else 0
        file_branches[line_num] = (covered + hit, total + 1)

    def coverage_for_function(self, file_path: str, start_line: int, end_line: int) -> float | None:
        """Calcule le pourcentage de couverture d'une plage de lignes."""
        norm = normalize_path(file_path)
        matched_key = self._match_file_key(norm)
        if matched_key is None:
            return None

        # Priorité 1 : couverture des branches si des enregistrements BRDA existent
        branch_map = self.branches.get(matched_key, {})
        br_cov, br_tot = 0, 0
        for line in range(start_line, end_line + 1):
            if line in branch_map:
                cov, tot = branch_map[line]
                br_cov += cov
                br_tot += tot
        if br_tot > 0:
            return (br_cov / br_tot) * 100.0

        # Priorité 2 : couverture des lignes (DA)
        line_map = self.lines.get(matched_key, {})
        ln_cov, ln_tot = 0, 0
        for line in range(start_line, end_line + 1):
            if line in line_map:
                cov, tot = line_map[line]
                ln_cov += cov
                ln_tot += tot
        if ln_tot > 0:
            return (ln_cov / ln_tot) * 100.0

        # Si le fichier est présent dans le rapport mais la fonction n'a aucune ligne exécutable mesurée
        return 100.0

    def _match_file_key(self, norm_path: str) -> str | None:
        """Associe un chemin de fichier avec les clés normalisées du rapport."""
        if norm_path in self.lines:
            return norm_path
        # Recherche par suffixe
        for key in self.lines:
            if key.endswith(norm_path) or norm_path.endswith(key):
                return key
        return None


def normalize_path(path: str) -> str:
    """Normalise un chemin de fichier au format POSIX sans préfixe relatif."""
    clean = path.replace("\\", "/")
    if clean.startswith("file:"):
        clean = clean[5:]
    while clean.startswith("./"):
        clean = clean[2:]
    while "//" in clean:
        clean = clean.replace("//", "/")
    return clean


def calculate_crap(complexity: int, coverage_pct: float | None) -> float | None:
    """Calcule le score CRAP selon la formule Savoia & Evans : CC² × (1 − cov)³ + CC.

    Args:
        complexity: Complexité cyclomatique de McCabe (entier >= 1).
        coverage_pct: Pourcentage de couverture [0.0, 100.0] ou None.

    Returns:
        Le score CRAP arrondi à 2 décimales, ou None si pas de données de couverture.
    """
    if coverage_pct is None:
        return None
    cc = float(complexity)
    uncovered = max(0.0, 1.0 - (coverage_pct / 100.0))
    score = (cc * cc * (uncovered**3)) + cc
    return round(score, 2)


def is_test_file(path: Path) -> bool:
    """Détermine si un fichier Python est un test unitaire ou d'intégration."""
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return True
    return any(part in TEST_DIRS for part in path.parts)


def parse_lcov_file(lcov_path: Path) -> CoverageReport:
    """Parse un fichier LCOV pour en extraire la couverture des lignes et branches."""
    report = CoverageReport()
    if not lcov_path.is_file():
        return report

    current_file: str | None = None
    da_regex = re.compile(r"^DA:(\d+),(\d+)")
    brda_regex = re.compile(r"^BRDA:(\d+),[^,]*,[^,]*,(-|\d+)")

    with lcov_path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            line = line.strip()
            if line.startswith("SF:"):
                current_file = line[3:].strip()
            elif line == "end_of_record":
                current_file = None
            elif current_file is not None:
                da_match = da_regex.match(line)
                if da_match:
                    report.add_line(current_file, int(da_match.group(1)), int(da_match.group(2)))
                    continue
                brda_match = brda_regex.match(line)
                if brda_match:
                    report.add_branch(current_file, int(brda_match.group(1)), brda_match.group(2))
    return report


def find_lcov_report(root: Path) -> Path | None:
    """Recherche automatiquement un fichier de couverture LCOV dans les emplacements usuels."""
    candidates = [
        root / "coverage" / "lcov.info",
        root / "target" / "coverage" / "python" / "lcov.info",
        root / "coverage.info",
        root / "lcov.info",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class ComplexityVisitor:
    """Visiteur AST calculant la complexité cyclomatique de McCabe d'un sous-arbre."""

    def __init__(self) -> None:
        """Initialise le compteur de complexité."""
        self.complexity = 1

    def count(self, node: ast.AST) -> int:
        """Parcourt récursivement le nœud sans traverser les définitions de classes."""
        self.complexity = 1
        self._visit(node)
        return self.complexity

    def _visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            # Une classe imbriquée a son propre scope et ne gonfle pas la fonction parente
            if isinstance(child, ast.ClassDef):
                continue

            # Points de décision standard de McCabe
            if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp, ast.match_case)):
                self.complexity += 1
            elif isinstance(child, ast.comprehension):
                self.complexity += len(child.ifs)
            elif isinstance(child, ast.BoolOp):
                self.complexity += max(0, len(child.values) - 1)

            # Traversée récursive des expressions et instructions (y compris fonctions internes imbriquées)
            self._visit(child)


def _compute_module_namespace(file_path: Path, root: Path) -> str:
    """Calcule le nom de module Python pointé par rapport à la racine."""
    try:
        relative = file_path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = file_path

    parts = list(relative.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]

    name = parts[-1]
    if name.endswith(".py"):
        parts[-1] = name[:-3]
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def extract_functions(source_code: str, file_path: Path, root: Path) -> list[FunctionMetric]:
    """Extrait toutes les fonctions et méthodes de classes d'un code source Python."""
    try:
        tree = ast.parse(source_code, filename=str(file_path))
    except SyntaxError:
        return []

    module_ns = _compute_module_namespace(file_path, root)
    visitor = ComplexityVisitor()
    metrics: list[FunctionMetric] = []

    def walk_body(nodes: list[ast.stmt], class_stack: list[str]) -> None:
        for stmt in nodes:
            if isinstance(stmt, ast.ClassDef):
                walk_body(stmt.body, [*class_stack, stmt.name])
            elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                cc = visitor.count(stmt)
                start_line = stmt.lineno
                end_line = getattr(stmt, "end_lineno", stmt.lineno)

                class_path = ".".join(class_stack)
                ns = f"{module_ns}.{class_path}" if (module_ns and class_path) else (class_path or module_ns)

                metrics.append(
                    FunctionMetric(
                        name=stmt.name,
                        namespace=ns,
                        complexity=cc,
                        start_line=start_line,
                        end_line=end_line,
                        path=normalize_path(str(file_path.relative_to(root) if file_path.is_relative_to(root) else file_path)),
                    )
                )

    walk_body(tree.body, [])
    return metrics


def get_changed_python_files(root: Path) -> list[Path]:
    """Identifie les fichiers Python modifiés ou ajoutés d'après Git."""
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "-z", "--untracked-files=all", "--", "."],
        capture_output=True,
        text=False,
        check=False,
    )
    if result.returncode != 0:
        return []

    changed: list[Path] = []
    entries = result.stdout.split(b"\0")
    for raw in entries:
        if len(raw) < 4:
            continue
        rel_str = raw[3:].decode("utf-8", errors="replace")
        path = (root / rel_str).resolve()
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix == ".py" and not is_test_file(path):
            changed.append(path)
    return sorted(changed)


def discover_python_files(paths: list[Path], root: Path, changed_only: bool = False) -> list[Path]:
    """Découvre récursivement tous les fichiers Python pertinents pour l'analyse."""
    if changed_only:
        return get_changed_python_files(root)

    if not paths:
        src_dir = root / "src"
        search_roots = [src_dir] if src_dir.is_dir() else [root]
    else:
        search_roots = paths

    found: set[Path] = set()
    for target in search_roots:
        if target.is_file() and target.suffix == ".py":
            if not is_test_file(target):
                found.add(target.resolve())
            continue

        if not target.is_dir():
            continue

        for dirpath, dirnames, filenames in os.walk(target):
            # Pruning des dossiers ignorés
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d not in TEST_DIRS]
            for fname in filenames:
                if fname.endswith(".py"):
                    fpath = Path(dirpath) / fname
                    if not is_test_file(fpath):
                        found.add(fpath.resolve())

    return sorted(found)


def analyze_codebase(
    files: list[Path],
    root: Path,
    coverage: CoverageReport | None = None,
) -> list[FunctionMetric]:
    """Analyse l'ensemble des fichiers Python et calcule complexité et scores CRAP."""
    results: list[FunctionMetric] = []
    for file_path in files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        funcs = extract_functions(content, file_path, root)
        for func in funcs:
            cov_pct = coverage.coverage_for_function(func.path, func.start_line, func.end_line) if coverage else None
            score = calculate_crap(func.complexity, cov_pct)
            results.append(
                FunctionMetric(
                    name=func.name,
                    namespace=func.namespace,
                    complexity=func.complexity,
                    start_line=func.start_line,
                    end_line=func.end_line,
                    path=func.path,
                    coverage=round(cov_pct, 1) if cov_pct is not None else None,
                    crap=score,
                )
            )

    # Tri : pires scores CRAP d'abord, puis plus haute complexité
    def sort_key(m: FunctionMetric) -> tuple[int, float, int, str, str]:
        crap_val = m.crap if m.crap is not None else -1.0
        return (0 if m.crap is not None else 1, -crap_val, -m.complexity, m.namespace, m.name)

    return sorted(results, key=sort_key)


def render_report_table(metrics: list[FunctionMetric], top_n: int | None = None, out: TextIO = sys.stdout) -> None:
    """Affiche un tableau ASCII clair et formaté du rapport CRAP."""
    if not metrics:
        out.write("Aucune fonction Python à analyser.\n")
        return

    display_list = metrics[:top_n] if top_n else metrics

    fn_w = max(25, min(45, max(len(m.name) for m in display_list)))
    ns_w = max(30, min(55, max(len(m.namespace) for m in display_list)))

    header = f"{'Fonction':<{fn_w}} {'Namespace':<{ns_w}} {'CC':>4} {'Couv%':>7} {'CRAP':>8} {'Risque':<10}"
    separator = "-" * len(header)

    out.write("\nRapport de Santé CRAP (Change Risk Anti-Patterns)\n")
    out.write("==================================================\n")
    out.write(f"Total fonctions : {len(metrics)} | Affichées : {len(display_list)}\n\n")
    out.write(header + "\n")
    out.write(separator + "\n")

    for m in display_list:
        cov_str = f"{m.coverage:5.1f}%" if m.coverage is not None else "  N/A "
        crap_str = f"{m.crap:8.1f}" if m.crap is not None else "     N/A"
        out.write(f"{m.name:<{fn_w}} {m.namespace:<{ns_w}} {m.complexity:4d} {cov_str} {crap_str} {m.status_label:<10}\n")
    out.write("\n")


def build_arg_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur de ligne de commande."""
    parser = argparse.ArgumentParser(
        description="Calculateur de score CRAP (Change Risk Anti-Patterns) pour AnkiForge.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Fichiers ou répertoires à analyser (défaut : tout src/ankidraft/).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Racine du dépôt Git (défaut : répertoire courant).",
    )
    parser.add_argument(
        "--changed",
        action="store_true",
        help="Analyse uniquement les fichiers Python modifiés/ajoutés selon Git.",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Seuil CRAP maximal toléré. Retourne exit code 2 si dépassé.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Limite l'affichage aux N fonctions ayant le score le plus défavorable.",
    )
    parser.add_argument(
        "--no-coverage",
        action="store_true",
        help="Calcule la complexité cyclomatique uniquement sans couverture.",
    )
    parser.add_argument(
        "--lcov",
        type=Path,
        default=None,
        help="Chemin explicite vers le fichier de couverture LCOV.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Exporte le rapport au format JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée principal du script CLI."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    root = args.root.resolve()
    files = discover_python_files(args.paths, root, changed_only=args.changed)

    if not files:
        if args.changed:
            sys.stdout.write("Aucun fichier source Python modifié détecté par Git.\n")
        else:
            sys.stdout.write("Aucun fichier Python trouvé pour l'analyse.\n")
        return 0

    coverage: CoverageReport | None = None
    if not args.no_coverage:
        lcov_file = args.lcov.resolve() if args.lcov else find_lcov_report(root)
        if lcov_file and lcov_file.is_file():
            coverage = parse_lcov_file(lcov_file)
        else:
            sys.stderr.write(
                "Avis : Aucun rapport LCOV trouvé (ex: coverage/lcov.info). "
                "La couverture est évaluée à 0.0% pour les fonctions non couvertes.\n"
                "Pour générer un rapport LCOV : uv run pytest --cov=src/ankidraft --cov-report=lcov:coverage/lcov.info\n\n"
            )
            coverage = CoverageReport()

    metrics = analyze_codebase(files, root, coverage)

    display_metrics = metrics[: args.top] if args.top else metrics
    if args.json:
        payload = [asdict(m) for m in display_metrics]
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    else:
        render_report_table(metrics, top_n=args.top)

    if args.threshold is not None:
        scored = [m.crap for m in metrics if m.crap is not None]
        if scored:
            worst = max(scored)
            if worst > args.threshold:
                sys.stderr.write(f"ERREUR QUALITÉ : Le seuil CRAP maximal est dépassé ({worst:.1f} > {args.threshold:.1f}).\n")
                return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
