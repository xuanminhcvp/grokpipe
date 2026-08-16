# Authoritative Lifecycle Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hoàn thiện durable job runtime để scheduler, retry, account, result và recovery có một authority, đồng thời giữ legacy mode làm rollback và không gọi live provider.

**Architecture:** `LifecycleRuntime` điều phối các policy thuần và một `SQLiteLifecycleRepository`. Scheduler dùng execution identity bền vững; legacy worker/executor được bọc bằng adapter và chỉ phát fact trong mode mới. Shadow chạy monitor thật; authoritative chỉ được kiểm bằng fake/inert workload trong kế hoạch này.

**Tech Stack:** Python 3.14, stdlib `sqlite3`, dataclass/enum hiện có, `unittest`/pytest, Hypothesis, HTTP handler harness giả.

## Global Constraints

- Không mở live Chrome/provider và không tiêu credit.
- Mặc định production vẫn là `legacy`; `shadow` chỉ quan sát; `authoritative` phải opt-in.
- Không thêm writer, retry timer hoặc re-enqueue authority mới.
- Mỗi behavior change phải có test fail đúng nguyên nhân trước implementation.
- Sau mỗi task chạy test mục tiêu; trước kết luận chạy `./test-job-lifecycle.command` và compile gate.
- `queue_ident` là compatibility label, không phải durable identity.

---

### Task 1: Durable execution identity và CAS

**Files:**
- Modify: `sfboard/jobs/persistence.py`
- Modify: `sfboard/jobs/scheduler.py`
- Modify: `tests/job_lifecycle/test_persistence.py`
- Modify: `tests/job_lifecycle/test_scheduler.py`

**Interfaces:**
- Produces: `DurableExecution.version`, `scope_key`, lease fields; `SqliteSchedule.insert`, `compare_and_set`, `load_active`.
- Preserves: `SqliteSchedule.upsert/pending/in_flight` compatibility cho test/caller cũ trong thời gian migration.

- [ ] **Step 1: Viết regression rerun không hồi sinh execution terminal**

```python
def test_rerun_same_queue_ident_keeps_new_execution_identity(self):
    self.s.upsert(exe("SF-A", execution_id="exec-old", state="finished"))
    self.s.upsert(exe("SF-A", execution_id="exec-new", state="ready"))
    rows = self.s.all_executions()
    self.assertEqual({r.execution_id for r in rows}, {"exec-old", "exec-new"})
```

- [ ] **Step 2: Chạy test và xác nhận RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_persistence.py::SqliteScheduleTest::test_rerun_same_queue_ident_keeps_new_execution_identity -q`

Expected: FAIL vì dòng `exec-old` bị đổi thành `ready` và `exec-new` mất.

- [ ] **Step 3: Thêm schema v2 và CAS**

`execution_id` giữ primary key. Thay unique toàn lịch sử bằng partial unique active
trên `(kind, scope_key)` với state `ready|waiting|leased`; thêm `version`, `seq`,
`lease_id`, `lease_expires_at`. Migration schema v1 phải giữ dữ liệu cũ.

- [ ] **Step 4: Test stale version và concurrent lease**

```python
with self.assertRaises(ScheduleVersionConflict):
    self.s.compare_and_set("exec-1", expected_version=0, state="finished")
```

Hai thread CAS cùng version chỉ một thread thắng.

- [ ] **Step 5: Chạy test mục tiêu và full scheduler/persistence**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_persistence.py tests/job_lifecycle/test_scheduler.py -q`

- [ ] **Step 6: Commit**

```bash
git add sfboard/jobs/persistence.py sfboard/jobs/scheduler.py tests/job_lifecycle/test_persistence.py tests/job_lifecycle/test_scheduler.py
git commit -m "fix: preserve durable execution identity"
```

### Task 2: Scheduler retry/release không mất dấu

