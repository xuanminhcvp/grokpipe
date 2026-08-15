# Job Lifecycle Phase 2 Shadow Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm `MemoryJobStore`, `JobManager` và legacy projection ở shadow mode để đo lifecycle mismatch mà không thay đổi production authority.

**Architecture:** Legacy `JOBS`, queues, workers, retry, auto và account registry tiếp tục quyết production. Một observer fail-open nhận bản ghi sau mỗi legacy `JOBS` write, chiếu nó vào immutable shadow Job qua `JobManager`; store mới đảm bảo CAS, event idempotency và atomic state+event nhưng tuyệt đối không enqueue hoặc gọi executor.

**Tech Stack:** Python 3.14 runtime hiện tại, tương thích Python 3.9+, stdlib `dataclasses`, `threading`, `typing.Protocol`, `uuid`, `unittest`/`pytest`; không thêm dependency.

## Global Constraints

- Phase 2 chỉ triển khai Bead `beads-foundation-7lt.7`.
- Chỉ bắt đầu implementation trong worktree sạch tạo từ đúng baseline chứa toàn bộ thay đổi hiện hành đã được duyệt. Nếu workspace còn file không rõ ownership, dừng để chốt checkpoint; không stash/reset hoặc gom chúng vào commit Phase 2.
- Production authority vẫn là legacy: `JOBS`, `PriorityQueue`, worker, retry và auto.
- Default mode là `legacy`; `shadow` chỉ bật bằng `GROKPIPE_JOB_MODE=shadow`.
- Shadow không được import/đọc/ghi `IMG_QUEUE`, `VID_QUEUE`, `CHO_RIENG`, worker, executor, account registry hoặc Playwright.
- Observer chạy sau legacy write và mọi exception của observer phải bị cô lập, không đổi return/value/state của legacy.
- `JobManager` là nơi duy nhất áp transition shadow; store chỉ đảm bảo persistence semantics/CAS.
- Không sửa hoặc hạ bốn `expectedFailure` hiện tại trong Phase 2.
- Không mở Chrome, không gọi provider, không restart board đang chạy và không tiêu credit.
- Mỗi task dùng red-green TDD, commit riêng và chạy targeted tests trước full gate.
- Full gate cuối phase phải là `361+ passed`, đúng `4 xfailed`, coverage `sfboard.jobs >= 80%`, compile PASS.

---

## File map

| File | Trách nhiệm |
|---|---|
| `sfboard/jobs/store.py` | `JobStore` protocol, `MemoryJobStore`, CAS, event idempotency và atomic write result |
| `sfboard/jobs/manager.py` | Bảng transition chuẩn, command/fact skeleton và manager-only transition API |
| `sfboard/jobs/projection.py` | Chiếu legacy state/message sang shadow Job/Event, phát mismatch không sửa legacy |
| `sfboard/jobs/__init__.py` | Export public symbols của Phase 2 |
| `sfboard/hangdoi.py` | Optional fail-open observer sau `_Jobs.__setitem__` |
| `sfboard/sfboard.py` | `legacy|shadow` startup wiring và diagnostic projection |
| `tests/job_lifecycle/test_store.py` | Atomic create/transition, CAS, idempotent event và collision tests |
| `tests/job_lifecycle/test_manager_transitions.py` | Legal/illegal matrix, terminal monotonicity, progress và race tests |
| `tests/job_lifecycle/test_legacy_projection.py` | Mapping, rerun identity, mismatch, observer isolation và startup mode tests |
| `tests/job_lifecycle/helpers.py` | Reset observer giữa tests để không rò global state |
| `docs/JOB-LIFECYCLE-README.md` | Cập nhật current phase sau khi toàn bộ gate xanh |

---

### Task 1: In-memory store với CAS và idempotent event

**Files:**
- Create: `sfboard/jobs/store.py`
- Create: `tests/job_lifecycle/test_store.py`
- Modify: `sfboard/jobs/__init__.py`

**Interfaces:**
- Consumes: `Job`, `JobId`, `JobState`, `JobEvent` từ `sfboard.jobs.models`.
- Produces: `JobStore`, `MemoryJobStore`, `StoreWriteResult`, `JobNotFound`, `JobAlreadyExists`, `VersionConflict`, `EventConflict`, `StoreInvariantError`.
- `MemoryJobStore.create(job, event) -> StoreWriteResult` ghi Job+Event atomically.
- `MemoryJobStore.transition(job_id, expected_version, to_state, event) -> StoreWriteResult` tăng version đúng một.
- `MemoryJobStore.append_event(job_id, event) -> StoreWriteResult` append progress event, không tăng version.
- Gửi lại cùng `event_id` và cùng payload trả result cũ với `applied=False`; cùng ID khác payload ném `EventConflict`.

- [ ] **Step 1: Viết test store trước implementation**

