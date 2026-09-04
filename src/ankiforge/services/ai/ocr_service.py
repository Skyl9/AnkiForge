import base64
import logging
import mimetypes
import shutil
import subprocess  # nosec B404
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ankiforge.database.base import db
from ankiforge.database.models import DocumentPageModel
from ankiforge.services.ai.base import LLMProvider, MockProvider
from ankiforge.services.ai.flexible_service import AIManager
from ankiforge.services.ai.vision_category_service import VisionCategoryService
from ankiforge.services.cards.media_manager import MediaManager
from ankiforge.utils.paths import get_app_data_dir

logger = logging.getLogger(__name__)

# Code Swift natif pour exécuter VNRecognizeTextRequest sur macOS via l'Apple Neural Engine
SWIFT_OCR_SOURCE = """
import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    exit(1)
}

let imagePath = CommandLine.arguments[1]
let fileURL = URL(fileURLWithPath: imagePath)

guard let image = NSImage(contentsOf: fileURL),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    exit(2)
}

let request = VNRecognizeTextRequest { request, error in
    if let error = error {
        fputs("Error: \\(error.localizedDescription)\\n", stderr)
        return
    }
    guard let observations = request.results as? [VNRecognizedTextObservation] else {
        return
    }
    let strings = observations.compactMap { observation in
        observation.topCandidates(1).first?.string
    }
    print(strings.joined(separator: "\\n"))
}

request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("Handler error: \\(error.localizedDescription)\\n", stderr)
    exit(3)
}
"""


def build_multimodal_payload(prompt: str, image_paths: Sequence[str | Path]) -> list[dict[str, Any]]:
    """
    Construit un payload multimodal conforme au format standard (OpenAI-style).
    Encode les images en Base64 avec détection automatique du type MIME.
    """
    payload: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

    for p in image_paths:
        path_obj = Path(p)
        if not path_obj.exists():
            logger.warning("Image introuvable pour payload multimodal : %s", p)
            continue

        mime, _ = mimetypes.guess_type(str(path_obj))
        if not mime or not mime.startswith("image/"):
            mime = "image/png"

        try:
            with open(path_obj, "rb") as f:
                b64_str = base64.b64encode(f.read()).decode("utf-8")
            payload.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime};base64,{b64_str}",
                    },
                }
            )
        except Exception as e:
            logger.warning("Échec d'encodage base64 de l'image %s : %s", p, e)

    return payload


