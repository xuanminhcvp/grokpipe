# Job Lifecycle Phase 0–1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Khóa hành vi lifecycle hiện tại bằng characterization tests và thêm domain model/error taxonomy thuần, chưa nối chúng vào production.

**Architecture:** Phase 0 chỉ quan sát `hangdoi.py` và `sfboard.py` qua test harness, fake board và source inspection; known bug được ghi bằng `expectedFailure`. Phase 1 thêm package `sfboard/jobs` chỉ chứa immutable value objects, enums và validation; package này chưa được import từ runtime hiện tại.

**Tech Stack:** Python 3.9+, `unittest`, `dataclasses`, `enum`, `uuid`, `ast`, `queue`, `tempfile`; không thêm dependency.

## Global Constraints

- Không sửa `sfboard/sfboard.py`, `sfboard/hangdoi.py`, executor hoặc UI trong Phase 0–1.
- Không mở Chrome, không gọi provider và không tiêu credit trong test.
- `JOBS`, `PriorityQueue`, retry và account hiện tại vẫn là production authority.
- Canonical Job states: `CREATED`, `QUEUED`, `RUNNING`, `RETRY_WAIT`, `COMPLETED`, `FAILED`, `CANCELLED`, `NEEDS_ATTENTION`.
- Terminal Job states: `COMPLETED`, `FAILED`, `CANCELLED`.
- Explicit rerun tạo Job mới; asset id không phải job, execution hoặc attempt id.
- Test chạy bằng stdlib: `python3 -m unittest discover -s tests/job_lifecycle -p 'test_*.py'`.
- Mỗi known bug chỉ chuyển từ `expectedFailure` thành test thường ở phase sửa đúng bug đó.

---

## File map

| File | Trách nhiệm |
|---|---|
| `tests/job_lifecycle/helpers.py` | Import cô lập, reset global, fake board/HTTP capture, lấy source function bằng AST |
| `tests/job_lifecycle/test_queue_characterization.py` | Priority/order/queue identity và `dat_job` hiện tại |
| `tests/job_lifecycle/test_current_state_writers.py` | Executable inventory cho các writer lifecycle quan trọng |
| `tests/job_lifecycle/test_cancel_characterization.py` | Cancel flags, group identity mismatch và stop generation |
| `tests/job_lifecycle/test_retry_characterization.py` | Retry timer/guard/counter authorities hiện tại |
| `tests/job_lifecycle/test_auto_characterization.py` | Auto image/video enqueue và duplicate guard |
| `tests/job_lifecycle/test_account_characterization.py` | Forced-account và worker-bound assignment hiện tại |
| `tests/job_lifecycle/test_http_contract.py` | Schema `/api/jobs` và response create/cancel hiện tại |
| `sfboard/jobs/models.py` | Typed identity, enums và immutable lifecycle facts |
| `sfboard/jobs/errors.py` | Error taxonomy và immutable `ErrorFact` |
| `tests/job_lifecycle/test_models.py` | Validation/invariant của Phase 1 |
| `tests/job_lifecycle/test_errors.py` | Error class và submitted-boundary validation |

---

### Task 1: Test harness cô lập và queue characterization

**Files:**
- Create: `tests/job_lifecycle/__init__.py`
- Create: `tests/job_lifecycle/helpers.py`
- Create: `tests/job_lifecycle/test_queue_characterization.py`
- Test: `tests/job_lifecycle/test_queue_characterization.py`

**Interfaces:**
- Consumes: `sfboard/hangdoi.py::{xep,lay,y_trong_hang,thu_tu_hang,dat_job,gan_nguon_board}`.
- Produces: `load_hangdoi()`, `load_sfboard()`, `reset_legacy_state(module)`, `function_source(path, name)` cho các task sau.

- [ ] **Step 1: Tạo package test và helper import/reset**

```python
# tests/job_lifecycle/helpers.py
from __future__ import annotations

import ast
import importlib
import importlib.util
import io
import json
import queue
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SFBOARD_DIR = ROOT / "sfboard"


def load_hangdoi():
    path = str(SFBOARD_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    return importlib.import_module("hangdoi")


def load_sfboard():
    path = str(SFBOARD_DIR)
    if path not in sys.path:
        sys.path.insert(0, path)
    module_name = "_sfboard_runtime_for_tests"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, SFBOARD_DIR / "sfboard.py")
    if spec is None or spec.loader is None:
        raise AssertionError("Không tạo được import spec cho sfboard.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def reset_legacy_state(module) -> None:
    for name in ("JOBS", "VET", "DA_HUY", "DUNG_RIENG", "TAY_SF", "_HOAN"):
        value = getattr(module, name, None)
        if value is not None:
            value.clear()
    if hasattr(module, "GEN"):
        module.GEN["dung"] = 0
    for name in ("IMG_QUEUE", "VID_QUEUE"):
        q = getattr(module, name, None)
        if q is None:
            continue
        while True:
            try:
                q.get_nowait()
                q.task_done()
            except queue.Empty:
                break


def function_source(path: Path, name: str) -> str:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"Không tìm thấy function {name} trong {path}")


class CaptureHandlerMixin:
    def prepare(self, path: str, raw: bytes = b"") -> None:
        self.path = path
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)
        self.captured = None

    def _json(self, obj, code=200):
        self.captured = (code, json.loads(json.dumps(obj, ensure_ascii=False)))
```

