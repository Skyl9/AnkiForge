"""
Gestionnaire central de cycle de vie des extensions AnkiForge (PluginManager).
Gère la découverte dynamique, le vendoring sys.path, l'isolation try/catch,
le Safe Mode et la compatibilité Nuitka.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
import tempfile
import traceback
import zipfile
from pathlib import Path
from typing import Any

from ankiforge.services.plugins.api import AnkiForgeAPI
from ankiforge.services.plugins.manifest_schema import AddonInfo, AddonManifest, AddonStatus

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Gestionnaire centralisé pour la découverte, le chargement et la gestion des addons AnkiForge.
    """

    _instance: PluginManager | None = None

    def __init__(self, addons_dir: Path | None = None) -> None:
        if addons_dir is None:
            from ankiforge.utils.paths import get_app_data_dir

            self.addons_dir = get_app_data_dir() / "addons"
        else:
            self.addons_dir = Path(addons_dir)

        self.addons_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.addons_dir.parent / "addons_meta.json"

        self._addons: dict[str, AddonInfo] = {}
        self._apis: dict[str, AnkiForgeAPI] = {}
        self._modules: dict[str, Any] = {}
        self._disabled_addon_ids: set[str] = set()
        self._safe_mode: bool = False

        self._load_meta()

    @classmethod
    def get_instance(cls, addons_dir: Path | None = None) -> PluginManager:
        """Singleton getter."""
        if cls._instance is None:
            cls._instance = PluginManager(addons_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Réinitialise l'instance (utilisé pour les tests)."""
        cls._instance = None

    @property
    def is_safe_mode(self) -> bool:
        return self._safe_mode

    def _load_meta(self) -> None:
        """Charge l'état d'activation des addons depuis addons_meta.json."""
        if self.meta_file.exists():
            try:
                with open(self.meta_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self._disabled_addon_ids = set(data.get("disabled", []))
            except Exception as e:
                logger.warning("Impossible de lire %s : %s", self.meta_file, e)
                self._disabled_addon_ids = set()
        else:
            self._disabled_addon_ids = set()

    def _save_meta(self) -> None:
        """Sauvegarde l'état d'activation dans addons_meta.json."""
        try:
            with open(self.meta_file, "w", encoding="utf-8") as f:
                json.dump({"disabled": sorted(list(self._disabled_addon_ids))}, f, indent=2)
        except Exception as e:
            logger.error("Erreur d'enregistrement de %s : %s", self.meta_file, e)

    def discover_addons(self) -> list[AddonInfo]:
        """
        Scanne le dossier ~/.ankiforge/addons/ pour découvrir tous les addons valides.
        """
        self._addons.clear()
        if not self.addons_dir.exists():
            return []

        for entry in self.addons_dir.iterdir():
            if not entry.is_dir():
                continue

            manifest_file = entry / "manifest.json"
            if not manifest_file.exists():
                logger.debug("Dossier %s ignoré : aucun manifest.json trouvé.", entry.name)
                continue

            try:
                with open(manifest_file, encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest = AddonManifest(**manifest_data)
            except Exception as e:
                logger.warning("Manifest invalide pour %s : %s", entry.name, e)
                continue

            # Vérifier l'existence de la doc (config.md ou README.md)
            has_doc = False
            doc_content = ""
            for doc_name in ["config.md", "README.md", "readme.md"]:
                doc_path = entry / doc_name
                if doc_path.exists():
                    has_doc = True
                    try:
                        doc_content = doc_path.read_text(encoding="utf-8")
                    except Exception:
                        doc_content = ""
                    break

            # Schéma de configuration initial
            config_data = {}
            config_file = entry / "config.json"
            if config_file.exists():
                try:
                    with open(config_file, encoding="utf-8") as f:
                        config_data = json.load(f)
                except Exception:
                    config_data = {}

            is_enabled = manifest.id not in self._disabled_addon_ids
            status = AddonStatus.DISABLED if not is_enabled else AddonStatus.DISABLED

            addon_info = AddonInfo(
                manifest=manifest,
                folder_path=entry,
                status=status,
                is_enabled=is_enabled,
                config_schema=config_data,
                has_documentation=has_doc,
                doc_markdown=doc_content,
            )
            self._addons[manifest.id] = addon_info

        return list(self._addons.values())

    def check_safe_mode_trigger(self) -> bool:
        """
        Vérifie si le Safe Mode doit être déclenché (flag CLI ou touche Shift maintenue sous Qt).
        """
        if "--safe-mode" in sys.argv:
            return True

        try:
            from PySide6.QtCore import Qt
            from PySide6.QtGui import QGuiApplication

            app = QGuiApplication.instance()
            if app and isinstance(app, QGuiApplication):
                modifiers = QGuiApplication.queryKeyboardModifiers()
                if bool(modifiers & Qt.KeyboardModifier.ShiftModifier):
                    logger.warning("🛡️ Touche Shift détectée au boot : Activation du Safe Mode (Addons désactivés) !")
                    return True
        except Exception:
            pass  # nosec B110

        return False

    def load_all_addons(self, safe_mode: bool | None = None) -> dict[str, bool]:
        """
        Découvre et initialise tous les addons activés.
        """
        if safe_mode is None:
            self._safe_mode = self.check_safe_mode_trigger()
        else:
            self._safe_mode = safe_mode

        self.discover_addons()

        results: dict[str, bool] = {}
        if self._safe_mode:
            logger.info("🛡️ Mode Sans Échec actif : aucun addon ne sera chargé au démarrage.")
            for addon_id, info in self._addons.items():
                info.status = AddonStatus.DISABLED
                results[addon_id] = False
            return results

        for addon_id, info in list(self._addons.items()):
            if info.is_enabled:
                success = self.load_addon(addon_id)
                results[addon_id] = success
            else:
                info.status = AddonStatus.DISABLED
                results[addon_id] = False

        return results

    def load_addon(self, addon_id: str) -> bool:
        """
        Charge et initialise un addon spécifique avec isolation try/catch et vendoring sys.path.
        """
        info = self._addons.get(addon_id)
        if not info:
            logger.warning("Addon introuvable : %s", addon_id)
            return False

        init_file = info.folder_path / info.manifest.entry_point
        if not init_file.exists():
            info.status = AddonStatus.ERROR
            info.error_message = f"Point d'entrée '{info.manifest.entry_point}' introuvable."
            logger.error("Addon '%s' : %s", addon_id, info.error_message)
            return False

        # 1. Vendoring sys.path
        vendor_dir = info.folder_path / "libs"
        if vendor_dir.exists() and str(vendor_dir) not in sys.path:
            sys.path.insert(0, str(vendor_dir))

        try:
            # 2. Création de l'API dédiée
            api = AnkiForgeAPI(info.manifest, info.folder_path)
            self._apis[addon_id] = api

            # 3. Chargement dynamique compatible Nuitka
            module_name = f"ankiforge_addon_{addon_id}"
            spec = importlib.util.spec_from_file_location(module_name, init_file)
            if not spec or not spec.loader:
                raise ImportError(f"Impossible de créer le module spec pour {init_file}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 4. Exécution du point d'entrée
            if hasattr(module, "init_addon"):
                module.init_addon(api)
                info.status = AddonStatus.ACTIVE
                info.error_message = None
                self._modules[addon_id] = module
                logger.info("Addon '%s' (v%s) initialisé avec succès.", addon_id, info.manifest.version)
                return True
            else:
                info.status = AddonStatus.ERROR
                info.error_message = "La fonction 'init_addon(api)' est manquante dans __init__.py."
                logger.warning("Addon '%s' : %s", addon_id, info.error_message)
                return False

        except Exception as e:
            tb = traceback.format_exc()
            info.status = AddonStatus.ERROR
            info.error_message = f"{type(e).__name__}: {str(e)}"
            logger.error("Erreur lors du chargement de l'addon '%s' :\n%s", addon_id, tb)
            return False

    def unload_addon(self, addon_id: str) -> bool:
        """
        Désenregistre les écouteurs et décharge un addon en mémoire.
        """
        if addon_id in self._apis:
            api = self._apis.pop(addon_id)
            api.events.unregister_all()

        module_name = f"ankiforge_addon_{addon_id}"
        if module_name in sys.modules:
            del sys.modules[module_name]
        self._modules.pop(addon_id, None)

        if addon_id in self._addons:
            self._addons[addon_id].status = AddonStatus.DISABLED

        return True

    def enable_addon(self, addon_id: str) -> bool:
        """Active un addon et sauvegarde dans les préférences."""
        if addon_id in self._disabled_addon_ids:
            self._disabled_addon_ids.remove(addon_id)
            self._save_meta()

        if addon_id in self._addons:
            self._addons[addon_id].is_enabled = True
            return self.load_addon(addon_id)
        return False

    def disable_addon(self, addon_id: str) -> bool:
        """Désactive un addon et sauvegarde dans les préférences."""
        self._disabled_addon_ids.add(addon_id)
        self._save_meta()

        if addon_id in self._addons:
            self._addons[addon_id].is_enabled = False
            self.unload_addon(addon_id)
            self._addons[addon_id].status = AddonStatus.DISABLED
            return True
        return False

    def install_addon_from_zip(self, zip_path: str | Path) -> tuple[bool, str]:
        """
        Installe un addon depuis une archive .zip.
        L'archive doit contenir manifest.json soit à la racine, soit dans un unique dossier racine.
        """
        zip_file = Path(zip_path)
        if not zip_file.exists():
            return False, f"Fichier zip introuvable : {zip_path}"

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = Path(tmp_dir)
                with zipfile.ZipFile(zip_file, "r") as zf:
                    zf.extractall(tmp_path)

                # Recherche du manifest.json
                manifest_location = None
                if (tmp_path / "manifest.json").exists():
                    manifest_location = tmp_path
                else:
                    for child in tmp_path.iterdir():
                        if child.is_dir() and (child / "manifest.json").exists():
                            manifest_location = child
                            break

                if not manifest_location:
                    return False, "Archive invalide : aucun 'manifest.json' trouvé à la racine ou dans un sous-dossier."

                with open(manifest_location / "manifest.json", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest = AddonManifest(**manifest_data)

                target_dir = self.addons_dir / manifest.id
                if target_dir.exists():
                    shutil.rmtree(target_dir)

                shutil.copytree(manifest_location, target_dir)

                # Rafraîchir et charger l'addon
                self.discover_addons()
                if manifest.id not in self._disabled_addon_ids:
                    self.load_addon(manifest.id)

                return True, f"Addon '{manifest.name}' (v{manifest.version}) installé avec succès !"

        except Exception as e:
            logger.error("Erreur lors de l'installation de l'archive %s : %s", zip_path, e, exc_info=True)
            return False, f"Erreur d'installation : {str(e)}"

    def uninstall_addon(self, addon_id: str) -> bool:
        """Désinstalle complètement un addon (suppression des fichiers)."""
        self.unload_addon(addon_id)
        if addon_id in self._disabled_addon_ids:
            self._disabled_addon_ids.remove(addon_id)
            self._save_meta()

        info = self._addons.pop(addon_id, None)
        if info and info.folder_path.exists():
            try:
                shutil.rmtree(info.folder_path)
                logger.info("Addon '%s' désinstallé avec succès.", addon_id)
                return True
            except Exception as e:
                logger.error("Erreur lors de la suppression de %s : %s", info.folder_path, e)
                return False
        return False

    def get_addon(self, addon_id: str) -> AddonInfo | None:
        """Retourne les informations d'un addon."""
        return self._addons.get(addon_id)

    def get_all_addons(self) -> list[AddonInfo]:
        """Retourne la liste de tous les addons découverts."""
        return list(self._addons.values())

    def get_addon_api(self, addon_id: str) -> AnkiForgeAPI | None:
        """Retourne l'instance API injectée dans l'addon."""
        return self._apis.get(addon_id)

    def open_addons_folder(self) -> None:
        """Ouvre le répertoire des addons dans le gestionnaire de fichiers OS."""
        self._open_folder_in_os(self.addons_dir)

    def open_addon_folder(self, addon_id: str) -> None:
        """Ouvre le sous-dossier d'un addon spécifique."""
        info = self._addons.get(addon_id)
        if info and info.folder_path.exists():
            self._open_folder_in_os(info.folder_path)

    @staticmethod
    def _open_folder_in_os(folder_path: Path) -> None:
        """Ouvre un dossier de manière multi-plateforme (macOS, Windows, Linux)."""
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.Popen(["open", str(folder_path)])  # nosec B603 B607
            elif system == "Windows":
                os.startfile(str(folder_path))  # type: ignore[attr-defined] # nosec B606
            else:
                subprocess.Popen(["xdg-open", str(folder_path)])  # nosec B603 B607
        except Exception as e:
            logger.error("Impossible d'ouvrir le dossier %s : %s", folder_path, e)


def get_plugin_manager(addons_dir: Path | None = None) -> PluginManager:
    """Accès singleton au gestionnaire de plugins."""
    return PluginManager.get_instance(addons_dir)
