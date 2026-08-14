# Các quyết định vòng đời job cần phê duyệt

Trạng thái tài liệu: **ĐÃ ĐƯỢC NGƯỜI DÙNG PHÊ DUYỆT TOÀN BỘ KHUYẾN NGHỊ**
Ngày phê duyệt: 2026-08-14
Ngày lập: 2026-08-14
Nguồn đối chiếu: `docs/JOB-LIFECYCLE-AUDIT.md` và code trong working tree hiện tại.

Tài liệu này không phải kiến trúc đích và không cho phép refactor production. Mục
đích của nó là tách các quyết định sản phẩm/lifecycle ra khỏi chi tiết triển khai,
để `JOB-ARCHITECTURE-TARGET.md` và `JOB-STATE-MACHINE.md` sau này không âm thầm
chọn hành vi thay người dùng.

## Kết quả phê duyệt

- Người dùng đã phê duyệt toàn bộ khuyến nghị D01–D29 ngày 2026-08-14.
- Các khuyến nghị là baseline bắt buộc của kiến trúc đích và state machine.
- Mọi thay đổi sau này phải ghi decision mới hoặc amendment có ngày, lý do và test
  bị ảnh hưởng; không sửa âm thầm policy đã duyệt.

## Các nguyên tắc nền đề xuất

1. `asset_id`, `job_id`, `attempt_id` và `batch_id` là các identity khác nhau.
2. Mỗi explicit rerun tạo một `job_id` mới; không hồi sinh job terminal cũ.
3. Server là nguồn sự thật duy nhất; UI, queue và worker không sở hữu lifecycle.
4. Cancel của một run phải thắng mọi timer, retry, watchdog và auto snapshot cũ.
5. Retry chỉ xảy ra theo error class và policy đã khai báo, không suy từ chuỗi lỗi.
6. Mỗi lần có khả năng tiêu credit phải được ghi thành một attempt riêng.

---

## D01 — Identity của asset, job, attempt và batch

**Hiện tại**

Một id SF/shot đồng thời được dùng làm asset id, queue identity, khóa `JOBS`, khóa
cancel và khóa retry. Lô ảnh dùng chuỗi phụ thuộc thành viên như `LO:a,b,c`.

**Lựa chọn**

- A. Giữ một id cho mọi khái niệm.
- B. Tách `asset_id`, `job_id`, `attempt_id`, `batch_id`.
- C. Chỉ thêm `job_id`, các identity còn lại vẫn suy từ job.

**Khuyến nghị: B.** `asset_id` chỉ tài sản ổn định; `job_id` là một lần user/auto
yêu cầu tạo; `attempt_id` là một lần executor thử; `batch_id` nhóm nhiều job có
cùng ý định hoặc cùng provider request. Đây là điều kiện để cancel, retry,
multi-copy và manual rerun không giẫm nhau.

**Code bị ảnh hưởng:** queue tuple, `JOBS`, `DA_HUY`, `DUNG_RIENG`, `TAY_SF`,
`_HOAN`, `BATCH`, API generate/video và UI queue drawer.
**Test bắt buộc:** rerun terminal sinh job mới; cancel run cũ không chặn run mới;
hai attempt không ghi đè lịch sử nhau.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D02 — Mô hình lô ảnh nhiều asset

**Hiện tại**

Một tin ChatGPT có thể tạo ảnh cho nhiều SF. Queue coi cả chuỗi `LO:a,b,c` là một
item, còn `JOBS` chủ yếu hiển thị từng thành viên. Không có entity biểu diễn provider
request dùng chung.

**Lựa chọn**

- A. Coi cả lô là một job; member chỉ là metadata.
- B. Mỗi asset có một job; `Batch/Execution` nhóm các job được gửi chung.
- C. Mỗi member hoàn toàn độc lập; executor tự gom động khi chạy.

**Khuyến nghị: B.** Mỗi asset cần terminal state riêng, nhưng một execution chung
phải ghi rõ tất cả member job để cancel, retry và partial result nhất quán.

**Code bị ảnh hưởng:** `_auto_scene`, `/api/tao-lo`, `/api/master`, `_generate_lo`,
`_generate_lo_ruot`, `dat_job`, cancel member và UI nhóm lô.
**Test bắt buộc:** partial success; cancel một member trước khi chạy; cancel trong
lúc provider request chung đang chạy; retry không làm job đã thành công regress.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D03 — Ý nghĩa của multi-copy

