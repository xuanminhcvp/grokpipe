# Live DOM Worker Cutover Implementation Plan

> **Execution:** dùng `superpowers:executing-plans`; mỗi behavior change phải đi
> qua RED → GREEN → REFACTOR. Không dùng subagent trong phiên này theo giới hạn
> điều phối hiện hành.

**Goal:** Cho worker Chrome/DOM thật chạy bằng lease của `LifecycleRuntime`, giữ
một authority cho retry/account/cancel/result và canary Grok không quá 20 submit.

**Architecture:** Runtime cấp `RuntimeLease` có account slot. Live worker gọi
one-attempt image/video executor và chỉ phát phase/output/error fact qua
`LegacyExecutorAdapter`. Session provider nhận callback tùy chọn tại các ranh
giới submit/download/save. Grok budget được reserve bền vững trước click submit.

**Tech Stack:** Python 3.14, pytest/unittest, Playwright sync API, SQLite lifecycle
repository, JSON atomic persistence cho canary budget.

## Global constraints

- Default vẫn `legacy`; live chỉ bật khi `authoritative` và
  `GROKPIPE_LIVE_EXECUTOR=1`.
- Không gọi legacy retry/re-enqueue/account rotation/JOBS writer từ live worker.
- Không chạy provider trước khi fake/static/full lifecycle/compile đều xanh.
- ChatGPT không giới hạn canary; Grok hard cap 20 persisted reservations.
- Không push/pull/sync. Sandbox không cho ghi `.git`, nên commit checkpoints chỉ
  thực hiện nếu quyền môi trường cho phép.

---

### Task 1: Lease mang account slot và adapter cancel-safe

**Files:**
- Modify: `sfboard/jobs/facts.py`
- Modify: `sfboard/jobs/runtime.py`
- Modify: `sfboard/jobs/executor_adapter.py`
- Modify: `tests/job_lifecycle/test_lifecycle_runtime.py`
- Modify: `tests/job_lifecycle/test_executor_adapter.py`

- [ ] Viết test lease giữ đúng `AccountSeat.slot`; chạy và xác nhận fail.
- [ ] Viết regression cancel xảy ra trong executor không gọi finalize trên lease
  đã bị thu hồi; chạy và xác nhận `RuntimeLeaseNotFound`.
- [ ] Thêm `account_slot` vào `RuntimeLease`, truyền từ allocator.
- [ ] Cho adapter nhận diện toàn bộ member đã `CANCELLED` sau execute/exception và
  trả outcome rỗng, không gọi success/failure.
- [ ] Chạy:
  `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_lifecycle_runtime.py tests/job_lifecycle/test_executor_adapter.py -q`

### Task 2: Grok canary budget bền vững

**Files:**
- Create: `sfboard/jobs/live_budget.py`
- Create: `tests/job_lifecycle/test_live_budget.py`
- Modify: `sfboard/jobs/__init__.py`
- Modify: `test-job-lifecycle.command`

- [ ] Viết RED tests: thiếu/zero limit fail closed; reserve tăng; restart giữ
  counter; concurrent reserve không vượt limit; exhausted không mutation.
- [ ] Implement `PersistentSubmitBudget.reserve()` bằng lock process + file lock,
  write temp/`os.replace`/fsync; limit không được giảm cho cùng scope.
- [ ] Không hoàn reservation sau lỗi click.
- [ ] Chạy:
  `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_live_budget.py -q`

### Task 3: Callback phase tại credit boundary của provider

**Files:**
- Modify: `grokpipe/grokpipe/executors/image_chatgpt.py`
- Modify: `grokpipe/grokpipe/executors/video_grok.py`
- Create: `tests/executors/test_live_phase_callbacks.py`

- [ ] Viết AST/regression tests chứng minh ChatGPT `on_submitted` nằm sau `_gui`
  success và trước wait; callback không chạy nếu `_gui` fail.
- [ ] Viết tests Grok `before_submit` ngay trước `_bam_submit`, `on_submitted`
  chỉ sau success, download/save callback đúng thứ tự.
- [ ] Thêm callback keyword-only optional, mặc định `None`, không đổi caller cũ.
- [ ] Chạy:
  `./.venv/bin/python3 -m pytest tests/executors/test_live_phase_callbacks.py tests/executors -q`

### Task 4: One-attempt image/video executor

**Files:**
- Create: `sfboard/live_executor.py`
- Create: `tests/job_lifecycle/test_live_executor.py`
- Modify: `sfboard/sfboard.py`

- [ ] Viết fake image tests: exact mapping success; thiếu/thừa output trả partial;
  cancelled member bị bỏ; phase order chuẩn.
- [ ] Viết fake video tests: pre-submit error retryable; post-submit error unknown;
  outputs main/extra; Grok budget reserve trước provider submit.
- [ ] Implement pure preparation/result mapping trong `live_executor.py`; DOM/file
  dependencies inject được để unit test không mở Chrome.
- [ ] Implement board bridge dựng prompt/ref/start frame, set thread-local account
  từ lease, gọi session đúng một lần và apply `CommitVerdict` an toàn.
- [ ] Chạy:
  `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_live_executor.py tests/job_lifecycle/test_executor_adapter.py -q`

### Task 5: Live authoritative worker và authority guard

**Files:**
- Modify: `sfboard/sfboard.py`
- Modify: `tests/job_lifecycle/test_authoritative_wiring.py`
- Create: `tests/job_lifecycle/test_live_authority_guard.py`
- Modify: `tests/job_lifecycle/test_inert_board_smoke.py`

- [ ] Viết RED wiring tests: auth không live inert; auth+live chọn worker mới;
  legacy không đổi; auto producer không tự chạy trong canary.
- [ ] Viết AST guard cấm live path gọi `_enqueue`, `_xep`, queue `.put`,
  `_xoay_chrome`, `_dat_nhan_lo`, hoặc assign `JOBS[...]`.
- [ ] Implement supervisor live lease-loop; projection chạy sau mỗi outcome;
  lỗi không được làm worker biến mất im lặng.
- [ ] Thêm diagnostics hiển thị mode/live/Grok remaining.
- [ ] Chạy:
  `./.venv/bin/python3 -m pytest tests/job_lifecycle/test_authoritative_wiring.py tests/job_lifecycle/test_live_authority_guard.py tests/job_lifecycle/test_inert_board_smoke.py -q`

### Task 6: Verification và controlled live canary

**Files:**
- Modify: `docs/JOB-LIFECYCLE-STATUS.md`
- Modify: Bead `beads-foundation-gbo`

- [x] Chạy `./test-job-lifecycle.command`.
- [x] Chạy full `./.venv/bin/python3 -m pytest -q` và `git diff --check`.
- [x] Backup toàn project và xác nhận runtime queue không active.
- [x] Start controlled board với `GROKPIPE_JOB_MODE=authoritative`,
  `GROKPIPE_LIVE_EXECUTOR=1`, `GROKPIPE_LIVE_GROK_LIMIT=20`, auto producer off.
- [x] ChatGPT canary: single REF/image, grouped REF, cancellation/restart; kiểm
  submit count, phase timeline và file tải thật.
- [x] Grok canary: một video trước; mở rộng có chọn lọc, tổng persisted
  reservations `<=20`; dừng ngay khi duplicate/download/session sai.
- [x] Cập nhật README/migration/audit bằng evidence thật. Chỉ close Bead khi unit/full/live đều
  đạt acceptance; nếu môi trường/provider chặn thì giữ IN_PROGRESS và ghi rõ.
