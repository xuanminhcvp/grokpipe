# Job lifecycle — cửa vào kỹ thuật

> Trạng thái: **production authoritative + live** (cập nhật 2026-08-17).
> File này là điểm bắt đầu; plan/spec trong `docs/superpowers/` chỉ là lịch sử.

## Đọc trong 60 giây

SF Board không còn dùng dictionary `JOBS` hay vòng retry DOM làm nguồn sự thật.
Luồng production là:

```text
UI/API/auto producer
    → command + idempotency key
    → SQLite lifecycle
    → scheduler + execution lease
    → account allocator
    → one-attempt image/video worker
    → fact theo phase
    → LifecycleRuntime
    → result commit + projection/API/UI
```

Authority duy nhất cho state, retry, cancel, recovery, account lease và kết quả
là `LifecycleRuntime` cùng repository SQLite. Worker không tự re-enqueue và lớp
legacy không được quyết định lifecycle production.

## Chế độ chạy

| Mode | Mục đích | Có phải production mặc định? |
|---|---|---|
| `authoritative` + live | SQLite/runtime điều phối worker thật | Có |
| `shadow` | So projection mới với luồng cũ | Không |
| `legacy` | Rollback có chủ đích | Không |

Mặc định trong code và `chay-board.command`:

```bash
GROKPIPE_JOB_MODE=authoritative
GROKPIPE_LIVE_EXECUTOR=1
```

Board từ chối hạ khỏi authoritative khi còn execution active. Nếu khởi tạo
authoritative thất bại, startup thất bại rõ ràng thay vì âm thầm chạy nửa mới
nửa cũ.

## Nguồn sự thật và identity

Database của mỗi project:

```text
<PROJECT>/.grokpipe/job-lifecycle.sqlite3
```

Các identity không được trộn:

- `AssetId`: output logic như REF/SF/video.
- `JobId`: một ý định xử lý asset tại một thời điểm.
- `BatchId`: nhóm job do một command tạo.
- `ExecutionId`: đơn vị scheduler/worker thực thi vật lý.
- `AttemptId`: một lần thử của execution trên một account lease.

Một execution có thể gộp nhiều job REF/SF, nhưng từng job vẫn có state và output
riêng. Multi-copy tạo các job riêng; không dùng một job với bộ đếm copy mơ hồ.

## Invariant không được phá

1. Mỗi side effect có idempotency key; replay cùng payload trả cùng intent,
   replay khác payload phải conflict.
2. Chỉ runtime được transition state và quyết định retry.
3. Mỗi execution active có tối đa một lease; mỗi account seat có tối đa một
   owner trong cùng slot.
4. Worker báo fact, không tự ghi state hoặc tự xếp lại.
5. Kết quả chỉ commit từ lease hợp lệ; late/stale result không được ghi đè asset
   hiện tại trái policy.
6. Mất kết nối sau submit không được tự gửi lại video mù.
7. Cancel/stop phải tác động đúng execution và toàn bộ member vật lý của nó.
8. Restart không làm mất intent; recovery dựa vào attempt phase.
9. UI/API là projection của server state, không phải authority lạc quan.
10. Legacy compatibility không được sinh thêm writer/retry/account authority.

## State và phase

Job states:

```text
created → queued → running → completed
                       ↘ retry_wait → queued
                       ↘ failed
                       ↘ needs_attention
created/queued/retry_wait/running → cancelled (theo luật cancel)
```

Attempt phases:

```text
preparing → attaching → ready_to_submit → submitted
          → waiting_provider → downloading → saving → finished
```

Chi tiết transition, cancel và recovery: [JOB-STATE-MACHINE.md](JOB-STATE-MACHINE.md).

## Retry và credit boundary

- Validation/permanent: `failed`, không phạt account.
- Quota/rate-limit: retry có backoff, cooldown và xoay account.
- Session lỗi trước submit: ưu tiên reconnect cùng account một lần, sau đó có
  thể xoay.
- Account lost trước submit: retry và xoay account.
- Outcome không rõ hoặc session/account mất sau submit: `needs_attention`.
- Batch trả thiếu: chỉ member chưa xong quay lại; member đã hoàn tất không hồi
  sinh.

Grok live cần `GROKPIPE_LIVE_GROK_LIMIT` trong khoảng `1..20`. Budget được lưu
theo scope tại `<PROJECT>/.grokpipe/live-grok-canary.json`; mỗi submit thật được
reserve bền vững để không vượt trần sau restart.