**Hiện tại**

`/api/generate?n>1` xếp nhiều item có cùng ident. Chúng là các kết quả user muốn
giữ để lựa chọn, nhưng state lại giống nhiều retry của cùng job.

**Lựa chọn**

- A. Coi mỗi copy là một attempt của cùng job.
- B. Coi mỗi copy là một child job/output độc lập trong một batch.
- C. Một job có trường `desired_copies` và state tổng hợp, không có child job.

**Khuyến nghị: B.** Retry là thử lại để đạt cùng một output; multi-copy là nhiều
output có chủ ý và phải có success/failure/account riêng.

**Code bị ảnh hưởng:** `/api/generate`, `_enqueue`, `BATCH`, `_batch_tick`, lưu
versions và UI progress.
**Test bắt buộc:** N copy với tổ hợp success/failure; retry một copy không tạo thêm
copy ngoài yêu cầu; terminal aggregate không phụ thuộc thứ tự worker hoàn tất.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D04 — Bộ state chuẩn

**Hiện tại**

Chỉ có `queued`, `running`, `done`, `error`; retry wait, cancel requested, blocked,
partial và orphan được mã hóa trong `msg`.

**Lựa chọn**

- A. Giữ bốn state và thêm reason code.
- B. Dùng state đầy đủ: `CREATED`, `QUEUED`, `RUNNING`, `RETRY_WAIT`, `COMPLETED`,
  `FAILED`, `CANCELLED`, cộng `NEEDS_ATTENTION` cho external outcome không chắc chắn.
- C. State cực chi tiết cho mọi bước upload/submit/download/copy.

**Khuyến nghị: B.** Không thêm state theo từng bước DOM; chi tiết đó là attempt
phase/event. `NEEDS_ATTENTION` chỉ dùng khi restart sau submit mà không biết provider
đã tính credit/trả kết quả hay chưa.

**Code bị ảnh hưởng:** mọi writer `JOBS`, `/api/jobs`, queue drawer và auto logic.
**Test bắt buộc:** transition table; terminal không regress; retry wait có thể cancel;
unknown external outcome không tự submit lại.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D05 — Chạy lại job terminal

**Hiện tại**

Manual rerun và auto có thể ghi `queued/running` lên cùng khóa asset từng là
`done/error`, làm mất ranh giới giữa hai lần chạy.

**Lựa chọn**

- A. Revive job cũ và reset counter.
- B. Giữ job cũ terminal, tạo `job_id` mới liên kết `rerun_of`.

**Khuyến nghị: B.** Lịch sử, credit và cancel token của lần cũ phải bất biến.

**Code bị ảnh hưởng:** mọi endpoint tạo/tạo lại, auto, `chay-anh.py`, cleanup UI.
**Test bắt buộc:** completed/failed/cancelled không chuyển ngược; rerun có counter và
cancel scope mới.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D06 — Nguồn sự thật và độ bền qua restart

**Hiện tại**

`JOBS`, queue, timer, retry và cancel đều ở RAM; restart làm mất toàn bộ lifecycle.

**Lựa chọn**

- A. In-memory là target chính thức; restart nghĩa là bỏ toàn bộ job.
- B. `JobStore` SQLite là authoritative; queue có thể dựng lại từ store.
- C. File JSON event log.

**Khuyến nghị: B.** SQLite có transaction, compare-and-set, không cần dịch vụ ngoài
và phù hợp ứng dụng local. Migration nên bắt đầu bằng adapter tương thích in-memory,
sau đó mới bật persistence; không thay storage và lifecycle trong cùng một phase.

**Code bị ảnh hưởng:** startup `main`, `JOBS`, queue initialization, retry timers,
API jobs và cleanup.
**Test bắt buộc:** restart ở `QUEUED`, `RETRY_WAIT`, `RUNNING`; transaction đồng thời;
schema migration; file DB hỏng/lock.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D07 — Idempotency và enqueue trùng

**Hiện tại**

Mỗi producer có điều kiện chống trùng khác nhau. Không có uniqueness constraint cho
logical run; cùng ident có thể nằm trong queue nhiều lần ngoài multi-copy chủ ý.

**Lựa chọn**