`tests/job_lifecycle/__init__.py` để rỗng. Không thêm logic setup toàn cục.

- [ ] **Step 2: Viết queue tests trước khi thay đổi code**

```python
# tests/job_lifecycle/test_queue_characterization.py
import queue
import unittest

from helpers import load_hangdoi, reset_legacy_state


class QueueCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)
        self.h.gan_nguon_board(lambda: {
            "scenes": [{"shots": [
                {"id": "V-S1-1", "sf": "SF-S1-1"},
                {"id": "V-S1-B1", "sf": "SF-S1-B1"},
                {"id": "V-S1-2", "sf": "SF-S1-2"},
            ]}]
        }, lambda: 1)

    def test_order_uses_board_shot_order_including_suffix(self):
        q = queue.PriorityQueue()
        self.h.xep(q, ("img", "SF-S1-2", 0, False))
        self.h.xep(q, ("img", "SF-S1-B1", 0, False))
        self.h.xep(q, ("img", "SF-S1-1", 0, False))
        self.assertEqual(
            self.h.thu_tu_hang(q),
            ["SF-S1-1", "SF-S1-B1", "SF-S1-2"],
        )

    def test_queue_identity_and_take_round_trip(self):
        q = queue.PriorityQueue()
        item = ("img", "LO:SF-S1-1,SF-S1-2", 0, True)
        self.h.xep(q, item)
        self.assertEqual(self.h.y_trong_hang(q), {item[1]})
        self.assertEqual(self.h.lay(q, timeout=0.1), item)

    def test_dat_job_spreads_group_state_to_members(self):
        state = {"state": "queued", "msg": "chờ"}
        self.h.dat_job("LO:A,B", state)
        self.assertEqual(self.h.JOBS["LO:A,B"]["state"], "queued")
        self.assertEqual(self.h.JOBS["A"]["state"], "queued")
        self.assertEqual(self.h.JOBS["B"]["state"], "queued")
        self.assertIsNot(self.h.JOBS["A"], self.h.JOBS["B"])
```

- [ ] **Step 3: Chạy test để xác nhận characterization pass**

Run: `python3 -m unittest discover -s tests/job_lifecycle -p 'test_queue_characterization.py' -v`

Expected: 3 tests `OK`; không có browser process mới.

- [ ] **Step 4: Commit test harness và queue contract**

```bash
git add tests/job_lifecycle/__init__.py tests/job_lifecycle/helpers.py tests/job_lifecycle/test_queue_characterization.py
git commit -m "test: characterize legacy job queue"
```

---

### Task 2: State-writer inventory và cancel characterization

**Files:**
- Create: `tests/job_lifecycle/test_current_state_writers.py`
- Create: `tests/job_lifecycle/test_cancel_characterization.py`
- Test: hai file trên.

**Interfaces:**
- Consumes: `function_source`, legacy globals và `hangdoi.bi_huy/bo_co_huy/tang_dung_gen`.
- Produces: inventory executable giữ cho các writer/re-enqueue authority không biến mất âm thầm trước cutover.

- [ ] **Step 1: Viết writer inventory test với danh sách đã audit**

```python
# tests/job_lifecycle/test_current_state_writers.py
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class CurrentStateWriterInventoryTest(unittest.TestCase):
    def test_legacy_authority_markers_remain_visible_until_cutover(self):
        hangdoi = (ROOT / "sfboard/hangdoi.py").read_text(encoding="utf-8")
        board = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        required = {
            "JOBS writer hook": "class _Jobs(dict)",
            "group state spread": "def dat_job(",
            "image queue": "IMG_QUEUE",
            "video queue": "VID_QUEUE",
            "retry timer": "def _xep_lai_sau(",
            "retry guard": "_HOAN",
            "cancel flags": "DA_HUY",
            "forced account queue": "CHO_RIENG",
            "stop generation": "tang_dung_gen()",
            "auto producer": "def _auto_scene(",
            "worker assignment": "def _worker(",
        }
        combined = hangdoi + "\n" + board
        missing = [label for label, marker in required.items() if marker not in combined]
        self.assertEqual(missing, [], f"Authority marker biến mất: {missing}")

    def test_every_direct_jobs_write_stays_auditable(self):
        board = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(board.count("JOBS["), 20)
        self.assertIn("_dat_job(", board)
```

- [ ] **Step 2: Viết cancel tests, gồm expected failure cho identity lô**

