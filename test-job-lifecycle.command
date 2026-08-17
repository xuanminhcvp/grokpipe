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
COVERAGE_FILE="$COVERAGE_TMP/.coverage" "$PYTHON_BIN" -m pytest \
  tests/job_lifecycle tests/runtime_bugs tests/executors \
  --cov=sfboard.jobs \
  --cov-report=term-missing \
  --cov-fail-under=80

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
echo "  (coverage ở trên CHỈ đo sfboard/jobs — không đo sfboard.py lẫn executors)"