- A. Cho phép duplicate và để executor lọc file đã có.
- B. Mỗi active job có tối đa một queue entry/worker lease; request lặp trả lại job
  đang active.
- C. Mỗi API request luôn tạo job mới.

**Khuyến nghị: B.** API nhận idempotency key hoặc dùng constraint theo
`asset_id + request_scope`; explicit rerun chỉ hợp lệ khi không có active run hoặc
user xác nhận tạo parallel child job.

**Code bị ảnh hưởng:** `/api/generate`, `/api/tao-lo`, `/api/master`, video APIs,
auto, Scheduler.
**Test bắt buộc:** click đôi, HTTP retry, auto cooldown, hai HTTP thread đồng thời,
multi-copy có chủ ý.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D08 — Phân loại lỗi và hành động tương ứng

**Hiện tại**

Worker xoay account cho gần như mọi exception. `_loi_du_lieu()` chỉ thêm cảnh báo,
không ngăn retry ảnh. Một số reconnect và validation nằm trong executor.

**Lựa chọn**

- A. Mọi lỗi đều retry và rotate như hiện tại.
- B. Error class quyết định policy.
- C. Mỗi executor tự quyết policy riêng.

**Khuyến nghị: B**, với taxonomy tối thiểu:

| Error class | Retry | Account action | Credit |
|---|---|---|---|
| `VALIDATION` | Không | Không đổi | Không |
| `CANCELLED` | Không | Không đổi | Theo phase thực tế |
| `SESSION_TRANSIENT` trước submit | Có, cùng account một lần | Rotate nếu tái diễn | Không |
| `PROVIDER_TRANSIENT` | Có backoff | Có thể rotate | Theo `submitted_at` |
| `QUOTA/RATE_LIMIT` | Có nếu còn account/policy | Cooldown account, chọn account khác | Theo provider |
| `PERMANENT` | Không | Không đổi | Theo phase |
| `UNKNOWN_OUTCOME` | Không tự retry | Cách ly attempt | Có thể đã tiêu |

**Code bị ảnh hưởng:** `_worker`, `_loi_du_lieu`, executors, `_xoay_chrome`, retry
policy và UI error labels.
**Test bắt buộc:** mỗi error class dẫn tới đúng transition/account action.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D09 — Trần retry ảnh

**Hiện tại**

Retry worker ảnh là vô hạn; retry nguyên lô không trọn vẹn có trần 2; auto và script
ngoài lại có counter riêng.

**Lựa chọn**

- A. Giữ retry worker vô hạn.
- B. Trần cố định cho mọi ảnh.
- C. Trần cấu hình theo error class; hết trần thành `FAILED`, manual rerun tạo job mới.

**Khuyến nghị: C**, mặc định tối đa 8 attempt có khả năng submit, reconnect trước
submit không tính. Validation/permanent không retry. Con số phải cấu hình được nhưng
không được là nhiều counter chồng nhau.

**Lý do:** retry vô hạn che lỗi dữ liệu, giữ job không terminal và làm account quay
vòng qua đêm. Manual rerun vẫn cho user chủ động thử tiếp với run mới.

**Code bị ảnh hưởng:** `_worker`, `_xep_lai_sau`, `_HOAN`, auto, `chay-anh.py`.
**Test bắt buộc:** count theo submitted attempt; backoff; exhausted; manual rerun.
**Trạng thái:** Đã duyệt ngày 2026-08-14; chủ ý thay retry ảnh vô hạn bằng policy D09.

## D10 — Lượt ảnh trả thiếu/thừa/0/kèm chữ

**Hiện tại**

Executor gửi lại toàn bộ task tối đa `LO_THU_LAI=2`; sau đó ghép số ảnh nhận được
theo thứ tự và đánh lỗi member thiếu.

**Lựa chọn**

- A. Giữ retry toàn bộ lô và phép ghép theo thứ tự.
- B. Chỉ retry member thiếu dưới dạng request mới.
- C. Không retry tự động; đưa toàn bộ lượt vào review.

**Khuyến nghị: A với ràng buộc.** Giữ tối đa 2 retry để bảo toàn tính đồng bộ của
lô; lưu mọi output của mọi attempt; member đã hoàn tất không được regress; nếu thứ
tự không xác định thì chuyển member liên quan sang `NEEDS_ATTENTION` thay vì gắn
mù. Bật mã SF có thể cho phép ghép chắc chắn hơn.