```python
# tests/job_lifecycle/test_store.py
import unittest
from uuid import uuid4

from sfboard.jobs.models import (
    AssetId, EventActor, Job, JobEvent, JobId, JobKind, JobOrigin, JobState,
)
from sfboard.jobs.store import (
    EventConflict, JobAlreadyExists, MemoryJobStore, VersionConflict,
)


def make_job(state=JobState.CREATED, version=0):
    return Job(
        JobId.new(), AssetId("SF-S1-1"), JobKind.IMAGE, JobOrigin.MANUAL,
        state=state, version=version,
    )


def make_event(job, *, event_id=None, from_state=None, to_state=None, reason="test"):
    return JobEvent(
        event_id or uuid4(), job.job_id, EventActor.MANAGER,
        "test_event", reason, from_state=from_state, to_state=to_state,
    )


class MemoryJobStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()

    def test_create_writes_job_and_event_atomically(self):
        job = make_job()
        event = make_event(job, reason="created")
        result = self.store.create(job, event)
        self.assertTrue(result.applied)
        self.assertEqual(self.store.get(job.job_id), job)
        self.assertEqual(self.store.events_for(job.job_id), (event,))

    def test_duplicate_event_replays_without_second_append(self):
        job = make_job()
        event = make_event(job, reason="created")
        first = self.store.create(job, event)
        replay = self.store.create(job, event)
        self.assertTrue(first.applied)
        self.assertFalse(replay.applied)
        self.assertEqual(replay.job, first.job)
        self.assertEqual(self.store.events_for(job.job_id), (event,))

    def test_same_event_id_with_different_payload_is_conflict(self):
        job = make_job()
        event_id = uuid4()
        self.store.create(job, make_event(job, event_id=event_id, reason="one"))
        with self.assertRaises(EventConflict):
            self.store.append_event(
                job.job_id, make_event(job, event_id=event_id, reason="two")
            )

    def test_duplicate_job_with_new_event_is_rejected(self):
        job = make_job()
        self.store.create(job, make_event(job, reason="one"))
        with self.assertRaises(JobAlreadyExists):
            self.store.create(job, make_event(job, reason="two"))

    def test_transition_is_atomic_and_increments_version_once(self):
        job = make_job()
        self.store.create(job, make_event(job, reason="created"))
        event = make_event(
            job, from_state=JobState.CREATED, to_state=JobState.QUEUED,
            reason="scheduled",
        )
        result = self.store.transition(job.job_id, 0, JobState.QUEUED, event)
        self.assertEqual(result.job.state, JobState.QUEUED)
        self.assertEqual(result.job.version, 1)
        self.assertEqual(self.store.events_for(job.job_id)[-1], event)

    def test_cas_conflict_changes_neither_job_nor_events(self):
        job = make_job()
        created = make_event(job, reason="created")
        self.store.create(job, created)
        event = make_event(
            job, from_state=JobState.CREATED, to_state=JobState.QUEUED,
            reason="scheduled",
        )
        with self.assertRaises(VersionConflict):
            self.store.transition(job.job_id, 9, JobState.QUEUED, event)
        self.assertEqual(self.store.get(job.job_id), job)
        self.assertEqual(self.store.events_for(job.job_id), (created,))

    def test_progress_event_does_not_change_version(self):
        job = make_job(state=JobState.RUNNING, version=4)
        self.store.create(job, make_event(job, reason="bootstrap"))
        event = make_event(job, reason="progress")
        result = self.store.append_event(job.job_id, event)
        self.assertEqual(result.job.version, 4)
        self.assertEqual(result.job.state, JobState.RUNNING)
```

- [ ] **Step 2: Chạy test để xác nhận RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py -q`

Expected: collection FAIL với `ModuleNotFoundError: No module named 'sfboard.jobs.store'`.

- [ ] **Step 3: Implement store nhỏ nhất đáp ứng contract**

```python
# sfboard/jobs/store.py
from __future__ import annotations

from dataclasses import dataclass, replace
from threading import RLock
from typing import Optional, Protocol, Tuple
from uuid import UUID

from .models import Job, JobEvent, JobId, JobState


class JobStoreError(RuntimeError):
    pass


class JobNotFound(JobStoreError):
    pass


class JobAlreadyExists(JobStoreError):
    pass


class VersionConflict(JobStoreError):
    pass


class EventConflict(JobStoreError):
    pass


class StoreInvariantError(JobStoreError):
    pass


@dataclass(frozen=True)
class StoreWriteResult:
    job: Job
    event: JobEvent
    applied: bool


class JobStore(Protocol):
    def create(self, job: Job, event: JobEvent) -> StoreWriteResult: ...
    def get(self, job_id: JobId) -> Optional[Job]: ...
    def events_for(self, job_id: JobId) -> Tuple[JobEvent, ...]: ...
    def append_event(self, job_id: JobId, event: JobEvent) -> StoreWriteResult: ...
    def transition(
        self, job_id: JobId, expected_version: int,
        to_state: JobState, event: JobEvent,
    ) -> StoreWriteResult: ...


class MemoryJobStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[JobId, Job] = {}
        self._events: dict[JobId, list[JobEvent]] = {}
        self._event_results: dict[UUID, StoreWriteResult] = {}

    def _replay(self, job_id: JobId, event: JobEvent) -> Optional[StoreWriteResult]:
        result = self._event_results.get(event.event_id)
        if result is None:
            return None
        if result.job.job_id != job_id or result.event != event:
            raise EventConflict(f"event_id {event.event_id} đã mang payload khác")
        return replace(result, applied=False)

    def create(self, job: Job, event: JobEvent) -> StoreWriteResult:
        with self._lock:
            replay = self._replay(job.job_id, event)
            if replay is not None:
                return replay
            if job.job_id in self._jobs:
                raise JobAlreadyExists(str(job.job_id))
            if event.job_id != job.job_id or event.from_state is not None:
                raise StoreInvariantError("create event không khớp job")
            result = StoreWriteResult(job, event, True)
            self._jobs[job.job_id] = job
            self._events[job.job_id] = [event]
            self._event_results[event.event_id] = result
            return result

    def get(self, job_id: JobId) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def events_for(self, job_id: JobId) -> Tuple[JobEvent, ...]:
        with self._lock:
            return tuple(self._events.get(job_id, ()))

    def append_event(self, job_id: JobId, event: JobEvent) -> StoreWriteResult:
        with self._lock:
            replay = self._replay(job_id, event)
            if replay is not None:
                return replay
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFound(str(job_id))
            if event.job_id != job_id or event.from_state is not None:
                raise StoreInvariantError("progress event không hợp lệ")
            result = StoreWriteResult(job, event, True)
            self._events[job_id].append(event)
            self._event_results[event.event_id] = result
            return result

    def transition(
        self, job_id: JobId, expected_version: int,
        to_state: JobState, event: JobEvent,
    ) -> StoreWriteResult:
        with self._lock:
            replay = self._replay(job_id, event)
            if replay is not None:
                return replay
            current = self._jobs.get(job_id)
            if current is None:
                raise JobNotFound(str(job_id))
            if current.version != expected_version:
                raise VersionConflict(
                    f"expected={expected_version}, actual={current.version}"
                )
            if (
                event.job_id != job_id
                or event.from_state != current.state
                or event.to_state != to_state
            ):
                raise StoreInvariantError("transition event không khớp snapshot")
            updated = replace(current, state=to_state, version=current.version + 1)
            result = StoreWriteResult(updated, event, True)
            self._jobs[job_id] = updated
            self._events[job_id].append(event)
            self._event_results[event.event_id] = result
            return result
