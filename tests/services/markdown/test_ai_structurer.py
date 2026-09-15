"""Tests unitaires pour AIDocumentStructurer."""

from typing import Any

from ankiforge.services.ai.base import LLMProvider
from ankiforge.services.markdown.ai_structurer import (
    AIDocumentStructurer,
    StructuringOptions,
    StructuringProfile,
)


class DummyStructuringProvider(LLMProvider):
    """Fournisseur de test déterministe pour la structuration IA."""

    def __init__(self, output_text: str = "") -> None:
        self.output_text = output_text or (
            "# Introduction à la Thermodynamique\n\n"
            "**Sujet :** Principes fondamentaux • Niveau Universitaire\n\n"
            "## [00:00] Premier Principe\n\n"
            "L'énergie se conserve : \\[ \\Delta U = Q - W \\]\n\n"
            "## 📌 Points Clés à Retenir\n\n"
            "- L'énergie ne disparaît jamais."
        )

    def generate(
        self,
        system_prompt: str,
        user_prompt: str | list[dict[str, Any]],
        response_format: str = "json",
        max_tokens: int | None = None,
    ) -> str:
        return self.output_text


def test_build_system_prompt_profiles() -> None:
    opt_didactic = StructuringOptions(profile=StructuringProfile.DIDACTIC)
    p1 = AIDocumentStructurer.build_system_prompt(opt_didactic)
    assert "SYNTHÈSE DIDACTIQUE" in p1
    assert "KaTeX" in p1
    assert "📌 Points Clés à Retenir" in p1

    opt_verbatim = StructuringOptions(profile=StructuringProfile.POLISHED_VERBATIM)
    p2 = AIDocumentStructurer.build_system_prompt(opt_verbatim)
    assert "RETRANSCRIPTION POLIE" in p2

    opt_summary = StructuringOptions(profile=StructuringProfile.EXECUTIVE_SUMMARY)
    p3 = AIDocumentStructurer.build_system_prompt(opt_summary)
    assert "FICHE DE SYNTHÈSE" in p3


def test_structure_document_single_pass_with_katex() -> None:
    provider = DummyStructuringProvider()
    opts = StructuringOptions(profile=StructuringProfile.DIDACTIC, normalize_katex=True)

    progress_events: list[tuple[str, float]] = []

    def on_progress(msg: str, val: float) -> None:
        progress_events.append((msg, val))

    raw_input = "bonjour aujourd'hui nous parlons d'énergie et de thermodynamique."
    res = AIDocumentStructurer.structure_document(
        content=raw_input,
        options=opts,
        ai_provider=provider,
        progress_callback=on_progress,
    )

    assert "# Introduction à la Thermodynamique" in res
    assert "## [00:00] Premier Principe" in res
    # Vérifie que la formule LaTeX \\[ ... \\] a été automatiquement normalisée en $$ par le post-processeur
    assert "$$\n\\Delta U = Q - W\n$$" in res
    assert "## 📌 Points Clés à Retenir" in res
    assert len(progress_events) >= 2


def test_structure_document_empty_input() -> None:
    res = AIDocumentStructurer.structure_document("")
    assert res == ""
