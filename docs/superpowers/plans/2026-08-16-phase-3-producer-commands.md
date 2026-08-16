# Phase 3 Producer Commands Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hợp nhất mọi producer ảnh/video qua command service có idempotency và một legacy enqueue adapter, để request lặp không tạo queue action trùng và multi-copy có Job identity riêng.

**Architecture:** `ProducerService` thuần tạo Job/Batch intent trong `MemoryJobStore`; `LegacyEnqueueAdapter` là ranh giới duy nhất chuyển intent sang các callback legacy được inject. `legacy` giữ queue/worker/executor hiện tại và không tạo core intent; `shadow` tạo intent, bind projection rồi mới giao đúng legacy action, còn `authoritative` vẫn bị từ chối.

**Tech Stack:** Python 3 dataclass/Enum/Protocol/RLock/SHA-256, `unittest`, HTTP handler harness, JavaScript `crypto.randomUUID`, AST characterization gate, Beads.

## Global Constraints

- Current production authority trước và sau Phase 3 vẫn là legacy: `JOBS`, `PriorityQueue`, worker, retry, auto execution và account allocation.
- Không thêm Scheduler, lease, `execution_id`, retry writer, account writer, durable outbox hoặc persistence.
- `sfboard/jobs/producer.py` không import `hangdoi`, HTTP, queue, executor, account registry, Playwright hoặc provider.
- `sfboard/jobs/compat.py` chỉ gọi dependency đã inject; không tự import runtime legacy.
- Default `GROKPIPE_JOB_MODE=legacy`; `shadow` là opt-in; `authoritative` và mode lạ fail-safe về `legacy`.
- API cũ giữ nguyên status/field; chỉ thêm `job_id`, `job_ids`, `batch_id`, `replayed`.
- Fingerprint không chứa prompt, cookie, token, media, DSN, base64 hoặc đường dẫn asset nhạy cảm.
- Test mặc định không mở Chrome, không gọi provider và không tiêu credit.
- Hạ đúng hai `expectedFailure`: auto-video duplicate và multi-copy identity; giữ đúng hai xfail cancel identity/forced-account retry.
- Sau mọi thay đổi lifecycle chạy targeted test; gate cuối bắt buộc `./test-job-lifecycle.command`, coverage `sfboard.jobs >= 80%`, compile PASS và static authority guard PASS.

## File Map

- Create `sfboard/jobs/producer.py`: request/result types, canonical fingerprint, active-scope semantics và command API.
- Create `sfboard/jobs/compat.py`: typed legacy delivery plan và per-intent delivery serialization.
- Modify `sfboard/jobs/store.py`: atomic intent/batch storage, exact-key replay/conflict và active-scope index.
- Modify `sfboard/jobs/projection.py`: bind một legacy key tới một hoặc nhiều command-created Job.
- Modify `sfboard/jobs/__init__.py`: export public Phase 3 API.
- Modify `sfboard/sfboard.py`: runtime initialization, injected adapter callbacks, common producer helper, năm HTTP route và `_auto_scene`.
- Modify `sfboard/ui/board.js`: tạo `Idempotency-Key` theo từng user action mà không đổi UI.
- Create `sfboard/ui/job-request.js`: helper request nhỏ, chạy được cả browser và Node behavior test.
- Modify `sfboard/ui/index.html`: nạp helper trước `board.js`.
- Modify `sfboard/chay-anh.py`: giữ key ổn định qua network retry và xoay key khi explicit rerun sau terminal error.
- Create `tests/job_lifecycle/test_producer.py`: command/idempotency/active-scope/rerun/batch tests.
- Create `tests/job_lifecycle/test_legacy_adapter.py`: adapter concurrency, partial delivery và legacy equivalence.
- Modify `tests/job_lifecycle/test_store.py`: atomic store tests.
- Modify `tests/job_lifecycle/test_legacy_projection.py`: binding/group/multi-copy tests và startup wiring.
- Modify `tests/job_lifecycle/test_create_endpoint.py`: HTTP duplicate, response metadata, key precedence, batch identity.
- Modify `tests/job_lifecycle/test_http_contract.py`: additive response schema and 400/409/500 mapping.
- Modify `tests/job_lifecycle/test_auto_characterization.py`: chuyển hai Phase 3 xfail thành regression xanh.
- Modify `tests/job_lifecycle/test_current_state_writers.py`: guard dependency và producer authority mới.
- Create `tests/job_lifecycle/test_client_idempotency.py`: static contracts cho `board.js` và `chay-anh.py`.
- Modify `docs/JOB-LIFECYCLE-README.md` và `docs/JOB-MIGRATION-PLAN.md`: cập nhật phase/evidence/rollback.

---

### Task 1: Atomic Intent and Batch Store

**Files:**
- Modify: `sfboard/jobs/store.py`
- Modify: `sfboard/jobs/__init__.py`
- Modify: `tests/job_lifecycle/test_store.py`

**Interfaces:**
- Consumes: `Job`, `JobEvent`, `JobId`, `Batch`, `BatchId`, `JobState` từ `sfboard/jobs/models.py`.
- Produces: `IdempotencyRecord`, `IntentWriteResult`, `IdempotencyConflict`, `ActiveJobConflict`; `JobStore.create_intent/get_intent/mark_intent_delivered/get_batch/latest_for_scope`.

- [ ] **Step 1: Viết test đỏ cho replay, conflict và atomic batch**

Thêm imports `Batch`, `BatchId`, `BatchMode` và các type store mới, rồi thêm các test sau vào `MemoryJobStoreTest`:

```python
def make_intent(key, fingerprint, scope, jobs, batch=None):
    return IdempotencyRecord(
        key=key,
        fingerprint=fingerprint,
        scope_fingerprint=scope,
        job_ids=tuple(job.job_id for job in jobs),
        batch_id=batch.batch_id if batch else None,
        delivered=False,
    )


def test_intent_same_key_and_fingerprint_replays_original_jobs(self):
    job = make_job()
    event = make_event(job, reason="producer.create")
    record = make_intent("key-1", "fp-1", "scope-1", (job,))
    first = self.store.create_intent(record, None, ((job, event),))
    replay = self.store.create_intent(record, None, ((job, event),))
    self.assertFalse(first.replayed)
    self.assertTrue(replay.replayed)
    self.assertEqual(replay.jobs, (job,))
    self.assertEqual(self.store.events_for(job.job_id), (event,))


def test_intent_same_key_with_changed_fingerprint_conflicts_without_write(self):
    first = make_job()
    self.store.create_intent(
        make_intent("key-1", "fp-1", "scope-1", (first,)),
        None,
        ((first, make_event(first)),),
    )
    changed = make_job()
    with self.assertRaises(IdempotencyConflict):
        self.store.create_intent(
            make_intent("key-1", "fp-2", "scope-2", (changed,)),
            None,
            ((changed, make_event(changed)),),
        )
    self.assertIsNone(self.store.get(changed.job_id))


def test_batch_validation_failure_writes_no_member(self):
    one, two = make_job(), make_job()
    batch = Batch(
        BatchId.new(), JobKind.IMAGE, BatchMode.IMAGE_GROUP,
        (one.job_id, two.job_id),
    )
    wrong_event = make_event(one)
    with self.assertRaises(StoreInvariantError):
        self.store.create_intent(
            make_intent("batch-1", "fp-b", "scope-b", (one, two), batch),
            batch,
            ((one, make_event(one)), (two, wrong_event)),
        )
    self.assertIsNone(self.store.get(one.job_id))
    self.assertIsNone(self.store.get(two.job_id))
    self.assertIsNone(self.store.get_batch(batch.batch_id))


def test_mark_delivered_updates_original_key_and_scope_alias(self):
    job = make_job()
    first = make_intent("key-1", "fp-1", "scope-1", (job,))
    self.store.create_intent(first, None, ((job, make_event(job)),))
    alias_job = make_job()
    alias = make_intent("key-2", "fp-1", "scope-1", (alias_job,))
    replay = self.store.create_intent(alias, None, ((alias_job, make_event(alias_job)),))
    self.assertTrue(replay.replayed)
    self.store.mark_intent_delivered("key-2")
    self.assertTrue(self.store.get_intent("key-1").delivered)
    self.assertTrue(self.store.get_intent("key-2").delivered)


def test_active_scope_with_changed_payload_is_conflict(self):
    first = make_job()
    self.store.create_intent(
        make_intent("key-1", "fp-1", "scope-1", (first,)),
        None,
        ((first, make_event(first)),),
    )
    changed = replace(make_job(), forced_account_id="account-two")
    with self.assertRaises(ActiveJobConflict):
        self.store.create_intent(
            make_intent("key-2", "fp-2", "scope-1", (changed,)),
            None,
            ((changed, make_event(changed)),),
        )
    self.assertIsNone(self.store.get(changed.job_id))
```

