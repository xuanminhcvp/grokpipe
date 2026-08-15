# Thiết kế migration an toàn cho lifecycle ảnh/video

Ngày duyệt: 2026-08-16

Trạng thái: **ĐÃ ĐƯỢC NGƯỜI DÙNG DUYỆT**

Beads epic: `beads-foundation-7lt`

## 1. Bối cảnh

Production hiện vẫn ở Phase 0–1. `JOBS`, `PriorityQueue`, worker, retry timer,
auto-runner, watchdog và account registry legacy vẫn là authority thực tế. Gói
`sfboard.jobs` mới cung cấp domain model và hạ tầng quan sát; production chưa
cutover sang core mới.

Hệ thống đã có regression suite, runtime journal, dấu vết bước và các guard quan
trọng. Tuy vậy, lifecycle vẫn có nhiều writer/re-enqueue authority, state nằm
trong RAM, account assignment chưa bền vững và bốn ambiguity còn được khóa bằng
`expectedFailure`.

Thiết kế này không thay thế các quyết định sản phẩm trong:

- `docs/JOB-LIFECYCLE-DECISIONS.md`;
- `docs/JOB-STATE-MACHINE.md`;
- `docs/JOB-ARCHITECTURE-TARGET.md`;
- `docs/JOB-MIGRATION-PLAN.md`.

Nếu có mâu thuẫn, bốn tài liệu trên là nguồn quyết định theo đúng thứ tự phạm vi:
quy tắc sản phẩm, state machine, kiến trúc đích và thứ tự migration. Tài liệu này
khóa cách thực hiện hướng migration an toàn đã được người dùng duyệt.

## 2. Mục tiêu

1. Chỉ một authority được quyền quyết định lifecycle của job.
2. Không submit trùng ngoài multi-copy có chủ ý.
3. Cancel/stop thắng mọi timer, auto snapshot, watchdog và late result cũ.
4. Retry, account allocation và provider execution có ranh giới riêng, test được.
5. Restart không làm mất queued/retry-wait job hoặc tự submit lại outcome chưa rõ.
6. UI/API hiện tại tiếp tục hoạt động trong toàn bộ migration.
7. Mỗi phase có regression test, feature gate và rollback độc lập.
8. Test mặc định không mở Chrome, gọi provider hoặc tiêu credit.

## 3. Không nằm trong phạm vi

- Không big-bang rewrite `sfboard.py`.
- Không thay UI chỉ để phản ánh cấu trúc nội bộ mới trước phase compatibility.
- Không sửa DOM/provider automation nếu phase đang làm không yêu cầu adapter đó.
- Không thay prompt, asset hay ảnh/video đang dùng.
- Không cutover hoặc restart production khi còn job active.
- Không chạy live-provider smoke test nếu người dùng chưa opt-in rõ ràng.

## 4. Kiến trúc đích

```text
UI / HTTP API
      |
      v
JobManager ----------------------> Compatibility Projection
  |                                      |
  |                                      v
  +--> JobStore (SQLite)             UI / API cũ
  |
  +--> Scheduler --> AccountAllocator --> Worker
  |                                      |
  |                                      +--> ImageExecutor
  |                                      +--> VideoExecutor
  |
  +--> RetryPolicy
  +--> Auto Producer commands
  +--> Invariant Monitor (chỉ cảnh báo)
```

### 4.1 Quyền sở hữu

- **JobManager** là authority duy nhất được chuyển state và ghi lifecycle event.
- **JobStore** lưu job, execution, attempt, lease, event và lịch retry trong một
  transaction/CAS boundary.
- **Scheduler** là nơi duy nhất tạo schedule entry và cấp execution lease.
- **RetryPolicy** trả quyết định; không ghi store, enqueue hoặc xoay account.
- **AccountAllocator** cấp account lease trước execution; không quyết state/retry.
- **Worker** nhận lease, gọi executor và báo fact; không tự retry, enqueue, xoay
  account hoặc ghi state.
- **Executor** thực hiện đúng một attempt và ghi rõ submit boundary.
- **Auto Producer** chỉ gửi `CreateJob` idempotent; không revive hoặc retry job.
- **Invariant Monitor** chỉ phát cảnh báo; không sửa state hoặc re-enqueue.
- **Compatibility Projection** dịch snapshot/event core sang schema UI/API cũ;
  projection không có quyền ghi ngược vào core.