```python
# tests/job_lifecycle/test_cancel_characterization.py
import queue
import unittest

from helpers import load_hangdoi, reset_legacy_state


class CancelCharacterizationTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)

    def test_cancel_flag_can_be_peeked_without_consuming(self):
        self.h.DA_HUY.add("A")
        self.assertTrue(self.h.bi_huy("A", an=False))
        self.assertTrue(self.h.bi_huy("A", an=True))
        self.assertFalse(self.h.bi_huy("A", an=False))

    def test_new_manual_intent_clears_old_cancel_flag(self):
        self.h.DA_HUY.update({"A", "LO:A"})
        self.h.bo_co_huy("A", "LO:A")
        self.assertFalse(self.h.DA_HUY)

    def test_stop_generation_is_monotonic(self):
        before = self.h.dung_gen()
        self.assertEqual(self.h.tang_dung_gen(), before + 1)
        self.assertEqual(self.h.dung_gen(), before + 1)

    @unittest.expectedFailure
    def test_member_only_jobs_can_resolve_physical_group_queue_identity(self):
        q = queue.PriorityQueue()
        self.h.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        self.h.JOBS["B"] = {"state": "queued", "msg": "chờ"}
        self.h.xep(q, ("img", "LO:A,B", 0, False))
        queued_members = {k for k, v in self.h.JOBS.items() if v["state"] == "queued"}
        cancel_tokens = set(queued_members)
        cancel_tokens.update(
            key for key in self.h.JOBS
            if key.startswith("LO:") and any(x in queued_members for x in key[3:].split(","))
        )
        self.assertIn("LO:A,B", cancel_tokens)
```

- [ ] **Step 3: Chạy hai suite và kiểm tra expected failure đúng một ca**

Run: `python3 -m unittest tests/job_lifecycle/test_current_state_writers.py tests/job_lifecycle/test_cancel_characterization.py -v`

Expected: `OK (expected failures=1)`; failure là `test_member_only_jobs_can_resolve_physical_group_queue_identity`.

- [ ] **Step 4: Commit writer/cancel evidence**

```bash
git add tests/job_lifecycle/test_current_state_writers.py tests/job_lifecycle/test_cancel_characterization.py
git commit -m "test: capture lifecycle writer and cancel behavior"
```

---

### Task 3: Retry, auto và account characterization

**Files:**
- Create: `tests/job_lifecycle/test_retry_characterization.py`
- Create: `tests/job_lifecycle/test_auto_characterization.py`
- Create: `tests/job_lifecycle/test_account_characterization.py`
- Test: ba file trên.

**Interfaces:**
- Consumes: `function_source(path, name)` và source contracts hiện tại.
- Produces: regression gates cho re-enqueue, duplicate auto-video và forced-account retry.

- [ ] **Step 1: Viết retry authority tests**

```python
# tests/job_lifecycle/test_retry_characterization.py
import unittest
from pathlib import Path
from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class RetryCharacterizationTest(unittest.TestCase):
    def test_retry_timer_checks_stop_generation_and_cancel_before_enqueue(self):
        src = function_source(BOARD, "_xep_lai_sau")
        self.assertIn("dung_gen() != gen", src)
        self.assertIn("_bi_huy(item[1], an=False)", src)
        self.assertIn("_xep(Q, item)", src)

    def test_retry_authorities_are_explicitly_counted(self):
        src = BOARD.read_text(encoding="utf-8")
        markers = ["_xep_lai_sau(", "_HOAN", "AUTO_MAX_TRY", "VID_MAX_TRY"]
        self.assertEqual([m for m in markers if m not in src], [])

    def test_video_has_inner_session_reconnect_and_outer_retry_cap(self):
        video = function_source(BOARD, "_gen_video")
        worker = function_source(BOARD, "_worker")
        self.assertIn("for attempt in range(2)", video)
        self.assertIn("_is_dead_session_error(e)", video)
        self.assertIn("VID_MAX_TRY", worker)
        self.assertIn("_xep_lai_sau", worker)
```

- [ ] **Step 2: Viết auto duplicate expected failure**

```python
# tests/job_lifecycle/test_auto_characterization.py
import unittest
from pathlib import Path
from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]


class AutoCharacterizationTest(unittest.TestCase):
    @unittest.expectedFailure
    def test_auto_video_blocks_both_running_and_queued(self):
        src = function_source(ROOT / "sfboard/sfboard.py", "_auto_scene")
        normalized = " ".join(src.split())
        self.assertIn(
            'JOBS.get(sh["id"], {}).get("state") in ("running", "queued")',
            normalized,
        )

    def test_auto_image_checks_running_and_queued(self):
        src = function_source(ROOT / "sfboard/sfboard.py", "_auto_scene")
        self.assertIn('not in ("running", "queued")', src)

    @unittest.expectedFailure
    def test_auto_producer_observes_same_stop_barrier_as_retry_timer(self):
        src = function_source(ROOT / "sfboard/sfboard.py", "_auto_scene")
        self.assertTrue("dung_gen()" in src or "stop_barrier" in src)

    @unittest.expectedFailure
    def test_multi_copy_enqueue_uses_distinct_job_identity_per_copy(self):
        src = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        generate_route = src[src.index('elif u.path == "/api/generate"'):
                             src.index('elif u.path == "/api/dung-het"')]
        self.assertTrue("copy_index" in generate_route or "job_id" in generate_route)
```

- [ ] **Step 3: Viết account-assignment characterization**