- [ ] **Step 2: Chạy test và xác nhận đỏ đúng nguyên nhân**

Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py -q
```

Expected: FAIL tại import `IdempotencyRecord`/`IdempotencyConflict` vì API intent chưa tồn tại.

- [ ] **Step 3: Thêm immutable records, exceptions và protocol methods**

Trong `store.py`, thêm:

```python
class IdempotencyConflict(JobStoreError):
    pass


class ActiveJobConflict(JobStoreError):
    pass


@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    fingerprint: str
    scope_fingerprint: str
    job_ids: Tuple[JobId, ...]
    batch_id: Optional[BatchId]
    delivered: bool


@dataclass(frozen=True)
class IntentWriteResult:
    record: IdempotencyRecord
    jobs: Tuple[Job, ...]
    batch: Optional[Batch]
    replayed: bool
```

`scope_fingerprint` là field bổ sung cần thiết để store thực hiện atomic active-scope dedupe; nó chỉ là SHA-256 structural scope, không chứa payload thô.

Mở rộng `JobStore`:

```python
def create_intent(
    self,
    record: IdempotencyRecord,
    batch: Optional[Batch],
    jobs_and_events: Tuple[Tuple[Job, JobEvent], ...],
) -> IntentWriteResult: ...

def get_intent(self, key: str) -> Optional[IdempotencyRecord]: ...
def mark_intent_delivered(self, key: str) -> IdempotencyRecord: ...
def get_batch(self, batch_id: BatchId) -> Optional[Batch]: ...
def latest_for_scope(self, scope_fingerprint: str) -> Optional[IdempotencyRecord]: ...
```

- [ ] **Step 4: Implement atomic create/replay/scope alias**

Thêm store fields:

```python
self._batches: dict[BatchId, Batch] = {}
self._intents: dict[str, IdempotencyRecord] = {}
self._scope_intents: dict[str, str] = {}
```

Implement `create_intent` theo thứ tự validate-all-then-write:

```python
def create_intent(self, record, batch, jobs_and_events):
    with self._lock:
        exact = self._intents.get(record.key)
        if exact is not None:
            if exact.fingerprint != record.fingerprint:
                raise IdempotencyConflict(record.key)
            return self._intent_result(exact, replayed=True)

        scope_key = self._scope_intents.get(record.scope_fingerprint)
        if scope_key is not None:
            scoped = self._intents[scope_key]
            scoped_jobs = tuple(self._jobs[job_id] for job_id in scoped.job_ids)
            incoming_origin = jobs_and_events[0][0].origin
            blocks_new = incoming_origin is JobOrigin.AUTO or any(
                job.state in {
                    JobState.CREATED, JobState.QUEUED, JobState.RUNNING,
                    JobState.RETRY_WAIT, JobState.NEEDS_ATTENTION,
                }
                for job in scoped_jobs
            )
            if blocks_new:
                if scoped.fingerprint != record.fingerprint:
                    raise ActiveJobConflict(record.scope_fingerprint)
                self._intents[record.key] = scoped
                return IntentWriteResult(
                    scoped, scoped_jobs,
                    self._batches.get(scoped.batch_id) if scoped.batch_id else None,
                    True,
                )

        self._validate_intent(record, batch, jobs_and_events)
        for job, event in jobs_and_events:
            self._jobs[job.job_id] = job
            self._events[job.job_id] = [event]
            self._event_results[event.event_id] = StoreWriteResult(job, event, True)
        if batch is not None:
            self._batches[batch.batch_id] = batch
        self._intents[record.key] = record
        self._scope_intents[record.scope_fingerprint] = record.key
        return IntentWriteResult(record, tuple(j for j, _ in jobs_and_events), batch, False)
```

`_validate_intent` phải kiểm tra: non-empty key/fingerprints/job_ids, ordered `record.job_ids` khớp tuple job, không trùng JobId/EventId, mọi Job là `CREATED version=0`, create event khớp Job và `from_state is None`, batch id/members khớp record/jobs, và không có Job/Batch/Event cũ. Không mutate bất kỳ dict nào trước khi tất cả check đã qua.

`mark_intent_delivered` dùng `replace(record, delivered=True)` và cập nhật mọi alias có `value.key == record.key`; `get_*` đọc dưới cùng `RLock`. `latest_for_scope` resolve `_scope_intents[scope_fingerprint]` về immutable record hiện tại, không trả dict nội bộ.

- [ ] **Step 5: Chạy store tests và type/compile check**

Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py -q
./.venv/bin/python3 -m compileall -q sfboard/jobs
```

Expected: toàn bộ test PASS; compile exit 0.

- [ ] **Step 6: Export API và commit**

Export sáu Phase 3 symbols mới từ `sfboard/jobs/__init__.py`, rồi:

```bash
git add sfboard/jobs/store.py sfboard/jobs/__init__.py tests/job_lifecycle/test_store.py
git commit -m "feat: add atomic producer intent store"
```

---

### Task 2: Producer Service, Fingerprints and Rerun Semantics

**Files:**
- Create: `sfboard/jobs/producer.py`
- Modify: `sfboard/jobs/__init__.py`
- Create: `tests/job_lifecycle/test_producer.py`

**Interfaces:**
- Consumes: `JobStore.create_intent/mark_intent_delivered`, `Job`, `Batch`, typed IDs và enums.
- Produces: `CreateJobRequest`, `CreateBatchRequest`, `ProducerResult`, `ProducerService.create_job/create_batch/rerun_job/mark_delivered`.

- [ ] **Step 1: Viết test đỏ cho key replay, concurrent scope dedupe và rerun**

Tạo `test_producer.py` với fixture:

```python
def image_request(asset="SF-S1-01", *, origin=JobOrigin.MANUAL, manual=True):
    return CreateJobRequest(
        asset_id=AssetId(asset),
        kind=JobKind.IMAGE,
        origin=origin,
        request_scope="project-a:http.generate",
        manual=manual,
    )


def terminal_job(job, store, target):
    manager = JobManager(store)
    current = job
    for state in (JobState.QUEUED, JobState.RUNNING, target):
        result = manager.transition(TransitionCommand(
            current.job_id,
            current.version,
            state,
            EventActor.MANAGER,
            "test.transition",
            "test.terminal",
            uuid4(),
        ))
        current = result.job
    return current


class ProducerServiceTest(unittest.TestCase):
    def setUp(self):
        self.store = MemoryJobStore()
        self.service = ProducerService(self.store)

    def test_same_key_replays_same_job(self):
        first = self.service.create_job(image_request(), "key-1")
        replay = self.service.create_job(image_request(), "key-1")
        self.assertEqual(replay.jobs, first.jobs)
        self.assertTrue(replay.replayed)

    def test_same_key_changed_request_raises_idempotency_conflict(self):
        self.service.create_job(image_request("SF-S1-01"), "key-1")
        with self.assertRaises(IdempotencyConflict):
            self.service.create_job(image_request("SF-S1-02"), "key-1")

    def test_two_keys_same_active_scope_return_one_job(self):
        out = []
        barrier = threading.Barrier(2)
        def create(key):
            barrier.wait()
            out.append(self.service.create_job(image_request(), key))
        threads = [threading.Thread(target=create, args=(key,)) for key in ("a", "b")]
        for thread in threads: thread.start()
        for thread in threads: thread.join(2)
        self.assertEqual(len({result.jobs[0].job_id for result in out}), 1)
        self.assertEqual(sum(not result.replayed for result in out), 1)

    def test_manual_after_terminal_creates_rerun_link(self):
        first = self.service.create_job(image_request(), "key-1")
        terminal_job(first.jobs[0], self.store, JobState.COMPLETED)
        rerun = self.service.create_job(image_request(), "key-2")
        self.assertNotEqual(rerun.jobs[0].job_id, first.jobs[0].job_id)
        self.assertEqual(rerun.jobs[0].rerun_of, first.jobs[0].job_id)

    def test_auto_after_failed_replays_terminal_job(self):
        request = image_request(origin=JobOrigin.AUTO, manual=False)
        first = self.service.create_job(request)
        terminal_job(first.jobs[0], self.store, JobState.FAILED)
        replay = self.service.create_job(request)
        self.assertEqual(replay.jobs[0].job_id, first.jobs[0].job_id)
        self.assertTrue(replay.replayed)
```

Helper trên tạo legal transition events qua `JobManager`; test không ghi snapshot trực tiếp.

- [ ] **Step 2: Viết test đỏ cho atomic batch và multi-copy identity**

```python
def test_multi_copy_creates_distinct_children_and_ordered_copy_indexes(self):
    member = image_request()
    result = self.service.create_batch(
        CreateBatchRequest((member, member, member), BatchMode.MULTI_COPY),
        "multi-1",
    )
    self.assertEqual(len({job.job_id for job in result.jobs}), 3)
    self.assertEqual(tuple(job.copy_index for job in result.jobs), (0, 1, 2))
    self.assertEqual(result.batch.member_job_ids, tuple(job.job_id for job in result.jobs))


def test_image_group_rejects_duplicate_asset_without_store_write(self):
    member = image_request()
    with self.assertRaises(ValueError):
        self.service.create_batch(
            CreateBatchRequest((member, member), BatchMode.IMAGE_GROUP),
            "group-1",
        )
    self.assertIsNone(self.store.get_intent("group-1"))
```

- [ ] **Step 3: Chạy producer tests và xác nhận đỏ**

Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_producer.py -q
```

Expected: FAIL vì `sfboard.jobs.producer` chưa tồn tại.

- [ ] **Step 4: Implement request/result types và canonical hashes**

Tạo `producer.py` với dataclasses đúng spec. Canonical payload phải là primitives duy nhất:

```python
def _canonical(requests, mode):
    return {
        "assets": [str(request.asset_id) for request in requests],
        "kinds": [request.kind.value for request in requests],
        "origins": [request.origin.value for request in requests],
        "scopes": [request.request_scope for request in requests],
        "mode": mode.value if mode else None,
        "manual": [request.manual for request in requests],
        "replace": [request.replace_current for request in requests],
        "forced_accounts": [request.forced_account_id for request in requests],
        "fallback": [request.allow_account_fallback for request in requests],
    }