**Code bị ảnh hưởng:** `_generate_lo_ruot`, hộp phân loại, metadata lượt, batch state.
**Test bắt buộc:** 0/N, thiếu giữa lô, thừa, có chữ, cancel giữa retry, output các
attempt trước vẫn truy cập được.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D11 — Retry và cách đếm credit video

**Hiện tại**

Video tối đa 5 `tries` ở worker, có thêm reconnect nội bộ một lần. `tries` tăng theo
exception vòng worker, không chứng minh request đã submit hoặc đã tiêu credit.

**Lựa chọn**

- A. Giữ “5 exception”.
- B. Tối đa 5 attempt đã submit; thao tác trước submit không tính credit attempt.
- C. Không retry video tự động.

**Khuyến nghị: B.** Ghi `submitted_at`/`consumes_credit`; reconnect trước submit là
cùng attempt hoặc preflight retry. Outcome không chắc chắn sau submit không được tự
submit lần nữa.

**Code bị ảnh hưởng:** `_gen_video`, `_worker`, Grok executor, daily credit counter.
**Test bắt buộc:** lỗi trước submit, sau submit, download lỗi, nhiều clip một submit,
restart sau submit.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D12 — Auto-runner sau khi job terminal lỗi

**Hiện tại**

Auto có retry/cooldown riêng và có thể tiếp tục gọi producer cho asset còn thiếu;
với video còn có thể enqueue lại item vẫn `queued`.

**Lựa chọn**

- A. Auto tạo job mới vô hạn cho tới khi có file.
- B. Auto chỉ tạo một job; retry nằm trong job policy; terminal failure cần user
  manual rerun.
- C. Auto được tạo tối đa N job mới sau terminal.

**Khuyến nghị: B.** Auto là producer, không phải retry controller. Nó không được
revive/tạo run mới khi cùng asset có failed job chưa được user xử lý.

**Code bị ảnh hưởng:** `_auto_allow`, `_auto_scene`, `_auto_runner`, AUTO state/UI.
**Test bắt buộc:** queued backlog, exhausted retry, bật/tắt auto, restart, manual
acknowledge rồi rerun.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D13 — Cancel job queued và retry-wait

**Hiện tại**

Cancel phải suy từ `JOBS` sang chuỗi lô trong queue. Timer retry không phải queue
item và mang state `running`, nên nhiều đường cancel không chạm được nó.

**Lựa chọn**

- A. Tiếp tục dùng flag theo ident và để worker bỏ qua sau khi nhấc.
- B. Transition atomically sang `CANCELLED`; queue/timer chỉ chạy item nếu version/
  lease còn hợp lệ.

**Khuyến nghị: B.** Không cần xóa vật lý chính xác khỏi heap; stale queue token phải
không lease được job đã cancelled. Cancel gắn với `job_id`, không gắn asset/ident.

**Code bị ảnh hưởng:** `/api/huy-viec`, `/api/huy`, `DA_HUY`, retry timer, Scheduler.
**Test bắt buộc:** cancel trước/sau dequeue, trong retry wait, token cũ đến muộn,
rerun cùng asset.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D14 — Dừng một job đang chạy

**Hiện tại**

Ảnh lô dùng cờ theo member nhưng provider request là cả lô; dừng một member làm cả
lô dừng. Video chỉ dừng đáng tin trước submit; sau submit nên chạy nốt để không mất
credit.

**Lựa chọn**

- A. Nút dừng member luôn cố dừng, bất kể side effect.
- B. Semantics phụ thuộc execution phase và provider.

**Khuyến nghị: B.** Ảnh đang chạy chung lô: UI phải nói rõ và yêu cầu xác nhận dừng
cả execution; mọi member chưa hoàn tất thành `CANCELLED`. Video trước submit có thể
cancel; sau submit từ chối cancel và để tải/lưu kết quả. Không hiển thị “đang dừng”
nếu hệ thống biết không thể dừng.

**Code bị ảnh hưởng:** `/api/dung-viec`, `_generate_lo_ruot`, `_gen_video`, UI drawer.
**Test bắt buộc:** image batch cancel, video pre/post submit, cancel đúng thời điểm
phase đổi.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D15 — Semantics của “Dừng tất cả”