```python
# tests/job_lifecycle/test_account_characterization.py
import unittest
from pathlib import Path
from helpers import function_source

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "sfboard/sfboard.py"


class AccountCharacterizationTest(unittest.TestCase):
    def test_worker_is_bound_to_endpoint_before_queue_take(self):
        src = function_source(BOARD, "_worker")
        self.assertLess(src.index("_TL.endpoint = endpoint"), src.index("_lay(QUEUE"))

    def test_forced_image_work_uses_private_port_queue(self):
        src = function_source(BOARD, "_worker")
        self.assertIn("CHO_RIENG.get(_my_port)", src)
        self.assertIn('_rieng.pop(0)', src)

    @unittest.expectedFailure
    def test_forced_account_constraint_is_carried_by_every_retry_item(self):
        retry_src = function_source(BOARD, "_xep_lai_sau")
        self.assertIn("forced_account", retry_src)
```

- [ ] **Step 4: Chạy ba suite**

Run: `python3 -m unittest tests/job_lifecycle/test_retry_characterization.py tests/job_lifecycle/test_auto_characterization.py tests/job_lifecycle/test_account_characterization.py -v`

Expected: `OK (expected failures=4)`; target behavior gồm auto-video queued guard, stop barrier của auto, multi-copy identity và forced-account retry constraint.

- [ ] **Step 5: Commit retry/auto/account evidence**

```bash
git add tests/job_lifecycle/test_retry_characterization.py tests/job_lifecycle/test_auto_characterization.py tests/job_lifecycle/test_account_characterization.py
git commit -m "test: characterize retry auto and account assignment"
```

---

### Task 4: HTTP compatibility contract

**Files:**
- Modify: `tests/job_lifecycle/helpers.py`
- Create: `tests/job_lifecycle/test_http_contract.py`
- Test: `tests/job_lifecycle/test_http_contract.py`

**Interfaces:**
- Consumes: `load_sfboard`, `CaptureHandlerMixin`.
- Produces: `make_handler(module, path, raw=b"")` và schema gate cho legacy UI.

- [ ] **Step 1: Thêm fake board và handler constructor**

```python
# append tests/job_lifecycle/helpers.py
class FakeBoard:
    path = __file__

    def read(self):
        return {"scenes": []}

    def get_sf(self, sf_id):
        return {"id": sf_id}

    def get_shot(self, shot_id):
        return (None, None)

    def find_file(self, asset_id):
        return None

    def video_file(self, shot_id):
        return None


def make_handler(module, path: str, raw: bytes = b""):
    cls = type("CaptureHandler", (CaptureHandlerMixin, module.Handler), {})
    handler = object.__new__(cls)
    handler.prepare(path, raw)
    return handler
```

- [ ] **Step 2: Viết `/api/jobs` schema test và source contract cho create/cancel**

```python
# tests/job_lifecycle/test_http_contract.py
import unittest
from pathlib import Path

from helpers import FakeBoard, load_sfboard, make_handler, reset_legacy_state

ROOT = Path(__file__).resolve().parents[2]


class HttpContractTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        reset_legacy_state(self.m)
        self.old_board = self.m.BOARD
        self.m.BOARD = FakeBoard()
        self.old_helpers = {
            name: getattr(self.m, name)
            for name in ("_auto_status", "_pl_dem", "_dan_ma_doc", "_auto_vid_doc")
        }
        self.m._auto_status = lambda: {}
        self.m._pl_dem = lambda: 0
        self.m._dan_ma_doc = lambda: {}
        self.m._auto_vid_doc = lambda: False

    def tearDown(self):
        self.m.BOARD = self.old_board
        for name, value in self.old_helpers.items():
            setattr(self.m, name, value)

    def test_jobs_response_keeps_legacy_top_level_schema(self):
        handler = make_handler(self.m, "/api/jobs")
        handler.do_GET()
        code, body = handler.captured
        self.assertEqual(code, 200)
        self.assertEqual(
            set(body),
            {"jobs", "auto", "nhom", "hang", "tho", "vet", "pl", "dan_ma",
             "loi", "auto_vid", "mtime"},
        )
        self.assertEqual(set(body["hang"]), {"anh", "video"})
        self.assertEqual(set(body["tho"]), {"img", "vid"})

    def test_create_and_cancel_routes_keep_response_keys(self):
        src = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
        self.assertIn('{"ok": True, "qua_lo": True, "so_ban": so_ban}', src)
        self.assertIn('"cho_da_huy": len(cho)', src)
        self.assertIn('"dang_chay": dang', src)
        self.assertIn('{"ok": True, "video": True}', src)
```

- [ ] **Step 3: Chạy HTTP contract trong môi trường không mở Chrome**

Run: `python3 -m unittest tests/job_lifecycle/test_http_contract.py -v`

Expected: 2 tests `OK`; không gọi `main()`, không tạo `Board` thật và không ghi project.

- [ ] **Step 4: Chạy toàn Phase 0**

Run: `python3 -m unittest discover -s tests/job_lifecycle -p 'test_*characterization.py' -v && python3 -m unittest tests/job_lifecycle/test_current_state_writers.py tests/job_lifecycle/test_http_contract.py -v`

