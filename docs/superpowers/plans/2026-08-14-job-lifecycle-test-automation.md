# Job Lifecycle Test Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tạo một lệnh local và một GitHub Actions workflow tự động chạy regression tests, coverage và compile gate cho lifecycle job ảnh/video mà không đổi production behavior.

**Architecture:** `pytest` tiếp tục chạy nguyên trạng 35 test `unittest` hiện có; `pytest-cov` chỉ đo package domain thuần `sfboard/jobs` với ngưỡng 80%. Script local và CI dùng cùng pytest/compile arguments, nhưng CI dùng Python của matrix còn script local dùng `.venv` của repo.

**Tech Stack:** Python 3.10/3.14, pytest 9.1.1, pytest-cov 7.1.0, coverage.py, Bash, GitHub Actions.

## Global Constraints

- Không sửa file production, lifecycle behavior hoặc năm known ambiguity.
- Không rewrite 35 test `unittest.TestCase` sang pytest style.
- Chỉ cài `pytest==9.1.1` và `pytest-cov==7.1.0`; không cài Hypothesis hoặc Sentry ở phase này.
- Coverage chỉ đo `sfboard/jobs` và bắt buộc `--cov-fail-under=80`.
- Baseline bắt buộc: 35 tests, 30 pass và đúng 5 xfailed/expected failures.
- Không chạy Chrome, provider, live integration, network request hoặc tác vụ có thể tiêu credit.
- CI chạy trên Python `3.10` và `3.14`, chỉ có quyền `contents: read`, không dùng secrets.
- Không push GitHub trong kế hoạch này.
- Mỗi commit trong repo này dùng message `update` theo quy ước hiện tại.

---

## File Map

- Create `requirements-test.txt`: pin duy nhất hai dependency test dùng chung cho local và CI.
- Create `pytest.ini`: giới hạn discovery mặc định vào `tests/job_lifecycle` và bật strict configuration.
- Create `test-job-lifecycle.command`: cổng local duy nhất cho pytest, coverage và compile.
- Create `.github/workflows/job-lifecycle-tests.yml`: chạy cùng gate trên pull request, push phù hợp và manual dispatch.
- Modify `docs/JOB-LIFECYCLE-README.md`: chỉ dẫn cài dependency, chạy gate và diễn giải baseline.
- Do not modify `.gitignore`: coverage data được chuyển vào thư mục tạm rồi dọn an toàn, nên không phát sinh artifact trong repo.

### Task 1: Pin test dependencies and configure pytest discovery

**Files:**
- Create: `requirements-test.txt`
- Create: `pytest.ini`

**Interfaces:**
- Consumes: 35 test `unittest` hiện có trong `tests/job_lifecycle/test_*.py`.
- Produces: môi trường test có `pytest==9.1.1`, `pytest-cov==7.1.0`; `python -m pytest` mặc định chỉ discover `tests/job_lifecycle`.

- [ ] **Step 1: Tạo virtual environment riêng trong worktree**

Run:

```bash
python3 -m venv .venv
```

Expected: `.venv/bin/python3` tồn tại và executable; `.venv/` vẫn bị Git ignore.

- [ ] **Step 2: Chứng minh pytest chưa phải dependency của worktree**

Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle -q
```

Expected: FAIL với `No module named pytest`. Nếu pytest đã có sẵn, ghi lại output/version rồi tiếp tục; không xóa package ngoài worktree.

- [ ] **Step 3: Tạo dependency manifest chính xác**

Create `requirements-test.txt`:

```text
pytest==9.1.1
pytest-cov==7.1.0
```

- [ ] **Step 4: Tạo pytest configuration giới hạn phạm vi**

Create `pytest.ini`:

```ini
[pytest]
testpaths = tests/job_lifecycle
python_files = test_*.py
pythonpath = tests/job_lifecycle
addopts = -ra --strict-config --strict-markers
```

`pythonpath` bảo toàn cách các characterization test hiện tại import top-level
`helpers`, giống `unittest discover -s tests/job_lifecycle`, mà không rewrite test.
Coverage không nằm trong `addopts`; targeted test không bị ép đo toàn package.

- [ ] **Step 5: Cài đúng dependency đã pin**

Run:

```bash
./.venv/bin/python3 -m pip install -r requirements-test.txt
```

Expected: cài thành công pytest 9.1.1 và pytest-cov 7.1.0 trong `.venv` của worktree.

- [ ] **Step 6: Xác minh version và dependency bị deferred**

Run:

```bash
./.venv/bin/python3 - <<'PY'
from importlib.metadata import version
from importlib.util import find_spec

assert version("pytest") == "9.1.1"
assert version("pytest-cov") == "7.1.0"
assert find_spec("hypothesis") is None
assert find_spec("sentry_sdk") is None
print("test dependencies: OK")
PY
```

Expected: `test dependencies: OK`.

- [ ] **Step 7: Chạy nguyên trạng suite cũ dưới pytest**

Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle -q -ra
```

