#!/bin/bash
set -euo pipefail

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="$REPO_ROOT/.venv/bin/python3"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Missing .venv. Run: python3 -m venv .venv" >&2
  exit 2
fi

if ! "$PYTHON_BIN" -c 'import pytest, pytest_cov' >/dev/null 2>&1; then
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
  tests/job_lifecycle \
  --cov=sfboard/jobs \
  --cov-report=term-missing \
  --cov-fail-under=80

"$PYTHON_BIN" -m py_compile \
  sfboard/hangdoi.py \
  sfboard/sfboard.py \
  sfboard/jobs/__init__.py \
  sfboard/jobs/models.py \
  sfboard/jobs/errors.py

echo "Job lifecycle gate: PASS"