def _digest(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

`scope_fingerprint` dùng project/request scope, kinds, ordered assets, batch mode và số copies; không dùng origin/manual/key. Validate `request_scope.strip()`, origin/manual consistency, forced-account fallback và đồng nhất kind trong batch.

- [ ] **Step 5: Implement create, active replay, explicit rerun và delivery marker**

Job construction:

```python
job = Job(
    job_id=JobId.new(),
    asset_id=request.asset_id,
    kind=request.kind,
    origin=request.origin,
    batch_id=batch_id,
    rerun_of=rerun_of,
    copy_index=copy_index,
    replace_current=request.replace_current,
    forced_account_id=request.forced_account_id,
    allow_account_fallback=request.allow_account_fallback,
)
event = JobEvent(
    uuid4(), job.job_id, EventActor.MANAGER,
    "producer.created", "producer.accepted",
)
```

Key resolution:

```python
if idempotency_key:
    key = _validate_key(idempotency_key)
elif all(request.origin is JobOrigin.AUTO for request in requests):
    key = "auto:" + scope_fingerprint
else:
    key = "request:" + uuid4().hex
```

Sau `create_intent`, dựng `ProducerResult` từ `IntentWriteResult`, đặt `delivery_required = not write.record.delivered`. Khi store trả một terminal manual scope cũ và key mới, set `rerun_of` về latest scoped Job trước khi atomic write; expose một read-only `latest_for_scope(scope_fingerprint)` trong store để lookup này nằm dưới lock, rồi `create_intent` tái kiểm scope trong cùng critical section. `rerun_job` bắt buộc old Job terminal, request asset/kind khớp old Job, key explicit non-empty.

- [ ] **Step 6: Chạy targeted tests và static forbidden-import check**

Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py tests/job_lifecycle/test_producer.py -q
./.venv/bin/python3 - <<'PY'
import ast
from pathlib import Path
p = Path('sfboard/jobs/producer.py')
t = ast.parse(p.read_text(encoding='utf-8'))
bad = {'hangdoi', 'http', 'playwright', 'provider', 'queue', 'requests', 'urllib'}
found = []
for node in ast.walk(t):
    if isinstance(node, ast.Import):
        names = [a.name for a in node.names]
    elif isinstance(node, ast.ImportFrom):
        names = [node.module or '']
    else:
        names = []
    found.extend(name for name in names if set(name.split('.')) & bad)
assert not found, found
PY
```

Expected: PASS và không có forbidden import.

- [ ] **Step 7: Export API và commit**

```bash
git add sfboard/jobs/producer.py sfboard/jobs/store.py sfboard/jobs/__init__.py tests/job_lifecycle/test_producer.py tests/job_lifecycle/test_store.py
git commit -m "feat: add idempotent producer commands"
```

---

### Task 3: Projection Binding to Command-Created Jobs

**Files:**
- Modify: `sfboard/jobs/projection.py`
- Modify: `tests/job_lifecycle/test_legacy_projection.py`

**Interfaces:**
- Consumes: command-created Job IDs already present in `JobManager.store`.
- Produces: `LegacyShadowProjection.bind(legacy_key: str, job_ids: Tuple[JobId, ...]) -> None`; `jobs_for(legacy_key) -> Tuple[Job, ...]`.

- [ ] **Step 1: Viết binding regression tests**

Đặt hai helper sau trong test module:

```python
def make_domain_job(asset):
    return Job(
        JobId.new(), AssetId(asset), JobKind.IMAGE, JobOrigin.MANUAL,
    )


def make_and_create(manager, asset):
    job = make_domain_job(asset)
    manager.create_job(job, uuid4(), EventActor.MANAGER, "producer.accepted")
    return job
```

```python
def test_bind_reuses_command_created_job(self):
    job = make_domain_job("A")
    self.manager.create_job(job, uuid4(), EventActor.MANAGER, "producer.accepted")
    self.projection.bind("A", (job.job_id,))
    self.projection.observe("A", None, {"state": "queued", "msg": "chờ"})
    self.assertEqual(self.projection.job_for("A").job_id, job.job_id)


def test_group_binding_projects_write_to_each_member(self):
    jobs = tuple(make_and_create(self.manager, asset) for asset in ("A", "B"))
    self.projection.bind("LO:A,B", tuple(job.job_id for job in jobs))
    self.projection.observe("LO:A,B", None, {"state": "queued", "msg": "chờ"})
    self.assertEqual(
        tuple(job.state for job in self.projection.jobs_for("LO:A,B")),
        (JobState.QUEUED, JobState.QUEUED),
    )


def test_active_binding_collision_records_mismatch_and_keeps_original(self):
    first = make_and_create(self.manager, "A")
    second = make_and_create(self.manager, "A")
    self.projection.bind("A", (first.job_id,))
    self.projection.bind("A", (second.job_id,))
    self.assertEqual(self.projection.job_for("A").job_id, first.job_id)
    self.assertEqual(self.projection.diagnostics()["mismatches"], 1)
```

- [ ] **Step 2: Chạy test và xác nhận đỏ tại missing bind/jobs_for**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py -q
```

- [ ] **Step 3: Đổi internal mapping sang tuple và implement bind**

Thay `_job_ids: dict[str, JobId]` bằng `_job_ids: dict[str, Tuple[JobId, ...]]`. `job_for` giữ backward compatibility bằng member đầu; `jobs_for` trả đủ members.

`bind` dưới projection lock:

```python
def bind(self, legacy_key, job_ids):
    if not legacy_key or not job_ids or len(set(job_ids)) != len(job_ids):
        raise ValueError("projection binding không hợp lệ")
    jobs = tuple(self._manager.get(job_id) for job_id in job_ids)
    current_ids = self._job_ids.get(legacy_key)
    if current_ids is not None and current_ids != job_ids:
        current = tuple(self._manager.get(job_id) for job_id in current_ids)
        if any(not job.state.is_terminal for job in current):
            self._record_mismatch(ShadowMismatch(
                legacy_key, current[0].state, jobs[0].state,
                "projection.bind_active_collision",
            ))
            return
    self._job_ids[legacy_key] = tuple(job_ids)
```

Refactor `observe` thành vòng lặp qua bound Job IDs. Nếu chưa bind, `_start_job` vẫn tạo đúng một compatibility Job. Với bound group, same-state write ghi progress cho từng Job; transition dùng CAS riêng từng member; một member conflict chỉ ghi mismatch và không cản member còn lại.

- [ ] **Step 4: Chạy projection + manager/store tests**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py tests/job_lifecycle/test_manager_transitions.py tests/job_lifecycle/test_store.py -q
```

Expected: PASS; legacy first-write bootstrap và terminal-rerun tests cũ vẫn xanh.

- [ ] **Step 5: Commit**

```bash
git add sfboard/jobs/projection.py tests/job_lifecycle/test_legacy_projection.py
git commit -m "feat: bind legacy projection to producer jobs"
```

---

### Task 4: Single Legacy Enqueue Adapter

**Files:**
- Create: `sfboard/jobs/compat.py`
- Modify: `sfboard/jobs/__init__.py`
- Create: `tests/job_lifecycle/test_legacy_adapter.py`

**Interfaces:**
- Consumes: `ProducerResult`; injected state/enqueue/bind/mark callbacks.
- Produces: `LegacyAction`, `LegacyPlan`, `LegacyDeliveryResult`, `LegacyEnqueueAdapter.deliver` và `deliver_legacy`.

- [ ] **Step 1: Viết adapter tests cho concurrency và replay**

Tạo fake callbacks ghi `(action_key, queue_ident)` và các factories:

```python
def make_producer_result(key, count=1):
    jobs = tuple(
        Job(JobId.new(), AssetId(f"A-{index}"), JobKind.IMAGE, JobOrigin.MANUAL)
        for index in range(count)
    )
    return ProducerResult(jobs, None, key, False, True)


def make_two_job_result(key):
    return make_producer_result(key, count=2)


def make_two_action_plan(result):
    return LegacyPlan(tuple(
        LegacyAction(
            action_id=f"member-{index}",
            legacy_keys=(str(job.asset_id),),
            job_ids=(job.job_id,),
            queue_kind="img",
            queue_ident="LO:" + str(job.asset_id),
            manual=True,
            state={"state": "queued", "msg": "chờ"},
        )
        for index, job in enumerate(result.jobs)
    ))


def make_legacy_plan():
    return LegacyPlan((
        LegacyAction(
            action_id="legacy-0", legacy_keys=("A",), job_ids=(),
            queue_kind="img", queue_ident="LO:A", manual=True,
            state={"state": "queued", "msg": "chờ"},
        ),
    ))
```

Sau đó thêm tests:

```python
def test_two_threads_deliver_one_intent_once(self):
    result = make_producer_result("intent-1")
    plan = LegacyPlan((
        LegacyAction(
            action_id="member-0", legacy_keys=("A",), job_ids=(result.jobs[0].job_id,),
            queue_kind="img", queue_ident="LO:A", manual=True,
            state={"state": "queued", "msg": "chờ · 1 ảnh"},
        ),
    ))
    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=lambda: (barrier.wait(), self.adapter.deliver(result, plan))) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(2)
    self.assertEqual(self.enqueued, [("intent-1:member-0:enqueue", "LO:A")])
    self.assertEqual(self.marked, ["intent-1"])


def test_partial_failure_retries_only_unconfirmed_action(self):
    result = make_two_job_result("intent-2")
    plan = make_two_action_plan(result)
    self.fail_once_on = "intent-2:member-1:enqueue"
    with self.assertRaises(RuntimeError):
        self.adapter.deliver(result, plan)
    self.adapter.deliver(result, plan)
    self.assertEqual(self.counts["intent-2:member-0:enqueue"], 1)
    self.assertEqual(self.counts["intent-2:member-1:enqueue"], 2)
    self.assertEqual(self.marked, ["intent-2"])


def test_legacy_delivery_does_not_dedupe_distinct_calls(self):
    plan = make_legacy_plan()
    self.adapter.deliver_legacy(plan)
    self.adapter.deliver_legacy(plan)
    self.assertEqual(len(self.enqueued), 2)
```

- [ ] **Step 2: Chạy test và xác nhận đỏ**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_adapter.py -q
```

- [ ] **Step 3: Implement typed plan and per-key locking**

Public dataclasses:

```python
@dataclass(frozen=True)
class LegacyAction:
    action_id: str
    legacy_keys: Tuple[str, ...]
    job_ids: Tuple[JobId, ...]
    queue_kind: str
    queue_ident: str
    manual: bool
    state: Optional[Mapping[str, object]] = None
    forced_account_id: Optional[str] = None


@dataclass(frozen=True)
class LegacyPlan:
    actions: Tuple[LegacyAction, ...]


@dataclass(frozen=True)
class LegacyDeliveryResult:
    delivered: bool
    replayed: bool
    completed_action_ids: Tuple[str, ...]
```

Constructor callback signatures:

```python
LegacyEnqueueAdapter(
    set_job_state: Callable[[str, Mapping[str, object], str], None],
    enqueue_image: Callable[[str, bool, str], None],
    enqueue_video: Callable[[str, bool, str], None],
    enqueue_private_image: Callable[[str, str, bool, str], None],
    bind_projection: Callable[[str, Tuple[JobId, ...]], None],
    mark_delivered: Callable[[str], None],
)
```