**Hiện tại**

Tăng generation, clear auto, vét queue, gắn flags, bấm Stop trên browser và có thể
đóng Chrome. Vẫn có race với auto snapshot; video đã submit có thể bị mất kết quả.

**Lựa chọn**

- A. Hard stop: đóng mọi Chrome và chấp nhận mất outcome/credit.
- B. Controlled stop: cancel queued/retry-wait, ngăn producer mới, interrupt ảnh
  nếu có thể, để video đã submit hoàn tất và lưu.
- C. Hai nút riêng “Dừng an toàn” và “Dừng khẩn cấp”.

**Khuyến nghị: C.** Mặc định dùng controlled stop. Hard stop chỉ là thao tác khẩn
cấp có cảnh báo rõ nguy cơ mất credit/kết quả.

**Code bị ảnh hưởng:** `/api/dung-het`, auto generation, Scheduler, executors,
Chrome lifecycle và UI confirmation.
**Test bắt buộc:** stop đua auto/timer/watchdog; submitted video; hard stop; không job
mới chạy sau stop barrier.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D16 — Quyền của watchdog

**Hiện tại**

`_gac_hang_doi` suy orphan từ chênh lệch `JOBS`/queue và có quyền enqueue lại ảnh,
video; tự có counter tối đa 12.

**Lựa chọn**

- A. Giữ watchdog là re-enqueuer cứu hộ.
- B. Watchdog chỉ quan sát/cảnh báo; Scheduler phục hồi lease theo state/store.
- C. Bỏ watchdog hoàn toàn.

**Khuyến nghị: B.** Khi JobStore/Scheduler đã atomic, recovery là trách nhiệm của
Scheduler dựa trên lease, không phải suy từ UI state. Watchdog vẫn có giá trị phát
hiện invariant bị phá nhưng không được mutate lifecycle.

**Code bị ảnh hưởng:** `_gac_hang_doi`, queue inspection, metrics/logging.
**Test bắt buộc:** expired lease recovery đúng một lần; watchdog không enqueue;
cancel/stop không bị cứu lại.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D17 — Assignment tài khoản mặc định

**Hiện tại**

Worker gắn account cạnh tranh lấy item; job không lưu assignment. Nhãn account chỉ
được đóng dấu sau khi một thread ghi state.

**Lựa chọn**

- A. Tiếp tục để worker cạnh tranh không lưu assignment.
- B. `AccountAllocator` chọn account cho từng attempt và lưu trước khi execute.
- C. Job gắn cứng account từ lúc tạo.

**Khuyến nghị: B.** Job không cần account cố định; mỗi attempt phải có `account_id`,
selection reason và lease. Retry policy có thể loại account vừa lỗi.

**Code bị ảnh hưởng:** supervisor, `_worker`, `_TL`, `_pool`, `JOBS.tk`, account UI.
**Test bắt buộc:** hai worker cạnh tranh; retry đổi account; nhãn/history đúng;
account bị tắt giữa lease.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D18 — “Ép tài khoản” áp dụng trong bao lâu

**Hiện tại**

`/api/tao-lo?tk=port` đưa lần đầu vào `CHO_RIENG`; lỗi xong retry trở về queue chung,
nên có thể chạy account khác.

**Lựa chọn**

- A. Chỉ ép lần đầu, retry được fallback tự do.
- B. Ép toàn bộ job và mọi retry; hết khả dụng thì `FAILED/RETRY_WAIT` chờ chính nó.
- C. Ép ưu tiên, nhưng fallback sau N lần và phải ghi rõ.

**Khuyến nghị: B.** Từ “ép” phải có nghĩa ổn định. Nếu muốn C, UI phải gọi là
“ưu tiên tài khoản” và cho user chọn fallback.

**Code bị ảnh hưởng:** `/api/tao-lo`, `CHO_RIENG`, retry timer, AccountAllocator.
**Test bắt buộc:** forced account lỗi/tắt/restart; không chạy nhầm account; explicit
allow-fallback.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D19 — Một tab lỗi có được xoay cả account không

**Hiện tại**

Một worker/tab exception có thể `_xoay_chrome`, đóng cả cửa sổ account và làm các
tab/job sibling cùng rơi.

**Lựa chọn**

