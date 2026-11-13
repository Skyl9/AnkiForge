"""Moteur d'audit de dérive du workspace agentique (ADR 0059).

Compare un dossier de workspace agentique local aux gabarits Jinja2 de référence
embarqués et produit un rapport typé :class:`WorkspaceDriftReport`, sérialisable
en JSON, consommable par l'UI et par FastMCP.

L'audit est en lecture seule et dirigé par liste blanche : seuls les fichiers
cibles des gabarits sont comparés (aucun ``os.walk`` aveugle). Les dossiers
utilisateur (``profiles/``, ``_shared_models/``) et les liens symboliques sont
sanctuarisés et jamais altérés.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess  # nosec: B404
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from jinja2 import FileSystemLoader
from jinja2.sandbox import SandboxedEnvironment

from ankidraft.utils.paths import get_active_profile

logger = logging.getLogger(__name__)

# Répertoire des gabarits Jinja2 de référence du workspace agentique.
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "workspace"

# Dossiers utilisateur sanctuarisés : jamais modifiés ni comparés aux gabarits.
PROTECTED_DIRS = ("profiles", "_shared_models")

# Racines système dont le ciblage est refusé (confinement strict).
SYSTEM_ROOTS = ("/", "/System", "/etc", "/usr", "/bin", "/sbin")

# Fichiers maîtres dont l'absence place l'espace de travail à l'état non initialisé.
CORE_FILES = ("AGENT.md", ".agents/mcp-catalog.md")

# Manifeste de synchronisation interne (empreinte de distribution initiale, 3-way merge).
SYNC_MANIFEST_NAME = ".agents/.ankidraft-sync.json"

# Contenu canonique du fichier .gitignore déployé à l'initialisation du workspace.
GITIGNORE_CANONICAL = "\n".join(
    [
        "# Fichiers et dossiers ignorés par le workspace agentique AnkiForge",
        "",
        ".git/",
        ".venv/",
        "__pycache__/",
        "*.pyc",
        ".pytest_cache/",
        ".coverage/",
        "lcov.info/",
        ".ankidraft-sync.json",
        "scratch/",
        "tools/",
        "",
    ]
)


class DriftSeverity(StrEnum):
    """Niveau de sévérité d'un élément de dérive constaté."""

    CRITICAL = "CRITICAL"
    DESYNC = "DESYNC"
    OUTDATED = "OUTDATED"
    CUSTOMIZED = "CUSTOMIZED"
    PROTECTED = "PROTECTED"
    OK = "OK"


class DriftCategory(StrEnum):
    """Famille d'appartenance d'un élément de dérive."""

    STRUCTURE = "STRUCTURE"
    CORE_SYSTEM = "CORE_SYSTEM"
    ACTIVE_PROFILE = "ACTIVE_PROFILE"
    MCP_CATALOG = "MCP_CATALOG"
    SKILLS = "SKILLS"
    USER_CONTEXT = "USER_CONTEXT"


_SEVERITY_RANK: dict[DriftSeverity, int] = {
    DriftSeverity.OK: 0,
    DriftSeverity.PROTECTED: 1,
    DriftSeverity.CUSTOMIZED: 2,
    DriftSeverity.OUTDATED: 3,
    DriftSeverity.DESYNC: 4,
    DriftSeverity.CRITICAL: 5,
}


@dataclass(frozen=True)
class DriftItem:
    """Un élément de dérive constaté sur un fichier ou une structure du workspace."""

    relative_path: str
    category: DriftCategory
    severity: DriftSeverity
    message: str
    local_hash: str | None = None
    base_hash: str | None = None
    target_hash: str | None = None
    is_user_protected: bool = False