```

Export toàn bộ public store symbols trong `sfboard/jobs/__init__.py`; không export `JobStoreError` nếu không dùng bên ngoài package.

- [ ] **Step 4: Chạy targeted tests để xác nhận GREEN**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py tests/job_lifecycle/test_models.py tests/job_lifecycle/test_errors.py -q`

Expected: tất cả PASS, không có `xfailed` trong nhóm targeted này.

- [ ] **Step 5: Commit store**

```bash
git add sfboard/jobs/store.py sfboard/jobs/__init__.py tests/job_lifecycle/test_store.py
git commit -m "feat: add in-memory job store semantics"
```

---

### Task 2: JobManager và bảng transition chuẩn

**Files:**
- Create: `sfboard/jobs/manager.py`
- Create: `tests/job_lifecycle/test_manager_transitions.py`
- Modify: `sfboard/jobs/__init__.py`

**Interfaces:**
- Consumes: `JobStore` và exceptions từ Task 1; domain models Phase 1.
- Produces: `LEGAL_TRANSITIONS`, `TransitionCommand`, `IllegalTransition`, `JobManager`.
- `JobManager.create_job(job, event_id, actor, reason_code) -> StoreWriteResult` chỉ nhận `CREATED`.
- `JobManager.bootstrap_shadow(job, event_id, reason_code) -> StoreWriteResult` chỉ nhận `origin=COMPATIBILITY`; dùng để quan sát legacy đang chạy dở, không phải production command.
- `JobManager.transition(command) -> StoreWriteResult` kiểm bảng trước CAS.
- `JobManager.record_progress(...) -> StoreWriteResult` append event, không đổi state/version.

- [ ] **Step 1: Viết legal/illegal matrix và race tests**

```python
# tests/job_lifecycle/test_manager_transitions.py
import threading
import unittest
from uuid import uuid4

from sfboard.jobs.manager import (
    LEGAL_TRANSITIONS, IllegalTransition, JobManager, TransitionCommand,
)
from sfboard.jobs.models import (
    AssetId, EventActor, Job, JobEvent, JobId, JobKind, JobOrigin, JobState,
)
from sfboard.jobs.store import MemoryJobStore, VersionConflict


def seed_manager(state):
    store = MemoryJobStore()
    manager = JobManager(store)
    job = Job(
        JobId.new(), AssetId("SF-S1-1"), JobKind.IMAGE,
        JobOrigin.COMPATIBILITY, state=state,
    )
    manager.bootstrap_shadow(job, uuid4(), "test.seed")
    return manager, store, job


class JobManagerTransitionTest(unittest.TestCase):
    def test_transition_table_matches_approved_state_machine(self):
        expected = {
            JobState.CREATED: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
            JobState.QUEUED: {JobState.RUNNING, JobState.FAILED, JobState.CANCELLED},
            JobState.RUNNING: {
                JobState.COMPLETED, JobState.RETRY_WAIT, JobState.FAILED,
                JobState.CANCELLED, JobState.NEEDS_ATTENTION,
            },
            JobState.RETRY_WAIT: {
                JobState.QUEUED, JobState.FAILED, JobState.CANCELLED,
            },
            JobState.NEEDS_ATTENTION: {
                JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED,
            },
            JobState.COMPLETED: set(),
            JobState.FAILED: set(),
            JobState.CANCELLED: set(),
        }
        self.assertEqual(LEGAL_TRANSITIONS, expected)

    def test_every_allowed_pair_applies_and_increments_version(self):
        for source, targets in LEGAL_TRANSITIONS.items():
            for target in targets:
                with self.subTest(source=source, target=target):
                    manager, _store, job = seed_manager(source)
                    result = manager.transition(TransitionCommand(
                        job.job_id, 0, target, EventActor.MANAGER,
                        "test.transition", "test.allowed", uuid4(),
                    ))
                    self.assertEqual(result.job.state, target)
                    self.assertEqual(result.job.version, 1)

    def test_every_disallowed_pair_is_rejected_without_write(self):
        for source in JobState:
            for target in JobState:
                if target in LEGAL_TRANSITIONS[source]:
                    continue
                with self.subTest(source=source, target=target):
                    manager, store, job = seed_manager(source)
                    before = store.events_for(job.job_id)
                    with self.assertRaises(IllegalTransition):
                        manager.transition(TransitionCommand(
                            job.job_id, 0, target, EventActor.MANAGER,
                            "test.transition", "test.denied", uuid4(),
                        ))
                    self.assertEqual(store.get(job.job_id), job)
                    self.assertEqual(store.events_for(job.job_id), before)

    def test_progress_event_does_not_fake_running_to_running(self):
        manager, store, job = seed_manager(JobState.RUNNING)
        result = manager.record_progress(
            job.job_id, uuid4(), EventActor.WORKER,
            "attempt.progress", "test.progress",
        )
        self.assertEqual(result.job.state, JobState.RUNNING)
        self.assertEqual(result.job.version, 0)
        self.assertIsNone(store.events_for(job.job_id)[-1].from_state)

    def test_complete_cancel_race_allows_exactly_one_cas_winner(self):
        manager, store, job = seed_manager(JobState.RUNNING)
        barrier = threading.Barrier(3)
        outcomes = []

        def run(target):
            barrier.wait()
            try:
                result = manager.transition(TransitionCommand(
                    job.job_id, 0, target, EventActor.MANAGER,
                    "test.race", "test.race", uuid4(),
                ))
                outcomes.append(("ok", result.job.state))
            except VersionConflict:
                outcomes.append(("conflict", target))

        threads = [
            threading.Thread(target=run, args=(JobState.COMPLETED,)),
            threading.Thread(target=run, args=(JobState.CANCELLED,)),
        ]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(2)
        self.assertEqual(sum(kind == "ok" for kind, _ in outcomes), 1)
        self.assertEqual(sum(kind == "conflict" for kind, _ in outcomes), 1)
        self.assertIn(store.get(job.job_id).state, {JobState.COMPLETED, JobState.CANCELLED})
```

