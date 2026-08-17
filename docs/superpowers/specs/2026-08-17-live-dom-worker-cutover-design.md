# Live DOM worker cutover — thiết kế được duyệt

Trạng thái: **ĐÃ ĐƯỢC DUYỆT** qua yêu cầu triển khai live ngày 2026-08-17.
ChatGPT được phép test tự do; Grok có trần cứng tối đa **20 lần submit** cho toàn
bộ canary, kể cả khi board hoặc process bị restart.

## Mục tiêu

Nối worker Chrome/DOM thật vào `LifecycleRuntime` mà không trả lại quyền quyết
định queue, retry, account, cancel hoặc result cho code legacy. Việc bật live là
opt-in riêng; mode authoritative không bật live vẫn inert và không mở Chrome.

## Quyết định kiến trúc

Chọn adapter **một lần thử** (one-attempt) dùng lại session/DOM hiện có:

```text
producer command
      │
      ▼
LifecycleRuntime ── lease + account seat ──► live worker
      ▲                                      │
      │ phase/result/error facts             ▼
      └──────────────────────────── one-attempt DOM executor
                                             │
                                             ▼
                                      ResultCommit
                                             │
                                             ▼
                                compatibility UI projection
```

Không gọi nguyên `_generate_lo_ruot` hoặc `_gen_video` từ runtime vì hai hàm
legacy vẫn tự ghi `JOBS`, retry, xoay Chrome và xếp queue. Không viết lại toàn bộ
provider layer trong đợt này vì phạm vi/rủi ro DOM quá lớn. Các hàm session được
thêm callback phase tùy chọn, giữ tương thích tuyệt đối với đường legacy.

## Authority và feature flag

- `legacy`: giữ nguyên worker cũ.
- `authoritative` không có live flag: runtime/fake path hiện tại, không mở Chrome.
- `authoritative` + `GROKPIPE_LIVE_EXECUTOR=1`: worker mới được phép lease và gọi
  Chrome thật.
- Auto producer bị giữ tắt trong canary. Mọi ca live được đưa vào có chủ đích.
- Worker live không được gọi `_enqueue`, `_xep`, `PriorityQueue.put`,
  `_xoay_chrome`, hoặc ghi trực tiếp `JOBS`.

`LifecycleRuntime` là nơi duy nhất lease, retry, cancel, chọn account và finalize.
Worker chỉ phát facts và file đầu ra. `CompatibilityProjection` là nơi duy nhất
đổi dữ liệu lifecycle thành nhãn UI cũ.

## Account và browser session

`RuntimeLease` mang cả `account_id`, `account_seat_id` và `account_slot`. Worker
gán `_TL.endpoint`/`_TL.slot` từ lease trước khi tạo session; khi seat thay đổi,
session thread-local cũ được đóng/bỏ trước khi dùng seat mới. Mất session trước
submit là lỗi transient của account; mất dấu kết quả sau submit là
`UNKNOWN_OUTCOME`, không submit lại mù.

## Phase và ranh giới tính credit

Callback được đặt sát hành vi DOM thật:

1. `ATTACHING`: chuẩn bị/upload ref hoặc start frame.
2. `SUBMITTED`: chỉ phát ngay sau khi nút submit thành công.
3. `WAITING_PROVIDER`: provider đã nhận yêu cầu, đang chờ output.
4. `DOWNLOADING`: trước khi tải URL/video về máy.
5. `SAVING`: trước khi đưa file vào version path.

Với Grok, callback `before_submit` đặt ngay trước `_bam_submit` để atomically giữ
một suất budget. Suất đã giữ không hoàn lại dù thao tác click thất bại; cách đếm
bảo thủ này đảm bảo số submit thật không bao giờ vượt trần.

## Image one-attempt

- Chỉ lấy các member còn `RUNNING` trong lease, theo thứ tự asset ổn định.
- Dựng prompt/ref giống đường legacy nhưng không mutation lifecycle.
- Gọi `ChatGPTSession.generate_lo` đúng một lần; callback báo `SUBMITTED` ngay sau
  `_gui` thành công.
- Tải toàn bộ kết quả về turn directory bằng downloader hiện có.
- Chỉ map file sang member khi số ảnh hợp lệ đúng bằng số member và không lẫn
  text/error. Nếu thiếu/thừa/không xác định mapping, giữ file turn để debug nhưng
  trả partial outcome; runtime sử dụng retry budget của execution.