Expected: mọi characterization hợp lệ pass; 5 expected failures được báo rõ.

- [ ] **Step 5: Commit HTTP compatibility gate**

```bash
git add tests/job_lifecycle/helpers.py tests/job_lifecycle/test_http_contract.py
git commit -m "test: lock legacy job API contract"
```

---

### Task 5: Typed identity, Job enums và immutable Job model

**Files:**
- Create: `sfboard/jobs/__init__.py`
- Create: `sfboard/jobs/models.py`
- Create: `tests/job_lifecycle/test_models.py`
- Test: `tests/job_lifecycle/test_models.py`

**Interfaces:**
- Produces: `AssetId`, `JobId`, `BatchId`, `ExecutionId`, `AttemptId`, `JobState`, `JobKind`, `JobOrigin`, `Job`.
- Consumes: chỉ Python stdlib; không import legacy module.

- [ ] **Step 1: Viết failing tests cho identity và Job**

```python
# tests/job_lifecycle/test_models.py
import dataclasses
import unittest
from uuid import UUID

from sfboard.jobs.models import AssetId, Job, JobId, JobKind, JobOrigin, JobState


class JobModelTest(unittest.TestCase):
    def test_typed_identity_round_trip(self):
        job_id = JobId.new()
        self.assertEqual(JobId.parse(str(job_id)), job_id)
        UUID(str(job_id))

    def test_asset_id_cannot_be_used_as_job_id(self):
        with self.assertRaises(ValueError):
            JobId.parse("SF-S1-1")

    def test_job_defaults_to_created_and_is_immutable(self):
        job = Job(
            job_id=JobId.new(), asset_id=AssetId("SF-S1-1"),
            kind=JobKind.IMAGE, origin=JobOrigin.MANUAL,
        )
        self.assertEqual(job.state, JobState.CREATED)
        self.assertEqual(job.version, 0)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            job.state = JobState.RUNNING

    def test_terminal_predicate_is_exact(self):
        self.assertEqual(
            {s for s in JobState if s.is_terminal},
            {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED},
        )
        self.assertFalse(JobState.NEEDS_ATTENTION.is_terminal)
```

- [ ] **Step 2: Chạy test và xác nhận import fail**

Run: `python3 -m unittest tests/job_lifecycle/test_models.py -v`

Expected: FAIL với `ModuleNotFoundError: No module named 'sfboard.jobs'`.

- [ ] **Step 3: Implement identity/enums/Job tối thiểu**

```python
# sfboard/jobs/models.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AssetId:
    value: str

    def __post_init__(self):
        if not self.value or not self.value.strip():
            raise ValueError("asset_id không được rỗng")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class _UuidId:
    value: UUID

    @classmethod
    def new(cls):
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str):
        try:
            return cls(UUID(value))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(f"{cls.__name__} phải là UUID hợp lệ") from exc

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class JobId(_UuidId):
    pass


@dataclass(frozen=True)
class BatchId(_UuidId):
    pass


@dataclass(frozen=True)
class ExecutionId(_UuidId):
    pass


@dataclass(frozen=True)
class AttemptId(_UuidId):
    pass


class JobState(str, Enum):
    CREATED = "created"
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_ATTENTION = "needs_attention"

    @property
    def is_terminal(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


class JobKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class JobOrigin(str, Enum):
    MANUAL = "manual"
    AUTO = "auto"
    CLI = "cli"
    COMPATIBILITY = "compatibility"


@dataclass(frozen=True)
class Job:
    job_id: JobId
    asset_id: AssetId
    kind: JobKind
    origin: JobOrigin
    state: JobState = JobState.CREATED
    version: int = 0
    batch_id: Optional[BatchId] = None
    rerun_of: Optional[JobId] = None
    copy_index: Optional[int] = None
    replace_current: bool = False
    forced_account_id: Optional[str] = None
    allow_account_fallback: bool = False

    def __post_init__(self):
        if not isinstance(self.job_id, JobId) or not isinstance(self.asset_id, AssetId):
            raise TypeError("job_id và asset_id phải dùng đúng typed identity")
        if self.version < 0:
            raise ValueError("version không được âm")
        if self.copy_index is not None and self.copy_index < 0:
            raise ValueError("copy_index không được âm")
        if self.allow_account_fallback and not self.forced_account_id:
            raise ValueError("fallback chỉ có nghĩa khi job ép account")
```

`sfboard/jobs/__init__.py` export chính xác các public type, không import legacy globals.

- [ ] **Step 4: Chạy model tests**

Run: `python3 -m unittest tests/job_lifecycle/test_models.py -v`

Expected: 4 tests `OK`.

- [ ] **Step 5: Commit identity và Job model**

```bash
git add sfboard/jobs/__init__.py sfboard/jobs/models.py tests/job_lifecycle/test_models.py
git commit -m "feat: add immutable job lifecycle identities"
```

---

### Task 6: Batch, Execution và Attempt invariants

**Files:**
- Modify: `sfboard/jobs/models.py`
- Modify: `sfboard/jobs/__init__.py`
- Modify: `tests/job_lifecycle/test_models.py`
- Test: `tests/job_lifecycle/test_models.py`

