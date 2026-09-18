#!/usr/bin/env python3
"""Script d'audit statique et de contrôle de cohérence pour les skills AnkiForge.

Vérifie :
1. La structure et le frontmatter YAML de chaque skill dans .agents/skills/*/SKILL.md
   (kebab-case, description avec déclencheurs, section d'exclusion, taille <= 150 lignes)
2. La synchronisation bidirectionnelle avec GEMINI.md et AGENTS.md
3. La synchronisation avec .github/copilot-instructions.md
4. La validité des références de skills dans .agents/profiles/*.yaml
5. L'existence des fichiers référencés (references/, scripts/) et l'absence de print()
6. Les risques de collision de triggers entre descriptions de skills
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


def _print(msg: str = "") -> None:
    """Sortie console propre sans enfreindre la règle T20 (print())."""
    sys.stdout.write(f"{msg}\n")


KEBAB_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_SKILL_LINES = 150
TRIGGER_KEYWORDS = ["use when", "activer", "activat", "invoqu", "lorsque", "demande"]
REFERENCED_FILE_RE = re.compile(r"(?:references/[A-Za-z0-9_./-]+\.md|scripts/[A-Za-z0-9_./-]+\.py)")
PROFILE_LINK_RE = re.compile(r"(?m)^\s*-\s*[\"']?(\.agents/skills/[^\"'\n]+)[\"']?")
STOPWORDS = {
    "skill",
    "skills",
    "user",
    "asks",
    "when",
    "with",
    "pour",
    "dans",
    "avec",
    "les",
    "des",
    "aux",
    "une",
    "qui",
    "use",
    "the",
    "and",
    "that",
    "this",
    "from",
    "audit",
    "audits",
    "auditer",
    "rapport",
    "report",
    "produce",
    "produit",
    "produire",
    "lorsque",
    "demande",
}


def _description_tokens(description: str) -> set[str]:
    """Extrait les mots significatifs d'une description pour détecter les collisions."""
    words = re.findall(r"[a-zà-ÿ0-9]{4,}", description.lower())
    return {w for w in words if w not in STOPWORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / len(a | b) if inter else 0.0


def _parse_frontmatter(content: str) -> dict[str, str] | None:
    """Extrait et parse le frontmatter YAML d'un fichier markdown."""
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", content, re.DOTALL)
    if not match:
        return None

    raw_yaml = match.group(1)
    try:
        data = yaml.safe_load(raw_yaml)
        if isinstance(data, dict) and "name" in data and "description" in data:
            return {
                "name": str(data["name"]).strip(),
                "description": str(data["description"]).strip(),
            }
    except Exception:
        pass

    metadata: dict[str, str] = {}
    name_match = re.search(r"^name:\s*(.+)$", raw_yaml, re.MULTILINE)
    if name_match:
        metadata["name"] = name_match.group(1).strip().strip("'\"")
    else:
        return None

    desc_match = re.search(r"^description:\s*(?:>|\|)?\s*\n?((?:(?:\s{2,}|\t).*|\s*\n)*)", raw_yaml, re.MULTILINE)
    if desc_match and desc_match.group(1).strip():
        metadata["description"] = " ".join(line.strip() for line in desc_match.group(1).splitlines() if line.strip())
    else:
        single_desc = re.search(r"^description:\s*(.+)$", raw_yaml, re.MULTILINE)
        if single_desc:
            metadata["description"] = single_desc.group(1).strip().strip("'\"")
        else:
            return None

    return metadata


def audit_skills(repo_root: Path) -> dict[str, Any]:
    """Exécute l'audit complet du parc de skills et des fichiers de référence."""
    results: dict[str, Any] = {
        "status": "PASS",
        "skills_found": 0,
        "skills": {},
        "errors": [],
        "warnings": [],
        "references": {
            "gemini_md": {"present": False, "missing_skills": [], "extra_skills": []},
            "agents_md": {"present": False, "skills_referenced": False, "missing_skills": []},
            "copilot_instructions": {"present": False, "skills_referenced": False},
            "profiles": {"valid": True, "broken_links": []},
        },
    }

    skills_dir = repo_root / ".agents" / "skills"
    if not skills_dir.exists():
        results["status"] = "FAIL"
        results["errors"].append(f"Le dossier des skills est introuvable : {skills_dir}")
        return results

    # 1. Analyse de chaque skill
    skill_names: set[str] = set()
    descriptions: dict[str, str] = {}
    for skill_path in sorted(skills_dir.iterdir()):
        if not skill_path.is_dir():
            continue

        skill_name = skill_path.name
        skill_names.add(skill_name)
        skill_file = skill_path / "SKILL.md"

        skill_info: dict[str, Any] = {
            "path": str(skill_file.relative_to(repo_root)),
            "exists": skill_file.exists(),
            "name_is_kebab_case": bool(KEBAB_RE.fullmatch(skill_name)),
            "valid_frontmatter": False,
            "has_description": False,
            "has_triggers": False,
            "has_negative_triggers": False,
            "line_count": 0,
            "missing_references": [],
            "subfolders": [p.name for p in skill_path.iterdir() if p.is_dir()],
            "issues": [],
        }

        if not skill_file.exists():
            skill_info["issues"].append("Fichier SKILL.md manquant")
            results["errors"].append(f"Skill '{skill_name}' : fichier SKILL.md manquant.")
            results["skills"][skill_name] = skill_info
            continue

        content = skill_file.read_text(encoding="utf-8")
        skill_info["line_count"] = len(content.splitlines())
        if skill_info["line_count"] > MAX_SKILL_LINES:
            warning = f"Skill '{skill_name}' : SKILL.md fait {skill_info['line_count']} lignes (limite {MAX_SKILL_LINES})."
            skill_info["issues"].append(warning)
            results["warnings"].append(warning + " Pensez à déporter le contenu dans references/ ou scripts/.")

        if not skill_info["name_is_kebab_case"]:
            skill_info["issues"].append("Nom de dossier non kebab-case (a-z0-9-).")
            results["errors"].append(f"Skill '{skill_name}' : nom de dossier non kebab-case.")

        frontmatter = _parse_frontmatter(content)

        if not frontmatter or "name" not in frontmatter:
            skill_info["issues"].append("Frontmatter YAML invalide ou clé 'name' manquante")
            results["errors"].append(f"Skill '{skill_name}' : frontmatter YAML invalide.")
        else:
            skill_info["valid_frontmatter"] = True
            if frontmatter["name"] != skill_name:
                skill_info["issues"].append(f"Nom frontmatter ('{frontmatter['name']}') != nom dossier ('{skill_name}')")
                results["warnings"].append(f"Skill '{skill_name}' : nom YAML '{frontmatter['name']}' != nom du dossier.")

        description = frontmatter.get("description", "") if frontmatter else ""
        if description:
            skill_info["has_description"] = True
            descriptions[skill_name] = description
            if any(kw in description.lower() for kw in TRIGGER_KEYWORDS):
                skill_info["has_triggers"] = True
            else:
                skill_info["issues"].append("Description sans déclencheur explicite ('Use when...')")
                results["warnings"].append(f"Skill '{skill_name}' : aucun déclencheur explicite dans description.")
        else:
            skill_info["issues"].append("Clé 'description' manquante dans le frontmatter")
            results["errors"].append(f"Skill '{skill_name}' : description manquante.")

        # Vérification de la section négative (anti-pattern guard) — propagée au statut
        if "## ⛔ Ne PAS utiliser ce skill si" in content or "## Ne pas utiliser ce skill si" in content:
            skill_info["has_negative_triggers"] = True
        else:
            issue = "Section d'exclusion '## ⛔ Ne PAS utiliser ce skill si...' manquante (garde-fou requis)."
            skill_info["issues"].append(issue)
            results["warnings"].append(f"Skill '{skill_name}' : {issue}")

        # Existence des fichiers référencés (references/ et scripts/)
        for ref in sorted(set(REFERENCED_FILE_RE.findall(content))):
            target = skill_path / ref
            if not target.exists():
                skill_info["missing_references"].append(ref)
                results["warnings"].append(f"Skill '{skill_name}' : fichier référencé introuvable : '{ref}'.")

        # Absence de print() dans les scripts d'assistance (règle T20)
        scripts_dir = skill_path / "scripts"
        if scripts_dir.exists():
            for script in sorted(scripts_dir.glob("*.py")):
                script_text = script.read_text(encoding="utf-8")
                if re.search(r"(?m)^(?!.*def _print)\s*print\(", script_text):
                    results["warnings"].append(f"Skill '{skill_name}' : 'print(' détecté dans {script.name} (utiliser _print / sys.stdout.write).")

        results["skills"][skill_name] = skill_info

    results["skills_found"] = len(skill_names)

    # 1bis. Collisions de triggers entre descriptions
    for name_a, name_b in [pair for pair in ((a, b) for a in sorted(descriptions) for b in sorted(descriptions) if a < b)]:
        similarity = _jaccard(_description_tokens(descriptions[name_a]), _description_tokens(descriptions[name_b]))
        if similarity >= 0.45:
            results["warnings"].append(f"Collision potentielle de triggers entre '{name_a}' et '{name_b}' (similarité {similarity:.2f}).")

    # 2. Vérification GEMINI.md
    gemini_file = repo_root / "GEMINI.md"
    if gemini_file.exists():
        results["references"]["gemini_md"]["present"] = True
        gemini_content = gemini_file.read_text(encoding="utf-8")

        for skill_name in skill_names:
            expected_pattern = f".agents/skills/{skill_name}/SKILL.md"
            if expected_pattern not in gemini_content:
                results["references"]["gemini_md"]["missing_skills"].append(skill_name)
                results["errors"].append(f"GEMINI.md : le skill '{skill_name}' n'est pas référencé ({expected_pattern}).")

        # Détecter les skills mentionnés dans GEMINI.md qui n'existent pas sur le disque
        gemini_skill_refs = re.findall(r"\.agents/skills/([a-zA-Z0-9_-]+)/SKILL\.md", gemini_content)
        for ref_name in gemini_skill_refs:
            if ref_name not in skill_names:
                results["references"]["gemini_md"]["extra_skills"].append(ref_name)
                results["errors"].append(f"GEMINI.md : référence un skill inexistant sur disque : '{ref_name}'.")
    else:
        results["errors"].append("Fichier GEMINI.md introuvable à la racine.")

    # 3. Vérification AGENTS.md (répertoire + listing de chaque skill)
    agents_file = repo_root / "AGENTS.md"
    if agents_file.exists():
        results["references"]["agents_md"]["present"] = True
        agents_content = agents_file.read_text(encoding="utf-8")
        if ".agents/skills/" in agents_content:
            results["references"]["agents_md"]["skills_referenced"] = True
        else:
            results["warnings"].append("AGENTS.md : aucune mention du répertoire .agents/skills/ dans la documentation.")
        for skill_name in skill_names:
            if skill_name not in agents_content:
                results["references"]["agents_md"]["missing_skills"].append(skill_name)
                results["warnings"].append(f"AGENTS.md : le skill '{skill_name}' n'apparaît pas dans le catalogue.")
    else:
        results["warnings"].append("Fichier AGENTS.md introuvable à la racine.")

    # 4. Vérification .github/copilot-instructions.md
    copilot_file = repo_root / ".github" / "copilot-instructions.md"
    if copilot_file.exists():
        results["references"]["copilot_instructions"]["present"] = True
        copilot_content = copilot_file.read_text(encoding="utf-8")
        if ".agents/skills/" in copilot_content:
            results["references"]["copilot_instructions"]["skills_referenced"] = True
        else:
            results["warnings"].append(".github/copilot-instructions.md : aucune mention du répertoire .agents/skills/.")
    else:
        results["warnings"].append("Fichier .github/copilot-instructions.md introuvable.")

    # 5. Vérification des profils .agents/profiles/*.yaml
    profiles_dir = repo_root / ".agents" / "profiles"
    if profiles_dir.exists():
        for profile_path in profiles_dir.glob("*.yaml"):
            p_content = profile_path.read_text(encoding="utf-8")
            for s_ref in PROFILE_LINK_RE.findall(p_content):
                target_path = repo_root / s_ref
                if not target_path.exists():
                    results["references"]["profiles"]["valid"] = False
                    results["references"]["profiles"]["broken_links"].append({"profile": profile_path.name, "target": s_ref})
                    results["errors"].append(f"Profil {profile_path.name} : lien brisé vers '{s_ref}'.")

    if results["errors"]:
        results["status"] = "FAIL"
    elif results["warnings"]:
        results["status"] = "WARN"

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit de cohérence des skills AnkiForge")
    parser.add_argument("--json", action="store_true", help="Afficher le résultat au format JSON")
    parser.add_argument("--quiet", action="store_true", help="Afficher uniquement les erreurs")
    args = parser.parse_args()

    # .agents/skills/mise-a-jour-metadonnees/scripts/auditer_coherence_skills.py -> parents[4] is repo root
    repo_root = Path(__file__).resolve().parents[4]
    audit_res = audit_skills(repo_root)

    if args.json:
        _print(json.dumps(audit_res, indent=2, ensure_ascii=False))
        return 0 if audit_res["status"] != "FAIL" else 1

    _print(f"\n{'=' * 60}")
    _print(f"📊 Audit de Cohérence des Skills AnkiForge [{audit_res['status']}]")
    _print(f"{'=' * 60}")
    _print(f"Skills analysés : {audit_res['skills_found']}")

    if audit_res["errors"]:
        _print(f"\n❌ ERREURS ({len(audit_res['errors'])}):")
        for err in audit_res["errors"]:
            _print(f"  - {err}")

    if audit_res["warnings"] and not args.quiet:
        _print(f"\n⚠️ AVERTISSEMENTS ({len(audit_res['warnings'])}):")
        for warn in audit_res["warnings"]:
            _print(f"  - {warn}")

    if audit_res["status"] == "PASS":
        _print("\n✅ Tous les skills et fichiers de référence sont parfaitement synchronisés !")

    _print(f"{'=' * 60}\n")
    return 0 if audit_res["status"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