**Files:**
- Modify: `sfboard/jobs/scheduler.py`
- Modify: `sfboard/sfboard.py`
- Create: `tests/job_lifecycle/test_scheduler_retry_wiring.py`
- Modify: `tests/job_lifecycle/test_current_state_writers.py`

**Interfaces:**
- Produces: `_lich_tra(lease, outcome, not_before)`; retry dùng `Scheduler.release`.
- Consumes: Task 1 CAS semantics.

- [ ] **Step 1: Viết integration regression cho retry timer**

```python
def test_worker_failure_releases_same_execution_instead_of_finishing_it(self):
    lease = board._lich_nhan("img", "LO:A")
    board._lich_tra(lease, outcome="retry", not_before=120.0)
    execution = board._JOB_SCHEDULER.get(lease.execution_id)
    self.assertEqual(execution.state, ExecutionState.READY)
    self.assertEqual(execution.not_before, 120.0)
```

- [ ] **Step 2: Chạy RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_scheduler_retry_wiring.py -q`

Expected: FAIL vì `_lich_tra` luôn `finish`.

- [ ] **Step 3: Tách outcome trong worker**

Success/cancel/final failure gọi `finish`; lỗi còn retry gọi `release(not_before)`.
Trong shadow/legacy, timer chỉ là transport compatibility và không được tạo execution
mới. Không đổi luật retry production ở task này.

- [ ] **Step 4: Test forced private retry và queue retry cùng giữ execution_id**

Assert cả `_legacy_enqueue_private_image` và `_xep` transport đều không làm lịch
thành FINISHED trong thời gian chờ.

- [ ] **Step 5: Chạy gate mục tiêu**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_scheduler_retry_wiring.py tests/job_lifecycle/test_retry_characterization.py tests/job_lifecycle/test_account_characterization.py -q`

- [ ] **Step 6: Commit**

```bash
git add sfboard/jobs/scheduler.py sfboard/sfboard.py tests/job_lifecycle/test_scheduler_retry_wiring.py tests/job_lifecycle/test_current_state_writers.py
git commit -m "fix: keep retry execution leased by scheduler"
```

### Task 3: SQLite JobStore dùng chung lifecycle repository

**Files:**
- Create: `sfboard/jobs/sqlite_store.py`
- Modify: `sfboard/jobs/store.py`
- Modify: `sfboard/jobs/persistence.py`
- Create: `tests/job_lifecycle/test_sqlite_store.py`
- Create: `tests/job_lifecycle/test_sqlite_concurrency.py`
- Modify: `test-job-lifecycle.command`

**Interfaces:**
- Produces: `SQLiteLifecycleRepository(path)` implementing `JobStore`, schedule persistence and `transaction()`.
- Consumes: domain `Job`, `Batch`, `JobEvent`, `IdempotencyRecord`, `DurableExecution`.

- [ ] **Step 1: Viết contract test chạy cùng bộ semantics của MemoryJobStore**

```python
class SQLiteStoreContract(StoreContractMixin, unittest.TestCase):
    def make_store(self):
        return SQLiteLifecycleRepository(self.path)
```

Contract gồm create/event replay, changed-payload conflict, CAS transition,
concurrent duplicate intent, batch, scope conflict và delivered alias.

- [ ] **Step 2: Chạy RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_sqlite_store.py -q`

Expected: collection/import FAIL vì repository chưa tồn tại.

- [ ] **Step 3: Implement normalized SQLite repository**

Tables lưu jobs, batches, events/result snapshots, intent records/aliases,
scope intents, executions và attempts. `transaction()` dùng `BEGIN IMMEDIATE` dưới
`RLock`; nested repository calls không commit nửa chừng. Schema version phải được
đọc/kiểm/migrate rõ ràng.

- [ ] **Step 4: Concurrency/fault tests**

```python
def test_two_connections_create_same_intent_only_one_physical_record(self):
    results = run_two_threads(lambda store: store.create_intent(*self.intent()))
    self.assertEqual(sum(not r.replayed for r in results), 1)

