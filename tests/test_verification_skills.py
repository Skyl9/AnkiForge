"""Tests unitaires pour le skill de vérification de l'environnement d'agent."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = REPO_ROOT / ".agents" / "skills" / "verification-environnement"
SKILL_FILE = SKILL_DIR / "SKILL.md"
CLAUDE_SKILL_LINK = REPO_ROOT / ".claude" / "skills" / "verification-environnement"
GEMINI_FILE = REPO_ROOT / "GEMINI.md"
AGENTS_FILE = REPO_ROOT / "AGENTS.md"


def test_verification_skill_file_exists() -> None:
    """Le skill de vérification par environnement doit exister dans .agents/skills/."""
    assert SKILL_FILE.is_file(), f"Fichier SKILL.md introuvable : {SKILL_FILE}"


def test_verification_skill_frontmatter_and_limits() -> None:
    """Le frontmatter doit être valide, comporter les déclencheurs et respecter la limite de lignes."""
    assert SKILL_FILE.is_file()
    content = SKILL_FILE.read_text(encoding="utf-8")
    lines = content.splitlines()

    assert len(lines) <= 150, f"Le fichier SKILL.md ne doit pas dépasser 150 lignes (actuel : {len(lines)})"

    # Extraction YAML frontmatter
    assert content.startswith("---"), "Le fichier doit débuter par un frontmatter YAML"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "Le frontmatter doit être délimité par '---'"

    data = yaml.safe_load(parts[1])
    assert isinstance(data, dict), "Le frontmatter doit être un dictionnaire YAML valide"
    assert data.get("name") == "verification-environnement", "Le nom du skill doit être 'verification-environnement'"

    desc = data.get("description", "")
    assert desc, "La description est obligatoire"
    assert any(kw in desc.lower() for kw in ["use when", "activer", "lorsque", "demande"]), "La description doit contenir un déclencheur explicite ('Use when...')"


def test_verification_skill_contains_non_negotiable_rules() -> None:
    """Le skill doit expliciter les règles non négociables d'écriture et leur justification."""
    assert SKILL_FILE.is_file()
    content = SKILL_FILE.read_text(encoding="utf-8")

    # 1. Typage strict
    assert "disallow_untyped_defs" in content, "Le skill doit mentionner disallow_untyped_defs"
    assert "mypy" in content.lower(), "Le skill doit citer Mypy pour le typage strict"

    # 2. Interdiction de print()
    assert "print(" in content or "print()" in content or "print" in content, "Le skill doit interdire print()"
    assert "SecretRedactionFilter" in content or "logging" in content, "Le skill doit expliquer le logging sécurisé"

    # 3. Headless Qt
    assert "QT_QPA_PLATFORM=offscreen" in content or "offscreen" in content, "Le skill doit mentionner l'exécution Qt headless"

    # 4. Aucun emoji dans le code
    assert "emoji" in content.lower(), "Le skill doit mentionner l'interdiction des emojis dans le code"

    # 5. Mocks obligatoires pour tout appel LLM
    assert "mock" in content.lower(), "Le skill doit stipuler les mocks obligatoires pour tout appel LLM"

    # 6. Conventions d'arborescence et anglais technique (utils vs ressources)
    assert "utils" in content and ("ressources" in content or "anglais" in content.lower()), (
        "Le skill doit rappeler la convention d'anglais technique pour l'arborescence (ex. utils/ et non ressources/)"
    )


def test_verification_skill_cites_canonical_verification_command() -> None:
    """Le skill doit citer la commande canonique script/verify.py et les méthodes d'exécution par environnement."""
    assert SKILL_FILE.is_file()
    content = SKILL_FILE.read_text(encoding="utf-8")

    assert "script/verify.py" in content, "Le skill doit citer la commande canonique script/verify.py"
    assert "--fix" in content, "Le skill doit mentionner l'option --fix"
    assert "--all-tests" in content, "Le skill doit mentionner l'option --all-tests"

    # Méthodes d'exécution par environnement d'agent
    assert "run_command" in content, "Le skill doit citer run_command pour Antigravity / Gemini"
    assert "bash" in content.lower(), "Le skill doit citer l'outil Bash pour Claude Code"


def test_verification_skill_negative_guard() -> None:
    """Le skill doit comporter la section de garde-fou négatif '## ⛔ Ne PAS utiliser ce skill si...'."""
    assert SKILL_FILE.is_file()
    content = SKILL_FILE.read_text(encoding="utf-8")

    assert "## ⛔ Ne PAS utiliser ce skill si" in content or "## Ne pas utiliser ce skill si" in content, "Le skill doit contenir la section d'exclusion négative"


def test_claude_skill_symlink_exists() -> None:
    """Le symlink dans .claude/skills/ doit pointer vers le skill dans .agents/skills/."""
    assert CLAUDE_SKILL_LINK.exists() or CLAUDE_SKILL_LINK.is_symlink(), f"Le symlink {CLAUDE_SKILL_LINK} doit exister pour Claude Code"
    assert CLAUDE_SKILL_LINK.resolve() == SKILL_DIR.resolve(), f"Le symlink {CLAUDE_SKILL_LINK} doit pointer vers {SKILL_DIR}"


def test_skill_registered_in_gemini_and_agents_docs() -> None:
    """Le skill doit être enregistré dans GEMINI.md et dans AGENTS.md."""
    assert GEMINI_FILE.is_file()
    gemini_text = GEMINI_FILE.read_text(encoding="utf-8")
    assert ".agents/skills/verification-environnement/SKILL.md" in gemini_text, "Le skill doit être référencé dans GEMINI.md"

    assert AGENTS_FILE.is_file()
    agents_text = AGENTS_FILE.read_text(encoding="utf-8")
    assert "verification-environnement" in agents_text, "Le skill doit être répertorié dans AGENTS.md sous Agent Skills Catalog"


def test_auditer_coherence_skills_passes() -> None:
    """L'auditeur de cohérence statique des skills doit valider le skill sans erreur."""
    sys.path.insert(0, str(REPO_ROOT / ".agents" / "skills" / "mise-a-jour-metadonnees" / "scripts"))
    try:
        from auditer_coherence_skills import audit_skills  # type: ignore[import-not-found]
    finally:
        sys.path.pop(0)

    results = audit_skills(REPO_ROOT)
    assert results["status"] != "FAIL", f"L'audit des skills a échoué avec des erreurs : {results['errors']}"

    skill_info = results["skills"].get("verification-environnement")
    assert skill_info is not None, "Le skill 'verification-environnement' doit être audité"
    assert skill_info["exists"], "Le skill doit exister"
    assert skill_info["valid_frontmatter"], "Le frontmatter doit être valide"
    assert skill_info["has_description"], "La description doit être présente"
    assert skill_info["has_triggers"], "Les déclencheurs doivent être présents"
    assert skill_info["has_negative_triggers"], "La section négative doit être présente"
    assert not skill_info["missing_references"], f"Références introuvables : {skill_info['missing_references']}"