`deliver` lấy lock từ `_locks[idempotency_key]`, skip nếu `result.delivery_required` false hoặc key trong `_delivered`, bind mọi legacy key trước state/queue, và ghi `_completed_steps` chỉ sau callback return thành công. `deliver_legacy` chạy cùng `_run_action` nhưng dùng nonce mới và không đọc/ghi `_delivered`.

- [ ] **Step 4: Validate plan trước side effect**

Trước callback đầu tiên, reject empty plan, duplicate `action_id`, kind ngoài `img/vid`, empty queue ident/legacy key/job_ids trong shadow delivery, forced account trên video, và member JobId không thuộc `ProducerResult.jobs`. Validation failure không gọi callback nào.

- [ ] **Step 5: Chạy tests và forbidden-import check**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_adapter.py tests/job_lifecycle/test_producer.py -q
./.venv/bin/python3 - <<'PY'
import ast
from pathlib import Path
p = Path('sfboard/jobs/compat.py')
t = ast.parse(p.read_text(encoding='utf-8'))
imports = []
for n in ast.walk(t):
    if isinstance(n, ast.Import): imports += [a.name for a in n.names]
    if isinstance(n, ast.ImportFrom): imports += [n.module or '']
assert not any(x.split('.')[0] in {'hangdoi', 'sfboard'} for x in imports), imports
PY
```

- [ ] **Step 6: Export and commit**

```bash
git add sfboard/jobs/compat.py sfboard/jobs/__init__.py tests/job_lifecycle/test_legacy_adapter.py
git commit -m "feat: add single legacy enqueue adapter"
```

---

### Task 5: Runtime Initialization and Common Producer Boundary

**Files:**
- Modify: `sfboard/sfboard.py`
- Modify: `tests/job_lifecycle/test_legacy_projection.py`
- Modify: `tests/job_lifecycle/helpers.py`

**Interfaces:**
- Consumes: `ProducerService`, `LegacyEnqueueAdapter`, shared `MemoryJobStore`, `JobManager`, projection.
- Produces: `_JOB_PRODUCER`, `_JOB_ADAPTER`, `_init_job_shadow`, `_producer_submit`, `_producer_metadata`, `_request_idempotency_key`.

- [ ] **Step 1: Viết startup tests cho one-store wiring và fail-safe legacy**

```python
def test_shadow_runtime_shares_store_between_producer_and_projection(self):
    projection = self.m._init_job_shadow("shadow")
    self.assertIs(projection._manager.store, self.m._JOB_PRODUCER.store)
    self.assertIsNotNone(self.m._JOB_ADAPTER)


def test_legacy_runtime_has_adapter_but_no_producer_intent_service(self):
    self.m._init_job_shadow("legacy")
    self.assertIsNotNone(self.m._JOB_ADAPTER)
    self.assertIsNone(self.m._JOB_PRODUCER)


def test_reinit_failure_clears_all_shadow_components(self):
    self.m._init_job_shadow("shadow")
    with patch("jobs.producer.ProducerService", side_effect=RuntimeError("no core")):
        self.assertIsNone(self.m._init_job_shadow("shadow"))
    self.assertEqual(self.m._JOB_MODE, "legacy")
    self.assertIsNone(self.m._JOB_PRODUCER)
    self.assertIsNone(self.m.hangdoi.JOBS.shadow_observer)
    self.assertIsNotNone(self.m._JOB_ADAPTER)
```

- [ ] **Step 2: Chạy startup tests và xác nhận đỏ**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py -q
```

- [ ] **Step 3: Initialize adapter in both modes, core only in shadow**

Thêm globals `_JOB_PRODUCER = None`, `_JOB_ADAPTER = None`. Tách `_make_legacy_adapter(projection=None, producer=None)`; injected callbacks là:

```python
set_job_state=lambda ident, state, _action_key: _dat_job(ident, dict(state))
enqueue_image=lambda ident, manual, _action_key: _xep(
    IMG_QUEUE, ("img", ident, 0, manual)
)
enqueue_video=lambda ident, manual, _action_key: _xep(
    VID_QUEUE, ("vid", ident, 0, manual)
)
enqueue_private_image=_legacy_enqueue_private_image
bind_projection=(projection.bind if projection else lambda _key, _ids: None)
mark_delivered=(producer.mark_delivered if producer else lambda _key: None)
```

`_legacy_enqueue_private_image` giữ đúng representation thật của `CHO_RIENG` là `port -> list[ident]`: convert port, append `ident` dưới `_CR_LOCK`, rồi sort bằng `_uu_tien`. Legacy callback queue vẫn dùng đúng tuple cũ. Không thêm queue/retry/account authority trong core modules.

`_init_job_shadow` luôn dựng legacy adapter; chỉ khi selected=`shadow` mới dựng một `MemoryJobStore`, một `JobManager`, projection và `ProducerService` dùng cùng store. Exception reset mode/observer/producer rồi dựng lại adapter legacy.

- [ ] **Step 4: Add common dispatch helpers**

`_request_idempotency_key` precedence:

```python
def _request_idempotency_key(handler, query, raw):
    header = (handler.headers.get("Idempotency-Key") or "").strip()
    if header:
        return header
    query_key = (query.get("idempotency_key", [""])[0] or "").strip()
    if query_key:
        return query_key
    if raw:
        try:
            body = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(body, dict):
            return str(body.get("idempotency_key") or "").strip() or None
    return None
```

`_producer_submit(request_or_batch, idempotency_key, plan_factory)`:

```python
if _JOB_ADAPTER is None:
    _init_job_shadow(_JOB_MODE)
if _JOB_MODE == "shadow" and _JOB_PRODUCER is not None:
    result = (
        _JOB_PRODUCER.create_batch(request_or_batch, idempotency_key)
        if isinstance(request_or_batch, CreateBatchRequest)
        else _JOB_PRODUCER.create_job(request_or_batch, idempotency_key)
    )
    _JOB_ADAPTER.deliver(result, plan_factory(result))
    return result
_JOB_ADAPTER.deliver_legacy(plan_factory(None))
return None
```

`_producer_metadata(None)` trả `job_id=None`, `job_ids=[]`, `batch_id=None`, `replayed=False`; shadow result stringify typed IDs.

- [ ] **Step 5: Update reset helper and run startup/legacy regression**

`reset_legacy_state` gọi `_init_job_shadow("legacy")` nếu module có helper này, rồi mới clear legacy collections. Run:

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_legacy_projection.py tests/job_lifecycle/test_queue_characterization.py -q
```

- [ ] **Step 6: Commit**

```bash
git add sfboard/sfboard.py tests/job_lifecycle/test_legacy_projection.py tests/job_lifecycle/helpers.py
git commit -m "feat: wire producer runtime behind legacy mode gate"
```

---

### Task 6: Migrate Five HTTP Producers

**Files:**
- Modify: `sfboard/sfboard.py`
- Modify: `tests/job_lifecycle/test_create_endpoint.py`
- Modify: `tests/job_lifecycle/test_http_contract.py`

**Interfaces:**
- Consumes: common runtime helpers from Task 5.
- Produces: all five producer routes through `_producer_submit`; additive metadata and deterministic 400/409/500 mapping.

- [ ] **Step 1: Viết HTTP shadow tests cho duplicate và metadata**

Trong test setup bật `self.m._init_job_shadow("shadow")`; teardown trả legacy. Thêm:

```python
def test_generate_same_key_returns_same_job_and_one_queue_action(self):
    first = self.goi("/api/generate?sf=SF-S1-01&idempotency_key=click-1")
    second = self.goi("/api/generate?sf=SF-S1-01&idempotency_key=click-1")
    self.assertEqual(first[1]["job_id"], second[1]["job_id"])
    self.assertFalse(first[1]["replayed"])
    self.assertTrue(second[1]["replayed"])
    self.assertEqual(self.m.IMG_QUEUE.qsize(), 1)