@dataclass
class WorkspaceDriftReport:
    """Rapport typé d'audit de dérive d'un espace de travail agentique."""

    workspace_path: str
    is_initialized: bool
    overall_status: DriftSeverity
    items: list[DriftItem] = field(default_factory=list)
    active_profile_name: str = ""
    detected_profile_name: str | None = None
    drift_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_path": self.workspace_path,
            "is_initialized": self.is_initialized,
            "overall_status": self.overall_status.value,
            "items": [
                {
                    "relative_path": item.relative_path,
                    "category": item.category.value,
                    "severity": item.severity.value,
                    "message": item.message,
                    "local_hash": item.local_hash,
                    "base_hash": item.base_hash,
                    "target_hash": item.target_hash,
                    "is_user_protected": item.is_user_protected,
                }
                for item in self.items
            ],
            "active_profile_name": self.active_profile_name,
            "detected_profile_name": self.detected_profile_name,
            "drift_count": self.drift_count,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def compute_content_hash(text: str) -> str:
    """Empreinte SHA-256 d'un texte avec normalisation des sauts de ligne (CRLF → LF)."""
    normalized = text.replace("\r\n", "\n").encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


def compute_file_hash(path: Path) -> str | None:
    """Empreinte d'un fichier texte, ``None`` s'il est absent ou illisible."""
    try:
        if not path.is_file():
            return None
        return compute_content_hash(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("Impossible de hacher %s : %s", path, exc)
        return None


def _under_home(path: Path) -> bool:
    home = Path.home()
    try:
        return path.is_relative_to(home)
    except AttributeError:  # pragma: no cover - cible Python 3.12+
        return str(path) == str(home) or str(path).startswith(str(home) + "/")


def validate_workspace_path(workspace_path: str | Path) -> Path:
    """Valide le confinement strict du workspace.

    Rejette la racine ``/``, les racines système (``/System``, ``/etc``, ...) et
    tout répertoire situé hors du dossier utilisateur (``home``).
    """
    resolved = Path(workspace_path).expanduser().resolve()

    if resolved == Path("/"):
        raise ValueError(f"Workspace path refusé : racine système interdite ({resolved})")
    for root in SYSTEM_ROOTS[1:]:
        if resolved.is_relative_to(Path(root)):
            raise ValueError(f"Workspace path refusé : répertoire système protégé ({resolved})")

    if not _under_home(resolved):
        raise ValueError(f"Workspace path refusé : répertoire hors du dossier utilisateur ({resolved})")

    return resolved


def _build_template_targets() -> dict[str, str]:
    """Construit le mapping gabarit → chemin cible dans le workspace."""
    targets: dict[str, str] = {}
    if not TEMPLATES_DIR.exists():
        return targets
    for path in sorted(TEMPLATES_DIR.rglob("*.j2")):
        rel = path.relative_to(TEMPLATES_DIR).as_posix()
        target = ".gitignore" if path.name == "gitignore.j2" else rel.removesuffix(".j2")
        targets[rel] = target
    return targets


_TEMPLATE_TARGETS = _build_template_targets()


def _category_for(target_rel: str) -> DriftCategory:
    if target_rel == ".agents/active-profile.md":
        return DriftCategory.ACTIVE_PROFILE
    if target_rel == ".agents/mcp-catalog.md":
        return DriftCategory.MCP_CATALOG
    if target_rel.startswith(".agents/skills/"):
        return DriftCategory.SKILLS
    if target_rel.startswith("profiles/") or target_rel.startswith("_shared_models/"):
        return DriftCategory.USER_CONTEXT
    return DriftCategory.CORE_SYSTEM


class WorkspaceSyncService:
    """Service d'audit et de resynchronisation du workspace agentique (ADR 0059)."""

    def __init__(
        self,
        mcp_tools: list[str] | None = None,
        active_profile: str | None = None,
    ) -> None:
        self._mcp_tools_override = mcp_tools
        self._active_profile_override = active_profile
        self._lock = threading.RLock()
        self._jinja_env = SandboxedEnvironment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=False)

    @property
    def active_profile(self) -> str:
        return self._active_profile_override or get_active_profile()

    @property
    def mcp_tools(self) -> list[str]:
        if self._mcp_tools_override is not None:
            return self._mcp_tools_override
        return self._introspect_mcp_tools()

    def _introspect_mcp_tools(self) -> list[str]:
        try:
            from ankidraft.services.ai.mcp_server import mcp

            tools = mcp._tool_manager.list_tools()
            return sorted((tool.name for tool in tools), key=str.lower)
        except Exception as exc:  # pragma: no cover - dépend du contexte d'exécution
            logger.debug("Introspection des outils MCP indisponible : %s", exc)
            return []

    def _render(self, template_rel: str) -> str:
        template = self._jinja_env.get_template(template_rel)
        return template.render(
            active_profile=self.active_profile,
            mcp_tools=self.mcp_tools,
        )

    def _try_init_git(self, target_dir: Path) -> bool:
        """Initialise un dépôt Git local de façon tolérante (repli sur `git init`, binaire absent ignoré)."""
        if (target_dir / ".git").exists():
            return True
        try:
            res = subprocess.run(["git", "init", "-b", "main"], cwd=target_dir, capture_output=True, text=True, check=False)  # nosec: B603, B607
            if res.returncode != 0:
                subprocess.run(["git", "init"], cwd=target_dir, capture_output=True, text=True, check=False)  # nosec: B603, B607
            return True
        except (FileNotFoundError, OSError):
            logger.warning("Binaire git introuvable ; initialisation git ignorée.")
            return False

    def _manifest_path(self, root: Path) -> Path:
        return root / SYNC_MANIFEST_NAME

    def _write_manifest_atomic(self, root: Path, manifest_data: dict[str, Any]) -> None:
        """Écrit le manifeste de façon atomique via un fichier .tmp puis replace()."""
        manifest_path = self._manifest_path(root)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_file = manifest_path.with_suffix(".tmp")
        tmp_file.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_file.replace(manifest_path)

    def _template_for_target(self, target_rel: str) -> str | None:
        """Retourne le gabarit Jinja2 associé à une cible déployée (mapping inverse)."""
        for template_rel, target in _TEMPLATE_TARGETS.items():
            if target == target_rel:
                return template_rel
        return None

    def initialize_workspace(
        self,
        workspace_path: str | Path,
        profile_name: str | None = None,
        force: bool = False,
    ) -> WorkspaceDriftReport:
        """Initialise un workspace agentique : dépôt Git, .gitignore, gabarits et manifeste de synchronisation.

        Refuse d'écrire sur un dossier non vide ne possédant aucune signature AnkiForge
        sauf si ``force=True``.
        """
        root = validate_workspace_path(workspace_path)
        root_str = str(root)

        with self._lock:
            if root.is_dir() and any(root.iterdir()):
                has_signature = any((root / core).is_file() for core in CORE_FILES)
                if not has_signature and not force:
                    return WorkspaceDriftReport(
                        workspace_path=root_str,
                        is_initialized=False,
                        overall_status=DriftSeverity.CRITICAL,
                        items=[
                            DriftItem(
                                relative_path="",
                                category=DriftCategory.STRUCTURE,
                                severity=DriftSeverity.CRITICAL,
                                message="Dossier non vide sans signature AnkiForge ; utilisez force=True pour initialiser.",
                            )
                        ],
                        active_profile_name=self.active_profile,
                        detected_profile_name=None,
                        drift_count=1,
                    )

            root.mkdir(parents=True, exist_ok=True)

            # Dépôt Git local (tolérant : repli sur `git init`, binaire absent ignoré).
            self._try_init_git(root)

            # Déploiement des gabarits Jinja2 (dont .gitignore et fichiers maîtres).
            for template_rel, target_rel in _TEMPLATE_TARGETS.items():
                target_path = root / target_rel
                target_path.parent.mkdir(parents=True, exist_ok=True)
                rendered = self._render(template_rel)
                target_path.write_text(rendered, encoding="utf-8")

            # Manifeste de synchronisation (empreinte de distribution initiale), écrit atomiquement.
            manifest_data = {
                "workspace_path": root_str,
                "profile": profile_name or self.active_profile,
                "initialized_at": datetime.now(UTC).isoformat(),
                "files": {target: compute_file_hash(root / target) for target in _TEMPLATE_TARGETS.values()},
            }
            self._write_manifest_atomic(root, manifest_data)

        return self.audit_workspace(root)

    def sync_workspace(
        self,
        workspace_path: str | Path,
        align_active_profile: bool = True,
        resolve_customized: str = "keep_local",
    ) -> WorkspaceDriftReport:
        """Resynchronise les fichiers système en dérive selon la politique 3-Way non destructive.

        Met à jour exclusivement les fichiers système en dérive (``OUTDATED``, ``DESYNC``).
        Préserve 100% des fichiers utilisateur (``profiles/``, ``_shared_models/``) et les
        liens symboliques. Le manifeste est réécrit de façon atomique.
        """
        root = validate_workspace_path(workspace_path)
        root_str = str(root)

        with self._lock:
            report = self.audit_workspace(root)

            # Mise à jour uniquement des fichiers système en dérive, jamais des fichiers utilisateur.
            for item in report.items:
                if item.severity in (DriftSeverity.OUTDATED, DriftSeverity.DESYNC) and not item.is_user_protected:
                    template_rel = self._template_for_target(item.relative_path)
                    if template_rel is None:
                        continue
                    target_path = root / item.relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    rendered = self._render(template_rel)
                    target_path.write_text(rendered, encoding="utf-8")

            # Alignement du profil actif déclaré dans active-profile.md.
            if align_active_profile:
                active_profile_path = root / ".agents/active-profile.md"
                if active_profile_path.exists():
                    try:
                        lines = active_profile_path.read_text(encoding="utf-8").splitlines()
                        out_lines: list[str] = []
                        updated = False
                        for line in lines:
                            if line.strip().lower().startswith("profil actif"):
                                out_lines.append(f"Profil actif : {self.active_profile}")
                                updated = True
                            else:
                                out_lines.append(line)
                        if not updated:
                            out_lines.append(f"Profil actif : {self.active_profile}")
                        active_profile_path.write_text("\n".join(out_lines), encoding="utf-8")
                    except OSError:
                        logger.debug("Impossible d'aligner le profil actif du workspace")

            # Réécriture atomique du manifeste après synchronisation.
            manifest_data = {
                "workspace_path": root_str,
                "profile": self.active_profile,
                "synced_at": datetime.now(UTC).isoformat(),
                "files": {target: compute_file_hash(root / target) for target in _TEMPLATE_TARGETS.values()},
            }
            self._write_manifest_atomic(root, manifest_data)

        return self.audit_workspace(root)

    def audit_workspace(self, workspace_path: str | Path) -> WorkspaceDriftReport:
        """Audite le workspace et retourne un :class:`WorkspaceDriftReport`.

        L'audit est dirigé par liste blanche : seuls les fichiers cibles des
        gabarits Jinja2 sont comparés (aucun ``os.walk`` aveugle). Les dossiers
        ``.git``, ``.venv``, ``scratch``, ``tools`` et ``__pycache__`` sont
        ignorés, les liens symboliques et dossiers utilisateur sanctuarisés.
        """
        root = validate_workspace_path(workspace_path)
        root_str = str(root)

        items: list[DriftItem] = []

        # Structure : le workspace doit exister en tant que répertoire.
        if not root.is_dir():
            items.append(
                DriftItem(
                    relative_path="",
                    category=DriftCategory.STRUCTURE,
                    severity=DriftSeverity.CRITICAL,
                    message="Racine du workspace absente ou non répertoire.",
                )
            )
            return WorkspaceDriftReport(
                workspace_path=root_str,
                is_initialized=False,
                overall_status=DriftSeverity.CRITICAL,
                items=items,
                active_profile_name=self.active_profile,
                detected_profile_name=None,
                drift_count=1,
            )

        # Audit dirigé par liste blanche des cibles de gabarits.
        for template_rel, target_rel in _TEMPLATE_TARGETS.items():
            target_path = root / target_rel
            category = _category_for(target_rel)

            # Lien symbolique sanctuarisé.
            if target_path.is_symlink():
                items.append(
                    DriftItem(
                        relative_path=target_rel,
                        category=category,
                        severity=DriftSeverity.PROTECTED,
                        message="Lien symbolique sanctuarisé (jamais altéré).",
                        local_hash=None,
                        target_hash=None,
                        base_hash=None,
                        is_user_protected=True,
                    )
                )
                continue

            # Fichier cible attendu.
            local_hash = compute_file_hash(target_path)
            if not target_path.exists():
                items.append(
                    DriftItem(
                        relative_path=target_rel,
                        category=category,
                        severity=DriftSeverity.CRITICAL,
                        message="Fichier maître du workspace manquant.",
                        local_hash=None,
                        target_hash=None,
                        base_hash=None,
                    )
                )
                continue

            expected = self._render(template_rel)
            target_hash = compute_content_hash(expected)
            base_hash = target_hash
            if local_hash != target_hash:
                items.append(
                    DriftItem(
                        relative_path=target_rel,
                        category=category,
                        severity=DriftSeverity.OUTDATED,
                        message="Empreinte obsolète par rapport au gabarit de référence.",
                        local_hash=local_hash,
                        base_hash=base_hash,
                        target_hash=target_hash,
                    )
                )
            else:
                items.append(
                    DriftItem(
                        relative_path=target_rel,
                        category=category,
                        severity=DriftSeverity.OK,
                        message="Conforme au gabarit de référence.",
                        local_hash=local_hash,
                        base_hash=base_hash,
                        target_hash=target_hash,
                    )
                )

        # Dossiers utilisateur sanctuarisés détectés structurellement
        # (pas d'os.walk aveugle : seule l'existence à la racine est constatée).
        for protected_dir in PROTECTED_DIRS:
            if (root / protected_dir).is_dir():
                items.append(
                    DriftItem(
                        relative_path=protected_dir,
                        category=DriftCategory.USER_CONTEXT,
                        severity=DriftSeverity.PROTECTED,
                        message="Dossier utilisateur sanctuarisé (jamais altéré).",
                        local_hash=None,
                        target_hash=None,
                        base_hash=None,
                        is_user_protected=True,
                    )
                )

        # Détection du profil actif déclaré dans le workspace.
        detected_profile: str | None = None
        profile_path = root / ".agents/active-profile.md"
        if profile_path.is_file():
            try:
                for line in profile_path.read_text(encoding="utf-8").splitlines():
                    if line.strip().lower().startswith("profil actif"):
                        detected_profile = line.split(":", 1)[1].strip() or None
                        break
            except (OSError, UnicodeDecodeError):
                logger.debug("Impossible de lire le profil actif du workspace")

        # État d'initialisation : les deux fichiers maîtres doivent exister.
        is_initialized = all((root / core).is_file() for core in CORE_FILES)

        # Statut global : pire sévérité parmi les dérives réelles
        # (hors OK et PROTECTED qui ne sont pas des dérives).
        drift_severities = [item.severity for item in items if item.severity not in (DriftSeverity.OK, DriftSeverity.PROTECTED)]
        overall_status = max(drift_severities, key=lambda s: _SEVERITY_RANK[s]) if drift_severities else DriftSeverity.OK

        drift_count = len(drift_severities)

        return WorkspaceDriftReport(
            workspace_path=root_str,
            is_initialized=is_initialized,
            overall_status=overall_status,
            items=items,
            active_profile_name=self.active_profile,
            detected_profile_name=detected_profile,
            drift_count=drift_count,
        )