### 4.2 Identity bền vững

- `asset_id`: ảnh/shot logic trong project.
- `job_id`: một ý định tạo cụ thể; rerun luôn tạo job mới.
- `batch_id`: nhóm job có chủ ý, kể cả lô ảnh và multi-copy.
- `execution_id`: một lần được scheduler cấp lịch/lease.
- `attempt_id`: một lần gọi executor với account và submit boundary riêng.
- `lease_id + expected_version`: quyền thực thi có hạn; stale lease/token bị bỏ.

Không dùng asset ID, chuỗi `LO:<members>`, queue tuple hoặc state text thay cho
Job/Execution/Attempt identity.

## 5. Luồng dữ liệu

### 5.1 Tạo job

1. API/auto gửi `CreateJob` với idempotency key.
2. JobManager validate và ghi Job + event atomically.
3. Scheduler tạo đúng một schedule entry cho active job.
4. Request lặp trả lại cùng snapshot thay vì tạo submit thứ hai.
5. Multi-copy tạo các child job riêng trong cùng batch.

### 5.2 Thực thi

1. Worker xin lease theo capability.
2. Scheduler/JobManager xác minh state, version và lease expiry.
3. AccountAllocator cấp account lease, lưu account và lý do chọn trước khi chạy.
4. Executor báo các phase `prepared`, `submitted`, `downloaded`, `stored` hoặc
   typed error.
5. JobManager áp dụng event và quyết state atomically.

### 5.3 Retry

1. RetryPolicy nhận error class, submit boundary và attempt history.
2. Policy trả `retry_wait`, `failed` hoặc `needs_attention` cùng `not_before`.
3. JobManager ghi quyết định; Scheduler là thành phần duy nhất lên lịch lại.
4. Forced account là constraint của toàn job và sống qua mọi retry; fallback chỉ
   có khi job được tạo với flag rõ ràng.

### 5.4 Cancel và stop-all

1. Cancel dùng `job_id + expected_version`, không dùng asset ID/cancel set mơ hồ.
2. Queued/retry-wait chuyển `CANCELLED` atomically; token cũ không lease được.
3. Running nhận cancel request theo executor phase; video sau submit tiếp tục tải
   và lưu vì credit có thể đã bị trừ.
4. Stop-all mở producer barrier trước, chặn create/retry commit mới, sau đó cancel
   queued/retry-wait và phát cancel request cho running attempt.
5. Late result chỉ được ghi vào đúng attempt/version; không đè asset hiện hành.

### 5.5 Restart và recovery

- SQLite là nguồn sự thật; queue RAM chỉ là projection có thể dựng lại.
- Recover queued/retry-wait theo `not_before` và version.
- Running lease hết hạn trước submit có thể retry theo policy.
- Running attempt đã submit nhưng chưa rõ outcome chuyển `NEEDS_ATTENTION`, không
  tự submit lại.

## 6. Error, credit và account policy

Các nhóm lỗi tối thiểu:

- `VALIDATION` và `PERMANENT`: không retry, không làm xấu account health.
- `CANCELLED`: không retry; credit được ghi theo submit boundary thực tế.
- `SESSION_TRANSIENT` trước submit: reconnect cùng account theo policy giới hạn.
- `PROVIDER_TRANSIENT`: retry có backoff; chỉ đổi account khi policy yêu cầu.
- `QUOTA_RATE_LIMIT`: cooldown account và chọn account khác nếu constraint cho phép.
- `ACCOUNT_LOST`: phát fact cho mọi sibling lease; chỉ đóng/relaunch account khi
  đã xác nhận browser/session fatal.
- `UNKNOWN_OUTCOME` sau submit: `NEEDS_ATTENTION`, tuyệt đối không tự submit lại.

Retry ảnh mặc định tối đa 8 attempt có khả năng submit; reconnect trước submit
không tính. Retry video phải dựa trên submit boundary và bảo vệ credit. Không còn
luật “mọi exception đều xoay Chrome và retry”. Account ảnh chỉ chạy video khi
được user đánh dấu `allow_video=true`.

## 7. Chiến lược migration

### 7.1 Feature mode

- `legacy`: core mới không quyết production.
- `shadow`: legacy quyết; core mirror command/event và kiểm invariant.
- `authoritative`: core quyết; legacy chỉ là adapter/projection.

Mode là cơ chế migration nội bộ và bị xóa ở phase cuối.