def test_header_key_wins_over_query_key(self):
    handler = make_handler(self.m, "/api/generate?sf=SF-S1-01&idempotency_key=query")
    handler.headers["Idempotency-Key"] = "header"
    handler.do_POST()
    self.assertIsNotNone(self.m._JOB_PRODUCER.store.get_intent("header"))
    self.assertIsNone(self.m._JOB_PRODUCER.store.get_intent("query"))


def test_generate_multi_copy_returns_distinct_job_ids_and_one_batch(self):
    code, body = self.goi("/api/generate?sf=SF-S1-01&n=3&idempotency_key=multi")
    self.assertEqual(code, 200)
    self.assertEqual(len(body["job_ids"]), 3)
    self.assertEqual(len(set(body["job_ids"])), 3)
    self.assertIsNotNone(body["batch_id"])
    self.assertEqual(self.m.IMG_QUEUE.qsize(), 3)
```

- [ ] **Step 2: Viết route coverage cho master/tao-lo/genvideo/video-lo**

Mỗi route có một test shadow giữ field cũ (`so`, `ds`, `lo`, `bo`, `qua_lo`, `so_ban`) và assert thêm metadata. FakeBoard video fixture trả shot có prompt và start-frame file giả để `/api/genvideo` không chạm provider.

Concurrent double-click test dùng hai Handler thread cùng `Idempotency-Key` và assert một queue tuple, cùng `job_ids`.

- [ ] **Step 3: Chạy HTTP tests và xác nhận đỏ**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_create_endpoint.py tests/job_lifecycle/test_http_contract.py -q
```

- [ ] **Step 4: Migrate `/api/generate` and `/api/master`**

Giữ nguyên validation/board mutation/cancel clearing. Sau validation dựng request scope bằng real board identity và route:

```python
CreateJobRequest(
    AssetId(sf_id), JobKind.IMAGE, JobOrigin.MANUAL,
    request_scope=f"{_board_identity()}:http.generate",
    manual=True, replace_current=True,
)
```

`n == 1` dùng single request; `n > 1` dùng `CreateBatchRequest(tuple(request for _ in range(n)), BatchMode.MULTI_COPY)`. Plan có one action per copy, cùng physical `queue_ident="LO:" + sf_id`, và bind `sf_id`/`LO:sf_id` tới toàn bộ child Job IDs. Chỉ action đầu ghi aggregate `JOBS` state; cả N action enqueue đúng N tuple legacy.

`/api/master?chay=1` dùng `BatchMode.IMAGE_GROUP`, mỗi member action queue riêng `LO:<id>`.

- [ ] **Step 5: Migrate `/api/tao-lo`, `/api/genvideo`, `/api/video-lo`**

`/api/tao-lo`: giữ grouping/chunking hiện tại; một command batch chứa ordered unique member asset; mỗi physical lô thành one action, bind `LO:a,b` tới member Job IDs thuộc lô và mỗi member key tới Job tương ứng. Nếu request hiện tại có `ep`, set `forced_account_id=str(ep)` trên mọi member và plan dùng callback private-image để giữ đúng `CHO_RIENG[port] = [ident]` cũ.

`/api/genvideo`: single `JobKind.VIDEO`; action state `queued`, queue ident shot id.

`/api/video-lo`: one `BatchMode.BULK_VIDEO`; each shot one action; current skip counts remain unchanged.

Mọi success response merge `{**legacy_body, **_producer_metadata(result)}`.

- [ ] **Step 6: Map typed errors without side effects**

Bao `_producer_submit` bằng one helper trả:

```python
except IdempotencyConflict as exc:
    self._json({"ok": False, "err": "idempotency key đã dùng cho yêu cầu khác"}, 409)
except ActiveJobConflict as exc:
    self._json({"ok": False, "err": "đã có việc đang hoạt động trong phạm vi này"}, 409)
except (TypeError, ValueError) as exc:
    self._json({"ok": False, "err": str(exc)}, 400)
except Exception as exc:
    report_runtime_bug({
        "category": "producer_delivery", "severity": "ERROR",
        "job": {"kind": kind, "phase": "delivery"}, "exc": exc,
    })
    self._json({"ok": False, "err": "không giao được việc sang hàng đợi"}, 500)
```

Không đưa raw request/key/prompt vào runtime bug payload.

- [ ] **Step 7: Run HTTP, queue, stop and retry regressions**

```bash
./.venv/bin/python3 -m pytest \
  tests/job_lifecycle/test_create_endpoint.py \
  tests/job_lifecycle/test_http_contract.py \
  tests/job_lifecycle/test_queue_characterization.py \
  tests/job_lifecycle/test_stop_cancel_endpoints.py \
  tests/job_lifecycle/test_retry_properties.py -q
```

Expected: PASS; default legacy queue tuple snapshots unchanged.

- [ ] **Step 8: Commit**

```bash
git add sfboard/sfboard.py tests/job_lifecycle/test_create_endpoint.py tests/job_lifecycle/test_http_contract.py
git commit -m "feat: route http producers through command boundary"
```

---

### Task 7: Migrate Auto Producer and Turn Two Xfails Green

**Files:**
- Modify: `sfboard/sfboard.py`
- Modify: `tests/job_lifecycle/test_auto_characterization.py`
- Modify: `tests/job_lifecycle/test_ref_run_all.py`

**Interfaces:**
- Consumes: `_producer_submit`, existing `AUTO_LOCK` generation barrier và task grouping.
- Produces: stable auto scopes; no queued/running/terminal-failed revive; no direct auto `_xep`/`_enqueue` producer call.

- [ ] **Step 1: Replace source-only xfail assertions with behavioral regressions**

Bỏ decorator `@unittest.expectedFailure` khỏi đúng hai Phase 3 tests. Auto-video test phải set `JOBS[shot]` lần lượt `queued` và `running`, gọi `_auto_scene`, assert `VID_QUEUE.qsize() == 0` và `_auto_allow` không tăng try.

Multi-copy test gọi shadow `/api/generate?n=3`, assert three distinct `job_ids`, one `batch_id`, three legacy queue items và replay cùng key không tăng queue size.

- [ ] **Step 2: Add terminal-failed auto tests**

Thêm board inert vào test module:

```python
class _ReadyVideoBoard:
    path = __file__

    def __init__(self, scene):
        self.scene = scene

    def read(self):
        return {"scenes": [self.scene]}

    def find_file(self, _asset_id):
        return "/fake/start-frame.png"

    def video_file(self, _shot_id):
        return None
```

Regression dùng projection thật để lấy Job identity và legacy write thật để đưa Job về terminal:

