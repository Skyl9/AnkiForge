"""Tests unitaires purs pour la dataclass MarkerOptions et la génération CLI."""

from __future__ import annotations

import os
import time
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

import pytest

from ankiforge.services.parsing.marker_service import (
    MarkerOptions,
    detect_default_device,
)

pytestmark = pytest.mark.unit


def test_marker_options_defaults() -> None:
    """Vérifie les valeurs par défaut saines et l'immutabilité de MarkerOptions."""
    opts = MarkerOptions()

    assert opts.page_range is None
    assert opts.force_ocr is False
    assert opts.disable_ocr is False
    assert opts.strip_existing_ocr is False
    assert opts.disable_ocr_math is False
    assert opts.extract_images is True
    assert opts.filter_blank_pages is False
    assert opts.highres_image_dpi == 192
    assert opts.lowres_image_dpi == 96
    assert opts.pdftext_workers == 1
    assert opts.debug is False
    assert opts.device is None
    assert opts.extra_cli_args == []

    # Vérification de l'immutabilité (frozen=True)
    field_name = "force_ocr"
    with pytest.raises(FrozenInstanceError):
        setattr(opts, field_name, True)


def test_to_cli_args_invariants() -> None:
    """Garantit que --output_dir et --paginate_output sont systématiquement injectés."""
    opts = MarkerOptions()
    output_dir = Path("/tmp/ankiforge_test_out")
    args = opts.to_cli_args(output_dir)

    assert "--output_dir" in args
    idx_out = args.index("--output_dir")
    assert args[idx_out + 1] == str(output_dir)
    assert "--paginate_output" in args
    assert "--extract_images" in args
    assert "--use_llm" not in args


def test_to_cli_args_custom_options() -> None:
    """Vérifie la sérialisation CLI de l'ensemble des options de conversion."""
    opts = MarkerOptions(
        page_range="0-5",
        force_ocr=True,
        strip_existing_ocr=True,
        disable_ocr_math=True,
        filter_blank_pages=True,
        highres_image_dpi=300,
        lowres_image_dpi=150,
        pdftext_workers=4,
        debug=True,
    )
    args = opts.to_cli_args(Path("/tmp/out"))

    assert "--page_range" in args
    assert args[args.index("--page_range") + 1] == "0-5"
    assert "--force_ocr" in args
    assert "--strip_existing_ocr" in args
    assert "--disable_ocr_math" in args
    assert "--filter_blank_pages" in args
    assert "--highres_image_dpi" in args
    assert args[args.index("--highres_image_dpi") + 1] == "300"
    assert "--lowres_image_dpi" in args
    assert args[args.index("--lowres_image_dpi") + 1] == "150"
    assert "--pdftext_workers" in args
    assert args[args.index("--pdftext_workers") + 1] == "4"
    assert "--debug" in args


def test_to_cli_args_disable_ocr_and_no_images() -> None:
    """Vérifie la modulation de l'OCR et l'exclusion de l'extraction d'images."""
    opts = MarkerOptions(
        disable_ocr=True,
        extract_images=False,
    )
    args = opts.to_cli_args(Path("/tmp/out"))

    assert "--disable_ocr" in args
    assert "--force_ocr" not in args
    assert "--extract_images" not in args


def test_to_cli_args_extra_args() -> None:
    """Vérifie l'injection d'arguments CLI complémentaires autorisés."""
    opts = MarkerOptions(extra_cli_args=["--languages", "fr,en"])
    args = opts.to_cli_args(Path("/tmp/out"))

    assert "--languages" in args
    assert "fr,en" in args


def test_rejects_use_llm() -> None:
    """Interdit formellement l'utilisation du flag --use_llm."""
    with pytest.raises(ValueError, match="--use_llm"):
        MarkerOptions(extra_cli_args=["--use_llm"])

    with pytest.raises(ValueError, match="--use_llm"):
        MarkerOptions(extra_cli_args=["--use_llm=true"])


def test_detect_default_device_torch_cuda() -> None:
    """Valide la détection prioritaire de CUDA lorsque PyTorch le rapporte disponible."""
    with patch("ankiforge.services.parsing.marker_service._detect_torch_device", return_value="cuda"):
        assert detect_default_device() == "cuda"
        assert MarkerOptions.detect_default_device() == "cuda"


def test_detect_default_device_torch_mps() -> None:
    """Valide la détection de MPS lorsque PyTorch le rapporte disponible."""
    with patch("ankiforge.services.parsing.marker_service._detect_torch_device", return_value="mps"):
        assert detect_default_device() == "mps"
        assert MarkerOptions.detect_default_device() == "mps"


def test_detect_default_device_macos_arm64() -> None:
    """Valide la détection automatique de 'mps' sur macOS Apple Silicon en absence de torch hôte."""
    with (
        patch("ankiforge.services.parsing.marker_service._detect_torch_device", return_value=None),
        patch("ankiforge.services.parsing.marker_service.platform.system", return_value="Darwin"),
        patch("ankiforge.services.parsing.marker_service.platform.machine", return_value="arm64"),
    ):
        assert detect_default_device() == "mps"
        assert MarkerOptions.detect_default_device() == "mps"


