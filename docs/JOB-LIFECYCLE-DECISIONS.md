# Quyết định lifecycle job đã chốt

> Trạng thái: **đã phê duyệt và đã triển khai**. Các mã D01–D29 được giữ ổn
> định để test, commit và hồ sơ migration còn tra cứu được.

## Nguyên tắc nền

- Một authority cho state/retry/account/result.
- Tách identity logic khỏi đơn vị thực thi vật lý.
- Mọi side effect idempotent và bền vững.
- Retry phải biết đã submit hay chưa.
- UI là projection; SQLite là source of truth.

## D01 — Identity

`AssetId`, `JobId`, `BatchId`, `ExecutionId`, `AttemptId` là các identity riêng.
Không dùng asset key hoặc queue label thay cho JobId.

## D02 — Lô ảnh nhiều asset

Một image execution có thể gộp nhiều job; từng job giữ state/output riêng. Lỗi
partial không được làm mất kết quả member đã xong.

## D03 — Multi-copy

Mỗi copy là một JobId riêng trong batch `multi_copy`, có thể truy vết và retry
độc lập.

## D04 — Bộ state

Dùng đúng tám state: `created`, `queued`, `running`, `retry_wait`, `completed`,
`failed`, `cancelled`, `needs_attention`.

## D05 — Rerun terminal

Rerun là intent và JobId mới; không hồi sinh job terminal cũ.

## D06 — Độ bền

SQLite lifecycle trong project là nguồn sự thật. Restart phải recover, không
được mất queue hoặc dựng lại state chỉ từ UI.

## D07 — Idempotency

Cùng key + cùng payload replay intent cũ; cùng key + payload khác conflict.
Active scope chặn intent sống cạnh tranh cùng asset.

## D08 — Error taxonomy

Phân biệt cancelled, validation, permanent, provider transient, session
transient, account lost, quota/rate-limit và unknown outcome; mỗi lớp có action
và account policy riêng.

## D09 — Trần retry ảnh

Retry ảnh bị giới hạn bởi submit budget và whole-execution budget trong một
`RetryPolicy`; worker/watchdog không có bộ đếm riêng.

## D10 — Output ảnh thiếu/thừa

Thiếu output là partial; output hợp lệ commit theo member. Output thừa/không ánh
xạ chắc chắn không được tự gán. Zero output là lỗi attempt.

## D11 — Retry và credit video

Submit fact là ranh giới credit. Lỗi sau submit hoặc outcome không rõ chuyển
`needs_attention`, không tự submit lần nữa.

## D12 — Auto sau lỗi terminal

Auto không tự hồi sinh job terminal. Rerun cần intent mới theo policy/operator.

## D13 — Cancel queued/retry-wait

Hủy execution/member bền vững và chuyển `cancelled`; không chỉ xóa item UI.

## D14 — Dừng job đang chạy

Image có thể revoke lease/cancel attempt. Video sau submit không được báo hủy
giả; runtime trả reason rõ.

## D15 — Dừng tất cả

Stop-all chặn nhận việc mới và áp dụng cancel theo execution/phase cho mọi item.
State UI phải lấy lại từ server.

## D16 — Watchdog

Watchdog chỉ phát hiện/báo fact hoặc kích hoạt recovery đã định; không tự ghi
state, tự release tùy tiện hay re-enqueue.

## D17 — Assignment mặc định

Allocator chọn account healthy có seat; quota và concurrency là constraint
runtime, không phải lựa chọn DOM ad-hoc.

## D18 — Forced account

Force áp dụng cho execution/intent đã yêu cầu. Fallback chỉ xảy ra nếu policy
cho phép; không trở thành mặc định vĩnh viễn cho asset.

## D19 — Lỗi tab và account

Lỗi một tab/job không tự làm hỏng toàn account. Chỉ fatal account fact mới đổi
health; quota dùng cooldown.

## D20 — Video trên account ảnh

Khả năng chạy video do capability/config account quyết định. Không suy ra chỉ
từ việc account đã chạy ảnh.

## D21 — Recovery

Trước submit → retry; sau submit/thiếu attempt → `needs_attention`; terminal giữ
nguyên.

## D22 — Ordering và fairness

Scheduler tôn trọng ready time/`not_before`; retry có backoff không được chen
vô hạn làm đói job mới.

## D23 — Cancel token

Token/lease thuộc generation cụ thể. Token cũ đến muộn không được cancel hoặc
commit vào generation mới.

## D24 — Server state và UI

UI có thể hiển thị pending nhưng phải reconcile response/projection server;
không tự quyết state cuối.

## D25 — API và `JOBS`

Giữ response tương thích trong migration, nhưng mọi producer đi qua command
boundary. `JOBS`/legacy chỉ là projection/adapter, không là authority.

## D26 — Atomicity

Intent, schedule, transition, attempt, fact và cancel quan trọng phải nằm trong
repository transaction; rollback phải khôi phục cache/constraint.

## D27 — Retention và dọn

Dọn UI/history không được xoá fact cần cho idempotency, audit, recovery hoặc
credit. Retention vật lý cần policy riêng.

## D28 — Asset mutation khi active

Upload/xóa/gắn asset phải ghi nhận mutation hoặc từ chối theo policy để late
result không ghi đè thay đổi của người dùng.

## D29 — Tạo lại asset đã duyệt

`replace_current` là lựa chọn rõ. Tạo version mới không mặc định thay current đã
duyệt; commit result phải tôn trọng policy.

## Thay đổi quyết định

Muốn đổi D01–D29 phải có:

1. bug/requirement cụ thể;
2. cập nhật design và migration impact;
3. regression/property test trước implementation;
4. audit mọi authority/writer;
5. full lifecycle gate và kế hoạch rollback.
