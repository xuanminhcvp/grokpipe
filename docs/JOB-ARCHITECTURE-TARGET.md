# Kiến trúc lifecycle job ảnh/video

> Trạng thái: kiến trúc đích đã là production authority. Từ “đích” trong tên
> file được giữ để các liên kết cũ không gãy.

## Mục tiêu

- Chạy ảnh và video bền vững qua restart.
- Không tạo trùng do retry HTTP, double-click hoặc reconnect.
- Gộp batch để tận dụng provider nhưng vẫn giữ state/output từng asset.
- Phân account an toàn dưới concurrency và quota.
- Không tiêu credit lần hai khi outcome video chưa rõ.
- Debug được bằng identity, event, phase và reason code thay vì đọc nhiều biến
  toàn cục rời rạc.

## Sơ đồ thành phần

```text
Producer boundary
  UI · HTTP · auto · external client
              │ command + idempotency
              ▼
       ProducerService
              │ atomic intent/job/batch
              ▼
 SQLiteLifecycleRepository ◀───────────────┐
              │                            │
              ▼                            │ event/attempt/execution
      LifecycleRuntime                     │
       ├─ Scheduler                        │
       ├─ AccountAllocator                 │
       ├─ RetryPolicy                      │
       └─ ResultCommitter                  │
              │ lease                      │ fact theo phase
              ▼                            │
      Live executor / provider ────────────┘
              │
              ▼
       Projection · API · UI
```

Dependency đi từ HTTP/worker vào domain/runtime, không ngược lại. Module domain
không phụ thuộc DOM, Playwright hoặc global state của board.

## Quyền sở hữu

| Dữ liệu/quyết định | Owner |
|---|---|
| intent, idempotency, active scope | `ProducerService` + repository |
| state transition, event | `LifecycleRuntime`/manager |
| execution ordering, lease, `not_before` | scheduler |
| account seat, force/fallback, cooldown | account allocator |
| retry action, delay, rotate | `RetryPolicy` |
| output hợp lệ, stale/late verdict | result committer |
| thao tác browser của đúng một attempt | live executor |
| hiển thị/compatibility | projection/API/UI |

Không component nào khác được tự nhận quyền của bảng trên.

## Mô hình dữ liệu

### Job

Một ý định logic đối với một asset:

- `job_id`, `asset_id`, `kind`, `origin`;
- state hiện tại;
- account preference/force và fallback policy;
- replace-current policy;
- batch membership và metadata cần thiết.

Terminal states là `completed`, `failed`, `cancelled`. `needs_attention` không
terminal vì cần quyết định của người dùng/operator.

### Batch

Nhóm job tạo trong một command. Các mode hiện có:

- `image_group`: gộp nhiều asset ảnh vào một lượt provider;
- `multi_copy`: nhiều job riêng cho nhiều bản sao;
- `bulk_video`: nhiều video job trong một yêu cầu bulk.

Batch không thay thế identity của job.

### Execution

Đơn vị scheduler/worker vật lý, chứa một hoặc nhiều `JobId`, kind, queue identity,
state scheduler, lease và thời điểm `not_before`. Retry cả execution vẫn không
được hồi sinh member đã terminal thành công.

### Attempt

Một lần thử cụ thể của execution:

- account và account lease;
- phase trước/sau submit;
- thời điểm bắt đầu, submit, kết thúc;
- outcome và credit consumption.

Attempt là ranh giới để quyết định retry an toàn.

### Event

Mỗi transition có event id, actor, type và reason code. Event idempotent cho phép
replay cùng fact mà không transition hai lần; cùng id nhưng payload khác phải bị
từ chối.

### Account lease

Seat được cấp theo account/slot/work key và có TTL. Lease được release khi
attempt kết thúc; quota có cooldown; fatal account error làm account unhealthy.

## Transaction boundary

Các thao tác sau phải atomic trong repository transaction:

- tạo/replay intent, job, batch và active scope;
- schedule execution và transition `created → queued`;
- lease execution, tạo attempt và transition `queued → running`;
- commit fact success/failure/partial cùng event và scheduler state;
- cancel execution cùng toàn bộ member;
- startup recovery.

Nếu transaction rollback, scheduler cache/constraint phải được restore từ
repository; không để memory nói khác SQLite.

## Luồng producer

1. Client tạo idempotency key.
2. Producer fingerprint toàn payload có ý nghĩa.
3. Cùng key + cùng payload trả intent cũ; cùng key + payload khác conflict.
4. Active-scope chặn hai intent đang sống cùng tranh một asset.
5. Runtime schedule execution và đánh dấu intent đã delivery trong cùng luồng
   transaction phối hợp.

Retry vận chuyển giữ key. Người dùng chủ động “chạy lại” job terminal tạo key và
JobId mới.

## Luồng worker

1. Scheduler chọn execution ready.
2. Account allocator cấp seat trước khi lease execution.
3. Runtime tạo attempt ở `preparing`, chuyển member sang `running`.
4. Worker thực hiện đúng một attempt và báo phase/fact.
5. Runtime commit success, partial hoặc error; worker không tự retry.
6. Runtime release scheduler/account lease và chiếu state ra UI.

## Kết quả và late result

Kết quả gắn với work key và lease. Result committer chỉ chấp nhận lease hiện
hành, tôn trọng `replace_current`, từ chối result bị revoke/stale và ngăn attempt
cũ ghi đè version mới sau cancel/rerun/upload.

## Recovery

- Execution chưa lease: giữ nguyên ready/waiting.
- Lease có attempt chưa submit: đóng attempt cũ, release để retry ngay.
- Đã submit: đóng outcome `unknown`, finish execution và chuyển member
  `needs_attention`.
- Thiếu attempt record cho lease: cũng `needs_attention`; không đoán rằng chưa
  submit.

## Compatibility và rollback

`sfboard.py` giữ adapter/projection để API/UI cũ tiếp tục hoạt động. `JOBS` và
`hangdoi.py` không được là nguồn transition/retry production. Rollback:

```bash
GROKPIPE_JOB_MODE=legacy GROKPIPE_LIVE_EXECUTOR=0 ./chay-board.command <project>
```

Không rollback khi còn authoritative execution active. Legacy chỉ được xoá sau
soak đủ dài và audit chứng minh không còn consumer bắt buộc.

## Tiêu chí kiến trúc

- Một authority cho mỗi quyết định.
- Identity bền vững và tra xuyên từ UI đến output.
- Mọi side effect idempotent.
- Retry dựa trên phase/credit, không dựa vào chuỗi lỗi mơ hồ.
- Concurrency có lease/transaction, không dựa vào check-then-set global dict.
- Restart có recovery xác định.
- Diagnostics không rò credential.
- Compatibility có ranh giới và đường loại bỏ rõ.