class OCRService:
    """
    Service central de transcription OCR et d'analyse visuelle par catégories.
    Gère l'accélération matérielle macOS (Apple Vision) et le repli multiplateforme
    sur les modèles de vision (VLM : Qwen2.5-VL, Claude 3.7, Gemini 2.5).
    """

    def __init__(self, media_manager: MediaManager | None = None) -> None:
        self.media_manager = media_manager or MediaManager()
        self._apple_vision_binary: Path | None = None
        self._apple_vision_tested = False

    def is_apple_vision_available(self) -> bool:
        """
        Vérifie si le framework Apple Vision est exploitable sur la machine courante.
        Conditionné à macOS (darwin) et à la présence du binaire compilé ou du compilateur Swift.
        """
        if sys.platform != "darwin":
            return False

        if self._apple_vision_tested:
            return self._apple_vision_binary is not None and self._apple_vision_binary.exists()

        self._apple_vision_tested = True
        bin_dir = get_app_data_dir() / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        bin_path = bin_dir / "ankiforge_vision_ocr"

        # 1. Vérifier si le binaire existe déjà
        if bin_path.exists() and os_is_executable(bin_path):
            self._apple_vision_binary = bin_path
            return True

        # 2. Tenter de compiler le binaire autonome via swiftc
        swiftc = shutil.which("swiftc")
        if swiftc:
            try:
                swift_src = bin_dir / "ankiforge_vision_ocr.swift"
                swift_src.write_text(SWIFT_OCR_SOURCE, encoding="utf-8")
                res = subprocess.run(  # nosec B603
                    [swiftc, "-O", str(swift_src), "-o", str(bin_path)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                if res.returncode == 0 and bin_path.exists():
                    self._apple_vision_binary = bin_path
                    logger.info("Binaire Apple Vision OCR compilé avec succès dans %s", bin_path)
                    return True
                logger.debug("Échec compilation swiftc : %s", res.stderr)
            except Exception as e:
                logger.debug("Compilation Apple Vision impossible : %s", e)

        # 3. Vérifier si swift interprété est disponible
        if shutil.which("swift"):
            self._apple_vision_binary = None  # Mode interprété
            return True

        return False

    def transcribe_with_apple_vision(self, image_path: str | Path) -> str | None:
        """Transcrit une image via le framework natif Apple Vision sous macOS."""
        if not self.is_apple_vision_available():
            return None

        p = Path(image_path)
        if not p.exists():
            return None

        try:
            cmd = [str(self._apple_vision_binary), str(p)] if self._apple_vision_binary and self._apple_vision_binary.exists() else ["swift", "-e", SWIFT_OCR_SOURCE, str(p)]

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)  # nosec B603
            if res.returncode == 0:
                return res.stdout.strip()
            logger.warning("Erreur exécution Apple Vision OCR (code %d) : %s", res.returncode, res.stderr)
        except Exception as e:
            logger.warning("Exception lors de l'appel Apple Vision : %s", e)

        return None

    def transcribe_with_vlm(
        self,
        image_path: str | Path,
        provider: LLMProvider,
        system_prompt: str = "Tu es un transcripteur expert de documents académiques.",
        custom_instructions: str = "",
    ) -> str:
        """Transcrit une image via un modèle de langage visuel (VLM)."""
        prompt = custom_instructions or (
            "Transcris fidèlement et intégralement le contenu textuel, les formules mathématiques "
            "et les tableaux de cette image au format Markdown propre. "
            "Convertis les tableaux en Markdown ou HTML et les équations en LaTeX ($...$ ou $$...$$). "
            "Ne produis aucune explication préalable, uniquement le contenu extrait."
        )
        payload = build_multimodal_payload(prompt, [image_path])
        return provider.generate(system_prompt=system_prompt, user_prompt=payload, response_format="text").strip()

    def transcribe_image(
        self,
        image_path: str | Path,
        category_id: str = "structured",
        provider_override: LLMProvider | None = None,
    ) -> str:
        """
        Transcrit une image en appliquant la catégorie d'IA sélectionnée par l'utilisateur.
        Assure le repli multiplateforme si le moteur demandé est indisponible.
        """
        category = VisionCategoryService.get_category_by_id(category_id)
        if not category:
            category = VisionCategoryService.get_categories()[0]

        # 1. Si un provider est fourni explicitement (ex: injection de test ou override)
        if provider_override:
            return self.transcribe_with_vlm(
                image_path,
                provider_override,
                custom_instructions=category.custom_instructions,
            )

        # 2. Résolution du provider configuré pour la catégorie
        resolved = VisionCategoryService.resolve_provider_for_category(category)

        if resolved == "native":
            # Demande d'OCR matériel (Apple Vision sous macOS)
            if self.is_apple_vision_available():
                native_text = self.transcribe_with_apple_vision(image_path)
                if native_text:
                    return native_text

            # Fallback si Apple Vision échoue ou sous Linux/Windows : utilisation de l'IA active
            logger.info("Repli multiplateforme : utilisation du VLM configuré pour la transcription.")
            active_ai = AIManager()
            return self.transcribe_with_vlm(
                image_path,
                active_ai.provider,
                custom_instructions=category.custom_instructions,
            )

        if isinstance(resolved, LLMProvider):
            return self.transcribe_with_vlm(
                image_path,
                resolved,
                custom_instructions=category.custom_instructions,
            )

        return MockProvider().generate("", "", response_format="text")

    def transcribe_page(
        self,
        page_id: int,
        category_id: str = "structured",
        provider_override: LLMProvider | None = None,
    ) -> DocumentPageModel:
        """
        Transcrit une DocumentPageModel, met à jour son champ ocr_text et son statut en base SQLite.
        """
        with db.atomic():
            page = DocumentPageModel.get_by_id(page_id)
            media_path = self.media_manager.media_dir / page.media.filename
            if not media_path.exists():
                raise FileNotFoundError(f"Fichier média manquant : {media_path}")

            page.status = "ocr_running"
            page.save()

            text = self.transcribe_image(media_path, category_id=category_id, provider_override=provider_override)

            page.ocr_text = text
            page.status = "ready"
            page.save()

            logger.info("Page ID %d (album %d, p.%d) transcrite (%d caractères)", page.id, page.document.id, page.page_number, len(text))
            return page


def os_is_executable(path: Path) -> bool:
    """Vérifie si un fichier dispose des droits d'exécution."""
    import os

    return os.access(str(path), os.X_OK)