```python
def test_auto_video_failed_intent_is_not_revived_by_next_scan(self):
    shot = {"id": "V-S1-01", "sf": "SF-S1-01", "prompt": "move"}
    scene = {"id": "S1", "sfs": [], "shots": [shot]}
    state = {"try": {}, "last": {}, "stat": {}}
    self.m.BOARD = _ReadyVideoBoard(scene)
    self.m._auto_vid_doc = lambda: True
    self.m._init_job_shadow("shadow")
    with self.m.AUTO_LOCK:
        self.m.AUTO[scene["id"]] = state
    self.m._auto_scene(scene, state, 1)
    first_job = self.m._JOB_SHADOW.job_for(shot["id"])
    self.m._dat_job(shot["id"], {"state": "error", "msg": "provider failed"})
    while not self.m.VID_QUEUE.empty():
        self.m.VID_QUEUE.get_nowait()
        self.m.VID_QUEUE.task_done()
    self.m._auto_scene(scene, state, 20)
    self.assertEqual(self.m.VID_QUEUE.qsize(), 0)
    self.assertEqual(self.m._JOB_SHADOW.job_for(shot["id"]).job_id, first_job.job_id)
```

Thêm image-group case với scene `{"id": "S1", "sfs": [{"id": "SF-S1-01", "refs": {}}], "shots": []}`: scan lần đầu, lấy projection Job, ghi legacy `error`, drain `IMG_QUEUE`, scan ở cycle 20, rồi assert queue vẫn 0 và JobId không đổi. Giữ stop-generation race test cũ nguyên vẹn.

- [ ] **Step 3: Chạy auto tests và xác nhận đỏ đúng Phase 3 behavior**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_auto_characterization.py tests/job_lifecycle/test_ref_run_all.py -q
```

- [ ] **Step 4: Route auto image batches through producer inside existing barrier**

Trong mỗi `with AUTO_LOCK` commit block, sau generation/identity recheck, dựng `CreateBatchRequest(mode=IMAGE_GROUP)` với scope:

```python
f"{_board_identity()}:auto:{sc['id']}:image:{m}:{','.join(lo)}"
```

Plan giữ exact legacy state message và queue ident `LO:`. Chỉ tăng `_auto_allow(..., ghi=True)` cho member khi `result is None` (legacy) hoặc `not result.replayed` (shadow).

- [ ] **Step 5: Route auto video through producer and block both active labels**

Giữ fast legacy label guard:

```python
if JOBS.get(sh["id"], {}).get("state") in ("running", "queued"):
    continue
```

Sau đó submit `CreateJobRequest(origin=AUTO, manual=False)` với stable scope:

```python
f"{_board_identity()}:auto:{sc['id']}:video:{sh['id']}"
```

Adapter action queue kind `vid`, ident shot id. Chỉ ghi auto attempt/log khi delivery thực sự mới; replay active/failed không gọi queue callback.

- [ ] **Step 6: Run auto + stop + property tests**

```bash
./.venv/bin/python3 -m pytest \
  tests/job_lifecycle/test_auto_characterization.py \
  tests/job_lifecycle/test_ref_run_all.py \
  tests/job_lifecycle/test_stop_cancel_endpoints.py \
  tests/job_lifecycle/test_queue_properties.py -q
```

Expected: PASS và không còn expectedFailure trong hai test Phase 3.

- [ ] **Step 7: Commit**

```bash
git add sfboard/sfboard.py tests/job_lifecycle/test_auto_characterization.py tests/job_lifecycle/test_ref_run_all.py
git commit -m "fix: make auto producer idempotent"
```

---

### Task 8: Client Idempotency Keys Without UI Changes

**Files:**
- Create: `sfboard/ui/job-request.js`
- Modify: `sfboard/ui/board.js`
- Modify: `sfboard/ui/index.html`
- Modify: `sfboard/chay-anh.py`
- Create: `tests/job_lifecycle/test_client_idempotency.py`

**Interfaces:**
- Consumes: server `Idempotency-Key` support and additive response metadata.
- Produces: `GrokpipeJobRequest.postJob(path, key, fetchImpl)`; Python `post(path, idempotency_key)` và `RequestKeys` lifecycle.

- [ ] **Step 1: Write executable client request-behavior tests**

```python
def test_browser_helper_sends_the_supplied_key_and_returns_response_body():
    program = r"""
const { postJob } = require('./sfboard/ui/job-request.js');
const calls = [];
const fakeFetch = async (path, options) => {
  calls.push({ path, options });
  return { json: async () => ({ ok: true, job_id: 'job-1' }) };
};
(async () => {
  const result = await postJob('/api/generate?sf=A', 'stable-key', fakeFetch);
  if (calls.length !== 1) process.exit(10);
  if (calls[0].options.headers['Idempotency-Key'] !== 'stable-key') process.exit(11);
  if (result.body.job_id !== 'job-1' || result.key !== 'stable-key') process.exit(12);
})().catch(() => process.exit(13));
"""
    completed = subprocess.run(
        ["node", "-e", program], cwd=ROOT, capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_cli_post_sends_the_supplied_key(monkeypatch):
    module = load_chay_anh_module()
    seen = []
    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen(seen))
    body = module.post("/api/generate?sf=A", "stable-key")
    assert seen[0].get_header("Idempotency-key") == "stable-key"
    assert body == {"ok": True, "job_id": "job-1"}


def test_cli_request_key_is_stable_until_explicit_rotation():
    module = load_chay_anh_module()
    keys = module.RequestKeys(lambda: iter(("key-1", "key-2")).__next__())
    assert keys.for_asset("A") == "key-1"
    assert keys.for_asset("A") == "key-1"
    assert keys.rotate("A") == "key-2"
    assert keys.for_asset("A") == "key-2"
```

`load_chay_anh_module` dùng `importlib.util.spec_from_file_location`; `fake_urlopen` trả context manager có `read()` là JSON `{"ok": true, "job_id": "job-1"}`. Test HTML parse `sfboard/ui/index.html` và assert script `job-request.js` đứng trước `board.js`, vì sai thứ tự sẽ làm browser không có global helper.

- [ ] **Step 2: Run and confirm red**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_client_idempotency.py -q
```

- [ ] **Step 3: Add browser/Node helper and migrate only producer fetches**

Tạo `sfboard/ui/job-request.js`:

```javascript
function createJobRequestApi(root) {
  function newJobKey() {
    return root.crypto.randomUUID();
  }

  async function postJob(path, key = newJobKey(), fetchImpl = root.fetch) {
    const response = await fetchImpl(path, {
    method: 'POST',
    headers: { 'Idempotency-Key': key },
    });
    return { key, response, body: await response.json() };
  }

  return { newJobKey, postJob };
}

const GrokpipeJobRequest = createJobRequestApi(globalThis);
if (typeof module !== 'undefined' && module.exports) module.exports = GrokpipeJobRequest;
globalThis.GrokpipeJobRequest = GrokpipeJobRequest;
```

Nạp file này trước `board.js`, rồi destructure `const { newJobKey, postJob } = GrokpipeJobRequest;` ở đầu `board.js`. Mỗi click/bulk action tạo key một lần trước request. Các vòng gọi nhiều shot tạo một key riêng cho từng shot và giữ nó trong biến tới khi request settle. Không đổi text, DOM, layout hoặc visible flow.

- [ ] **Step 4: Add stable keys to `chay-anh.py`**

Đưa CLI execution vào `main(argv=None)` để import không chạy vòng lặp. Thêm:

```python
class RequestKeys:
    def __init__(self, factory=lambda: uuid.uuid4().hex):
        self._factory = factory
        self._keys = {}

    def for_asset(self, asset_id):
        return self._keys.setdefault(asset_id, self._factory())

    def rotate(self, asset_id):
        self._keys[asset_id] = self._factory()
        return self._keys[asset_id]
```

Khởi tạo `IDEMPOTENCY = RequestKeys()` trong `main`. `post`:

```python
def post(path, idempotency_key):
    request = urllib.request.Request(
        API + path,
        method='POST',
        headers={'Idempotency-Key': idempotency_key},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)
```