## Video và chống tải nhầm

- Mỗi video attempt gắn với đúng source SF, execution, account và dấu vết submit.
- Ledger các Grok post đã thấy được lưu local ở
  `~/.grokpipe-grok-posts.jsonl` với quyền file hạn chế.
- Khi mở session, post lịch sử đang có sẵn trong tab được seed trước khi submit;
  worker chỉ chấp nhận post mới thuộc attempt hiện tại.
- Download/save nằm sau phase submit/wait; kết quả chỉ commit qua lease hiện tại.

## Cancel, stop và restart

- Queued/retry-wait: hủy execution/member tương ứng và chuyển `cancelled`.
- Image đang chạy: có thể hủy execution và thu hồi result lease.
- Video đã submit: không cưỡng bức cancel như job chưa tốn credit; trả lý do
  `video.already_submitted` để tránh outcome mơ hồ.
- “Dừng tất cả” phải ngăn việc chờ và xử lý đúng các execution đang chạy, không
  chỉ đổi nhãn UI.
- Recovery trước submit → `retry_wait`; sau submit hoặc thiếu attempt record →
  `needs_attention`.

## Debug bắt buộc

1. Ghi lại asset/job/execution/account/time và hành động người dùng.
2. Đọc `/api/chan-doan`, `/api/jobs`, log board và runtime bug journal.
3. Xác định phase xảy ra lỗi và authority đã ghi transition nào.
4. Dùng Serena tìm symbol/callers; ast-grep tìm mọi writer/assignment; `rg` cho
   endpoint, reason code và docs.
5. Viết regression test tái hiện trước khi sửa.
6. Chạy gate đầy đủ.

Không chữa lỗi bằng xoá SQLite, reset toàn queue, thêm một retry loop hoặc thêm
writer vào `JOBS`.

## Verification

Gate local:

```bash
./test-job-lifecycle.command
```

Gate chạy:

- `tests/job_lifecycle`;
- `tests/runtime_bugs`;
- `tests/executors`;
- coverage tối thiểu 80% cho `sfboard.jobs`;
- `py_compile` các module lifecycle/board/executor chính.

Mốc gate gần nhất: **709 test pass**, không xfail; `sfboard.jobs` đạt **91,19%**
coverage. Live provider không nằm trong gate mặc định vì có thể tiêu credit.

## Quan sát runtime

- API chính: `/api/jobs`, `/api/chan-doan`, `/api/accounts`.
- Journal bền vững: `.grokpipe/runtime-bugs/events.jsonl`.
- Journal phải redact credential/token; bridge Beads/Sentry chỉ bật khi có cấu
  hình/opt-in local rõ ràng.
- Invariant monitor phải bằng 0 trước khi kết luận board ổn định.

## File map hiện hành

| File | Trách nhiệm |
|---|---|
| `sfboard/jobs/models.py` | identity, state, batch, execution, attempt, lease |
| `sfboard/jobs/sqlite_store.py` | repository SQLite authoritative |
| `sfboard/jobs/producer.py` | command, fingerprint, idempotency |
| `sfboard/jobs/runtime.py` | transaction, transition, lease, fact, recovery |
| `sfboard/jobs/scheduler.py` | ready/waiting/leased execution và `not_before` |
| `sfboard/jobs/accounts.py` | account seat, force/fallback, health/cooldown |
| `sfboard/jobs/retry.py` | retry policy duy nhất |
| `sfboard/jobs/results.py` | commit/revoke result theo lease |
| `sfboard/jobs/executor_adapter.py` | fact boundary với legacy executor |
| `sfboard/live_executor.py` | one-attempt image/video execution |
| `sfboard/sfboard.py` | HTTP/UI/startup/compatibility wiring |
| `sfboard/hangdoi.py` | compatibility/projection, không phải authority mặc định |

## Đọc tiếp

- [Kiến trúc](JOB-ARCHITECTURE-TARGET.md)
- [State machine](JOB-STATE-MACHINE.md)
- [Quyết định đã chốt](JOB-LIFECYCLE-DECISIONS.md)
- [Lịch sử migration](JOB-MIGRATION-PLAN.md)
- [Audit hiện hành](JOB-LIFECYCLE-AUDIT.md)
