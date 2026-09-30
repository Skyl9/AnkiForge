"""Tests du worker d'import documentaire par lot (résilience, annulation, séquencement)."""

from unittest.mock import patch

from ankiforge.services.workers.document_batch_worker import (
    DocumentBatchTask,
    DocumentBatchWorker,
    plan_batch_tasks,
)
from ankiforge.services.workers.document_worker import derive_document_title

PARSER_PATH = "ankiforge.services.workers.document_batch_worker.DocumentParser"


class _FakeParser:
    """Faux parseur : renvoie un contenu déterministe ou lève pour les sources « cassées »."""

    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.failures = failures or {}
        self.calls: list[str] = []

    def parse_document(self, source, progress_callback=None, check_cancel=None):
        self.calls.append(source)
        if progress_callback is not None:
            progress_callback(f"Parsing de {source}")
        error = self.failures.get(source)
        if error is not None:
            raise error
        return f"Contenu de {source}"


# ── derive_document_title ────────────────────────────────────────────────────


def test_derive_document_title_uses_file_stem_truncated() -> None:
    assert derive_document_title("/tmp/mes/notes de cours.md") == "notes de cours"
    assert derive_document_title(f"/tmp/{'a' * 120}.md") == "a" * 50


def test_derive_document_title_handles_urls() -> None:
    assert derive_document_title("https://exemple.fr/ma/page") == "Web - page"
    assert derive_document_title("https://exemple.fr/") == "Web - exemple.fr"


# ── plan_batch_tasks ────────────────────────────────────────────────────────


def test_plan_batch_tasks_dedupes_and_keeps_order(tmp_path) -> None:
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("a", encoding="utf-8")
    b.write_text("b", encoding="utf-8")

    plan = plan_batch_tasks([str(a), str(b), str(a), "  "])

    assert [t.path for t in plan.tasks] == [str(a), str(b)]
    assert [t.index for t in plan.tasks] == [0, 1]
    assert plan.skipped == []


def test_plan_batch_tasks_reports_only_genuinely_missing_paths(tmp_path) -> None:
    """Un doublon n'est pas un fichier introuvable : seuls les chemins absents sont signalés."""
    a = tmp_path / "a.md"
    a.write_text("a", encoding="utf-8")

    plan = plan_batch_tasks([str(a), str(a), str(tmp_path / "absent.md")])

    assert [t.path for t in plan.tasks] == [str(a)]
    assert plan.skipped == [str(tmp_path / "absent.md")]


def test_plan_batch_tasks_rejects_directories(tmp_path) -> None:
    plan = plan_batch_tasks([str(tmp_path)])
    assert plan.tasks == []
    assert plan.skipped == [str(tmp_path)]


# ── DocumentBatchWorker ─────────────────────────────────────────────────────


def test_batch_worker_emits_started_finished_for_every_task() -> None:
    tasks = [DocumentBatchTask(index=0, path="/tmp/a.md"), DocumentBatchTask(index=1, path="/tmp/b.md")]
    worker = DocumentBatchWorker(tasks)

    started: list[tuple[int, str]] = []
    finished: list[tuple[int, str, str, str]] = []
    worker.document_started.connect(lambda i, p: started.append((i, p)))
    worker.document_finished.connect(lambda i, p, t, c: finished.append((i, p, t, c)))

    with patch(PARSER_PATH, return_value=_FakeParser()):
        worker.run()

    assert started == [(0, "/tmp/a.md"), (1, "/tmp/b.md")]
    assert [f[1] for f in finished] == ["/tmp/a.md", "/tmp/b.md"]
    assert [f[2] for f in finished] == ["a", "b"]


def test_batch_worker_continues_after_a_failed_document() -> None:
    tasks = [DocumentBatchTask(index=0, path="/tmp/ok.md"), DocumentBatchTask(index=1, path="/tmp/ko.md"), DocumentBatchTask(index=2, path="/tmp/ok2.md")]
    worker = DocumentBatchWorker(tasks)

    finished: list[tuple[int, str, str, str]] = []
    failed: list[tuple[int, str, str]] = []
    worker.document_finished.connect(lambda i, p, t, c: finished.append((i, p, t, c)))
    worker.document_failed.connect(lambda i, p, e: failed.append((i, p, e)))

    parser = _FakeParser({"/tmp/ko.md": ValueError("Format de fichier non supporté : .ko")})
    with patch(PARSER_PATH, return_value=parser):
        worker.run()

    assert parser.calls == ["/tmp/ok.md", "/tmp/ko.md", "/tmp/ok2.md"]
    assert [f[1] for f in finished] == ["/tmp/ok.md", "/tmp/ok2.md"]
    assert finished[0][2] == "ok"
    assert failed == [(1, "/tmp/ko.md", "Format de fichier non supporté : .ko")]


def test_batch_worker_reports_success_and_failure_counts(qtbot) -> None:
    tasks = [DocumentBatchTask(index=0, path="/tmp/ok.md"), DocumentBatchTask(index=1, path="/tmp/ko.md")]
    worker = DocumentBatchWorker(tasks)
    summaries: list[tuple[int, int]] = []
    worker.batch_finished.connect(lambda ok, ko: summaries.append((ok, ko)))

    with patch(PARSER_PATH, return_value=_FakeParser({"/tmp/ko.md": RuntimeError("boom")})):
        worker.run()

    assert summaries == [(1, 1)]


def test_batch_worker_stops_the_queue_on_cancellation() -> None:
    tasks = [DocumentBatchTask(index=0, path="/tmp/a.md"), DocumentBatchTask(index=1, path="/tmp/b.md")]
    worker = DocumentBatchWorker(tasks)
    worker.cancel()

    parser = _FakeParser()
    cancelled: list[int] = []
    summaries: list[tuple[int, int]] = []
    worker.cancelled.connect(lambda: cancelled.append(1))
    worker.batch_finished.connect(lambda ok, ko: summaries.append((ok, ko)))

    with patch(PARSER_PATH, return_value=parser):
        worker.run()

    assert parser.calls == []
    assert cancelled == [1]
    assert summaries == [(0, 0)]


def test_batch_worker_cancellation_inside_a_task_stops_the_queue() -> None:
    tasks = [DocumentBatchTask(index=0, path="/tmp/a.md"), DocumentBatchTask(index=1, path="/tmp/b.md")]
    worker = DocumentBatchWorker(tasks)

    class _CancellingParser(_FakeParser):
        def parse_document(self, source, progress_callback=None, check_cancel=None):
            self.calls.append(source)
            worker.cancel()
            raise InterruptedError("Annulation utilisateur")

    parser = _CancellingParser()
    finished: list[str] = []
    worker.document_finished.connect(lambda i, p, t, c: finished.append(p))

    with patch(PARSER_PATH, return_value=parser):
        worker.run()

    assert parser.calls == ["/tmp/a.md"]
    assert finished == []


def test_batch_worker_runs_in_a_thread_and_awaits_finished(qtbot) -> None:
    tasks = [DocumentBatchTask(index=0, path="/tmp/a.md")]
    worker = DocumentBatchWorker(tasks)

    with patch(PARSER_PATH, return_value=_FakeParser()), qtbot.waitSignal(worker.document_finished, timeout=5000) as blocker:
        worker.start()

    assert blocker.args[1] == "/tmp/a.md"
    worker.wait(2000)
    assert worker.isFinished()