- Member đã `COMPLETED` không được chạy lại trong attempt kế tiếp.

## Video one-attempt

- Validate shot, prompt và start frame trước submit.
- Cho phép reconnect nội bộ chỉ trước submit.
- `before_submit` giữ Grok budget; sau `SUBMITTED`, mọi lỗi không chứng minh được
  provider chưa nhận đều thành `UNKNOWN_OUTCOME`/`NEEDS_ATTENTION`.
- Tải và lưu main/extra files vào version paths, rồi trả mapping theo `JobId`.
- Executor không retry, re-enqueue, đổi account health hay ghi `JOBS`.

## Result, cancel và late outcome

Adapter chuyển output sang `ResultCommit`:

- `ACCEPT`: cập nhật current/picked cho board.
- `STORE_AS_VERSION` hoặc `REJECT`: không ghi đè current; version đã tốn lượt vẫn
  được giữ để đối chiếu.
- Cancel trước submit kết thúc `CANCELLED` và adapter không được finalize lease đã
  bị runtime thu hồi.
- Cancel video sau submit bị runtime từ chối; worker tiếp tục tải để tránh mất
  kết quả đã tính credit.
- `nen_dung` đọc state runtime, không đọc cờ queue legacy.

## Trần Grok bền vững

- Live Grok chỉ chạy khi có limit hợp lệ và khác 0.
- Canary cấu hình `GROKPIPE_LIVE_GROK_LIMIT=20`.
- Reservation được ghi atomically vào `.grokpipe/live-grok-canary.json` trước
  click submit. File chứa scope/counter và được fsync; restart không reset.
- Một process không được giảm counter hoặc đổi scope khi đang còn execution.
- Khi đủ 20 reservation, mọi video attempt dừng trước submit với lỗi rõ ràng.
- ChatGPT không dùng budget này.

## Canary

Chỉ bắt đầu sau khi unit/fake/static/full lifecycle/compile đều xanh:

1. Backup project state và xác nhận queue rỗng.
2. Khởi động board controlled bằng authoritative + live flag, auto producer tắt.
3. Chạy một image/REF ChatGPT; xác minh đúng một submit, file tải được, current
   cập nhật và UI hoàn tất.
4. Chạy batch REF/nhiều ảnh; kiểm mapping, partial retry, cancel và restart.
5. Chạy một video Grok, sau đó chỉ mở rộng đến các ca cần thiết; tổng reservation
   không quá 20.
6. Dừng ngay khi có submit trùng, session/account sai hoặc download không về.

Default vẫn là `legacy` trong canary. Chỉ cân nhắc đổi default sau khi có log/file
evidence và invariant monitor không báo mismatch.

### Kết quả canary 2026-08-17

- ChatGPT single REF trả/tải `1/1` trong một attempt.
- Grouped `PORTRAIT + *_FULL` trả/tải `2/2` trong một execution. Canary đầu phát
  hiện backend tách dependency nội bộ; regression được viết đỏ trước khi sửa.
- Stop-all trước submit không tạo attempt/output và không hồi sinh; recovery sau
  restart giữ nguyên job identity và chỉ tạo một attempt.
- Grok dùng một persisted reservation trong giới hạn `1/20`, tải MP4 hợp lệ và
  decode đầy đủ không lỗi; mọi invariant monitor đều bằng 0.

Quyết định sau canary ban đầu là giữ `legacy` tới Phase 12. Phase 12 ngày
2026-08-17 đã chuyển launcher/runtime default sang `authoritative + live`, đưa
structured lifecycle vào UI/API và bật auto-producer mới; legacy còn lại là
rollback explicit trong thời gian soak, không chạy song song với authority mới.

## Verification bắt buộc

- Regression đỏ–xanh cho callback placement, account slot, cancellation race và
  persisted Grok budget.
- Fake one-attempt image/video tests cho success, partial, pre/post-submit error,
  cancel và late output.
- Static authority guard cho worker live.
- `./test-job-lifecycle.command`, full pytest, compile gate, `git diff --check`.
- Live canary lưu log, phase timeline, số reservation và output paths làm evidence.

## Rollback

Tắt `GROKPIPE_LIVE_EXECUTOR` và restart board để quay về worker legacy. Không
rollback khi runtime còn execution active; phải cancel/resolve rõ từng execution
trước để tránh hai worker cùng xử lý một job.
