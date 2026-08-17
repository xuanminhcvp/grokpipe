#!/bin/bash
set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing .venv. Run: python3 -m venv .venv" >&2
  exit 2
fi

if ! "$PYTHON_BIN" -c 'import pytest, pytest_cov, hypothesis, loguru' >/dev/null 2>&1; then
  echo "Missing test dependencies. Run: ./.venv/bin/python3 -m pip install -r requirements-test.txt" >&2
  exit 2
fi

COVERAGE_TMP="$(mktemp -d "${TMPDIR:-/tmp}/grokpipe-job-lifecycle-cov.XXXXXX")"
cleanup() {
  rm -r -- "$COVERAGE_TMP"
}
trap cleanup EXIT

cd "$REPO_ROOT"
export COVERAGE_FILE="$COVERAGE_TMP/.coverage"

# Đo CẢ `sfboard` trong một lượt chạy, rồi ra hai báo cáo với hai sàn khác nhau.
# Trước 2026-08-17 gate chỉ đo `sfboard.jobs`, nên `sfboard.py` (3.998 statement)
# và các executor nằm ngoài mọi con số — hai bug "Chạy hết không chạy" và
# "Dọn lỗi không dọn được" đều sống trong đúng vùng không ai đo đó.
"$PYTHON_BIN" -m pytest \
  tests/job_lifecycle tests/runtime_bugs tests/executors \
  --cov=sfboard \
  --cov-report=

echo
echo "── Authority lifecycle (sàn 80%) ──"
"$PYTHON_BIN" -m coverage report \
  --include='sfboard/jobs/*' --show-missing --fail-under=80

echo
echo "── Toàn bộ sfboard, gồm sfboard.py và executor (sàn chống tụt 58%) ──"
# SÀN CHỐNG TỤT, không phải mục tiêu. Chỉ được nâng lên, không được hạ xuống:
# hạ sàn để test qua là bỏ đúng cái lưới vừa dựng. Mỗi lần thêm test cho
# `sfboard.py`, nâng số này lên sát mức mới.
"$PYTHON_BIN" -m coverage report --include='sfboard/*' --fail-under=58

"$PYTHON_BIN" -m py_compile \
  sfboard/hangdoi.py \
  sfboard/sfboard.py \
  sfboard/jobs/__init__.py \
  sfboard/jobs/models.py \
  sfboard/jobs/errors.py \
  sfboard/jobs/runtime_bug.py \
  sfboard/jobs/runtime_redaction.py \
  sfboard/jobs/runtime_fingerprint.py \
  sfboard/jobs/runtime_classifier.py \
  sfboard/jobs/runtime_journal.py \
  sfboard/jobs/runtime_sentry.py \
  sfboard/jobs/beads_bridge.py \
  sfboard/jobs/bugtool.py \
  sfboard/jobs/runtime_service.py \
  sfboard/jobs/store.py \
  sfboard/jobs/manager.py \
  sfboard/jobs/projection.py \
  sfboard/jobs/producer.py \
  sfboard/jobs/compat.py \
  sfboard/jobs/scheduler.py \
  sfboard/jobs/accounts.py \
  sfboard/jobs/retry.py \
  sfboard/jobs/results.py \
  sfboard/jobs/monitor.py \
  sfboard/jobs/persistence.py \
  sfboard/jobs/sqlite_store.py \
  sfboard/jobs/facts.py \
  sfboard/jobs/runtime.py \
  sfboard/jobs/executor_adapter.py \
  sfboard/jobs/live_budget.py \
  sfboard/live_executor.py \
  sfboard/chay-anh.py

echo "Job lifecycle gate: PASS"
echo "  (hai sàn: sfboard/jobs ≥ 80% và toàn sfboard ≥ 58% — sàn thứ hai chỉ nâng)"
