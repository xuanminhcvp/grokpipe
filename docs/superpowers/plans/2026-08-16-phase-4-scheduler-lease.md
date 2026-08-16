# Phase 4 — Scheduler và execution lease

**Mục tiêu:** hàng đợi thao tác bằng `execution_id`, một lease atomic thay nhịp
"nhấc việc rồi mới kịp ghi `running`", và huỷ một thành viên phải tra ra được lô
vật lý mà không cần quét `JOBS`.

**Ranh giới:** legacy `PriorityQueue` vẫn là backend thực thi trong phase này.
`Scheduler` mới không xếp hàng thay, không gọi provider, không cấp tài khoản.
Mode mặc định vẫn `legacy`.

## Vì sao phase này tồn tại

Hai lỗ hổng đang có, cả hai đều là hệ quả của "hàng đợi mang tên asset":

1. **Huỷ một thành viên không tìm ra lô.** `/api/huy-viec` tìm lô vật lý bằng
   cách quét `JOBS` lấy khoá `LO:` đang `queued`. Nhưng lúc lô mới xếp, `JOBS`
   chỉ có nhãn của TỪNG THÀNH VIÊN — khoá `LO:a,b` chưa tồn tại (nó chỉ được
   ghi khi thợ nhấc việc hoặc khi lô phải chờ khoá địa điểm). Kết quả: bấm huỷ
   một ảnh trong lô đang chờ thì server trả "đã huỷ 0 lô" còn lô vẫn nằm nguyên
   trong hàng và vẫn chạy. Đây là `xfail`
   `test_member_only_jobs_can_resolve_physical_group_queue_identity`.
2. **Cửa sổ "đã nhấc nhưng vẫn queued".** Từ `_lay()` tới lúc ghi `running` là
   một khoảng có thật; người gác coi việc đó là mồ côi và xếp lại. Đã vá bằng
   cách ghi `running` ngay khi nhấc, nhưng đó là vá — cấu trúc đúng là một
   thao tác lease ATOMIC.

## Task 1 — `sfboard/jobs/scheduler.py` thuần

Không import queue/playwright/account/hangdoi. Chỉ dữ liệu và thời gian truyền vào.

- `ScheduledExecution`: `execution_id · kind · queue_ident · member_keys ·
  priority · not_before · state · version · lease_id · lease_expires_at`.
- `Scheduler.schedule(...) -> ScheduledExecution` — cùng `queue_ident` đang
  READY/LEASED thì trả lại bản cũ (idempotent), không tạo execution thứ hai.
- `lease_next(kind, now, ttl)` — atomic: chọn theo `(priority, seq)`, bỏ qua
  `not_before` chưa tới, chuyển READY → LEASED và tăng version trong cùng lock.
- `lease_ident(kind, queue_ident, now, ttl)` — thợ legacy đã nhấc ident nào thì
  gắn lease đúng execution đó.
- `heartbeat · finish · release(not_before) · expire_leases(now)`.
- `execution_for_member(member_key)` và `cancel_member(member_key)` — đây là
  cửa trả lời "thành viên này thuộc lô vật lý nào".

Test trước: lease loại trừ hai thợ, hết hạn rồi mới cho thuê lại, `not_before`,
thứ tự ưu tiên, group lease chuyển cả lô trong một thao tác, schedule trùng
`queue_ident` không nhân bản.

## Task 2 — Đăng ký execution lúc giao việc

`_producer_submit` (mode shadow) đăng ký mỗi `LegacyAction` thành một
execution: `queue_ident`, `member_keys` = `state_idents` hoặc `legacy_keys`,
`priority = _uu_tien(queue_ident)`. Lỗi ở tầng scheduler KHÔNG được làm hỏng
việc giao — bọc fail-open như observer.

## Task 3 — Huỷ tra đúng lô vật lý

`_lo_chua(sf)` trả về danh sách ident lô đang chờ có chứa `sf`, theo thứ tự:

1. Scheduler (mode shadow) — nguồn đúng nhất.
2. HÀNG ĐỢI THẬT (`y_trong_hang(IMG_QUEUE)` + `CHO_RIENG`) — dùng cho mode
   legacy. Hàng đợi mới là nơi biết việc gì đang chờ; `JOBS` chỉ là nhãn.
3. Quét `JOBS` như cũ — giữ lại để không bỏ sót lô đã có khoá `LO:`.

`/api/huy-viec` dùng hàm này. Xoá `xfail` và thay bằng regression hành vi: xếp
`LO:A,B` với `JOBS` chỉ có nhãn thành viên, gọi `/api/huy-viec?sf=A`, phải thấy
lô bị gỡ khỏi hàng và phần còn lại được xếp lại.

## Task 4 — Thợ gắn lease (chỉ quan sát)

Trong `_worker`, sau khi nhấc được ident: mode shadow gọi `lease_ident`, xong
việc gọi `finish`. Không đổi luồng legacy, bọc try/except. Đây là bằng chứng
cho bất biến "không còn cửa sổ đã-nhấc-mà-vẫn-queued" trước khi Phase 10 giao
hẳn quyền cho scheduler.

## Cổng ra

- `./test-job-lifecycle.command` xanh, `xfailed` còn đúng **1** (forced-account,
  thuộc Phase 5).
- AST guard cũ vẫn xanh; `scheduler.py` nằm trong danh sách quét lõi.
- Smoke trơ trên board: không tạo việc thật, không tiêu credit.