Khi poll thấy terminal `error`, sau khi đếm đúng một lần, gọi `IDEMPOTENCY.rotate(i)` để lần intentional rerun có key mới. Network exception không đổi key. Khi POST thành công, đọc `job_id = result.get('job_id')` và log nếu có, fallback im lặng khi legacy trả null/không field.

- [ ] **Step 5: Run client and HTTP contract tests**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_client_idempotency.py tests/job_lifecycle/test_http_contract.py -q
node --check sfboard/ui/board.js
./.venv/bin/python3 -m py_compile sfboard/chay-anh.py
```

- [ ] **Step 6: Commit**

```bash
git add sfboard/ui/job-request.js sfboard/ui/index.html sfboard/ui/board.js sfboard/chay-anh.py tests/job_lifecycle/test_client_idempotency.py
git commit -m "feat: send stable producer idempotency keys"
```

---

### Task 9: Authority Guards, Documentation, Full Gate and Runtime Smoke

**Files:**
- Modify: `tests/job_lifecycle/test_current_state_writers.py`
- Modify: `docs/JOB-LIFECYCLE-README.md`
- Modify: `docs/JOB-MIGRATION-PLAN.md`
- Modify: `docs/JOB-LIFECYCLE-AUDIT.md`

**Interfaces:**
- Consumes: complete Phase 3 implementation.
- Produces: executable authority inventory, exact xfail count, migration evidence and rollback instructions.

- [ ] **Step 1: Write static guard before adjusting writer inventory**

Add AST test that scans `_auto_scene` and `Handler.do_POST` producer branches. It must fail on direct calls `_xep`/`_enqueue` and assignments to `JOBS[...]`; allowed call is `_producer_submit`. Scan new core files and reject imports/calls that claim queue/provider/account/executor authority. Keep legacy worker/retry markers unchanged.

```python
PRODUCER_ROUTES = {
    "/api/generate", "/api/master", "/api/tao-lo",
    "/api/genvideo", "/api/video-lo",
}


def _route_name(test):
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None
    left = test.left
    right = test.comparators[0] if test.comparators else None
    if (
        isinstance(test.ops[0], ast.Eq)
        and isinstance(left, ast.Attribute)
        and isinstance(left.value, ast.Name)
        and left.value.id == "u"
        and left.attr == "path"
        and isinstance(right, ast.Constant)
        and isinstance(right.value, str)
    ):
        return right.value
    return None


def producer_writer_violations(tree):
    targets = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_auto_scene":
            targets.append(("_auto_scene", node.body))
        if isinstance(node, ast.FunctionDef) and node.name == "do_POST":
            for branch in ast.walk(node):
                route = _route_name(branch.test) if isinstance(branch, ast.If) else None
                if route in PRODUCER_ROUTES:
                    targets.append((route, branch.body))

    violations = []
    for owner, statements in targets:
        for statement in statements:
            for node in ast.walk(statement):
                if isinstance(node, ast.Call):
                    name = (
                        node.func.id if isinstance(node.func, ast.Name)
                        else node.func.attr if isinstance(node.func, ast.Attribute)
                        else ""
                    )
                    if name in {"_xep", "_enqueue"}:
                        violations.append(f"{owner}:{node.lineno}:call {name}")
                if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                    assigned = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "JOBS"
                        for target in assigned
                    ):
                        violations.append(f"{owner}:{node.lineno}:write JOBS")
    return violations


def test_phase3_producers_use_one_compatibility_boundary(self):
    source = (ROOT / "sfboard/sfboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    violations = producer_writer_violations(tree)
    self.assertEqual(violations, [])
```

- [ ] **Step 2: Run guard and remove only obsolete producer writers**

```bash
./.venv/bin/python3 -m pytest tests/job_lifecycle/test_current_state_writers.py -q
```

Update `WRITER_CHO_PHEP` only after AST output proves which direct writes moved behind the adapter callback. Do not remove worker/result/retry/cancel writers belonging to later phases.

- [ ] **Step 3: Run focused Phase 3 suite**

```bash
./.venv/bin/python3 -m pytest \
  tests/job_lifecycle/test_store.py \
  tests/job_lifecycle/test_producer.py \
  tests/job_lifecycle/test_legacy_adapter.py \
  tests/job_lifecycle/test_legacy_projection.py \
  tests/job_lifecycle/test_create_endpoint.py \
  tests/job_lifecycle/test_http_contract.py \
  tests/job_lifecycle/test_auto_characterization.py \
  tests/job_lifecycle/test_client_idempotency.py \
  tests/job_lifecycle/test_current_state_writers.py -q
```

Expected: PASS, zero unexpected success/failure.

- [ ] **Step 4: Update lifecycle docs with exact authority and rollback**

README header becomes: Phase 3 producer command/idempotency triển khai trong shadow; production execution authority vẫn legacy; known ambiguity còn hai. Migration plan records commits/test counts. Audit moves five HTTP routes and auto producer to `ProducerService -> LegacyEnqueueAdapter`, while Scheduler/worker/retry/account/cancel remain legacy.

- [ ] **Step 5: Run full lifecycle/compile gate twice from clean process**

```bash
./test-job-lifecycle.command
./test-job-lifecycle.command
```

Expected both runs: exit 0, exactly `2 xfailed`, no `xpassed`, coverage `sfboard.jobs >= 80%`, compile PASS. Record exact pass count from output; do not infer it in advance.

- [ ] **Step 6: Inspect diff and verify no accidental authority expansion**

```bash
git status --short
git diff --check
git diff --stat 9fead78..HEAD
rg -n "_xep\(|_enqueue\(|JOBS\[" sfboard/sfboard.py
rg -n "playwright|connect_over_cdp|submit\(|PriorityQueue|CHO_RIENG" sfboard/jobs/producer.py sfboard/jobs/compat.py
```

Expected: only planned files changed; no whitespace errors; core producer has no production side effect; remaining legacy calls belong to worker/retry/cancel/callback wiring documented by AST guard.

- [ ] **Step 7: Commit docs/gates and request independent review**

```bash
git add tests/job_lifecycle/test_current_state_writers.py docs/JOB-LIFECYCLE-README.md docs/JOB-MIGRATION-PLAN.md docs/JOB-LIFECYCLE-AUDIT.md
git commit -m "docs: record phase 3 producer authority"
```

Use `superpowers:requesting-code-review`; reviewer compares range `9fead78..HEAD`, reruns focused/full gates and reports Critical/Important findings. Fix every valid Critical/Important through red-green TDD, rerun full gate, and request follow-up review until none remain.

- [ ] **Step 8: Restart board and perform inert runtime smoke**

Start board in `GROKPIPE_JOB_MODE=shadow` with the user's completed/empty queue. Smoke only:

```bash
curl -fsS http://localhost:8784/api/chan-doan
curl -fsS http://localhost:8784/api/jobs
```

Then use Handler/fake workload for duplicate POST; do not submit a real image/video provider task. Verify one queue action, same Job IDs on replay, diagnostics mode `shadow`, and no new runtime-bug event. Return board to the mode selected for deployment; if any duplicate/terminal revive/startup regression appears, set `GROKPIPE_JOB_MODE=legacy` and capture evidence before changing code.

- [ ] **Step 9: Close Bead only with evidence**

Attach exact full-gate output, review result, runtime smoke response summary and commit range to `beads-foundation-7lt.8`, then:

```bash
bd close beads-foundation-7lt.8 --reason="Phase 3 producer commands complete: full gate xanh với đúng 2 xfail, review không còn Critical/Important, inert runtime smoke pass"
```

Do not run `bd sync`, Git pull/push or any provider.
