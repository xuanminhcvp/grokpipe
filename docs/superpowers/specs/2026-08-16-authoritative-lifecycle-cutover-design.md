# Authoritative lifecycle cutover — thiết kế hoàn thiện

Trạng thái: **ĐÃ ĐƯỢC DUYỆT** qua `JOB-ARCHITECTURE-TARGET.md` và yêu cầu
“làm nốt hết, tự check đến lúc xong” ngày 2026-08-16.

## Mục tiêu

Hoàn thiện đường lifecycle mới để có thể chạy authoritative mà không còn hai nơi
quyết định queue, retry, account hoặc kết quả. Không gọi live provider và không
tiêu credit trong quá trình triển khai/kiểm thử.

## Phạm vi

1. Một durable identity cho mỗi execution; rerun cùng asset/legacy ident vẫn tạo
   execution mới, không hồi sinh dòng terminal cũ.
2. Scheduler in-memory và SQLite dùng chung một backend contract; lease, release,
   retry-wait, finish và recovery giữ version/CAS.
3. Retry không `finish` execution rồi xếp lén vào queue. Lỗi tạo
   `RetryDecision`, sau đó coordinator chuyển execution sang waiting/ready bằng
   `not_before`.
4. `AccountAllocator` cấp account seat trước executor; forced account và fallback
   là constraint của job qua mọi attempt.
5. `ResultCommit` là cửa duy nhất nhận kết quả. Lease cũ, job terminal hoặc user
   mutation không được ghi đè current output.
6. SQLite lưu Job, Batch, Event, Intent, Execution, Attempt và account constraint
   trong cùng lifecycle repository. Startup recovery dựng ready heap; execution
   đang chạy dở vào `NEEDS_ATTENTION`, không tự submit lại.
7. `InvariantMonitor` chạy thật trong shadow/authoritative diagnostics nhưng chỉ
   báo, tuyệt đối không enqueue hoặc sửa state.
8. API/UI cũ tiếp tục đọc compatibility projection. Mode `legacy` là rollback;
   mode mới không cho legacy writer/retry/watchdog trở thành authority thứ hai.

## Kiến trúc

```text
HTTP / Auto / CLI
        │ command + idempotency key
        ▼
LifecycleRuntime (coordinator duy nhất)
        ├── ProducerService
        ├── JobManager
        ├── Scheduler
        ├── RetryPolicy
        ├── AccountAllocator
        └── ResultCommit
                 │
                 ▼
SQLiteLifecycleRepository
  Job · Batch · Event · Intent · Execution · Attempt · Lease
                 │
                 ▼
LegacyExecutorAdapter → image/video executor → facts/results
                 │
                 ▼
CompatibilityProjection → JOBS/API/UI cũ
```

`LifecycleRuntime` không chứa DOM/provider logic. Executor không biết queue hoặc
transition; nó chỉ phát phase/result/error fact. Mọi thay đổi lifecycle và lịch
đều qua runtime/repository.

## Mode và authority

- `legacy`: hành vi hiện tại; runtime mới không quyết định execution.
- `shadow`: legacy thực thi; runtime mới mirror command/fact và monitor invariant.
- `authoritative`: runtime mới quyết định schedule/retry/account/result; legacy
  chỉ thực thi một attempt đã được lease và chiếu nhãn UI.

Không tự đổi default sang authoritative trong khi kiểm thử. Cổng ra là fake E2E,
restart/fault-injection và inert board smoke; không dùng live Chrome/provider.

## Durable identity và transaction

- `execution_id` là primary key bất biến.
- `queue_ident` chỉ là compatibility label, không unique toàn lịch sử.
- Chỉ một execution active cho `(kind, scope_key)`; uniqueness dùng partial active
  constraint hoặc transaction kiểm state, không tái dùng execution terminal.
- Mọi mutation dùng `expected_version`; conflict trả lỗi rõ, không ghi đè.
- Create intent + jobs + batch + executions + events là một transaction ở mode
  authoritative.
- Event/idempotency replay cùng payload trả kết quả cũ; cùng key khác payload là
  conflict.

## Retry, account và kết quả

- Retry budget đếm submitted attempts; pre-submit reconnect không tiêu budget.
- Unknown post-submit outcome → `NEEDS_ATTENTION`, không tự resubmit.
- Retry decision và chuyển `RETRY_WAIT/not_before` nằm trong một transaction.
- Account seat được lưu trước executor; browser/account mất tạo fact cho đúng
  attempt. `enabled`, health, cooldown và capability không nhập làm một.
- Result commit kiểm lease/version/job state/user mutation trước khi trả verdict;
  output bị chặn vẫn được giữ làm version nếu đã tốn lượt.

## Recovery và rollback

- Startup mở/migrate DB, kiểm schema version và integrity trước khi nhận producer.
- `QUEUED/RETRY_WAIT` dựng lại lịch theo priority/not_before.
- `RUNNING/LEASED` cũ thành attention; không tự chạy lại.
- DB lỗi/lock ở authoritative phải fail rõ/read-only diagnostic, không âm thầm
  quay legacy rồi tạo duplicate.
- Rollback về legacy chỉ khi repository không có execution active mới.

## Verification bắt buộc

- Regression đỏ–xanh cho identity rerun, retry lease, CAS, recovery, monitor wiring.
- Concurrency tests cho duplicate create/lease/account seat/result commit.
- Fake-provider E2E: create → lease → success; retry; unknown outcome; cancel;
  restart; forced account; late result.
- Static authority guard: mode mới không gọi legacy re-enqueue/retry writer.
- `./test-job-lifecycle.command`, compile gate, `git diff --check`.
- Inert smoke localhost không tạo job/provider/credit.

## Không thuộc phạm vi

- Thay thuật toán prompt/ref hoặc DOM selector.
- Đổi format asset/version trong `sf-board.json`.
- Chạy live Chrome/provider để “thử xem”.
- Làm lại UI ngoài các field/diagnostic cần cho lifecycle compatibility.
