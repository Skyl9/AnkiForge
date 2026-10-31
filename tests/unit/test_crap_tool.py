"""Tests unitaires du calculateur de scores CRAP (script/crap.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from script.crap import (
    CoverageReport,
    FunctionMetric,
    analyze_codebase,
    calculate_crap,
    extract_functions,
    main,
    parse_lcov_file,
)


@pytest.mark.unit
def test_calculate_crap_formula() -> None:
    """Valide les calculs de la formule Savoia & Evans selon différentes configurations."""
    # Couverture 100% : le terme de pénalité est nul, CRAP == CC
    assert calculate_crap(complexity=1, coverage_pct=100.0) == 1.0
    assert calculate_crap(complexity=5, coverage_pct=100.0) == 5.0
    assert calculate_crap(complexity=15, coverage_pct=100.0) == 15.0

    # Couverture 0% : pénalité maximale CC² + CC
    assert calculate_crap(complexity=1, coverage_pct=0.0) == 2.0  # 1² * 1 + 1 = 2
    assert calculate_crap(complexity=5, coverage_pct=0.0) == 30.0  # 5² * 1 + 5 = 30
    assert calculate_crap(complexity=10, coverage_pct=0.0) == 110.0  # 10² * 1 + 10 = 110

    # Couverture intermédiaire (50%) : CC² * (0.5)³ + CC
    # Pour CC=10 : 100 * 0.125 + 10 = 12.5 + 10 = 22.5
    assert calculate_crap(complexity=10, coverage_pct=50.0) == 22.5

    # Absence de couverture
    assert calculate_crap(complexity=8, coverage_pct=None) is None


@pytest.mark.unit
def test_function_metric_status_label() -> None:
    """Valide l'attribution des statuts de risque."""
    m_none = FunctionMetric("f", "ns", 1, 1, 2, "p", coverage=None, crap=None)
    assert m_none.status_label == "N/A"

    m_low = FunctionMetric("f", "ns", 3, 1, 5, "p", coverage=100.0, crap=3.0)
    assert m_low.status_label == "FAIBLE"

    m_acc = FunctionMetric("f", "ns", 8, 1, 10, "p", coverage=80.0, crap=15.2)
    assert m_acc.status_label == "ACCEPTABLE"

    m_warn = FunctionMetric("f", "ns", 5, 1, 10, "p", coverage=10.0, crap=28.5)
    assert m_warn.status_label == "ATTENTION"

    m_crit = FunctionMetric("f", "ns", 8, 1, 15, "p", coverage=5.0, crap=58.4)
    assert m_crit.status_label == "CRITIQUE"


@pytest.mark.unit
def test_complexity_visitor_rules() -> None:
    """Valide le calcul de la complexité cyclomatique de McCabe pour différentes constructions."""
    # Code linéaire : CC = 1
    code_linear = """
def linear(x, y):
    z = x + y
    return z * 2
"""
    funcs = extract_functions(code_linear, Path("dummy.py"), Path("."))
    assert len(funcs) == 1
    assert funcs[0].complexity == 1

    # Décisions if/elif/else : 1 de base + 1 (if) + 1 (elif) = 3
    code_if = """
def branches(x):
    if x > 10:
        return 1
    elif x > 5:
        return 2
    else:
        return 0
"""
    funcs = extract_functions(code_if, Path("dummy.py"), Path("."))
    assert funcs[0].complexity == 3

    # Boucles for et while : 1 de base + 1 (for) + 1 (while) = 3
    code_loops = """
def loops(items):
    for item in items:
        while item > 0:
            item -= 1
"""
    funcs = extract_functions(code_loops, Path("dummy.py"), Path("."))
    assert funcs[0].complexity == 3

    # Exception try/except : 1 de base + 1 (except) = 2
    code_try = """
def errors():
    try:
        do_work()
    except ValueError:
        pass
"""
    funcs = extract_functions(code_try, Path("dummy.py"), Path("."))
    assert funcs[0].complexity == 2

    # Opérateurs booléens composés : 1 de base + 2 (and avec 3 termes) + 1 (or avec 2 termes) = 4
    code_bool = """
def bools(a, b, c, d):
    return a and b and c or d
"""
    funcs = extract_functions(code_bool, Path("dummy.py"), Path("."))
    assert funcs[0].complexity == 4

    # Compréhension avec if : 1 de base + 1 (if dans comp) = 2
    code_comp = """
def comp(items):
    return [x for x in items if x % 2 == 0]
"""
    funcs = extract_functions(code_comp, Path("dummy.py"), Path("."))
    assert funcs[0].complexity == 2

    # Pattern matching : 1 de base + 2 (match cases) = 3
    code_match = """
def matching(value):
    match value:
        case 1:
            return "un"
        case 2:
            return "deux"
"""
    funcs = extract_functions(code_match, Path("dummy.py"), Path("."))
    assert funcs[0].complexity == 3


