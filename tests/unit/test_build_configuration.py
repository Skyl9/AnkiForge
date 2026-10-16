"""Tests de non-régression pour la configuration de compilation Nuitka et l'isolation des dépendances binaires."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from nuitka.utils.ModuleNames import ModuleName

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.mark.unit
class TestBuildConfiguration:
    """Valide les garde-fous de packaging et l'exclusion des modules tiers non requis."""

    def test_nuitka_config_excludes_anki_and_aqt(self) -> None:
        """Vérifie que nuitka_config.json contient anki et aqt dans nofollow_imports."""
        config_path = PROJECT_ROOT / "build_script" / "nuitka_config.json"
        assert config_path.exists(), f"Configuration introuvable : {config_path}"

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        nofollow = config.get("common", {}).get("nofollow_imports", [])
        assert "anki" in nofollow, "Le package 'anki' doit être exclu via common.nofollow_imports"
        assert "aqt" in nofollow, "Le package 'aqt' doit être exclu via common.nofollow_imports"

    def test_nuitka_config_excludes_heavy_runtime_dependencies(self) -> None:
        """Vérifie que nuitka_config.json exclut pymupdf, fitz, youtube_transcript_api et leurs sous-modules."""
        config_path = PROJECT_ROOT / "build_script" / "nuitka_config.json"
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        nofollow = config.get("common", {}).get("nofollow_imports", [])
        expected_exclusions = ("pymupdf", "fitz", "youtube_transcript_api", "defusedxml", "markdownify")
        for pkg in expected_exclusions:
            assert pkg in nofollow, f"Le package '{pkg}' doit être exclu via common.nofollow_imports pour éviter le débordement heap MSVC"

        # Vérifie que les sous-modules lourds problématiques sont bien interceptés par le pattern matching Nuitka
        for submodule in ("pymupdf", "pymupdf.mupdf", "fitz", "youtube_transcript_api", "youtube_transcript_api.proxies"):
            m = ModuleName(submodule)
            match, _ = m.matchesToShellPatterns(nofollow)
            assert match is True, f"Nuitka aurait dû exclure le sous-module '{submodule}' avec nofollow_imports"

    def test_copy_runtime_dependencies_skips_anki_and_aqt(self) -> None:
        """Vérifie que copy_runtime_dependencies.py n'embarque pas anki/aqt dans le bundle."""
        script_path = PROJECT_ROOT / "script" / "copy_runtime_dependencies.py"
        assert script_path.exists(), f"Script introuvable : {script_path}"

        tree = ast.parse(script_path.read_text(encoding="utf-8"))
        skip_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "skip_names" and isinstance(node.value, ast.Set):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                skip_names.add(elt.value)

        assert "anki" in skip_names, "'anki' doit être présent dans skip_names de copy_runtime_dependencies.py"
        assert "aqt" in skip_names, "'aqt' doit être présent dans skip_names de copy_runtime_dependencies.py"

    def test_build_nuitka_command_generates_nofollow_anki(self) -> None:
        """Vérifie que build_nuitka_command génère les drapeaux --nofollow-import-to pour anki et aqt."""
        from script.build_standalone import build_nuitka_command, load_config

        config = load_config()
        cmd = build_nuitka_command(config, target_os="darwin", jobs=2, version="1.3.0")

        assert "--nofollow-import-to=anki" in cmd, "Flag --nofollow-import-to=anki manquant dans la commande Nuitka"
        assert "--nofollow-import-to=aqt" in cmd, "Flag --nofollow-import-to=aqt manquant dans la commande Nuitka"

    def test_nuitka_pattern_matching_excludes_anki_submodules(self) -> None:
        """Vérifie que Nuitka exclut tous les sous-modules d'anki avec le pattern configuré."""
        config_path = PROJECT_ROOT / "build_script" / "nuitka_config.json"
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

        nofollow = config.get("common", {}).get("nofollow_imports", [])

        for submodule in ["anki", "anki._rsbridge", "anki._backend", "anki.collection", "anki.importing.apkg"]:
            m = ModuleName(submodule)
            match, _ = m.matchesToShellPatterns(nofollow)
            assert match is True, f"Nuitka aurait dû exclure le sous-module '{submodule}' avec nofollow_imports"

    def test_sanitize_macos_native_dependencies_patches_corrupt_id(self, tmp_path: Path) -> None:
        """Vérifie que sanitize_macos_native_dependencies corrige un install_name d'anki corrompu."""
        from script.build_standalone import sanitize_macos_native_dependencies

        fake_so = tmp_path / "_rsbridge.so"
        fake_so.write_bytes(b"mock_macho_content")

        with patch("subprocess.run") as mock_run:
            # Simule otool -D qui renvoie le chemin runner corrompu
            mock_run.side_effect = [
                MagicMock(
                    returncode=0,
                    stdout=f"{fake_so}:\n/Users/runner/work/anki/anki/out/rust/release-lto/deps/librsbridge.dylib\n",
                ),
                MagicMock(returncode=0, stdout=""),
            ]

            patched = sanitize_macos_native_dependencies(search_dirs=[tmp_path])
            assert patched is True
            assert mock_run.call_count == 2
            # Deuxième appel = install_name_tool -id
            install_cmd = mock_run.call_args_list[1][0][0]
            assert install_cmd[0] == "install_name_tool"
            assert install_cmd[1] == "-id"
            assert install_cmd[2] == "@rpath/_rsbridge.so"
            assert install_cmd[3] == str(fake_so)
