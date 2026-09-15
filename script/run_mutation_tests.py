#!/usr/bin/env python3
"""Moteur de Mutation Testing AST Natif pour AnkiForge.

Analyse la robustesse des assertions de tests en injectant des mutations
syntaxiques (inversions de comparaisons, altérations de constantes et
booléens) dans les composants critiques et en mesurant le taux de
mutants éliminés (Mutation Score).
"""

import argparse
import ast
import subprocess
import sys
from pathlib import Path
from typing import Any

TARGET_CONFIGS: dict[str, dict[str, Any]] = {
    "c_bridge": {
        "source": "src/ankiforge/utils/c_bridge.py",
        "test": "tests/utils/test_c_bridge.py",
        "description": "Calcul de distance Levenshtein (Bridge C & Fallback pur Python)",
    },
    "chunking": {
        "source": "src/ankiforge/services/parsing/chunking_service.py",
        "test": "tests/services/parsing/test_chunking_service.py",
        "description": "Découpage documentaire intelligent & métadonnées",
    },
    "anki_renderer": {
        "source": "src/ankiforge/utils/anki_renderer.py",
        "test": "tests/utils/test_anki_renderer.py",
        "description": "Moteur de rendu de cartes Anki (cloze, KaTeX, Jinja2)",
    },
    "vision_utils": {
        "source": "src/ankiforge/utils/vision_utils.py",
        "test": "tests/utils/test_vision_utils.py",
        "description": "Traitement et encodage d'images pour LLM multimodal",
    },
}


class MutationTransformer(ast.NodeTransformer):
    """Injecte une mutation unique à un index donné dans l'AST."""

    def __init__(self, target_mutation_index: int) -> None:
        super().__init__()
        self.target_index = target_mutation_index
        self.current_index = 0
        self.mutation_applied = False
        self.mutation_description = ""

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        new_ops = []
        for op in node.ops:
            if self.current_index == self.target_index:
                mutated_op = self._mutate_op(op)
                new_ops.append(mutated_op)
                self.mutation_applied = True
                self.mutation_description = f"Ligne {getattr(node, 'lineno', '?')} : Inversion d'opérateur {type(op).__name__} -> {type(mutated_op).__name__}"
            else:
                new_ops.append(op)
            self.current_index += 1
        node.ops = new_ops
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            if self.current_index == self.target_index:
                node.value = not node.value
                self.mutation_applied = True
                self.mutation_description = f"Ligne {getattr(node, 'lineno', '?')} : Inversion booléenne -> {node.value}"
            self.current_index += 1
        return node

    def _mutate_op(self, op: ast.cmpop) -> ast.cmpop:
        if isinstance(op, ast.Eq):
            return ast.NotEq()
        if isinstance(op, ast.NotEq):
            return ast.Eq()
        if isinstance(op, ast.Lt):
            return ast.GtE()
        if isinstance(op, ast.LtE):
            return ast.Gt()
        if isinstance(op, ast.Gt):
            return ast.LtE()
        if isinstance(op, ast.GtE):
            return ast.Lt()
        if isinstance(op, ast.Is):
            return ast.IsNot()
        if isinstance(op, ast.IsNot):
            return ast.Is()
        if isinstance(op, ast.In):
            return ast.NotIn()
        if isinstance(op, ast.NotIn):
            return ast.In()
        return op


def count_mutations_in_file(source_code: str) -> int:
    tree = ast.parse(source_code)

    class Counter(ast.NodeVisitor):
        def __init__(self) -> None:
            self.count = 0

        def visit_Compare(self, node: ast.Compare) -> None:
            self.count += len(node.ops)
            self.generic_visit(node)

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, bool):
                self.count += 1

    counter = Counter()
    counter.visit(tree)
    return counter.count


