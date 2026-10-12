"""Tests unitaires du hub de suivi d'une passe de réindexation (ADR 0021).

Le service est un simple QObject de signaux : ces tests l'exercent sans base de
données, sans thread et sans interface.
"""

from __future__ import annotations

import pytest

from ankiforge.services.reindex_activity_service import ReindexActivityService

pytestmark = pytest.mark.unit


def _service() -> ReindexActivityService:
    """Instance neuve (jamais le singleton partagé) pour isoler chaque test."""
    return ReindexActivityService()


def test_begin_starts_pass_and_emits_total() -> None:
    """Une passe démarre, s'active et annonce son total de documents."""
    service = _service()
    started: list[int] = []
    service.started.connect(started.append)

    assert service.begin(3) is True

    assert service.is_active() is True
    assert started == [3]


def test_begin_refuses_concurrent_pass_and_emits_refused() -> None:
    """Un second déclenchement pendant une passe est refusé explicitement."""
    service = _service()
    assert service.begin(3) is True

    refusals: list[tuple[int, int]] = []
    service.refused.connect(lambda n, total: refusals.append((n, total)))
    service.report_document(2, 3, "Deuxième")

    assert service.begin(1) is False
    assert refusals == [(2, 3)]


def test_report_document_emits_progress() -> None:
    service = _service()
    service.begin(3)
    seen: list[tuple[int, int, str]] = []
    service.progress.connect(lambda n, total, title: seen.append((n, total, title)))

    service.report_document(2, 3, "Chapitre 2")

    assert seen == [(2, 3, "Chapitre 2")]
    assert service.current_position() == (2, 3)


def test_report_fragments_emits_micro_progress() -> None:
    service = _service()
    service.begin(1)
    seen: list[tuple[int, int]] = []
    service.fragment_progress.connect(lambda cur, total: seen.append((cur, total)))

    service.report_fragments(4, 10)

    assert seen == [(4, 10)]


def test_reports_ignored_when_no_active_pass() -> None:
    """Hors passe, les rapports sont silencieusement ignorés (pas de bandeau fantôme)."""
    service = _service()
    progress: list[tuple[int, int, str]] = []
    fragments: list[tuple[int, int]] = []
    service.progress.connect(lambda n, total, title: progress.append((n, total, title)))
    service.fragment_progress.connect(lambda cur, total: fragments.append((cur, total)))

    service.report_document(1, 1, "Titre")
    service.report_fragments(1, 1)
    service.finish(1, 1, 0)

    assert progress == []
    assert fragments == []


def test_finish_emits_recap_and_deactivates() -> None:
    service = _service()
    service.begin(2)
    recap: list[tuple[int, int, int, bool]] = []
    service.finished.connect(lambda docs, frags, errs, cancelled: recap.append((docs, frags, errs, cancelled)))

    service.finish(2, 12, 1)

    assert recap == [(2, 12, 1, False)]
    assert service.is_active() is False


def test_cancel_is_cooperative_and_reported_on_finish() -> None:
    """L'annulation arme un drapeau lu par les workers et colore le récapitulatif."""
    service = _service()
    service.begin(5)
    service.report_document(3, 5, "Troisième")

    assert service.is_cancel_requested() is False
    service.request_cancel()
    assert service.is_cancel_requested() is True

    recap: list[tuple[int, int, int, bool]] = []
    service.finished.connect(lambda docs, frags, errs, cancelled: recap.append((docs, frags, errs, cancelled)))
    service.finish(2, 6, 0)

    assert recap == [(2, 6, 0, True)]
    assert service.is_cancel_requested() is False, "Le drapeau est réarmé pour la passe suivante."


def test_get_instance_is_a_singleton() -> None:
    assert ReindexActivityService.get_instance() is ReindexActivityService.get_instance()