Expected: exit 0; `30 passed, 5 xfailed`; không có fail/error/xpass mới.

- [ ] **Step 8: Commit dependency/config deliverable**

```bash
git add requirements-test.txt pytest.ini
git commit -m "update"
```

### Task 2: Build the one-command local lifecycle gate

**Files:**
- Create: `test-job-lifecycle.command`
- Modify: `docs/JOB-LIFECYCLE-README.md` (section `## Verification`)

**Interfaces:**
- Consumes: `.venv/bin/python3`, `requirements-test.txt`, `pytest.ini`, `tests/job_lifecycle`, `sfboard/jobs`.
- Produces: executable `./test-job-lifecycle.command` returning 0 only when tests, 80% coverage and all compile targets pass.

- [ ] **Step 1: Viết executable-contract check và xác nhận nó fail**

Run:

```bash
test -x test-job-lifecycle.command
```

Expected: exit 1 vì command chưa tồn tại.

- [ ] **Step 2: Tạo local gate với coverage file nằm ngoài repo**

Create `test-job-lifecycle.command`:

```bash
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
```

`mktemp -d` tạo đúng một thư mục riêng; trap chỉ xóa chính đường dẫn đó sau khi gate kết thúc.

- [ ] **Step 3: Đặt executable bit và xác minh contract**

Run:

```bash
chmod +x test-job-lifecycle.command
test -x test-job-lifecycle.command
```

Expected: exit 0.

- [ ] **Step 4: Thay section Verification trong AI entrypoint**

Replace section `## Verification` trong `docs/JOB-LIFECYCLE-README.md` bằng:

````markdown
## Verification

Cài dependency test một lần cho worktree:

```bash
./.venv/bin/python3 -m pip install -r requirements-test.txt
```

Sau mỗi thay đổi lifecycle, chạy gate chuẩn:

```bash
./test-job-lifecycle.command
```

Gate này chạy toàn bộ lifecycle tests, yêu cầu coverage `sfboard/jobs` tối thiểu
80%, rồi compile legacy runtime và domain package. Nó không mở browser, gọi provider
hoặc tiêu credit.

Kết quả Phase 0–1 hiện tại: 35 tests, 30 pass và đúng 5 `xfailed`. Một expected
failure biến thành unexpected success cũng phải được giải thích: chỉ bỏ decorator ở
phase sửa lỗi tương ứng và sau khi đã xác minh target behavior. Không được thêm
expected failure mới chỉ để làm gate xanh.
````

- [ ] **Step 5: Chạy local gate từ repo root**

Run:

```bash
./test-job-lifecycle.command
```

Expected: exit 0; `30 passed, 5 xfailed`; coverage `sfboard/jobs` ít nhất 80%; cuối output có `Job lifecycle gate: PASS`.

Nếu coverage thấp hơn 80%, dừng task và báo số đo/file thiếu coverage; không hạ threshold, không thêm `# pragma: no cover`, không viết assertion giả.

- [ ] **Step 6: Chứng minh command không phụ thuộc current directory**

Run:

```bash
(cd /tmp && /Users/may1/.codex/worktrees/grokpipe/job-lifecycle-phase-0-1/test-job-lifecycle.command)
```

Expected: cùng kết quả pass như Step 5.

- [ ] **Step 7: Xác minh gate không để lại coverage artifact**

Run:

```bash
test ! -e .coverage
test ! -e coverage.xml
test ! -d htmlcov
git status --short
```

Expected: ba lệnh đầu exit 0; status chỉ có hai file của Task 2 trước khi commit.

- [ ] **Step 8: Commit local gate and documentation**

```bash
git add test-job-lifecycle.command docs/JOB-LIFECYCLE-README.md
git commit -m "update"
```

### Task 3: Add the isolated GitHub Actions gate

**Files:**
- Create: `.github/workflows/job-lifecycle-tests.yml`

**Interfaces:**
- Consumes: `requirements-test.txt`, test suite, domain package and the same pytest/compile targets as the local command.
- Produces: required-quality signal on pull requests, pushes to `main`/`codex/**`, and manual dispatch for Python 3.10 and 3.14.

- [ ] **Step 1: Viết workflow-contract check và xác nhận nó fail**

Run:

```bash
test -f .github/workflows/job-lifecycle-tests.yml
```

Expected: exit 1 vì workflow chưa tồn tại.

- [ ] **Step 2: Tạo workflow không có secret hoặc live integration**

Create `.github/workflows/job-lifecycle-tests.yml`:

```yaml
name: Job lifecycle tests

on:
  pull_request:
  push:
    branches:
      - main
      - "codex/**"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version:
          - "3.10"
          - "3.14"
    steps:
      - name: Check out source
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: requirements-test.txt

      - name: Install test dependencies
        run: python -m pip install -r requirements-test.txt

      - name: Run lifecycle tests and coverage
        env:
          COVERAGE_FILE: ${{ runner.temp }}/job-lifecycle-${{ matrix.python-version }}.coverage
        run: >-
          python -m pytest tests/job_lifecycle
          --cov=sfboard/jobs
          --cov-report=term-missing
          --cov-fail-under=80

      - name: Compile legacy and domain modules
        run: >-
          python -m py_compile
          sfboard/hangdoi.py
          sfboard/sfboard.py
          sfboard/jobs/__init__.py
          sfboard/jobs/models.py
          sfboard/jobs/errors.py
```

- [ ] **Step 3: Parse workflow YAML**

Run:

```bash
ruby -e 'require "yaml"; YAML.parse_file(ARGV.fetch(0)); puts "workflow yaml: OK"' .github/workflows/job-lifecycle-tests.yml
```

Expected: `workflow yaml: OK`.

- [ ] **Step 4: Kiểm tra security/scope contract bằng nội dung workflow**

Run:

```bash
grep -F 'contents: read' .github/workflows/job-lifecycle-tests.yml
grep -F -- '--cov-fail-under=80' .github/workflows/job-lifecycle-tests.yml
grep -F '"3.10"' .github/workflows/job-lifecycle-tests.yml
grep -F '"3.14"' .github/workflows/job-lifecycle-tests.yml
! grep -Eiq 'secrets|sentry|dsn|playwright|selenium|chrome|curl|wget|provider' .github/workflows/job-lifecycle-tests.yml
```

Expected: bốn contract dương được in ra và negative scan exit 0.

- [ ] **Step 5: So sánh exact gate arguments giữa local và CI**

Run:

```bash
grep -F -- '--cov=sfboard/jobs' test-job-lifecycle.command .github/workflows/job-lifecycle-tests.yml
grep -F -- '--cov-report=term-missing' test-job-lifecycle.command .github/workflows/job-lifecycle-tests.yml
grep -F -- '--cov-fail-under=80' test-job-lifecycle.command .github/workflows/job-lifecycle-tests.yml
grep -F 'sfboard/jobs/errors.py' test-job-lifecycle.command .github/workflows/job-lifecycle-tests.yml
```

Expected: mỗi contract xuất hiện ở cả hai file.

- [ ] **Step 6: Commit CI deliverable**

```bash
git add .github/workflows/job-lifecycle-tests.yml
git commit -m "update"
```

### Task 4: Run the complete verification and scope audit

**Files:**
- Verify only; no new production file.

**Interfaces:**
- Consumes: toàn bộ deliverables của Tasks 1–3.
- Produces: evidence rằng local gate pass, legacy runner vẫn pass, YAML hợp lệ và diff không chạm production.

- [ ] **Step 1: Chạy canonical local gate lần cuối**

Run:

```bash
./test-job-lifecycle.command
```

Expected: exit 0; `30 passed, 5 xfailed`; coverage ít nhất 80%; `Job lifecycle gate: PASS`.

- [ ] **Step 2: Chạy legacy unittest runner để chứng minh compatibility**

Run:

```bash
./.venv/bin/python3 -m unittest discover -s tests/job_lifecycle -p 'test_*.py'
```

Expected: exit 0; `Ran 35 tests`; `OK (expected failures=5)`.

- [ ] **Step 3: Xác minh dependency và compile độc lập**

Run:

```bash
./.venv/bin/python3 -m pip check
./.venv/bin/python3 -m py_compile \
  sfboard/hangdoi.py sfboard/sfboard.py \
  sfboard/jobs/__init__.py sfboard/jobs/models.py sfboard/jobs/errors.py
```

Expected: `No broken requirements found.` và compile exit 0.

- [ ] **Step 4: Audit exact changed-file scope kể từ approved spec**

Run:

```bash
git diff --name-only 403adc8..HEAD
git status --short
```

Expected tracked implementation files chỉ gồm:

```text
.github/workflows/job-lifecycle-tests.yml
docs/JOB-LIFECYCLE-README.md
docs/superpowers/plans/2026-08-14-job-lifecycle-test-automation.md
docs/superpowers/specs/2026-08-14-job-lifecycle-test-automation-design.md
pytest.ini
requirements-test.txt
test-job-lifecycle.command
```

`git status --short` phải sạch. Không được có thay đổi trong `sfboard/`, `tests/job_lifecycle/`, runtime requirements hoặc `.gitignore`.

- [ ] **Step 5: Ghi kết quả handoff**

Trong final response, báo chính xác:

- branch và worktree đã triển khai;
- output test/coverage/compile vừa chạy;
- năm xfailed vẫn là known ambiguity, chưa được sửa;
- Hypothesis và Sentry vẫn deferred, không được cài;
- workflow mới chỉ tồn tại local và chưa push, nên GitHub Actions chưa chạy trên GitHub.