- A. Mọi lỗi job đóng cả account như hiện tại.
- B. Chỉ lỗi browser/session fatal mới đóng account; lỗi job/provider chỉ kết thúc
  attempt và cập nhật health/cooldown.
- C. Không bao giờ tự đóng account.

**Khuyến nghị: B.** Blast radius phải theo loại lỗi. Khi thật sự đóng browser, mọi
lease sibling phải nhận event `ACCOUNT_LOST` và được recovery có kiểm soát.

**Code bị ảnh hưởng:** `_worker`, `_xoay_chrome`, `_mark_dead`, supervisor, `BAN`.
**Test bắt buộc:** một tab DOM lỗi; browser crash; nhiều tab đang chạy; hai account
lỗi đồng thời.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D20 — Video chạy nhờ account ảnh

**Hiện tại**

Nếu không có account Grok bật, `_pool("vid")` dùng account ảnh. Profile đó có thể
không đăng nhập Grok; lỗi video không được phép đóng nhầm cửa sổ ảnh nhưng vẫn gây
worker/retry noise.

**Lựa chọn**

- A. Fallback tự động như hiện tại.
- B. Không fallback; video chờ tới khi có account video.
- C. Fallback chỉ khi account ảnh được user đánh dấu `allow_video=true`.

**Khuyến nghị: C.** Không suy rằng profile ChatGPT đã đăng nhập Grok. Capability
phải là cấu hình rõ ràng.

**Code bị ảnh hưởng:** `_pool`, supervisor, account schema/UI.
**Test bắt buộc:** không account video; account ảnh opt-in/opt-out; queue không quay
lỗi vô ích.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D21 — Recovery sau restart

**Hiện tại**

Không recovery; auto/script suy asset còn thiếu rồi tạo lại mà không biết attempt
cũ đã submit hay chưa.

**Lựa chọn**

- A. Mọi active job cũ thành `CANCELLED` khi restart.
- B. Recover `QUEUED/RETRY_WAIT`; `RUNNING` hết lease được retry.
- C. Recover theo execution phase và khả năng side effect.

**Khuyến nghị: C.** `QUEUED/RETRY_WAIT` phục hồi. `RUNNING` trước submit có thể
retry. `RUNNING` sau submit nhưng chưa có outcome chuyển `NEEDS_ATTENTION`, không tự
submit lại, đặc biệt với video có credit.

**Code bị ảnh hưởng:** JobStore, startup, executor phase events, Scheduler leases.
**Test bắt buộc:** kill/restart ở từng phase; không duplicate submit; user resolve
`NEEDS_ATTENTION`.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D22 — Queue ordering, retry fairness và `not_before`

**Hiện tại**

Priority dựa trên vị trí shot; retry timer xếp lại sau backoff nhưng khi vào queue
lại cạnh tranh theo priority gốc. Nhiều job sớm bị lỗi có thể liên tục quay lên đầu.

**Lựa chọn**

- A. Luôn giữ priority shot tuyệt đối.
- B. Priority shot + FIFO, nhưng retry có `not_before` và fairness penalty.
- C. FIFO thuần.

**Khuyến nghị: B.** Giữ thứ tự phim cho lần đầu, nhưng retry không được làm đói job
mới chạy được. Scheduler quản lý `not_before`, không dùng thread timer cho từng job.

**Code bị ảnh hưởng:** `hangdoi.uu_tien/xep`, `_xep_lai_sau`, Scheduler.
**Test bắt buộc:** ordering hậu tố shot; nhiều retry; starvation; cùng priority FIFO.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D23 — Cancel token và stop generation

**Hiện tại**

`DA_HUY` theo ident, `DUNG_RIENG` theo asset và `GEN` toàn cục. Cờ cũ có thể sống
qua lần chạy mới có cùng ident; producer phải nhớ gọi `bo_co_huy`.

**Lựa chọn**

- A. Giữ các set/generation và vá từng producer.
- B. Cancellation/version token gắn `job_id`; stop-all tạo system barrier/version.

**Khuyến nghị: B.** Queue token và worker lease mang expected version. Job/version
không khớp thì stale work bị bỏ mà không consume/clear cancel của run khác.

**Code bị ảnh hưởng:** `DA_HUY`, `DUNG_RIENG`, `GEN`, `bo_co_huy`, worker/timer.
**Test bắt buộc:** stale queue token, stale timer, rerun cùng asset, stop-all race.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D24 — Server state và optimistic UI