**Interfaces:**
- Produces: `BatchMode`, `Batch`, `ExecutionState`, `Execution`, `AttemptPhase`, `AttemptOutcome`, `CreditConsumption`, `Attempt`.
- Consumes: typed IDs và `JobKind` từ Task 5.

- [ ] **Step 1: Viết failing tests cho batch/execution/attempt**

```python
# append tests/job_lifecycle/test_models.py
from datetime import datetime, timezone
from sfboard.jobs.models import (
    Attempt, AttemptId, AttemptOutcome, AttemptPhase,
    Batch, BatchId, BatchMode, CreditConsumption, Execution, ExecutionId,
    ExecutionState,
)


class ExecutionModelTest(unittest.TestCase):
    def test_execution_rejects_empty_or_duplicate_members(self):
        with self.assertRaises(ValueError):
            Execution(ExecutionId.new(), JobKind.IMAGE, (), ExecutionState.READY, 1)
        job_id = JobId.new()
        with self.assertRaises(ValueError):
            Execution(ExecutionId.new(), JobKind.IMAGE, (job_id, job_id), ExecutionState.READY, 1)

    def test_attempt_before_submit_cannot_consume_credit(self):
        attempt = Attempt(
            AttemptId.new(), ExecutionId.new(), 1, "acct-1", "lease-1",
            AttemptPhase.READY_TO_SUBMIT, CreditConsumption.FALSE,
        )
        self.assertIsNone(attempt.submitted_at)

    def test_submitted_attempt_requires_timestamp_and_credit_classification(self):
        with self.assertRaises(ValueError):
            Attempt(
                AttemptId.new(), ExecutionId.new(), 1, "acct-1", "lease-1",
                AttemptPhase.SUBMITTED, CreditConsumption.FALSE,
            )
        now = datetime.now(timezone.utc)
        valid = Attempt(
            AttemptId.new(), ExecutionId.new(), 1, "acct-1", "lease-1",
            AttemptPhase.SUBMITTED, CreditConsumption.UNKNOWN, submitted_at=now,
        )
        self.assertEqual(valid.submitted_at, now)

    def test_finished_attempt_requires_outcome_and_finished_at(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            Attempt(
                AttemptId.new(), ExecutionId.new(), 1, "acct-1", "lease-1",
                AttemptPhase.FINISHED, CreditConsumption.TRUE, submitted_at=now,
            )

    def test_batch_mode_must_match_kind(self):
        with self.assertRaises(ValueError):
            Batch(BatchId.new(), JobKind.VIDEO, BatchMode.IMAGE_GROUP, (JobId.new(),))
```

- [ ] **Step 2: Chạy riêng test mới để thấy thiếu symbols**

Run: `python3 -m unittest tests.job_lifecycle.test_models.ExecutionModelTest -v`

Expected: FAIL khi import các type chưa được định nghĩa.

- [ ] **Step 3: Thêm immutable scheduling models và validation**

```python
# append sfboard/jobs/models.py
from datetime import datetime
from typing import Tuple


class BatchMode(str, Enum):
    IMAGE_GROUP = "image_group"
    MULTI_COPY = "multi_copy"
    BULK_VIDEO = "bulk_video"


@dataclass(frozen=True)
class Batch:
    batch_id: BatchId
    kind: JobKind
    mode: BatchMode
    member_job_ids: Tuple[JobId, ...]

    def __post_init__(self):
        if not self.member_job_ids or len(set(self.member_job_ids)) != len(self.member_job_ids):
            raise ValueError("batch cần member duy nhất và không rỗng")
        if self.mode in {BatchMode.IMAGE_GROUP, BatchMode.MULTI_COPY} and self.kind is not JobKind.IMAGE:
            raise ValueError("image batch phải có kind=image")
        if self.mode is BatchMode.BULK_VIDEO and self.kind is not JobKind.VIDEO:
            raise ValueError("bulk_video phải có kind=video")


class ExecutionState(str, Enum):
    READY = "ready"
    LEASED = "leased"
    WAITING = "waiting"
    FINISHED = "finished"


@dataclass(frozen=True)
class Execution:
    execution_id: ExecutionId
    kind: JobKind
    member_job_ids: Tuple[JobId, ...]
    state: ExecutionState
    priority: int

    def __post_init__(self):
        if not self.member_job_ids or len(set(self.member_job_ids)) != len(self.member_job_ids):
            raise ValueError("execution cần member duy nhất và không rỗng")


class AttemptPhase(str, Enum):
    PREPARING = "preparing"
    ATTACHING = "attaching"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    WAITING_PROVIDER = "waiting_provider"
    DOWNLOADING = "downloading"
    SAVING = "saving"
    FINISHED = "finished"


class AttemptOutcome(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class CreditConsumption(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Attempt:
    attempt_id: AttemptId
    execution_id: ExecutionId
    number: int
    account_id: str
    lease_id: str
    phase: AttemptPhase
    consumes_credit: CreditConsumption
    submitted_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    outcome: Optional[AttemptOutcome] = None

    def __post_init__(self):
        if self.number < 1 or not self.account_id or not self.lease_id:
            raise ValueError("attempt number/account/lease không hợp lệ")
        submitted_or_later = self.phase in {
            AttemptPhase.SUBMITTED, AttemptPhase.WAITING_PROVIDER,
            AttemptPhase.DOWNLOADING, AttemptPhase.SAVING, AttemptPhase.FINISHED,
        }
        if submitted_or_later and self.submitted_at is None:
            raise ValueError("phase sau submit cần submitted_at")
        if not submitted_or_later and self.submitted_at is not None:
            raise ValueError("phase trước submit không được có submitted_at")
        if submitted_or_later and self.consumes_credit is CreditConsumption.FALSE:
            raise ValueError("submit phải consume credit hoặc unknown")
        if not submitted_or_later and self.consumes_credit is not CreditConsumption.FALSE:
            raise ValueError("trước submit consumes_credit phải false")
        if self.phase is AttemptPhase.FINISHED:
            if self.finished_at is None or self.outcome is None:
                raise ValueError("finished attempt cần finished_at và outcome")
        elif self.finished_at is not None or self.outcome is not None:
            raise ValueError("attempt chưa finished không được có terminal fields")
```