def test_event_and_transition_rollback_together_on_exception(self):
    with self.assertRaises(RuntimeError):
        with self.store.transaction():
            self.manager.transition(self.transition())
            raise RuntimeError("fault injection")
    self.assertEqual(self.manager.get(self.job_id).state, JobState.QUEUED)

def test_unknown_schema_version_fails_closed(self):
    write_schema_version(self.path, 999)
    with self.assertRaises(UnsupportedSchemaVersion):
        SQLiteLifecycleRepository(self.path)

def test_locked_database_reports_explicit_error(self):
    hold_immediate_transaction(self.path)
    with self.assertRaises(LifecycleDatabaseBusy):
        SQLiteLifecycleRepository(self.path, timeout=0.01).transaction().__enter__()
```

- [ ] **Step 5: Chạy store suites**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_store.py tests/job_lifecycle/test_sqlite_store.py tests/job_lifecycle/test_sqlite_concurrency.py -q`

- [ ] **Step 6: Commit**

```bash
git add sfboard/jobs/sqlite_store.py sfboard/jobs/store.py sfboard/jobs/persistence.py tests/job_lifecycle/test_sqlite_store.py tests/job_lifecycle/test_sqlite_concurrency.py test-job-lifecycle.command
git commit -m "feat: add transactional sqlite lifecycle repository"
```

### Task 4: LifecycleRuntime làm authority duy nhất

**Files:**
- Create: `sfboard/jobs/runtime.py`
- Create: `sfboard/jobs/facts.py`
- Modify: `sfboard/jobs/retry.py`
- Modify: `sfboard/jobs/accounts.py`
- Modify: `sfboard/jobs/results.py`
- Create: `tests/job_lifecycle/test_lifecycle_runtime.py`
- Create: `tests/job_lifecycle/test_lifecycle_runtime_concurrency.py`

**Interfaces:**
- Produces: `LifecycleRuntime.submit`, `lease_for_worker`, `attempt_phase`,
  `attempt_succeeded`, `attempt_failed`, `cancel`, `recover`.
- Runtime is the only component allowed to combine Manager/Scheduler/Policy mutations.

- [ ] **Step 1: Viết fake E2E create → lease → success**

```python
result = runtime.submit(request, "click-1", plan_factory)
lease = runtime.lease_for_worker("9222", JobKind.IMAGE, now=1)
runtime.attempt_succeeded(lease.lease_id, outputs=("a.png",), event_id=uuid4())
self.assertEqual(runtime.job(result.jobs[0].job_id).state, JobState.COMPLETED)
```

- [ ] **Step 2: Chạy RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_lifecycle_runtime.py -q`

- [ ] **Step 3: Implement coordinator và fact dataclasses**

`submit` tạo intent/jobs/executions trong repository transaction. Lease ghi Attempt
và account seat trước khi trả cho worker. Facts idempotent theo event id; runtime
áp transition + schedule/account/result trong một transaction/lock.

- [ ] **Step 4: Viết matrix retry/account/result**

Cover validation fail, quota cooldown, forced no-fallback, pre-submit reconnect,
post-submit unknown outcome, stale lease, user mutation và duplicate fact.

- [ ] **Step 5: Concurrency tests**

Hai worker không nhận cùng execution; hai result cùng lease chỉ một commit; cancel
đua success chỉ một terminal transition.

- [ ] **Step 6: Chạy runtime suites**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_lifecycle_runtime.py tests/job_lifecycle/test_lifecycle_runtime_concurrency.py tests/job_lifecycle/test_retry_policy.py tests/job_lifecycle/test_accounts.py tests/job_lifecycle/test_results.py -q`

- [ ] **Step 7: Commit**