**Hiện tại**

Browser tự ghi local `JOBS=running` trước khi API trả lời; server có thể từ chối và
UI chỉ sửa lại ở lần poll sau.

**Lựa chọn**

- A. Giữ optimistic overwrite.
- B. UI có state riêng `submitting`; chỉ server response/poll cập nhật lifecycle.
- C. Optimistic lifecycle có request id và rollback.

**Khuyến nghị: B.** Đơn giản và tránh nguồn sự thật thứ hai. API trả `job_id`, state
và version ngay khi tạo thành công.

**Code bị ảnh hưởng:** `board.js`, generate/video APIs, `/api/jobs`.
**Test bắt buộc:** API reject/network error/click đôi; poll đến trong lúc submit.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D25 — Tương thích API và `JOBS` trong migration

**Hiện tại**

UI và script ngoài đọc `/api/jobs["jobs"]` theo asset id; nhiều endpoint chỉ trả
`ok` chứ không trả identity/version.

**Lựa chọn**

- A. Đổi API cùng lúc với core lifecycle.
- B. Giữ endpoint/schema cũ qua compatibility projection trong suốt migration;
  thêm API mới song song.
- C. Giữ API cũ vĩnh viễn làm public contract.

**Khuyến nghị: B.** JobStore là source thật; adapter chiếu active/latest job về
schema `JOBS` cho UI cũ. Chỉ chuyển UI sau khi core và regression tests ổn định.

**Code bị ảnh hưởng:** Handler `/api/jobs`, mọi API command, `board.js`,
`chay-anh.py`.
**Test bắt buộc:** contract API cũ; projection batch/member; UI cũ chạy qua từng
phase migration.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D26 — Atomicity và quyền transition

**Hiện tại**

Nhiều thread ghi dict trực tiếp; không có compare-and-set. Queue dequeue và state
`running` là hai thao tác tách rời.

**Lựa chọn**

- A. Thêm lock quanh `JOBS` nhưng giữ writer phân tán.
- B. Chỉ `JobManager` nhận command; `JobStore.transition(expected_state/version)`
  thực hiện atomic compare-and-set. Scheduler/worker/API không tự ghi state.
- C. Event bus đầy đủ.

**Khuyến nghị: B.** Đủ mạnh cho local app và ít phức tạp hơn event bus. Scheduler
cấp lease thông qua JobManager; RetryPolicy chỉ trả quyết định; executor chỉ phát
kết quả/event.

**Code bị ảnh hưởng:** toàn bộ writer trong audit, queue lease và JobStore.
**Test bắt buộc:** hai worker lease cùng job; cancel đua complete; retry_due đua
stop-all; terminal compare-and-set.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D27 — Lịch sử, retention và thao tác “dọn”

**Hiện tại**

`JOBS.pop` xóa current state; `VET` chỉ ở RAM và giới hạn 40 event/job, 400 job.
UI dọn done/error làm mất phần quan sát chính của lifecycle.

**Lựa chọn**

- A. Cleanup xóa hẳn job/history.
- B. Cleanup chỉ archive khỏi UI; event/attempt vẫn giữ theo retention.
- C. Giữ vĩnh viễn.

**Khuyến nghị: B.** Mặc định lưu metadata 90 ngày hoặc 10.000 job gần nhất; file
asset tuân policy riêng. User có thao tác purge rõ ràng nếu muốn xóa hẳn.

**Code bị ảnh hưởng:** `VET`, `/api/xoa-xong`, `/api/xoa-loi`, JobStore và UI filters.
**Test bắt buộc:** archive không mất audit; retention; purge không xóa asset ngoài ý.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D28 — Upload, xóa hoặc gắn asset khi job đang active

**Hiện tại**

Trong lúc job queued/running, user có thể upload, gắn ảnh từ hộp chờ hoặc xóa file.
Executor có thể về sau và ghi đè asset vừa thay; auto lại suy từ file hiện có nên
có thể thay đổi quyết định ở vòng kế tiếp.

**Lựa chọn**

- A. Cho phép mọi thao tác; lần ghi cuối thắng.
- B. Chặn mutation asset khi có active job.
- C. Mutation chủ động của user tạo event mới, cancel active job cũ trước khi áp
  dụng; nếu external attempt đã submit thì xử theo policy unknown/late result.