- [ ] **Step 2: Chạy test để xác nhận RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_manager_transitions.py -q`

Expected: collection FAIL vì `sfboard.jobs.manager` chưa tồn tại.

- [ ] **Step 3: Implement manager và transition table**

```python
# sfboard/jobs/manager.py
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .models import EventActor, Job, JobEvent, JobId, JobOrigin, JobState
from .store import JobNotFound, JobStore, StoreWriteResult, VersionConflict


LEGAL_TRANSITIONS = {
    JobState.CREATED: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.QUEUED: {JobState.RUNNING, JobState.FAILED, JobState.CANCELLED},
    JobState.RUNNING: {
        JobState.COMPLETED, JobState.RETRY_WAIT, JobState.FAILED,
        JobState.CANCELLED, JobState.NEEDS_ATTENTION,
    },
    JobState.RETRY_WAIT: {JobState.QUEUED, JobState.FAILED, JobState.CANCELLED},
    JobState.NEEDS_ATTENTION: {
        JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED,
    },
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


class IllegalTransition(RuntimeError):
    pass


@dataclass(frozen=True)
class TransitionCommand:
    job_id: JobId
    expected_version: int
    to_state: JobState
    actor: EventActor
    event_type: str
    reason_code: str
    event_id: UUID


class JobManager:
    def __init__(self, store: JobStore) -> None:
        self.store = store

    def get(self, job_id: JobId) -> Job:
        job = self.store.get(job_id)
        if job is None:
            raise JobNotFound(str(job_id))
        return job

    def create_job(
        self, job: Job, event_id: UUID, actor: EventActor, reason_code: str,
    ) -> StoreWriteResult:
        if job.state is not JobState.CREATED or job.version != 0:
            raise ValueError("create_job chỉ nhận CREATED version 0")
        event = JobEvent(
            event_id, job.job_id, actor, "job.created", reason_code,
        )
        return self.store.create(job, event)

    def bootstrap_shadow(
        self, job: Job, event_id: UUID, reason_code: str,
    ) -> StoreWriteResult:
        if job.origin is not JobOrigin.COMPATIBILITY or job.version != 0:
            raise ValueError("bootstrap chỉ dành cho compatibility shadow")
        event = JobEvent(
            event_id, job.job_id, EventActor.MANAGER,
            "legacy.bootstrap", reason_code,
        )
        return self.store.create(job, event)

    def transition(self, command: TransitionCommand) -> StoreWriteResult:
        current = self.get(command.job_id)
        if current.version != command.expected_version:
            raise VersionConflict(
                f"expected={command.expected_version}, actual={current.version}"
            )
        if command.to_state not in LEGAL_TRANSITIONS[current.state]:
            raise IllegalTransition(
                f"{current.state.value}->{command.to_state.value}"
            )
        event = JobEvent(
            command.event_id, command.job_id, command.actor,
            command.event_type, command.reason_code,
            from_state=current.state, to_state=command.to_state,
        )
        return self.store.transition(
            command.job_id, command.expected_version, command.to_state, event,
        )

    def record_progress(
        self, job_id: JobId, event_id: UUID, actor: EventActor,
        event_type: str, reason_code: str,
    ) -> StoreWriteResult:
        event = JobEvent(event_id, job_id, actor, event_type, reason_code)
        return self.store.append_event(job_id, event)
```

Export manager symbols trong `sfboard/jobs/__init__.py`.

- [ ] **Step 4: Chạy store+manager tests để xác nhận GREEN**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py tests/job_lifecycle/test_manager_transitions.py -q`

Expected: tất cả PASS; race test kết thúc dưới 2 giây và không có thread còn sống.

- [ ] **Step 5: Commit manager**

```bash
git add sfboard/jobs/manager.py sfboard/jobs/__init__.py tests/job_lifecycle/test_manager_transitions.py
git commit -m "feat: add shadow job manager transitions"
```

---

### Task 3: Pure legacy projection và mismatch diagnostics

**Files:**
- Create: `sfboard/jobs/projection.py`
- Create: `tests/job_lifecycle/test_legacy_projection.py`
- Modify: `sfboard/jobs/__init__.py`

**Interfaces:**
- Consumes: `JobManager`, `TransitionCommand`, `VersionConflict` và Phase 1 models.
- Produces: `LEGACY_STATE_MAP`, `ShadowMismatch`, `LegacyShadowProjection`.
- `LegacyShadowProjection.observe(key, old_value, new_value) -> None` không đọc global legacy nào.
- `LegacyShadowProjection.diagnostics() -> dict` chỉ trả count và recent mismatch đã lọc; không chứa prompt/message.
- `kind_resolver(key) -> JobKind` là dependency được inject từ runtime.

- [ ] **Step 1: Viết mapping, rerun và mismatch tests**

```python
# tests/job_lifecycle/test_legacy_projection.py (phần pure projection)
import unittest

from sfboard.jobs.manager import JobManager
from sfboard.jobs.models import JobKind, JobState
from sfboard.jobs.projection import LegacyShadowProjection
from sfboard.jobs.store import MemoryJobStore


class LegacyProjectionTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()
        self.manager = JobManager(self.store)
        self.projection = LegacyShadowProjection(
            self.manager, lambda key: JobKind.VIDEO if key.startswith("V-") else JobKind.IMAGE,
        )

    def test_first_write_bootstraps_current_legacy_state(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        job = self.projection.job_for("A")
        self.assertEqual(job.state, JobState.QUEUED)
        self.assertEqual(job.version, 1)

    def test_legal_legacy_sequence_uses_manager_transitions(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.projection.observe("A", {"state": "queued"}, {"state": "running"})
        self.projection.observe("A", {"state": "running"}, {"state": "done"})
        job = self.projection.job_for("A")
        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertEqual(job.version, 3)

    def test_same_state_write_is_progress_event_without_version_change(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.projection.observe("A", {"state": "queued"}, {"state": "running", "msg": "step 1"})
        before = self.projection.job_for("A")
        event_count = len(self.store.events_for(before.job_id))
        self.projection.observe("A", {"state": "running"}, {"state": "running", "msg": "step 2"})
        after = self.projection.job_for("A")
        self.assertEqual(after.version, before.version)
        self.assertEqual(len(self.store.events_for(after.job_id)), event_count + 1)

    def test_cancel_words_project_legacy_error_to_cancelled(self):
        self.projection.observe("A", None, {"state": "error", "msg": "đã huỷ riêng"})
        self.assertEqual(self.projection.job_for("A").state, JobState.CANCELLED)

    def test_plain_legacy_error_projects_to_failed(self):
        self.projection.observe("A", None, {"state": "error", "msg": "selector lỗi"})
        self.assertEqual(self.projection.job_for("A").state, JobState.FAILED)

    def test_terminal_to_active_creates_new_job_with_rerun_link(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        self.projection.observe("A", {"state": "queued"}, {"state": "running", "msg": "chạy"})
        self.projection.observe("A", {"state": "running"}, {"state": "done", "msg": "xong"})
        old = self.projection.job_for("A")
        self.projection.observe("A", {"state": "done"}, {"state": "queued", "msg": "tạo lại"})
        new = self.projection.job_for("A")
        self.assertNotEqual(new.job_id, old.job_id)
        self.assertEqual(new.rerun_of, old.job_id)
        self.assertEqual(new.state, JobState.QUEUED)
        self.assertEqual(new.version, 1)

    def test_first_running_write_is_reported_as_created_to_running_mismatch(self):
        self.projection.observe("A", None, {"state": "running", "msg": "chạy thẳng"})
        self.assertEqual(self.projection.job_for("A").state, JobState.CREATED)
        self.assertEqual(self.projection.diagnostics()["mismatches"], 1)

    def test_illegal_legacy_transition_records_mismatch_without_shadow_write(self):
        self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
        before = self.projection.job_for("A")
        self.projection.observe("A", {"state": "queued"}, {"state": "done", "msg": "xong"})
        self.assertEqual(self.projection.job_for("A"), before)
        diagnostics = self.projection.diagnostics()
        self.assertEqual(diagnostics["mismatches"], 1)
        self.assertEqual(diagnostics["recent_mismatches"][0]["legacy_key"], "A")
        self.assertNotIn("xong", str(diagnostics))
```

- [ ] **Step 2: Chạy test để xác nhận RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py -q`

Expected: collection FAIL vì `sfboard.jobs.projection` chưa tồn tại.

- [ ] **Step 3: Implement projection thuần, có lock riêng**

```python
# sfboard/jobs/projection.py
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Optional
from uuid import uuid4

from .manager import IllegalTransition, JobManager, TransitionCommand
from .models import (
    AssetId, EventActor, Job, JobId, JobKind, JobOrigin, JobState,
)
from .store import VersionConflict


LEGACY_STATE_MAP = {
    "queued": JobState.QUEUED,
    "running": JobState.RUNNING,
    "done": JobState.COMPLETED,
}
ACTIVE_STATES = {JobState.CREATED, JobState.QUEUED, JobState.RUNNING, JobState.RETRY_WAIT}
CANCEL_WORDS = (
    "đã huỷ", "đã hủy", "đã dừng", "huỷ riêng", "hủy riêng", "chưa chạy",
)


@dataclass(frozen=True)
class ShadowMismatch:
    legacy_key: str
    current_state: JobState
    target_state: JobState
    reason_code: str


def _target(value) -> Optional[JobState]:
    if not isinstance(value, dict):
        return None
    state = str(value.get("state") or "")
    if state != "error":
        return LEGACY_STATE_MAP.get(state)
    message = str(value.get("msg") or "").lower()
    return JobState.CANCELLED if any(word in message for word in CANCEL_WORDS) else JobState.FAILED


def _reason(value, target: JobState) -> str:
    state = str(value.get("state") or "") if isinstance(value, dict) else "unknown"
    return f"legacy.{state}.{target.value}"


class LegacyShadowProjection:
    def __init__(
        self, manager: JobManager, kind_resolver: Callable[[str], JobKind],
        mismatch_sink: Optional[Callable[[ShadowMismatch], None]] = None,
    ) -> None:
        self._manager = manager
        self._kind_resolver = kind_resolver
        self._mismatch_sink = mismatch_sink
        self._lock = RLock()
        self._job_ids: dict[str, JobId] = {}
        self._observed_writes = 0
        self._mismatch_count = 0
        self._mismatches: deque[ShadowMismatch] = deque(maxlen=20)

    def job_for(self, legacy_key: str) -> Job:
        with self._lock:
            return self._manager.get(self._job_ids[legacy_key])

    def _start_job(
        self, key: str, previous: Optional[Job], reason: str,
    ) -> Job:
        job = Job(
            JobId.new(), AssetId(key), self._kind_resolver(key),
            JobOrigin.COMPATIBILITY,
            rerun_of=previous.job_id if previous else None,
        )
        self._manager.create_job(job, uuid4(), EventActor.MANAGER, reason)
        self._job_ids[key] = job.job_id
        return job

    def _record_mismatch(self, mismatch: ShadowMismatch) -> None:
        self._mismatch_count += 1
        self._mismatches.append(mismatch)
        if self._mismatch_sink is not None:
            self._mismatch_sink(mismatch)

    def observe(self, key: str, old_value, new_value) -> None:
        target = _target(new_value)
        if target is None:
            return
        with self._lock:
            self._observed_writes += 1
            current = None
            if key in self._job_ids:
                current = self._manager.get(self._job_ids[key])
            reason = _reason(new_value, target)
            if current is None or (current.state.is_terminal and target in ACTIVE_STATES):
                current = self._start_job(key, current, reason)
            if current.state is target:
                self._manager.record_progress(
                    current.job_id, uuid4(), EventActor.MANAGER,
                    "legacy.progress", reason,
                )
                return
            command = TransitionCommand(
                current.job_id, current.version, target, EventActor.MANAGER,
                "legacy.transition", reason, uuid4(),
            )
            try:
                self._manager.transition(command)
            except (IllegalTransition, VersionConflict):
                self._record_mismatch(ShadowMismatch(
                    key, current.state, target, reason,
                ))

    def diagnostics(self) -> dict:
        with self._lock:
            return {
                "mode": "shadow",
                "observed_writes": self._observed_writes,
                "tracked_jobs": len(self._job_ids),
                "mismatches": self._mismatch_count,
                "recent_mismatches": [
                    {
                        "legacy_key": item.legacy_key,
                        "from": item.current_state.value,
                        "to": item.target_state.value,
                        "reason_code": item.reason_code,
                    }
                    for item in self._mismatches
                ],
            }
```

Export projection symbols trong `sfboard/jobs/__init__.py`.

- [ ] **Step 4: Chạy projection tests để xác nhận GREEN**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py -q`

Expected: 8 tests PASS; diagnostic không chứa legacy `msg`.

- [ ] **Step 5: Commit pure projection**

```bash
git add sfboard/jobs/projection.py sfboard/jobs/__init__.py tests/job_lifecycle/test_legacy_projection.py
git commit -m "feat: project legacy jobs into shadow core"
```

---

### Task 4: Fail-open observer tại legacy write boundary

**Files:**
- Modify: `sfboard/hangdoi.py:35-175`
- Modify: `tests/job_lifecycle/helpers.py:28-43`
- Modify: `tests/job_lifecycle/test_legacy_projection.py`

**Interfaces:**
- Consumes: `LegacyShadowProjection.observe(key, old_value, new_value)` từ Task 3.
- Produces: `hangdoi.gan_shadow_observer(observer_or_none) -> None`.
- Observer nhận bản sao old/new sau khi `_dong_dau` hoàn tất; không được mutate object trong `JOBS`.

- [ ] **Step 1: Thêm observer isolation tests**

```python
# append tests/job_lifecycle/test_legacy_projection.py
from helpers import load_hangdoi, reset_legacy_state


class LegacyObserverBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.h = load_hangdoi()
        reset_legacy_state(self.h)

    def tearDown(self):
        self.h.gan_shadow_observer(None)
        reset_legacy_state(self.h)

    def test_observer_runs_after_stamped_legacy_write(self):
        seen = []
        self.h.gan_shadow_observer(lambda key, old, new: seen.append((key, old, new)))
        self.h.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        self.assertEqual(seen[0][0], "A")
        self.assertIsNone(seen[0][1])
        self.assertIn("t", seen[0][2])
        self.assertEqual(self.h.JOBS["A"], seen[0][2])

    def test_observer_exception_never_blocks_legacy_write(self):
        def broken(_key, _old, _new):
            raise RuntimeError("shadow down")

        self.h.gan_shadow_observer(broken)
        self.h.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        self.assertEqual(self.h.JOBS["A"]["state"], "queued")

    def test_done_to_error_guard_does_not_emit_fake_shadow_write(self):
        seen = []
        self.h.gan_shadow_observer(lambda *args: seen.append(args))
        self.h.JOBS["A"] = {"state": "done", "msg": "xong"}
        seen.clear()
        self.h.JOBS["A"] = {"state": "error", "msg": "late"}
        self.assertEqual(seen, [])
        self.assertEqual(self.h.JOBS["A"]["state"], "done")
```

- [ ] **Step 2: Chạy observer tests để xác nhận RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py::LegacyObserverBoundaryTest -q`

Expected: FAIL với `AttributeError: module 'hangdoi' has no attribute 'gan_shadow_observer'`.

- [ ] **Step 3: Thêm observer sau legacy commit**

Trong `_Jobs` thêm class attribute:

```python
shadow_observer = None
```

Trong `__setitem__`, lấy old snapshot ngay đầu hàm và gọi observer chỉ sau `super().__setitem__(k, v)`:

```python
old_for_shadow = self.get(k)
if isinstance(old_for_shadow, dict):
    old_for_shadow = dict(old_for_shadow)

# giữ nguyên toàn bộ guard, _dong_dau, khi_loi và super().__setitem__ hiện có
super().__setitem__(k, v)

try:
    if self.shadow_observer:
        new_for_shadow = dict(v) if isinstance(v, dict) else v
        self.shadow_observer(k, old_for_shadow, new_for_shadow)
except Exception:
    pass  # shadow tuyệt đối không đổi legacy behavior
```

Ngay sau khai báo `JOBS` thêm API gắn observer:

```python
def gan_shadow_observer(observer) -> None:
    JOBS.shadow_observer = observer
```

Trong `reset_legacy_state` thêm trước khi clear globals:

```python
if hasattr(module, "gan_shadow_observer"):
    module.gan_shadow_observer(None)
```

- [ ] **Step 4: Chạy observer và legacy characterization tests**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py tests/job_lifecycle/test_queue_characterization.py tests/job_lifecycle/test_lo_member_labels.py -q`

Expected: tất cả PASS; `dat_job("LO:A,B")` phát observer riêng cho lô và từng member nhưng legacy values không đổi.

- [ ] **Step 5: Commit observer boundary**

```bash
git add sfboard/hangdoi.py tests/job_lifecycle/helpers.py tests/job_lifecycle/test_legacy_projection.py
git commit -m "feat: observe legacy job writes fail-open"
```

---

### Task 5: Startup mode và `/api/chan-doan` shadow diagnostics

**Files:**
- Modify: `sfboard/sfboard.py:1207-1245,4223-4239,5221-5292`
- Modify: `tests/job_lifecycle/test_legacy_projection.py`
- Modify: `tests/job_lifecycle/test_http_contract.py`

**Interfaces:**
- Consumes: `MemoryJobStore`, `JobManager`, `LegacyShadowProjection`, `hangdoi.gan_shadow_observer`.
- Produces: `_init_job_shadow(mode=None)`, `_job_shadow_diagnostics()` và diagnostic field `job_shadow`.
- Unsupported/invalid mode phải warning rồi giữ `legacy`; Phase 2 không có đường `authoritative`.

- [ ] **Step 1: Viết startup/diagnostic tests**

```python
# append tests/job_lifecycle/test_legacy_projection.py
from helpers import FakeBoard, ROOT, function_source, load_sfboard


class ShadowStartupTest(unittest.TestCase):
    def setUp(self):
        self.m = load_sfboard()
        self.board_old = self.m.BOARD
        self.m.BOARD = FakeBoard()
        self.m._init_job_shadow("legacy")

    def tearDown(self):
        self.m._init_job_shadow("legacy")
        self.m.BOARD = self.board_old

    def test_default_legacy_mode_has_no_observer(self):
        result = self.m._init_job_shadow("legacy")
        self.assertIsNone(result)
        self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
        self.assertEqual(self.m._job_shadow_diagnostics()["mode"], "legacy")

    def test_shadow_mode_attaches_projection_without_queue_dependency(self):
        projection = self.m._init_job_shadow("shadow")
        self.assertIsNotNone(projection)
        self.m.JOBS["A"] = {"state": "queued", "msg": "chờ"}
        diag = self.m._job_shadow_diagnostics()
        self.assertEqual(diag["mode"], "shadow")
        self.assertEqual(diag["tracked_jobs"], 1)

    def test_authoritative_or_unknown_mode_fails_safe_to_legacy(self):
        self.assertIsNone(self.m._init_job_shadow("authoritative"))
        self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
        self.assertEqual(self.m._job_shadow_diagnostics()["mode"], "legacy")

    def test_main_initializes_shadow_before_worker_threads(self):
        source = function_source(ROOT / "sfboard/sfboard.py", "main")
        self.assertLess(
            source.index("_init_job_shadow()"),
            source.index("threading.Thread(target=_supervisor"),
        )
```

Trong `test_http_contract.py`, thêm assertion vào test `/api/chan-doan` hiện có hoặc tạo test handler mới:

```python
handler = make_handler(self.m, "/api/chan-doan")
handler.do_GET()
code, payload = handler.captured
self.assertEqual(code, 200)
self.assertIn("job_shadow", payload)
self.assertIn(payload["job_shadow"]["mode"], {"legacy", "shadow"})
```

- [ ] **Step 2: Chạy startup tests để xác nhận RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py::ShadowStartupTest tests/job_lifecycle/test_http_contract.py -q`

Expected: FAIL vì `_init_job_shadow`, `_job_shadow_diagnostics` và response field chưa tồn tại.

- [ ] **Step 3: Implement fail-safe startup wiring**

Đặt cạnh `_LOG` và các runtime diagnostic helpers:

```python
_JOB_MODE = "legacy"
_JOB_SHADOW = None


def _job_shadow_diagnostics() -> dict:
    if _JOB_SHADOW is None:
        return {
            "mode": _JOB_MODE,
            "observed_writes": 0,
            "tracked_jobs": 0,
            "mismatches": 0,
            "recent_mismatches": [],
        }
    return _JOB_SHADOW.diagnostics()


def _init_job_shadow(mode=None):
    global _JOB_MODE, _JOB_SHADOW
    selected = str(mode or os.environ.get("GROKPIPE_JOB_MODE", "legacy")).strip().lower()
    hangdoi.gan_shadow_observer(None)
    _JOB_SHADOW = None
    if selected != "shadow":
        if selected != "legacy":
            _LOG.warning("job mode %r chưa được Phase 2 hỗ trợ — giữ legacy", selected)
        _JOB_MODE = "legacy"
        return None

    from jobs.manager import JobManager
    from jobs.models import JobKind
    from jobs.projection import LegacyShadowProjection
    from jobs.store import MemoryJobStore

    def kind_of(legacy_key):
        if legacy_key.startswith("LO:"):
            return JobKind.IMAGE
        return JobKind.VIDEO if _loai_viec(legacy_key) == "vid" else JobKind.IMAGE

    def log_mismatch(item):
        _LOG.warning(
            "shadow lifecycle lệch %s: %s → %s (%s)",
            item.legacy_key, item.current_state.value,
            item.target_state.value, item.reason_code,
        )

    projection = LegacyShadowProjection(
        JobManager(MemoryJobStore()), kind_of, log_mismatch,
    )
    hangdoi.gan_shadow_observer(projection.observe)
    _JOB_MODE = "shadow"
    _JOB_SHADOW = projection
    return projection
```

Trong `main`, gọi sau `BOARD = Board(film)` và trước mọi worker thread:

```python
BOARD = Board(film)
_init_job_shadow()
```

Trong `/api/chan-doan` response thêm:

```python
"job_shadow": _job_shadow_diagnostics(),
```

- [ ] **Step 4: Chạy startup, HTTP contract và full Phase 2 targeted tests**

Run:

```bash
./.venv/bin/python3 -m pytest \
  tests/job_lifecycle/test_store.py \
  tests/job_lifecycle/test_manager_transitions.py \
  tests/job_lifecycle/test_legacy_projection.py \
  tests/job_lifecycle/test_http_contract.py -q
```

Expected: tất cả PASS; không có Chrome process mới; default test process kết thúc với observer đã reset.

- [ ] **Step 5: Commit startup wiring**

```bash
git add sfboard/sfboard.py tests/job_lifecycle/test_legacy_projection.py tests/job_lifecycle/test_http_contract.py
git commit -m "feat: wire optional job shadow mode"
```

---

### Task 6: Static authority guard, documentation và Phase 2 gate

**Files:**
- Modify: `tests/job_lifecycle/test_current_state_writers.py`
- Modify: `docs/JOB-LIFECYCLE-README.md`
- Verify: toàn bộ Phase 2 diff.

**Interfaces:**
- Consumes: tất cả deliverable Task 1–5.
- Produces: executable guard rằng shadow core không có queue/provider/account authority và README ghi đúng migration phase.

- [ ] **Step 1: Viết static boundary test trước**

```python
# thêm method này bên trong CurrentStateWriterInventoryTest
    def test_phase2_shadow_core_has_no_production_authority(self):
        jobs_dir = ROOT / "sfboard/jobs"
        source = "\n".join(
            (jobs_dir / name).read_text(encoding="utf-8")
            for name in ("store.py", "manager.py", "projection.py")
        )
        forbidden = (
            "IMG_QUEUE", "VID_QUEUE", "CHO_RIENG", "_xep(", "_worker(",
            "_xoay_chrome(", "playwright", "generate_lo", "_gen_video(",
        )
        found = [marker for marker in forbidden if marker in source]
        self.assertEqual(found, [], f"Shadow core giành production authority: {found}")
```

- [ ] **Step 2: Chạy guard test và xác nhận GREEN với code Phase 2**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_current_state_writers.py -q`

Expected: PASS; nếu FAIL phải loại dependency vi phạm, không nới forbidden list.

- [ ] **Step 3: Cập nhật lifecycle entrypoint sau khi targeted suite xanh**

Đổi phần “Đọc trong 60 giây” của `docs/JOB-LIFECYCLE-README.md` thành nội dung chính xác:

```markdown
- Current phase: **Phase 2 shadow foundation đã triển khai; chưa cutover**.
- Production authority vẫn là legacy: `JOBS`, `PriorityQueue`, worker, retry và auto.
- Shadow `MemoryJobStore`/`JobManager` chỉ mirror legacy write và báo mismatch;
  không enqueue, gọi provider, retry hoặc cấp tài khoản.
- Bốn known ambiguity vẫn được khóa bằng `expectedFailure` và chỉ sửa ở phase tương ứng.
```

Ghi rõ `GROKPIPE_JOB_MODE=shadow` là opt-in nội bộ; không thêm hướng dẫn chạy live
provider vào README. Fake workload trong test là bằng chứng Phase 2 mặc định.

- [ ] **Step 4: Chạy full lifecycle/compile gate**

Run: `./test-job-lifecycle.command | tee /tmp/grokpipe-phase2-gate.log`

Expected:

- exit code `0`;
- ít nhất `361 passed` cộng các test Phase 2 mới;
- đúng `4 xfailed`, không `xpassed`;
- coverage `sfboard.jobs >= 80%`;
- dòng cuối `Job lifecycle gate: PASS`;
- compile legacy runtime và domain package thành công.

- [ ] **Step 5: Chạy structural authority audit và đọc diff**

Run:

```bash
ast-grep -p '_xep($QUEUE, $ITEM)' --lang python sfboard/jobs
rg -n 'IMG_QUEUE|VID_QUEUE|CHO_RIENG|_xoay_chrome|playwright|generate_lo|_gen_video' \
  sfboard/jobs/store.py sfboard/jobs/manager.py sfboard/jobs/projection.py
git diff --check
git diff --stat
git diff -- sfboard/jobs sfboard/hangdoi.py sfboard/sfboard.py tests/job_lifecycle docs/JOB-LIFECYCLE-README.md
```

Expected: hai lệnh authority search không có output; `git diff --check` sạch; diff chỉ chứa Phase 2 files và observer/startup/diagnostic wiring đã liệt kê.

- [ ] **Step 6: Commit gate/docs và cập nhật Bead**

```bash
git add tests/job_lifecycle/test_current_state_writers.py docs/JOB-LIFECYCLE-README.md
git commit -m "test: gate phase 2 shadow authority"
bd update beads-foundation-7lt.7 \
  --notes="$(tail -n 12 /tmp/grokpipe-phase2-gate.log)" \
  --json
```

Không đóng Bead nếu full gate, static guard hoặc fake shadow workload chưa đạt acceptance criteria.

---

## Phase 2 completion checkpoint

Trước khi lập plan Phase 3, xác nhận tất cả điều kiện sau:

- `GROKPIPE_JOB_MODE` mặc định là `legacy`.
- `shadow` mirror được fake workload nhưng không đổi legacy snapshot.
- Observer exception không chặn legacy write.
- Legal transition table và CAS race tests xanh.
- Không module Phase 2 nào có queue/provider/account authority.
- `/api/chan-doan.job_shadow` chỉ chứa metadata đã lọc.
- Full gate xanh và vẫn đúng bốn `xfail`.
- Board live hiện tại chưa bị restart/cutover.
- Bead `beads-foundation-7lt.7` có evidence và chỉ được close khi các điều kiện trên đều đạt.