```bash
git add sfboard/jobs/runtime.py sfboard/jobs/facts.py sfboard/jobs/retry.py sfboard/jobs/accounts.py sfboard/jobs/results.py tests/job_lifecycle/test_lifecycle_runtime.py tests/job_lifecycle/test_lifecycle_runtime_concurrency.py
git commit -m "feat: coordinate lifecycle facts through one runtime"
```

### Task 5: Shadow monitor và diagnostics chạy thật

**Files:**
- Modify: `sfboard/jobs/monitor.py`
- Modify: `sfboard/sfboard.py`
- Modify: `tests/job_lifecycle/test_monitor.py`
- Modify: `tests/runtime_bugs/test_diagnostics.py`

**Interfaces:**
- Produces: `_job_invariant_diagnostics()` với `tong`, `nang_nhat`, `theo_ma`, `findings` giới hạn.
- Monitor vẫn pure/read-only; caller đưa snapshot queue/schedule/JOBS.

- [ ] **Step 1: Viết test `/api/chan-doan` phát hiện queue có việc lịch thiếu**

```python
payload = get_diagnostics(queue_idents=["LO:A"], scheduled_idents=[])
self.assertEqual(payload["invariants"]["theo_ma"], {"lich.thieu": 1})
```

- [ ] **Step 2: Chạy RED**

Run: `./.venv/bin/python3 -m pytest tests/runtime_bugs/test_diagnostics.py -q`

- [ ] **Step 3: Nối monitor bằng snapshot dưới lock ngắn**

Không sửa queue/JOBS. Exception trả diagnostic error rõ nhưng không chặn endpoint.
Thêm scheduled/leased identity query read-only vào Scheduler.

- [ ] **Step 4: Test retry path không còn mismatch**

Sau Task 2, execution retry-wait phải nằm trong scheduled set và không phát
`lich.thieu`/`chay.khong_lease` sai.

- [ ] **Step 5: Chạy monitor/diagnostic suites và commit**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_monitor.py tests/runtime_bugs/test_diagnostics.py -q`

```bash
git add sfboard/jobs/monitor.py sfboard/sfboard.py tests/job_lifecycle/test_monitor.py tests/runtime_bugs/test_diagnostics.py
git commit -m "feat: expose read-only lifecycle invariants"
```

### Task 6: Runtime wiring, recovery và executor compatibility boundary

**Files:**
- Create: `sfboard/jobs/executor_adapter.py`
- Modify: `sfboard/sfboard.py`
- Modify: `sfboard/hangdoi.py`
- Modify: `tests/job_lifecycle/test_current_state_writers.py`
- Create: `tests/job_lifecycle/test_authoritative_wiring.py`
- Create: `tests/job_lifecycle/test_recovery_wiring.py`
- Modify: `tests/job_lifecycle/test_http_contract.py`

**Interfaces:**
- Produces: mode `authoritative`; `LegacyExecutorAdapter` emits facts without owning retry/state.
- Preserves: legacy/shadow behavior and API response compatibility.

- [ ] **Step 1: Viết mode gate tests**

```python
def test_legacy_mode_does_not_open_lifecycle_database(self):
    board._init_job_shadow("legacy")
    self.assertIsNone(board._JOB_RUNTIME)

def test_shadow_mode_never_changes_legacy_delivery(self):
    board._init_job_shadow("shadow")
    board._producer_submit(self.request, "key", self.plan_factory)
    self.assertEqual(self.legacy_enqueue_calls, 1)

def test_authoritative_mode_fails_closed_when_database_cannot_open(self):
    self.repository_factory.side_effect = PermissionError("read only")
    with self.assertRaises(LifecycleStartupError):
        board._init_job_shadow("authoritative")
```

- [ ] **Step 2: Chạy RED**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_authoritative_wiring.py -q`

- [ ] **Step 3: Nối startup/shutdown/recovery**

DB path nằm cạnh project nhưng ngoài `sf-board.json`. Authoritative mở repository,
runtime và adapter; queued/retry-wait phục hồi, leased cũ → attention. Legacy không
được mở DB. Shutdown flush/close idempotent.

