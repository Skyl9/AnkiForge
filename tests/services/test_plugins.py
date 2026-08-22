"""
Tests unitaires et d'intégration pour le système d'addons et plugins d'AnkiForge.
Valide la conformité Nuitka, l'isolation try/catch, le Safe Mode, le vendoring sys.path,
l'enregistrement d'actions d'éditeur, les étapes DAG et les outils MCP.
"""

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
import pytest
from pydantic import ValidationError

from ankiforge.services.plugins.api import PipelineHooksAPI, MCPHooksAPI
from ankiforge.services.plugins.event_bus import EventBus
from ankiforge.services.plugins.manifest_schema import AddonManifest, AddonStatus
from ankiforge.services.plugins.plugin_manager import PluginManager


@pytest.fixture
def temp_addons_dir():
    """Crée un répertoire temporaire isolé pour les addons de test."""
    temp_dir = tempfile.mkdtemp(prefix="ankiforge_test_addons_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def event_bus_clean():
    """Fournit un EventBus réinitialisé pour chaque test."""
    bus = EventBus()
    EventBus._instance = bus
    yield bus
    EventBus.reset_instance()


def test_manifest_validation():
    """Valide les contraintes et règles Pydantic du manifest.json."""
    # Manifeste valide
    m = AddonManifest(
        id="test_addon_1",
        name="Test Addon",
        version="1.2.0",
        author="Dev",
        description="Une extension de test",
    )
    assert m.id == "test_addon_1"
    assert m.entry_point == "__init__.py"

    # ID invalide (caractères interdits)
    with pytest.raises(ValidationError):
        AddonManifest(id="invalid id with spaces!", name="Bad Addon")


def test_event_bus_isolation(event_bus_clean):
    """Vérifie que l'EventBus isole les exceptions levées par les écouteurs."""
    received = []

    def good_handler(data):
        received.append(data)

    def faulty_handler(data):
        raise RuntimeError("Crash intentionnel dans l'écouteur !")

    def another_good_handler(data):
        received.append(f"second_{data}")

    event_bus_clean.on("custom_event", good_handler)
    event_bus_clean.on("custom_event", faulty_handler)
    event_bus_clean.on("custom_event", another_good_handler)

    # L'émission ne doit PAS planter malgré le faulty_handler
    event_bus_clean.emit("custom_event", "hello")
    assert "hello" in received
    assert "second_hello" in received

    # Test désabonnement
    event_bus_clean.off("custom_event", good_handler)
    event_bus_clean.emit("custom_event", "world")
    assert "second_world" in received
    assert "world" not in received


def test_plugin_discovery_and_loading(temp_addons_dir):
    """Teste la découverte, le chargement, les hooks et la configuration d'un addon valide."""
    addon_folder = temp_addons_dir / "my_demo_addon"
    addon_folder.mkdir(parents=True)

    # 1. manifest.json
    manifest = {
        "id": "my_demo_addon",
        "name": "My Demo Addon",
        "version": "2.0.0",
        "author": "Alice",
        "description": "Addon de test complet",
    }
    (addon_folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    # 2. config.json
    config = {"theme_color": "purple", "enable_feature_x": True, "count": 42}
    (addon_folder / "config.json").write_text(json.dumps(config), encoding="utf-8")

    # 3. config.md
    (addon_folder / "config.md").write_text("# Documentation\nGuide utilisateur.", encoding="utf-8")

    # 4. libs/ (vendoring)
    libs_dir = addon_folder / "libs"
    libs_dir.mkdir()

    # 5. __init__.py
    init_code = """
def init_addon(api):
    # Extension UI
    api.ui.add_editor_action("demo_btn", "Demo Action", "sparkle", lambda: None)

    # Extension DAG
    def custom_dag_executor(orchestrator, step, state):
        state.variables["dag_executed"] = True
    api.pipelines.register_step_type("CUSTOM_DEMO_STEP", custom_dag_executor)

    # Extension MCP
    def my_mcp_tool(query: str):
        return f"MCP query result: {query}"
    api.mcp.register_tool("demo_mcp_tool", my_mcp_tool, description="Demo Tool")

    # Réglages
    api.config.set("loaded_timestamp", 123456)
"""
    (addon_folder / "__init__.py").write_text(init_code, encoding="utf-8")

    # Instanciation PluginManager
    pm = PluginManager(addons_dir=temp_addons_dir)
    discovered = pm.discover_addons()
    assert len(discovered) == 1
    assert discovered[0].id == "my_demo_addon"
    assert discovered[0].has_documentation is True

    # Chargement
    results = pm.load_all_addons(safe_mode=False)
    assert results["my_demo_addon"] is True

    info = pm.get_addon("my_demo_addon")
    assert info is not None
    assert info.status == AddonStatus.ACTIVE

    # Vérification des points d'ancrage
    api = pm.get_addon_api("my_demo_addon")
    assert api is not None
    assert len(api.ui.get_registered_editor_actions()) == 1
    assert "CUSTOM_DEMO_STEP" in PipelineHooksAPI.get_registered_steps()
    assert "demo_mcp_tool" in MCPHooksAPI.get_registered_tools()

    # Vérification config mise à jour
    assert api.config.get("loaded_timestamp") == 123456
    assert api.config.get("count") == 42


def test_faulty_addon_isolation(temp_addons_dir):
    """Vérifie qu'un addon avec erreur de syntaxe ou exception ne fait pas planter l'application."""
    addon_folder = temp_addons_dir / "crash_addon"
    addon_folder.mkdir(parents=True)

    manifest = {"id": "crash_addon", "name": "Crash Addon", "version": "1.0.0"}
    (addon_folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    init_code = """
def init_addon(api):
    raise ZeroDivisionError("Division par zéro dans l'extension !")
"""
    (addon_folder / "__init__.py").write_text(init_code, encoding="utf-8")

    pm = PluginManager(addons_dir=temp_addons_dir)
    results = pm.load_all_addons(safe_mode=False)

    assert results["crash_addon"] is False
    info = pm.get_addon("crash_addon")
    assert info.status == AddonStatus.ERROR
    assert "ZeroDivisionError" in info.error_message


def test_safe_mode(temp_addons_dir):
    """Vérifie que le Safe Mode désactive le chargement de tous les addons."""
    addon_folder = temp_addons_dir / "addon_safe"
    addon_folder.mkdir(parents=True)

    manifest = {"id": "addon_safe", "name": "Safe Test", "version": "1.0.0"}
    (addon_folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (addon_folder / "__init__.py").write_text("def init_addon(api): pass", encoding="utf-8")

    pm = PluginManager(addons_dir=temp_addons_dir)
    results = pm.load_all_addons(safe_mode=True)

    assert pm.is_safe_mode is True
    assert results["addon_safe"] is False
    assert pm.get_addon("addon_safe").status == AddonStatus.DISABLED


def test_zip_installation_and_uninstall(temp_addons_dir):
    """Teste l'installation d'un addon depuis une archive ZIP et sa désinstallation."""
    # Créer un fichier ZIP temporaire
    with tempfile.TemporaryDirectory() as src_tmp:
        src_path = Path(src_tmp) / "zipped_addon"
        src_path.mkdir()

        manifest = {"id": "zipped_addon", "name": "Zipped Addon", "version": "3.1.4"}
        (src_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (src_path / "__init__.py").write_text("def init_addon(api): pass", encoding="utf-8")

        zip_dest = Path(src_tmp) / "package.zip"
        with zipfile.ZipFile(zip_dest, "w") as zf:
            zf.write(src_path / "manifest.json", arcname="zipped_addon/manifest.json")
            zf.write(src_path / "__init__.py", arcname="zipped_addon/__init__.py")

        pm = PluginManager(addons_dir=temp_addons_dir)
        success, msg = pm.install_addon_from_zip(zip_dest)
        assert success is True
        assert "v3.1.4" in msg

        # Vérifier présence
        info = pm.get_addon("zipped_addon")
        assert info is not None
        assert info.name == "Zipped Addon"

        # Désinstallation
        del_success = pm.uninstall_addon("zipped_addon")
        assert del_success is True
        assert pm.get_addon("zipped_addon") is None
        assert not (temp_addons_dir / "zipped_addon").exists()
