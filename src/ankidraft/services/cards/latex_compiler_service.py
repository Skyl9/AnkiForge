"""Service de Compilation LaTeX Sécurisé et Mise en Cache des Médias SVG pour AnkiForge.

Compile un fragment LaTeX en image vectorielle SVG (ou PNG) via la chaîne
latex + dvisvgm, avec sandboxing, timeout strict et cache déterministe
identique à Anki Desktop.
"""

import hashlib
import logging
import subprocess  # nosec B404 - intentional subprocess usage for LaTeX compilation
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from ankidraft.database.models.cards import MediaModel, NoteTypeModel
from ankidraft.services.profile_manager import ProfileManager
from ankidraft.utils.paths import get_active_profile

if TYPE_CHECKING:
    from ankidraft.services.cards.latex_environment_service import LatexEnvironmentService

logger = logging.getLogger(__name__)


class LatexCompilationError(Exception):
    """Exception levée lors d'un échec de compilation LaTeX.

    Attributes:
        message: Message d'erreur synthétique.
        log_excerpt: Extrait pertinent du fichier .log TeX pour diagnostic.
    """

    def __init__(self, message: str, log_excerpt: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.log_excerpt = log_excerpt


class LatexCompilerService:
    """Compile des fragments LaTeX en médias SVG/PNG mis en cache dans le profil actif.

    Le nom du fichier généré suit la convention déterministe d'Anki Desktop :
    `latex-<sha1>.svg` (ou `.png`), où le hash est calculé sur :
    `sha1(latex_pre + snippet + latex_post + is_svg)`.

    La compilation s'exécute dans un répertoire temporaire isolé avec les drapeaux
    de sécurité obligatoires (`-no-shell-escape`, `-halt-on-error`) et un timeout
    strict de 10 secondes.
    """

    LATEX_TIMEOUT_SECONDS = 10.0

    def __init__(self) -> None:
        self._profile_manager = ProfileManager()
        self._latex_env_service: LatexEnvironmentService | None = None  # Lazy init to avoid circular imports

    def _get_latex_env_service(self) -> "LatexEnvironmentService":
        """Initialisation paresseuse pour éviter l'import circulaire."""
        if self._latex_env_service is None:
            from ankidraft.services.cards.latex_environment_service import (
                LatexEnvironmentService,
            )

            self._latex_env_service = LatexEnvironmentService()
        return self._latex_env_service

    def compile_snippet_to_media(self, snippet: str, model: NoteTypeModel) -> str:
        """Compile un fragment LaTeX et retourne le nom du fichier média.

        Args:
            snippet: Le code LaTeX à compiler (sans délimiteurs).
            model: Le NoteTypeModel fournissant latex_pre, latex_post, latex_svg.

        Returns:
            Le nom du fichier média (ex: `latex-a1b2c3d4.svg`).

        Raises:
            LatexCompilationError: Si la compilation échoue (syntaxe, timeout, binaire manquant).
        """
        # 1. Calculer l'empreinte déterministe (identique à Anki Desktop)
        media_filename = self._compute_media_filename(snippet, model)

        # 2. Vérifier le cache : si le fichier existe déjà, le retourner immédiatement
        profile_name = get_active_profile()
        media_dir = self._profile_manager.get_media_dir(profile_name)
        media_path = media_dir / media_filename

        if media_path.exists():
            logger.debug("Cache hit pour LaTeX : %s", media_filename)
            return media_filename

        # 3. Vérifier la disponibilité de l'environnement LaTeX
        env_service = self._get_latex_env_service()
        if not env_service.is_latex_available():
            raise LatexCompilationError(
                "Environnement LaTeX non disponible : latex et/ou dvisvgm introuvables",
                "Installez MacTeX, TeX Live ou MiKTeX et configurez les chemins dans les paramètres.",
            )

        # 4. Compiler dans un répertoire temporaire isolé
        latex_bin = env_service.detect_latex_binary()
        dvisvgm_bin = env_service.detect_dvisvgm_binary()

        if not latex_bin or not dvisvgm_bin:
            raise LatexCompilationError(
                "Binaires LaTeX requis introuvables",
                f"latex: {latex_bin.path if latex_bin else 'NON TROUVÉ'}, dvisvgm: {dvisvgm_bin.path if dvisvgm_bin else 'NON TROUVÉ'}",
            )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            tex_file = tmp_path / "tmp.tex"
            dvi_file = tmp_path / "tmp.dvi"
            svg_file = tmp_path / "tmp.svg"
            log_file = tmp_path / "tmp.log"

            # 4.1 Écrire le fichier .tex complet
            latex_pre = model.latex_pre or ""
            latex_post = model.latex_post or ""
            tex_content = f"{latex_pre}\n{snippet}\n{latex_post}"
            tex_file.write_text(tex_content, encoding="utf-8")

            # 4.2 Compiler avec latex (Étape 1 : .tex -> .dvi)
            latex_cmd = [
                latex_bin.path,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-no-shell-escape",
                "tmp.tex",
            ]
            try:
                logger.debug("Exécution LaTeX : %s", " ".join(latex_cmd))
                result = subprocess.run(  # nosec B603 - trusted binary path, controlled args
                    latex_cmd,
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.LATEX_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise LatexCompilationError(
                    f"Timeout lors de la compilation LaTeX (> {self.LATEX_TIMEOUT_SECONDS}s)",
                    "La compilation a dépassé le temps imparti. Vérifiez les boucles infinies dans le code TeX.",
                ) from e

            if result.returncode != 0:
                log_excerpt = self._extract_log_errors(log_file)
                raise LatexCompilationError(
                    "Échec de la compilation LaTeX (latex)",
                    log_excerpt or result.stderr or result.stdout,
                )

            if not dvi_file.exists():
                raise LatexCompilationError(
                    "Fichier .dvi non généré par latex",
                    "La compilation latex s'est terminée sans produire de sortie DVI.",
                )

            # 4.3 Convertir DVI en SVG avec dvisvgm (Étape 2 : .dvi -> .svg)
            dvisvgm_cmd = [
                dvisvgm_bin.path,
                "--no-fonts",
                "--exact",
                "-Z",
                "2",
                "tmp.dvi",
                "-o",
                "tmp.svg",
            ]
            try:
                logger.debug("Exécution dvisvgm : %s", " ".join(dvisvgm_cmd))
                result = subprocess.run(  # nosec B603 - trusted binary path, controlled args
                    dvisvgm_cmd,
                    cwd=tmp_dir,
                    capture_output=True,
                    text=True,
                    timeout=self.LATEX_TIMEOUT_SECONDS,
                    check=False,
                )
            except subprocess.TimeoutExpired as e:
                raise LatexCompilationError(
                    f"Timeout lors de la conversion DVI->SVG (> {self.LATEX_TIMEOUT_SECONDS}s)",
                    "La conversion dvisvgm a dépassé le temps imparti.",
                ) from e

            if result.returncode != 0:
                log_excerpt = self._extract_log_errors(log_file)
                raise LatexCompilationError(
                    "Échec de la conversion DVI vers SVG (dvisvgm)",
                    log_excerpt or result.stderr or result.stdout,
                )

            if not svg_file.exists():
                raise LatexCompilationError(
                    "Fichier .svg non généré par dvisvgm",
                    "La conversion dvisvgm s'est terminée sans produire de sortie SVG.",
                )

            # 4.4 Copier le SVG vers le dossier médias du profil
            media_dir.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copy2(svg_file, media_path)

            # 4.5 Enregistrer dans MediaModel
            self._register_media_file(media_filename, media_path)

            logger.info("Compilation LaTeX réussie : %s", media_filename)
            return media_filename

    def _compute_media_filename(self, snippet: str, model: NoteTypeModel) -> str:
        """Calcule le nom de fichier média déterministe selon la convention Anki.

        Hash = sha1(latex_pre + snippet + latex_post + is_svg)
        Fichier = latex-<hash>.svg (ou .png si latex_svg=False)
        """
        latex_pre = model.latex_pre or ""
        latex_post = model.latex_post or ""
        is_svg = "1" if model.latex_svg else "0"

        # Reproduire exactement le calcul d'Anki : concaténation avec sauts de ligne
        payload = f"{latex_pre}\n{snippet}\n{latex_post}\n{is_svg}".encode()
        file_hash = hashlib.sha1(payload).hexdigest()  # nosec B324 - SHA-1 requis pour compatibilité Anki
        ext = "svg" if model.latex_svg else "png"
        return f"latex-{file_hash}.{ext}"

    def _extract_log_errors(self, log_file: Path) -> str:
        """Extrait les lignes d'erreur pertinentes du fichier .log TeX."""
        if not log_file.exists():
            return ""

        try:
            content = log_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()

            # Chercher les lignes d'erreur TeX typiques
            error_lines = []
            for i, line in enumerate(lines):
                if line.startswith("! ") or "Error:" in line or "Fatal error" in line:
                    # Inclure le contexte (ligne précédente et suivante)
                    start = max(0, i - 1)
                    end = min(len(lines), i + 3)
                    error_lines.extend(lines[start:end])
                    if len(error_lines) > 20:  # Limiter la taille
                        break

            if error_lines:
                return "\n".join(error_lines[:20])

            # Sinon retourner les 15 dernières lignes
            return "\n".join(lines[-15:])
        except Exception as e:
            logger.debug("Impossible de lire le fichier .log : %s", e)
            return ""

    def _register_media_file(self, filename: str, media_path: Path) -> None:
        """Enregistre le fichier média dans MediaModel pour l'indexation et la déduplication."""
        try:
            import hashlib

            # Calculer le checksum SHA-256 pour la déduplication
            content = media_path.read_bytes()
            checksum = hashlib.sha256(content).hexdigest()

            # Déterminer le MIME type
            mime_type = "image/svg+xml" if filename.endswith(".svg") else "image/png"

            # Créer ou récupérer l'entrée MediaModel
            MediaModel.get_or_create(
                filename=filename,
                defaults={
                    "original_name": filename,
                    "checksum": checksum,
                    "mime_type": mime_type,
                },
            )
            logger.debug("Média indexé dans MediaModel : %s", filename)
        except Exception as e:
            # Ne pas faire échouer la compilation si l'indexation échoue
            logger.warning("Échec de l'indexation du média %s : %s", filename, e)

    def is_ready(self) -> bool:
        """Retourne True si l'environnement LaTeX est disponible pour la compilation."""
        env_service = self._get_latex_env_service()
        return env_service.is_latex_available()


__all__ = ["LatexCompilerService", "LatexCompilationError"]