Không thêm transition method vào các dataclass.

- [ ] **Step 4: Export type và chạy toàn model suite**

Run: `python3 -m unittest tests/job_lifecycle/test_models.py -v`

Expected: 9 tests `OK`.

- [ ] **Step 5: Commit execution model**

```bash
git add sfboard/jobs/__init__.py sfboard/jobs/models.py tests/job_lifecycle/test_models.py
git commit -m "feat: model batches executions and attempts"
```

---

### Task 7: Event, account lease và error taxonomy

**Files:**
- Modify: `sfboard/jobs/models.py`
- Create: `sfboard/jobs/errors.py`
- Modify: `sfboard/jobs/__init__.py`
- Create: `tests/job_lifecycle/test_errors.py`
- Test: `tests/job_lifecycle/test_errors.py`

**Interfaces:**
- Produces: `JobEvent`, `EventActor`, `AccountLease`, `ErrorClass`, `ErrorFact`.
- Consumes: Job/Attempt typed IDs, `AttemptPhase`.

- [ ] **Step 1: Viết failing tests cho facts không mutable**

```python
# tests/job_lifecycle/test_errors.py
import dataclasses
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sfboard.jobs.errors import ErrorClass, ErrorFact
from sfboard.jobs.models import (
    AccountLease, AttemptId, AttemptPhase, EventActor, JobEvent, JobId, JobState,
)


class ErrorFactTest(unittest.TestCase):
    def test_all_approved_error_classes_exist(self):
        self.assertEqual(
            {e.value for e in ErrorClass},
            {"validation", "cancelled", "session_transient", "provider_transient",
             "quota_rate_limit", "permanent", "unknown_outcome", "account_lost"},
        )

    def test_unknown_outcome_requires_submitted_boundary(self):
        with self.assertRaises(ValueError):
            ErrorFact(ErrorClass.UNKNOWN_OUTCOME, "mất kết nối", AttemptPhase.ATTACHING)

    def test_error_fact_is_immutable(self):
        fact = ErrorFact(ErrorClass.SESSION_TRANSIENT, "tab đóng", AttemptPhase.PREPARING)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fact.message = "khác"


class LifecycleFactTest(unittest.TestCase):
    def test_transition_event_requires_both_states(self):
        with self.assertRaises(ValueError):
            JobEvent(
                uuid4(), JobId.new(), EventActor.MANAGER, "transition", "test",
                from_state=JobState.CREATED,
            )

    def test_account_lease_expiry_must_follow_acquisition(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            AccountLease("lease-1", "acct-1", AttemptId.new(), 0, now, now)
        valid = AccountLease(
            "lease-2", "acct-1", AttemptId.new(), 1, now, now + timedelta(minutes=1),
        )
        self.assertEqual(valid.slot, 1)
```

- [ ] **Step 2: Chạy test và xác nhận missing module**

Run: `python3 -m unittest tests/job_lifecycle/test_errors.py -v`

Expected: FAIL với `ModuleNotFoundError: No module named 'sfboard.jobs.errors'`.

- [ ] **Step 3: Implement error taxonomy**

```python
# sfboard/jobs/errors.py
from dataclasses import dataclass
from enum import Enum

from .models import AttemptPhase


class ErrorClass(str, Enum):
    VALIDATION = "validation"
    CANCELLED = "cancelled"
    SESSION_TRANSIENT = "session_transient"
    PROVIDER_TRANSIENT = "provider_transient"
    QUOTA_RATE_LIMIT = "quota_rate_limit"
    PERMANENT = "permanent"
    UNKNOWN_OUTCOME = "unknown_outcome"
    ACCOUNT_LOST = "account_lost"


@dataclass(frozen=True)
class ErrorFact:
    error_class: ErrorClass
    message: str
    phase: AttemptPhase
    provider_code: str = ""

    def __post_init__(self):
        if not self.message.strip():
            raise ValueError("error message không được rỗng")
        if self.error_class is ErrorClass.UNKNOWN_OUTCOME and self.phase in {
            AttemptPhase.PREPARING, AttemptPhase.ATTACHING, AttemptPhase.READY_TO_SUBMIT,
        }:
            raise ValueError("unknown outcome chỉ hợp lệ từ submit boundary")
```

