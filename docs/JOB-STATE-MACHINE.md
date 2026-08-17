# State machine chuẩn cho job ảnh/video

> Implementation authority: `sfboard/jobs/models.py`, `manager.py`,
> `runtime.py` và `retry.py`.

## Job states

| State | Ý nghĩa |
|---|---|
| `created` | intent/job đã ghi bền vững, chưa schedule |
| `queued` | execution đã schedule và sẵn sàng/chờ `not_before` |
| `running` | execution có lease và attempt active |
| `retry_wait` | attempt lỗi an toàn để retry, đang chờ |
| `completed` | output đã commit |
| `failed` | lỗi terminal hoặc hết retry budget |
| `cancelled` | bị user/system hủy hợp lệ |
| `needs_attention` | outcome không rõ hoặc cần quyết định thủ công |

Terminal: `completed`, `failed`, `cancelled`. Không tự coi
`needs_attention` là terminal.

## Transition chính

```text
created ──schedule──▶ queued ──lease──▶ running ──success──▶ completed
                               │          ├─ retryable ────▶ retry_wait
                               │          ├─ permanent ────▶ failed
                               │          └─ unknown ──────▶ needs_attention
                               │
retry_wait ──not_before due────┘

created/queued/retry_wait ──cancel──▶ cancelled
running ──safe cancel───────────────▶ cancelled
```

Mọi transition phải đi qua runtime/manager, sinh event actor/type/reason và nằm
trong transaction phù hợp.

## Attempt phases

| Phase | Credit semantics |
|---|---|
| `preparing` | chưa submit |
| `attaching` | đang chuẩn bị input, chưa submit |
| `ready_to_submit` | sẵn sàng, chưa submit |
| `submitted` | đã bấm gửi; có thể đã tiêu credit |
| `waiting_provider` | đang chờ provider |
| `downloading` | đã có kết quả, đang tải |
| `saving` | đang ghi output |
| `finished` | attempt đóng |

`submitted_at`, không chỉ tên phase hiện tại, là fact quan trọng để recovery và
retry biết submit đã xảy ra.

## Retry policy

| Error class/tình huống | Hành động |
|---|---|
| user cancel | `cancelled`, không tính retry budget |
| validation/permanent | `failed`, không phạt account |
| quota/rate-limit trước submit | `retry_wait`, backoff, cooldown + rotate |
| account lost trước submit | `retry_wait`, rotate |
| session transient lần đầu trước submit | retry ngay cùng account |
| session/provider transient tiếp theo | backoff, có thể rotate |
| unknown outcome | `needs_attention` |
| session/account lost sau submit | `needs_attention` |
| batch partial | retry execution cho member chưa xong |

Default submit budget do policy cấu hình theo kind; whole-execution retry có
trần riêng. Không thêm bộ đếm retry ở worker/UI/watchdog.

## Partial batch

Một execution ảnh có thể chứa nhiều job. Khi provider trả thiếu:

1. Output hợp lệ được commit cho đúng member.
2. Member đã `completed` không quay lại `running`.
3. Member thiếu output chuyển `retry_wait` nếu còn budget.
4. Retry execution chỉ chứa/diễn giải member còn sống theo runtime contract.

Không gán kết quả theo thứ tự tab hoặc tên file không kiểm chứng.

## Cancel

### Chưa chạy

`created`, `queued`, `retry_wait` có thể cancel. Scheduler bỏ execution/member,
runtime chuyển toàn bộ member vật lý liên quan sang `cancelled`.

### Image đang chạy

Runtime đóng attempt `cancelled`, finish execution, revoke result lease và
release account. Result đến muộn không được commit.

### Video đang chạy

- Trước submit: cancel như một attempt chưa tốn credit.
- Sau submit: không giả vờ hủy provider; trả `video.already_submitted`, tiếp tục
  quan sát hoặc đưa về xử lý outcome phù hợp.

## Dừng tất cả

Safe stop phải:

1. chặn producer/worker lấy thêm việc;
2. cancel các execution chưa submit;
3. xử lý execution đang chạy theo luật image/video ở trên;
4. release seat/lease có thể release;
5. phản ánh state server thật ra UI.

Không chỉ clear hàng đợi hiển thị. “Emergency stop” tiến trình chỉ dùng khi có
nguy cơ tiếp tục tiêu credit hoặc làm hỏng dữ liệu, và restart recovery vẫn phải
phân biệt trước/sau submit.

## Account semantics

- Allocation xảy ra trước execution lease.
- Preferred account là gợi ý; forced account có fallback policy rõ.
- Quota cooldown account, không fail vĩnh viễn job.
- Fatal account loss cập nhật health.
- Một lỗi tab/job không mặc định xoay hoặc đóng mọi account khác.
- Release seat phải xảy ra ở mọi outcome, kể cả exception/rollback.

## Restart/recovery

| Trạng thái bền vững | Recovery |
|---|---|
| execution ready/waiting | giữ nguyên |
| leased + attempt trước submit | đóng attempt lỗi, release → retry |
| leased + attempt đã submit | `needs_attention`, không resubmit |
| leased nhưng thiếu attempt | `needs_attention` |
| job terminal | không đổi |

## Mutation và rerun

- Chạy lại job terminal tạo JobId/intent mới.
- Upload/xoá/gắn asset khi có job active phải đi qua policy; mutation ghi dấu để
  late result không ghi đè.
- `replace_current=false` giữ current version đã duyệt.
- Cancel token/lease cũ không có quyền tác động generation mới.

## Transition bị cấm

- `completed → running` để retry lô partial.
- `cancelled → completed` bởi late result.
- `failed → queued` mà không tạo intent/rerun mới.
- `running → queued` không đóng attempt/lease.
- `needs_attention → retry_wait` tự động khi chưa có quyết định outcome.
- Ghi state trực tiếp từ UI, DOM worker, watchdog hoặc legacy projection.

## Gỡ `needs_attention`

`needs_attention` chỉ ra khỏi trạng thái đó bằng QUYẾT ĐỊNH CỦA NGƯỜI:

- `LifecycleRuntime.resolve_needs_attention` đưa job sang `cancelled`, actor
  `user`, reason `user.resolved_needs_attention`. Attempt cũ có thể đã tiêu
  credit nên nó không bao giờ được hồi sinh — lần chạy sau là intent mới.
- Giao diện gọi đường này qua `/api/xoa-loi` (nút “Dọn lỗi” và ✕ từng dòng).
- Auto KHÔNG được tự chạy đè lên scene còn `needs_attention`: vòng quét dừng,
  tự tắt và báo “Dọn lỗi rồi chạy lại”.

## Mở lứa mới cho một scope

Khoá intent của auto cố định theo scope, nên nó phải mang thêm thế hệ:

- Lứa trước còn sống (`created`/`queued`/`running`/`retry_wait`/
  `needs_attention`) → replay, không xếp thêm lượt.
- Lứa trước `failed` → auto vẫn bị chặn; lỗi permanent phải do người quyết
  định. Rerun tay vẫn mở.
- Lứa trước `cancelled`/`completed` → auto được mở thế hệ mới, khoá đổi theo
  parent terminal và job mới mang `rerun_of`.