def apply_mutation(source_code: str, mutation_index: int) -> tuple[str, str]:
    tree = ast.parse(source_code)
    transformer = MutationTransformer(mutation_index)
    mutated_tree = transformer.visit(tree)
    ast.fix_missing_locations(mutated_tree)
    return ast.unparse(mutated_tree), transformer.mutation_description


def run_test_against_mutation(test_file: str) -> bool:
    """Retourne True si le test échoue (c-à-d le mutant est tué)."""
    import os

    env = os.environ.copy()
    root_dir = Path(__file__).resolve().parent.parent
    env["PYTHONPATH"] = str(root_dir / "src")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["ANKIFORGE_MOCK_WEBENGINE"] = "1"

    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-o",
            "addopts=",
            "-q",
            "--tb=no",
            test_file,
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=root_dir,
    )
    # Le mutant est tué si le test échoue (code de retour != 0)
    return res.returncode != 0


def analyze_target(target_name: str, config: dict[str, Any], max_mutants: int = 15) -> tuple[int, int]:
    root_dir = Path(__file__).resolve().parent.parent
    source_file = root_dir / config["source"]
    test_file = root_dir / config["test"]

    if not source_file.exists() or not test_file.exists():
        print(f"⚠️ Fichier manquant pour {target_name}")
        return 0, 0

    original_code = source_file.read_text(encoding="utf-8")
    total_mutants = min(count_mutations_in_file(original_code), max_mutants)

    print(f"\n🧬 Analyse : {target_name} ({config['description']})")
    print(f"📁 Fichier : `{config['source']}` | 🧪 Tests : `{config['test']}`")
    print(f"🔢 Échantillon de mutants évalués : {total_mutants}")

    killed = 0
    survived = 0

    try:
        for idx in range(total_mutants):
            mutated_code, desc = apply_mutation(original_code, idx)
            # Écriture temporaire du mutant
            source_file.write_text(mutated_code, encoding="utf-8")

            is_killed = run_test_against_mutation(str(test_file))
            if is_killed:
                killed += 1
                print(f"  ✅ Mutant #{idx + 1:02d} TUÉ     — {desc}")
            else:
                survived += 1
                print(f"  ❌ Mutant #{idx + 1:02d} SURVÉCU — {desc}")

    finally:
        # Restauration systématique du fichier original
        source_file.write_text(original_code, encoding="utf-8")

    score = (killed / total_mutants * 100) if total_mutants > 0 else 100.0
    print(f"📊 Mutation Score pour {target_name} : **{score:.1f}%** ({killed}/{total_mutants} tués)")
    return killed, total_mutants


def main() -> None:
    parser = argparse.ArgumentParser(description="AnkiForge AST Mutation Testing Runner")
    parser.add_argument(
        "--target",
        choices=list(TARGET_CONFIGS.keys()) + ["all"],
        default="all",
        help="Cible à muter (défaut: all)",
    )
    parser.add_argument(
        "--max-mutants",
        type=int,
        default=10,
        help="Nombre maximum de mutants par module (défaut: 10)",
    )
    args = parser.parse_args()

    print("=" * 65)
    print("🧬 AnkiForge Native AST Mutation Testing")
    print("=" * 65)

    targets = list(TARGET_CONFIGS.keys()) if args.target == "all" else [args.target]

    total_killed = 0
    total_generated = 0

    for t in targets:
        k, g = analyze_target(t, TARGET_CONFIGS[t], max_mutants=args.max_mutants)
        total_killed += k
        total_generated += g

    global_score = (total_killed / total_generated * 100) if total_generated > 0 else 100.0

    print("\n" + "=" * 65)
    print(f"🏆 SCORE GLOBAL DE MUTATION : {global_score:.1f}% ({total_killed}/{total_generated} mutants tués)")
    if global_score >= 80:
        print("🟢 Excellente robustesse des assertions !")
    else:
        print("🟡 Certaines assertions méritent d'être renforcées.")
    print("=" * 65)


if __name__ == "__main__":
    main()
