"""Ranh giới với code cũ: chỉ được thêm vỏ bọc ghi sổ, không thêm quyền lực."""

import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard" / "sfboard.py"
SOURCE = BOARD.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def function_source(name):
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(SOURCE, node) or ""
    raise AssertionError(f"không tìm thấy {name} trong sfboard.py")


def top_level_names():
    return {node.name for node in TREE.body if isinstance(node, ast.FunctionDef)}


def test_supervisor_starts_the_instrumented_entry_point():
    supervisor = function_source("_supervisor")

    assert "target=_worker_entry" in supervisor
    assert "target=_worker," not in supervisor


def test_worker_entry_only_wraps_worker_and_reports_escaping_errors():
    entry = function_source("_worker_entry")

    assert "_worker(endpoint, kind, slot)" in entry
    assert "WORKER_CRASH" in entry
    assert "raise" in entry
    assert "QUEUE" not in entry
    assert "_dat_job" not in entry
    assert "_xep_lai_sau" not in entry


def test_worker_keeps_its_retry_and_rotation_logic():
    worker = function_source("_worker")

    assert "_xep_lai_sau(" in worker
    assert "_xoay_chrome(" in worker
    assert worker.count("report_runtime_bug(") == 1
    assert "RETRY_EXHAUSTED" in worker


def test_retry_exhaustion_reports_after_the_existing_state_write():
    worker = function_source("_worker")
    marker = worker.index("dừng để khỏi đốt credit")
    log_line = worker.index('_LOG.warning("video %s dừng sau', marker)
    report = worker.index("report_runtime_bug(", log_line)

    assert marker < log_line < report


def test_no_new_worker_queue_or_state_writer_is_introduced():
    names = top_level_names()

    assert {name for name in names if name.startswith("_worker")} == {"_worker", "_worker_entry"}
    assert SOURCE.count("def _xep_lai_sau(") == 1
    assert SOURCE.count("def _enqueue(") == 1
    assert "def _dat_job(" not in SOURCE
    assert "_HOAN = " not in SOURCE


@pytest.mark.parametrize(
    "name",
    ["report_runtime_bug", "runtime_bug_diagnostics", "start_runtime_bug_service"],
)
def test_runtime_bug_facade_import_is_defensive(name):
    assert f"def {name}(" in SOURCE  # bản dự phòng khi thiếu loguru
    assert f"{name}," in SOURCE or f"{name} " in SOURCE


def test_board_boots_and_shuts_down_the_service_exactly_once():
    main = function_source("main")

    assert main.count("start_runtime_bug_service(REPO_ROOT") == 1
    assert main.count("atexit.register(stop_runtime_bug_service)") == 1


def test_diagnostics_endpoint_exposes_only_the_bug_bridge_projection():
    assert SOURCE.count('"bug_bridge": runtime_bug_diagnostics()["bug_bridge"]') == 1
    assert "BeadsBridge" not in SOURCE
    assert "subprocess.run([\"bd\"" not in SOURCE


def test_error_book_and_root_logging_setup_are_untouched():
    assert "class _ThuLoi(logging.Handler)" in SOURCE
    assert "LOI_SO: collections.deque = collections.deque(maxlen=800)" in SOURCE
    assert "logger.remove()" not in SOURCE