- [ ] **Step 4: Thêm event/account facts vào models**

```python
# append sfboard/jobs/models.py
class EventActor(str, Enum):
    API = "api"
    AUTO = "auto"
    MANAGER = "manager"
    SCHEDULER = "scheduler"
    WORKER = "worker"
    USER = "user"
    RECOVERY = "recovery"


@dataclass(frozen=True)
class JobEvent:
    event_id: UUID
    job_id: JobId
    actor: EventActor
    event_type: str
    reason_code: str
    from_state: Optional[JobState] = None
    to_state: Optional[JobState] = None
    attempt_id: Optional[AttemptId] = None

    def __post_init__(self):
        if not self.event_type or not self.reason_code:
            raise ValueError("event_type/reason_code không được rỗng")
        if (self.from_state is None) != (self.to_state is None):
            raise ValueError("transition event cần cả from_state và to_state")


@dataclass(frozen=True)
class AccountLease:
    lease_id: str
    account_id: str
    attempt_id: AttemptId
    slot: int
    acquired_at: datetime
    expires_at: datetime

    def __post_init__(self):
        if not self.lease_id or not self.account_id or self.slot < 0:
            raise ValueError("account lease không hợp lệ")
        if self.expires_at <= self.acquired_at:
            raise ValueError("lease expiry phải sau acquired_at")
```

Export các type mới từ `sfboard/jobs/__init__.py`.

- [ ] **Step 5: Chạy model/error tests**

Run: `python3 -m unittest tests/job_lifecycle/test_models.py tests/job_lifecycle/test_errors.py -v`

Expected: tất cả tests `OK`.

- [ ] **Step 6: Commit facts và taxonomy**

```bash
git add sfboard/jobs/models.py sfboard/jobs/errors.py sfboard/jobs/__init__.py tests/job_lifecycle/test_errors.py
git commit -m "feat: define job events leases and error facts"
```

---

### Task 8: Phase 0–1 verification gate

**Files:**
- Modify only if a verification failure exposes a defect: files introduced in Tasks 1–7.
- Test: all `tests/job_lifecycle`.

**Interfaces:**
- Consumes: toàn bộ deliverable Phase 0–1.
- Produces: một verified checkpoint sẵn sàng cho Phase 2 shadow-mode planning.

- [ ] **Step 1: Chạy complete lifecycle suite**

Run: `python3 -m unittest discover -s tests/job_lifecycle -p 'test_*.py' -v`

Expected: suite `OK`; đúng 5 expected failures được ghi nhận, không có unexpected failure/error.

- [ ] **Step 2: Compile production hiện tại và package mới**

Run: `python3 -m py_compile sfboard/hangdoi.py sfboard/sfboard.py sfboard/jobs/__init__.py sfboard/jobs/models.py sfboard/jobs/errors.py`

Expected: exit code 0, không có output.

- [ ] **Step 3: Xác minh package mới chưa nối production**

Run: `rg -n 'from sfboard\.jobs|import sfboard\.jobs|from jobs|import jobs' sfboard/sfboard.py sfboard/hangdoi.py`

Expected: exit code 1 và không có output.

- [ ] **Step 4: Xác minh test không chứa live integration**

Run: `rg -n 'playwright|chromium|chatgpt\.com|grok\.com|requests\.(get|post)|urlopen' tests/job_lifecycle`

Expected: exit code 1 và không có output.

- [ ] **Step 5: Kiểm tra diff scope**

Run: `git diff --name-only HEAD~7..HEAD`

Expected: chỉ có `tests/job_lifecycle/*` và `sfboard/jobs/*`.

- [ ] **Step 6: Ghi checkpoint verification**

```bash
git status --short
git log --oneline -7
```

Expected: không có thay đổi chưa commit do Phase 0–1 tạo ra; các thay đổi có sẵn của người dùng vẫn giữ nguyên, không staged.

## Phase 0–1 Definition of Done

- Legacy queue/order/state/API behavior quan trọng có executable characterization.
- Năm known ambiguity được giữ dưới `expectedFailure`: cancel identity lô, auto-video duplicate queued, auto/stop barrier, multi-copy identity và forced-account retry mất constraint.
- Mọi test chạy offline, không ghi board thật và không mở provider.
- Domain package chỉ phụ thuộc stdlib, immutable và không biết Board/HTTP/browser/global queue.
- Asset/Job/Execution/Attempt dùng type khác nhau; SF id không parse được thành UUID entity id.
- Attempt invariants khóa ranh giới `SUBMITTED` và credit classification.
- Không có lifecycle transition method trong model; authority đó thuộc Phase 2 `JobManager`.
- Production chưa import `sfboard.jobs`, nên behavior chưa đổi.