**Khuyến nghị: C.** Ý định mới của user phải thắng run cũ nhưng không được xóa dấu
vết. Late result của job cũ chỉ vào versions/history, không tự đè current asset.

**Code bị ảnh hưởng:** upload, delete files/video, `_pl_gan`, `set_current`,
`set_video`, auto và terminal handlers.
**Test bắt buộc:** upload/delete đua queued/running/retry-wait; late success sau
cancel; current asset không bị run cũ đè.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

## D29 — Tạo lại asset đã duyệt và quyền đè current version

**Hiện tại**

Ảnh/video mới có thể đè current asset kể cả thẻ đã `approved`; bản cũ còn trong
versions. Một số câu xác nhận UI vẫn mô tả hành vi cũ “không thay bản đã duyệt”.

**Lựa chọn**

- A. Approved là khóa kỹ thuật; output mới chỉ vào versions chờ chọn.
- B. Approved chỉ là nhãn quy trình; explicit rerun được đè current như hiện tại.
- C. Cho user chọn mỗi lần tạo lại.

**Khuyến nghị: B**, nhưng chỉ với explicit rerun có xác nhận rõ. Auto không được
đè approved asset. UI và server phải cùng một thông điệp; job lưu `replace_current`
để late result không tự suy ý định.

**Code bị ảnh hưởng:** `/api/generate`, `/api/tao-lo`, `/api/video-lo?lai=1`,
`_generate_lo_ruot`, `_gen_video`, `board.js`.
**Test bắt buộc:** auto vs approved; explicit rerun; version cũ còn chọn lại được;
UI confirmation khớp server behavior.
**Trạng thái:** Đã duyệt ngày 2026-08-14.

---

## Các quyết định sản phẩm đã được phê duyệt rõ

Các khuyến nghị kỹ thuật D01-D05, D07, D13, D16, D23-D26 tạo nền an toàn và ít thay
đổi ý nghĩa sản phẩm. Các mục dưới đây thay đổi trực tiếp cách app chạy hoặc tiêu
credit và đã được người dùng phê duyệt cùng toàn bộ tài liệu:

1. **D06:** dùng SQLite để phục hồi lifecycle sau restart hay chấp nhận RAM-only.
2. **D09:** đổi retry ảnh từ vô hạn sang cap mặc định 8 attempt có submit.
3. **D10:** giữ retry toàn bộ lô ảnh tối đa 2 và cách xử kết quả thiếu.
4. **D11:** video cap 5 attempt đã submit, không phải 5 exception.
5. **D12:** auto dừng ở failed job, chờ user manual rerun, thay vì tạo job mới vô hạn.
6. **D14:** dừng một ảnh trong lô nghĩa là dừng cả provider execution.
7. **D15:** tách “Dừng an toàn” và “Dừng khẩn cấp”.
8. **D18:** ép account áp dụng cho mọi retry, không chỉ lần đầu.
9. **D19:** chỉ browser/session fatal mới được đóng cả account.
10. **D20:** video chỉ chạy nhờ account ảnh đã opt-in.
11. **D21:** job sau submit có outcome không chắc chắn chuyển `NEEDS_ATTENTION`,
    không tự submit lại.
12. **D27:** archive lịch sử 90 ngày/10.000 job thay vì xóa ngay.
13. **D28:** mutation asset chủ động cancel run cũ; late result không đè current.
14. **D29:** explicit rerun được đè asset đã duyệt, auto thì không.

## Điều kiện để chuyển sang thiết kế kiến trúc

**Kết quả: ĐÃ ĐẠT ngày 2026-08-14.**

- Tất cả quyết định bắt buộc ở trên đã có lựa chọn.
- Không còn thuật ngữ “job”, “attempt”, “batch”, “cancel”, “retry” mang hai nghĩa.
- Những thay đổi chủ ý so với hành vi hiện tại được đánh dấu rõ để regression test
  kiểm tra target behavior, không vô tình khóa bug cũ thành contract.
- Sau khi duyệt, bước kế tiếp mới là viết:
  `JOB-ARCHITECTURE-TARGET.md`, `JOB-STATE-MACHINE.md`, rồi
  `JOB-MIGRATION-PLAN.md`.