### 7.2 Thứ tự bắt buộc

1. Giữ Phase 0–1 làm baseline.
2. Phase 2: JobStore/JobManager in-memory ở shadow mode.
3. Phase 3: producer command, idempotency và multi-copy identity.
4. Phase 4: Scheduler và execution lease.
5. Phase 5: Attempt và AccountAllocator.
6. Phase 6–7: image/video executor adapters và submit boundary.
7. Phase 8–9: cancel/stop và RetryPolicy; xóa retry authority trùng.
8. Phase 10: SQLite authoritative và recovery.
9. Phase 11: auto producer/invariant monitor không còn re-enqueue authority.
10. Phase 12: UI/API projection cuối, xóa legacy writer và feature mode.

Không bỏ qua phase phụ thuộc và không hạ nhiều authority trong một commit.

### 7.3 Điều kiện cutover

Chỉ đổi sang authority mới khi:

- production queue không còn queued/running/retry timer/private-account work;
- auto producer đã tắt hoặc đang đứng sau barrier;
- targeted test, full lifecycle gate và compile gate đều xanh;
- shadow không còn mismatch chưa giải thích;
- fake-provider E2E của phase pass;
- rollback đã được xác định và không cần sửa dữ liệu bằng tay.

### 7.4 Rollback

- Trước authoritative cutover: tắt feature mode của phase, legacy vẫn quyết.
- Sau cutover có gate: dừng producer, chờ/cancel lease an toàn, quay lại projection
  đã xác minh; không chạy song song hai writer để “cứu nóng”.
- Rollback tức thì nếu có submit trùng, terminal regress, cancel/stop bị hồi sinh,
  queue/store/lease mismatch, credit attempt thiếu audit row hoặc API/UI mất thao
  tác chính.

## 8. Kiểm thử và bằng chứng

Mỗi behavior change phải đi theo red-green TDD:

1. Bỏ đúng một `expectedFailure` khi tới phase của bug đó.
2. Chạy targeted test và quan sát fail vì đúng nguyên nhân.
3. Implement thay đổi nhỏ nhất tại đúng owner.
4. Chạy targeted test xanh.
5. Chạy `./test-job-lifecycle.command` và compile gate.
6. Đọc diff và dùng AST guard xác nhận không thêm writer/re-enqueue authority.

Test bắt buộc theo phase gồm:

- state transition và terminal monotonicity;
- idempotency, click đôi, HTTP retry và auto backlog;
- worker lease race, stale token/timer và cancel/complete race;
- retry fairness, forced account và account health;
- image batch partial result và multi-copy aggregate;
- video pre/post-submit, unknown outcome và credit audit;
- restart recovery bằng SQLite;
- compatibility contract cho UI/API;
- property-based lifecycle sequences;
- fake-provider E2E, không mở Chrome thật mặc định.

Bốn `xfail` hiện tại chỉ được giảm bằng fix đã red-green; không thêm `xfail`, skip
hoặc nới assertion để làm gate xanh.

## 9. Quan sát và vận hành

- Giữ runtime journal đã lọc bí mật, fingerprint, bug bridge và `/api/chan-doan`.
- Mỗi event mới phải mang `job_id`, `execution_id`, `attempt_id`, phase, version và
  account lease khi có.
- Metrics tối thiểu: active jobs theo state, due retries, lease age, duplicate
  rejection, unknown outcomes, cancel latency và account cooldown.
- Shadow mismatch là diagnostic event, không tự sửa production.
- Không ghi prompt, cookie, token, DSN, base64 hoặc media vào log/event.

## 10. Tiêu chí hoàn tất

Chương trình migration hoàn tất khi:

1. JobManager/SQLite là source of truth duy nhất.
2. Scheduler là enqueue/lease authority duy nhất.
3. Worker/executor/account/retry không còn direct state writer.
4. Không còn watchdog, auto, timer hoặc client tự re-enqueue.
5. Bốn `xfail` hiện tại đã thành regression test xanh qua đúng phase.
6. Restart/recovery, cancel/stop, retry, account và credit suites pass.
7. UI/API cũ hoạt động qua projection cho tới khi compatibility được gỡ có chủ ý.
8. AST/static guard không còn legacy writer ngoài adapter được cho phép.
9. Full fake-provider E2E pass; live smoke test vẫn là opt-in.
10. Mỗi phase có commit, rollback note và bằng chứng gate độc lập.