@pytest.mark.unit
def test_nested_functions_and_classes() -> None:
    """Valide la gestion des fonctions imbriquées et méthodes de classes."""
    code = """
class Worker:
    def execute(self, items):
        def helper(x):
            if x > 0:
                return x * 2
            return 0
        return [helper(i) for i in items]

    class SubTask:
        def run(self):
            return 42
"""
    funcs = extract_functions(code, Path("src/ankiforge/services/worker.py"), Path("."))
    assert len(funcs) == 2

    # execute englobe la complexité de helper (1 de base + 1 if de helper = 2)
    exec_func = next(f for f in funcs if f.name == "execute")
    assert exec_func.namespace == "ankiforge.services.worker.Worker"
    assert exec_func.complexity == 2

    # run est dans la sous-classe imbriquée
    run_func = next(f for f in funcs if f.name == "run")
    assert run_func.namespace == "ankiforge.services.worker.Worker.SubTask"
    assert run_func.complexity == 1


@pytest.mark.unit
def test_coverage_report_line_and_branch_matching() -> None:
    """Valide l'extraction de la couverture depuis un rapport LCOV."""
    report = CoverageReport()
    file_path = "src/ankiforge/module.py"

    # Lignes 10 à 14
    report.add_line(file_path, 10, hits=1)
    report.add_line(file_path, 11, hits=1)
    report.add_line(file_path, 12, hits=0)
    report.add_line(file_path, 13, hits=0)

    # 2 couvertes sur 4 = 50%
    cov = report.coverage_for_function(file_path, start_line=10, end_line=13)
    assert cov == 50.0

    # Si des branches BRDA sont présentes, elles priment sur les lignes
    report.add_branch(file_path, 10, taken="1")
    report.add_branch(file_path, 10, taken="0")
    # 1 branche couverte sur 2 = 50%
    cov_br = report.coverage_for_function(file_path, start_line=10, end_line=13)
    assert cov_br == 50.0

    # Fichier absent du rapport -> None
    assert report.coverage_for_function("src/ankiforge/unknown.py", 1, 5) is None


@pytest.mark.unit
def test_parse_lcov_file(tmp_path: Path) -> None:
    """Valide le parsing d'un fichier LCOV réel."""
    lcov_content = """
SF:src/ankiforge/sample.py
DA:1,1
DA:2,1
DA:3,0
BRDA:2,0,0,1
BRDA:2,0,1,0
end_of_record
"""
    lcov_file = tmp_path / "lcov.info"
    lcov_file.write_text(lcov_content.strip(), encoding="utf-8")

    report = parse_lcov_file(lcov_file)
    assert "src/ankiforge/sample.py" in report.lines
    assert report.lines["src/ankiforge/sample.py"][1] == (1, 1)
    assert report.lines["src/ankiforge/sample.py"][3] == (0, 1)
    assert report.branches["src/ankiforge/sample.py"][2] == (1, 2)


@pytest.mark.unit
def test_analyze_codebase_and_cli_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Valide l'analyse globale et la détection de dépassement de seuil."""
    src_dir = tmp_path / "src" / "demo"
    src_dir.mkdir(parents=True)
    sample_file = src_dir / "target.py"

    # Fonction avec CC=5
    sample_file.write_text(
        """
def complex_fn(a, b, c):
    if a > 0:
        if b > 0:
            if c > 0:
                return 1
            return 2
        return 3
    elif a < -10:
        return 4
    return 0
""",
        encoding="utf-8",
    )

    # LCOV avec 0% de couverture
    lcov_content = f"SF:{sample_file}\nDA:2,0\nDA:3,0\nend_of_record\n"
    lcov_file = tmp_path / "lcov.info"
    lcov_file.write_text(lcov_content, encoding="utf-8")

    metrics = analyze_codebase([sample_file], tmp_path, parse_lcov_file(lcov_file))
    assert len(metrics) == 1
    fn = metrics[0]
    assert fn.name == "complex_fn"
    assert fn.complexity == 5
    assert fn.coverage == 0.0
    # CRAP = 5² * 1³ + 5 = 25 + 5 = 30.0
    assert fn.crap == 30.0
    assert fn.status_label == "ATTENTION"

    # Test CLI avec seuil 20 -> Doit retourner le code 2 car 30.0 > 20.0
    code_fail = main([str(sample_file), "--root", str(tmp_path), "--lcov", str(lcov_file), "--threshold", "20"])
    assert code_fail == 2

    # Test CLI avec seuil 40 -> Doit retourner 0 car 30.0 <= 40.0
    code_ok = main([str(sample_file), "--root", str(tmp_path), "--lcov", str(lcov_file), "--threshold", "40"])
    assert code_ok == 0