- [ ] **Step 4: Bọc executor facts**

Trong authoritative, worker nhận `RuntimeLease`; adapter gọi logic DOM hiện có và
chuyển success/error/phase thành runtime facts. Nhánh này không gọi `_xep_lai_sau`,
`_HOAN`, `_xoay_chrome` policy hoặc direct terminal `JOBS` writer. Compatibility
projection cập nhật UI sau runtime transition.

- [ ] **Step 5: Static guard và fake HTTP E2E**

AST guard quét authoritative functions để cấm `_xep`, `_enqueue`, queue `.put`,
`JOBS[...]` assignment và timer retry. HTTP fake create/cancel/retry giữ schema cũ
và thêm durable IDs.

- [ ] **Step 6: Restart tests**

Queued sống qua restart; leased video thành attention; forced account giữ nguyên;
same idempotency key không giao lần hai sau restart.

- [ ] **Step 7: Chạy wiring/recovery suites và commit**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_authoritative_wiring.py tests/job_lifecycle/test_recovery_wiring.py tests/job_lifecycle/test_http_contract.py tests/job_lifecycle/test_current_state_writers.py -q`

```bash
git add sfboard/jobs/executor_adapter.py sfboard/sfboard.py sfboard/hangdoi.py tests/job_lifecycle/test_authoritative_wiring.py tests/job_lifecycle/test_recovery_wiring.py tests/job_lifecycle/test_http_contract.py tests/job_lifecycle/test_current_state_writers.py
git commit -m "feat: wire opt-in authoritative lifecycle runtime"
```

### Task 7: Verification, docs và inert smoke

**Files:**
- Modify: `docs/JOB-LIFECYCLE-README.md`
- Modify: `docs/JOB-MIGRATION-PLAN.md`
- Modify: `docs/JOB-LIFECYCLE-AUDIT.md`
- Modify: `docs/JOB-ARCHITECTURE-SHORT.md` nếu file tồn tại
- Modify: `test-job-lifecycle.command`

**Interfaces:**
- Produces: bằng chứng cutover code path; không thay default/live provider.

- [ ] **Step 1: Chạy full gate mới hoàn toàn**

Run: `./test-job-lifecycle.command`

Expected: 0 failed, 0 xfailed, coverage threshold pass, compile PASS.

- [ ] **Step 2: Chạy fault-injection/fake E2E lặp**

Run: `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_lifecycle_runtime_concurrency.py tests/job_lifecycle/test_recovery_wiring.py -q --count=20` nếu plugin repeat có; nếu không dùng vòng shell 20 lần với cùng hai file.

- [ ] **Step 3: Inert board smoke**

Khởi động trên port tạm với project fixture rỗng và fake/no-provider mode; kiểm
`/api/chan-doan`, `/api/jobs`, UI asset, shutdown. Không gọi endpoint tạo provider.

- [ ] **Step 4: Static/diff gates**

```bash
git diff --check
./.venv/bin/python3 -m py_compile sfboard/sfboard.py sfboard/hangdoi.py sfboard/jobs/*.py
git status --short
```

- [ ] **Step 5: Cập nhật docs đúng authority thực tế**

Chỉ ghi “authoritative code path ready” nếu fake E2E/recovery xanh. Ghi rõ default
mode, rollback, DB path và việc live provider chưa được chạy.

- [ ] **Step 6: Commit docs/gate**

```bash
git add docs/JOB-LIFECYCLE-README.md docs/JOB-MIGRATION-PLAN.md docs/JOB-LIFECYCLE-AUDIT.md test-job-lifecycle.command
git commit -m "docs: record authoritative lifecycle verification"
```

- [ ] **Step 7: Independent code review và fix Critical/Important**

Review toàn range từ commit spec tới HEAD theo invariants, concurrency, recovery và
authority. Sau fix, chạy lại full gate và inert smoke trước khi đóng Bead.
