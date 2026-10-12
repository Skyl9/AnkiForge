"""Tests unitaires et d'intégration pour le script de synchronisation des instructions agents."""

from __future__ import annotations

from pathlib import Path

import pytest

from script.sync_agent_instructions import (
    BLOCK_HEADER_TEMPLATE,
    CANONICAL_INSTRUCTIONS_DIR,
    REPO_ROOT,
    TARGET_ADAPTERS,
    TargetAdapter,
    check_adapters_drift,
    extract_canonical_blocks,
    render_adapter_content,
    sync_all_adapters,
)

pytestmark = pytest.mark.unit


def test_canonical_instructions_directory_exists() -> None:
    """Le répertoire de la source canonique doit exister et contenir les 4 fragments requis."""
    assert CANONICAL_INSTRUCTIONS_DIR.is_dir(), f"Répertoire introuvable : {CANONICAL_INSTRUCTIONS_DIR}"

    expected_files = {
        "commandes.md",
        "regles_ingenierie.md",
        "architecture_points_cles.md",
        "catalogue_skills.md",
    }
    present_files = {f.name for f in CANONICAL_INSTRUCTIONS_DIR.glob("*.md")}
    missing = expected_files - present_files
    assert not missing, f"Fragments canoniques manquants sous {CANONICAL_INSTRUCTIONS_DIR} : {missing}"


def test_extract_canonical_blocks() -> None:
    """L'extraction des blocs canoniques doit charger tous les fragments non vides."""
    blocks = extract_canonical_blocks(CANONICAL_INSTRUCTIONS_DIR)
    assert "commandes" in blocks
    assert "regles_ingenierie" in blocks
    assert "architecture_points_cles" in blocks
    assert "catalogue_skills" in blocks

    for name, content in blocks.items():
        assert content.strip(), f"Le bloc canonique '{name}' ne doit pas être vide."
        # Vérifier que le contenu utilise le français et mentionne la commande verify.py dans commandes
        if name == "commandes":
            assert "script/verify.py" in content


def test_target_adapters_registry_contains_required_targets() -> None:
    """Le registre des cibles doit déclarer le quatuor d'adaptateurs requis."""
    registered_paths = {adapter.path for adapter in TARGET_ADAPTERS}
    expected = {
        "GEMINI.md",
        "AGENTS.md",
        "CLAUDE.md",
        ".github/copilot-instructions.md",
    }
    assert expected.issubset(registered_paths), f"Adaptateurs cibles manquants dans le registre : {expected - registered_paths}"


def test_render_adapter_content_replaces_canonical_blocks() -> None:
    """render_adapter_content doit injecter le contenu canonique entre les balises START et END."""
    template = "# Mon Adaptateur\n\nIntroduction spécifique.\n\n<!-- CANONICAL:START:commandes -->\nAncien contenu obsolète\n<!-- CANONICAL:END:commandes -->\n\nConclusion spécifique.\n"
    blocks = {"commandes": "## Nouvelles commandes canoniques"}
    adapter = TargetAdapter(path="TEST.md", expected_blocks=["commandes"])

    rendered, issues = render_adapter_content(template, adapter, blocks)
    assert not issues, f"Problèmes détectés : {issues}"
    assert "Ancien contenu obsolète" not in rendered
    assert "<!-- CANONICAL:START:commandes -->" in rendered
    assert "<!-- CANONICAL:END:commandes -->" in rendered
    assert "## Nouvelles commandes canoniques" in rendered
    assert "Ancien contenu obsolète" not in rendered
    assert "Introduction spécifique." in rendered
    assert "Conclusion spécifique." in rendered
    assert BLOCK_HEADER_TEMPLATE.format(block_name="commandes") in rendered


def test_render_adapter_detects_missing_tags() -> None:
    """render_adapter_content doit signaler une balise attendue mais absente."""
    template = "# Mon Adaptateur sans balise\n"
    blocks = {"commandes": "Contenu"}
    adapter = TargetAdapter(path="TEST.md", expected_blocks=["commandes"])

    _, issues = render_adapter_content(template, adapter, blocks)
    assert any("Balise manquante pour 'commandes'" in issue for issue in issues)


def test_sync_and_check_adapters_idempotence(tmp_path: Path) -> None:
    """La synchronisation dans un dossier temporaire doit être idempotente et passer le check."""
    fake_instructions = tmp_path / ".agents" / "instructions"
    fake_instructions.mkdir(parents=True)
    (fake_instructions / "commandes.md").write_text("Commandes test", encoding="utf-8")

    fake_file = tmp_path / "TEST.md"
    fake_file.write_text(
        "# Test\n<!-- CANONICAL:START:commandes -->\n<!-- CANONICAL:END:commandes -->\n",
        encoding="utf-8",
    )

    test_adapter = TargetAdapter(path="TEST.md", expected_blocks=["commandes"])
    test_adapters = [test_adapter]

    # Synchroniser
    synced, errors = sync_all_adapters(repo_root=tmp_path, adapters=test_adapters, instructions_dir=fake_instructions)
    assert not errors
    assert "TEST.md" in synced

    # Vérifier que le check passe
    is_ok, diffs = check_adapters_drift(repo_root=tmp_path, adapters=test_adapters, instructions_dir=fake_instructions)
    assert is_ok, f"Le check doit passer après synchronisation. Diffs : {diffs}"
    assert not diffs


def test_check_adapters_drift_detects_manual_modification(tmp_path: Path) -> None:
    """Une altération manuelle du contenu entre les balises doit être détectée par check_adapters_drift."""
    fake_instructions = tmp_path / ".agents" / "instructions"
    fake_instructions.mkdir(parents=True)
    (fake_instructions / "commandes.md").write_text("Commandes v1", encoding="utf-8")

    fake_file = tmp_path / "TEST.md"
    fake_file.write_text(
        "# Test\n<!-- CANONICAL:START:commandes -->\nAltération manuelle non synchronisée\n<!-- CANONICAL:END:commandes -->\n",
        encoding="utf-8",
    )

    test_adapters = [TargetAdapter(path="TEST.md", expected_blocks=["commandes"])]
    is_ok, diffs = check_adapters_drift(repo_root=tmp_path, adapters=test_adapters, instructions_dir=fake_instructions)
    assert not is_ok, "Le check de dérive doit échouer en présence d'une modification manuelle."
    assert "TEST.md" in diffs


@pytest.mark.integration
def test_all_live_adapters_in_sync_with_canonical_source() -> None:
    """Tous les adaptateurs réels du dépôt doivent être rigoureusement synchronisés avec la source canonique."""
    is_ok, diffs = check_adapters_drift(repo_root=REPO_ROOT, adapters=TARGET_ADAPTERS, instructions_dir=CANONICAL_INSTRUCTIONS_DIR)
    assert is_ok, "Dérive détectée sur les adaptateurs d'instructions du dépôt :\n" + "\n".join(f"--- {p} ---\n{d}" for p, d in diffs.items())