def test_detect_default_device_nvidia_cuda() -> None:
    """Valide la détection de 'cuda' sur machine avec GPU Nvidia via nvidia-smi en absence de torch hôte."""
    with (
        patch("ankiforge.services.parsing.marker_service._detect_torch_device", return_value=None),
        patch("ankiforge.services.parsing.marker_service.platform.system", return_value="Linux"),
        patch("ankiforge.services.parsing.marker_service.platform.machine", return_value="x86_64"),
        patch("ankiforge.services.parsing.marker_service.shutil.which", return_value="/usr/bin/nvidia-smi"),
    ):
        assert detect_default_device() == "cuda"


def test_detect_default_device_fallback_cpu() -> None:
    """Valide le repli transparent sur 'cpu' en l'absence d'accélérateur matériel."""
    with (
        patch("ankiforge.services.parsing.marker_service._detect_torch_device", return_value=None),
        patch("ankiforge.services.parsing.marker_service.platform.system", return_value="Linux"),
        patch("ankiforge.services.parsing.marker_service.platform.machine", return_value="x86_64"),
        patch("ankiforge.services.parsing.marker_service.shutil.which", return_value=None),
    ):
        assert detect_default_device() == "cpu"


def test_get_process_env_explicit_device() -> None:
    """Vérifie l'injection de TORCH_DEVICE avec un device explicite."""
    opts = MarkerOptions(device="cuda")
    env = opts.get_process_env(base_env={"CUSTOM_KEY": "val"})

    assert env["TORCH_DEVICE"] == "cuda"
    assert env["CUSTOM_KEY"] == "val"


def test_get_process_env_auto_device() -> None:
    """Vérifie l'injection automatique de TORCH_DEVICE quand device est None."""
    opts = MarkerOptions(device=None)
    with patch.object(MarkerOptions, "detect_default_device", return_value="mps"):
        env = opts.get_process_env(base_env={})
        assert env["TORCH_DEVICE"] == "mps"


def test_from_env_parsing() -> None:
    """Vérifie la désérialisation complète depuis les variables ANKIFORGE_MARKER_*."""
    test_env = {
        "ANKIFORGE_MARKER_PAGE_RANGE": "1-10",
        "ANKIFORGE_MARKER_FORCE_OCR": "true",
        "ANKIFORGE_MARKER_DISABLE_OCR": "0",
        "ANKIFORGE_MARKER_STRIP_EXISTING_OCR": "1",
        "ANKIFORGE_MARKER_DISABLE_OCR_MATH": "yes",
        "ANKIFORGE_MARKER_EXTRACT_IMAGES": "false",
        "ANKIFORGE_MARKER_FILTER_BLANK_PAGES": "true",
        "ANKIFORGE_MARKER_HIGHRES_IMAGE_DPI": "300",
        "ANKIFORGE_MARKER_LOWRES_IMAGE_DPI": "150",
        "ANKIFORGE_MARKER_PDFTEXT_WORKERS": "2",
        "ANKIFORGE_MARKER_DEBUG": "1",
        "ANKIFORGE_MARKER_DEVICE": "mps",
    }
    opts = MarkerOptions.from_env(env=test_env)

    assert opts.page_range == "1-10"
    assert opts.force_ocr is True
    assert opts.disable_ocr is False
    assert opts.strip_existing_ocr is True
    assert opts.disable_ocr_math is True
    assert opts.extract_images is False
    assert opts.filter_blank_pages is True
    assert opts.highres_image_dpi == 300
    assert opts.lowres_image_dpi == 150
    assert opts.pdftext_workers == 2
    assert opts.debug is True
    assert opts.device == "mps"


def test_from_env_defaults_when_empty() -> None:
    """Vérifie que from_env() avec un environnement vide restitue les valeurs par défaut."""
    opts = MarkerOptions.from_env(env={})
    default_opts = MarkerOptions()
    assert opts == default_opts


def test_from_env_reads_os_environ() -> None:
    """Vérifie la lecture transparente de os.environ lorsque l'argument env est None."""
    with patch.dict(os.environ, {"ANKIFORGE_MARKER_PAGE_RANGE": "5-15"}):
        opts = MarkerOptions.from_env()
        assert opts.page_range == "5-15"


def test_marker_options_fast_execution() -> None:
    """Garantit l'absence de régression de performance (< 50 ms pour 100 instanciations/générations)."""
    start = time.perf_counter()
    out = Path("/tmp")
    for _ in range(100):
        opts = MarkerOptions(page_range="1-2", force_ocr=True, device="cpu")
        _ = opts.to_cli_args(out)
        _ = opts.get_process_env(base_env={})
    duration = time.perf_counter() - start
    assert duration < 0.05, f"Exécution trop lente : {duration:.4f}s >= 0.05s"
