# Thiết kế Phase 3 — Producer command và idempotency

Ngày duyệt: 2026-08-16

Trạng thái: **ĐÃ ĐƯỢC NGƯỜI DÙNG DUYỆT**

Bead: `beads-foundation-7lt.8`

## 1. Bối cảnh và authority hiện tại

Phase 2 đã có `MemoryJobStore`, `JobManager`, transition table, legacy shadow
projection và observer fail-open. Production vẫn do `JOBS`, `PriorityQueue`,
`CHO_RIENG`, worker, retry timer và auto-runner legacy quyết định.

Producer hiện bị phân tán giữa năm HTTP route, `_auto_scene`, `_enqueue` và client
`chay-anh.py`. Mỗi đường tự kiểm duplicate, tự ghi `JOBS` và tự gọi `_xep` theo
một cách khác nhau. Hai ambiguity thuộc đúng Phase 3 vẫn đang được khóa bằng
`expectedFailure`:

- auto-video có thể enqueue lại shot đang `queued`;
- multi-copy dùng chung một logical job identity cho nhiều output có chủ ý.

Phase 3 chỉ hợp nhất ý định tạo và đường enqueue producer. Scheduler, worker,
executor, retry, cancel, account allocation và persistence chưa đổi authority.

## 2. Mục tiêu

1. Mọi HTTP/auto producer đi qua typed command API thống nhất.
2. Request lặp đồng thời tạo đúng một logical intent và đúng một lần legacy enqueue.
3. Explicit rerun terminal tạo Job mới, giữ `rerun_of`, không revive Job cũ.
4. Multi-copy tạo một Batch và N child Job identity khác nhau.
5. Auto không tạo run mới cho asset có active hoặc terminal-failed run chưa được
   user xử lý.
6. API/UI cũ tiếp tục hoạt động; response chỉ được bổ sung field.
7. Default `legacy` giữ behavior cũ; `shadow` bật command/idempotency rồi giao
   execution cho legacy adapter.
8. Không mở Chrome, gọi provider hoặc tiêu credit trong test mặc định.

## 3. Không nằm trong phạm vi

- Không đổi queue token sang `execution_id`; việc đó thuộc Phase 4.
- Không cấp account/attempt; việc đó thuộc Phase 5.
- Không sửa logic prompt/ref/provider/download/copy; việc đó thuộc Phase 6–7.
- Không thay cancel flag, stop barrier hoặc retry timer; việc đó thuộc Phase 8–9.
- Không thêm SQLite/recovery; idempotency Phase 3 chỉ bền trong process.
- Không thay layout hoặc thao tác UI nhìn thấy; JavaScript chỉ được thêm key cho
  request hiện có.
- Không bật `authoritative`; mode này tiếp tục bị từ chối an toàn.

## 4. Các hướng đã cân nhắc

### 4.1 Cutover toàn bộ producer ngay

Cho JobManager trực tiếp ghi queue và bắt mọi route dùng core mới. Hướng này nhanh
nhưng trộn command authority với queue authority trước khi Scheduler tồn tại,
rollback khó và trái luật không big-bang.

### 4.2 Command service + một legacy adapter duy nhất — chọn

Command service tạo intent/identity/idempotency trong core. Một adapter tương thích
duy nhất chuyển intent đã chấp nhận thành đúng các write/enqueue legacy đang dùng.
Ranh giới này test được, rollback được và trở thành đầu nối cho Scheduler Phase 4.

### 4.3 Chỉ vá điều kiện duplicate trong legacy

Ít diff nhất nhưng giữ năm producer authority, không tạo Job/Batch identity và
không cung cấp nền cho Scheduler. Hướng này không đạt mục tiêu migration.

## 5. Thành phần và dependency direction

```text
HTTP / Auto / CLI
       |
       v
ProducerService ----------------------+
       |                              |
       v                              v
JobManager -> JobStore           ProducerResult
       |                              |
       +--> idempotency intent        v
                              LegacyEnqueueAdapter
                                      |
                                      +--> JOBS / dat_job
                                      +--> _xep / _enqueue-compatible action
                                      +--> CHO_RIENG (forced image account)
```

### 5.1 `sfboard/jobs/producer.py`

Module thuần, không import `hangdoi`, `sfboard.py`, queue, executor, account
registry, HTTP hoặc Playwright.

Public request/result types:

```python
@dataclass(frozen=True)
class CreateJobRequest:
    asset_id: AssetId
    kind: JobKind
    origin: JobOrigin
    request_scope: str
    manual: bool = False
    replace_current: bool = False
    forced_account_id: Optional[str] = None
    allow_account_fallback: bool = False


@dataclass(frozen=True)
class CreateBatchRequest:
    members: Tuple[CreateJobRequest, ...]
    mode: BatchMode


@dataclass(frozen=True)
class ProducerResult:
    jobs: Tuple[Job, ...]
    batch: Optional[Batch]
    idempotency_key: str
    replayed: bool
    delivery_required: bool
```

`ProducerService` cung cấp:

```python
create_job(request, idempotency_key=None) -> ProducerResult
create_batch(request, idempotency_key=None) -> ProducerResult
rerun_job(old_job_id, request, idempotency_key) -> ProducerResult
mark_delivered(idempotency_key) -> None
```

Service validate request, dựng Job/Batch/Event, rồi gọi một atomic store boundary.
Service không ghi legacy state và không enqueue.

### 5.2 Idempotency trong `JobStore`

Store thêm immutable intent record:

```python
@dataclass(frozen=True)
class IdempotencyRecord:
    key: str
    fingerprint: str
    job_ids: Tuple[JobId, ...]
    batch_id: Optional[BatchId]
    delivered: bool
```

Và atomic API:

```python
create_intent(record, batch, jobs_and_events) -> IntentWriteResult
get_intent(key) -> Optional[IdempotencyRecord]
mark_intent_delivered(key) -> IdempotencyRecord
get_batch(batch_id) -> Optional[Batch]
```

Trong một `RLock` critical section, `create_intent` thực hiện toàn bộ:

1. key chưa có: validate tất cả Job/Event/Batch, ghi tất cả hoặc không ghi gì;
2. cùng key + cùng fingerprint: trả đúng Job/Batch cũ với `replayed=True`;
3. cùng key + fingerprint khác: ném `IdempotencyConflict`;
4. không bao giờ tạo một phần multi-copy batch.

Fingerprint là SHA-256 của canonical JSON chỉ gồm field cấu trúc an toàn: asset,
kind, origin, scope, batch mode, copy index, manual/replace/fallback và forced
account id. Không đưa prompt, message, cookie, token, media hoặc đường dẫn nhạy cảm
vào record/diagnostics.

`delivered` chỉ nói intent đã được giao sang legacy adapter trong process hiện tại;
nó chưa phải durable schedule fact. Phase 4 thay boundary này bằng Scheduler.

### 5.3 Active-scope constraint

Idempotency key rõ ràng là contract mạnh nhất. Khi client cũ không gửi key,
ProducerService dùng active scope:

```text
project identity + producer scope + kind + ordered asset ids + batch mode + copies
```

- Nếu scope có Job `CREATED/QUEUED/RUNNING/RETRY_WAIT/NEEDS_ATTENTION`, request lặp
  trả lại intent hiện có.
- Manual request sau terminal tạo explicit rerun mới và liên kết `rerun_of`.
- Auto request sau `FAILED/CANCELLED/NEEDS_ATTENTION` trả lại run cũ, không tạo run
  mới. User manual rerun mới mở một intent khác.
- Multi-copy parallel chỉ hợp lệ qua `CreateBatchRequest(mode=MULTI_COPY)`; không
  dùng cờ ngầm để vượt active constraint.

Client mới luôn gửi key để phân biệt HTTP retry với một thao tác manual mới. Với
client cũ không key, tương thích legacy được giữ: request manual sau terminal được
coi là rerun; retry mạng đến sau terminal không thể phân biệt tuyệt đối cho tới khi
client đó được nâng cấp.

### 5.4 Batch và identity

- Image group: mỗi asset có một Job; cùng `BatchId`, `BatchMode.IMAGE_GROUP`.
- Multi-copy: cùng asset nhưng N Job khác nhau, `copy_index=0..N-1`, cùng
  `BatchId`, `BatchMode.MULTI_COPY`.
- Bulk video: mỗi shot có một Job, cùng `BatchId`, `BatchMode.BULK_VIDEO`.
- Member order là canonical và có ý nghĩa; duplicate member trong image group bị
  reject trước store write.
- Retry sau này thuộc child Job/Attempt, không được sinh thêm copy ngoài N.

### 5.5 `sfboard/jobs/compat.py`

`LegacyEnqueueAdapter` là compatibility boundary duy nhất của producer. Module
nhận dependency injection thay vì tự import global:

```python
LegacyEnqueueAdapter(
    set_job_state,
    enqueue_image,
    enqueue_video,
    enqueue_private_image,
    bind_projection,
)

deliver(result, legacy_plan) -> LegacyDeliveryResult
```

Adapter có lock theo idempotency key. Mọi caller, kể cả replay sau delivery lỗi,
đều gọi `deliver`; chỉ thread giữ delivery claim được ghi `JOBS` và enqueue.
Sau khi toàn bộ legacy action thành công, adapter gọi `mark_delivered`. Request lặp
sau đó chỉ trả result cũ.

Phase 3 không thể transaction atomically giữa MemoryJobStore và `PriorityQueue`.
Nếu action lỗi giữa chừng, diagnostics ghi `delivery_pending`; không tự đoán và
enqueue thêm các action đã hoàn tất. Test adapter dùng injected fake action có
idempotent action key cho từng member/copy. Durable outbox/recovery thuộc Phase 4
và Phase 10.

Trong mode `legacy`, endpoint vẫn đi qua chính adapter nhưng không tạo core intent;
adapter gọi đúng các action cũ. Việc này gom producer writer mà không đổi kết quả.

### 5.6 Projection binding

Command-created Job phải là Job được legacy observer cập nhật; projection không
được tạo thêm compatibility Job cho cùng intent.

Projection thêm:

```python
bind(legacy_key, job_ids) -> None
```

- member asset key bind tới đúng child Job;
- `LO:a,b,c` bind tới toàn bộ member Job của image group;
- multi-copy asset key bind tới toàn bộ child Job của batch;
- group write được áp theo CAS cho từng member; member write cùng state chỉ là
  progress event;
- bind collision với active Job khác là mismatch, không âm thầm đổi mapping;
- terminal-to-active manual rerun chỉ đổi binding sau khi ProducerService đã tạo
  Job mới có `rerun_of`.

Do executor vẫn legacy ở Phase 3, multi-copy outcome còn là aggregate projection;
success/failure riêng từng child được hoàn thiện ở Phase 6. Phase 3 chỉ đảm bảo
identity và enqueue count đúng.

## 6. Wiring production

### 6.1 Mode

- `legacy`: không tạo producer intent; adapter thực thi behavior legacy tương đương.
- `shadow`: producer intent/idempotency chạy trước, projection được bind, adapter
  thực thi legacy enqueue; queue/worker/executor vẫn quyết kết quả production.
- mode lạ hoặc `authoritative`: warning đã lọc và giữ `legacy`.

Khởi tạo producer service dùng cùng `MemoryJobStore`/`JobManager`/projection của
Phase 2, không tạo store thứ hai.

### 6.2 HTTP routes

Các route sau chuyển sang helper producer chung:

- `/api/generate`;
- `/api/master`;
- `/api/tao-lo`;
- `/api/genvideo`;
- `/api/video-lo`.

Request đọc key theo thứ tự:

1. header `Idempotency-Key`;
2. query/body `idempotency_key`;
3. active-scope fallback cho client cũ.

Response giữ nguyên status và field cũ, bổ sung:

```json
{
  "job_id": "...",
  "job_ids": ["..."],
  "batch_id": "... hoặc null",
  "replayed": false
}
```

Route single trả `job_id`; batch/multi-copy trả cả `job_ids` và `batch_id`. Field
mới không làm client cũ hỏng.

### 6.3 Auto producer

`_auto_scene` không tự quyết duplicate bằng mỗi `JOBS.state`. Nó gửi request có
scope ổn định theo project/scene/asset/kind. Auto request đang active, queued hoặc
terminal-failed được replay, không enqueue lần hai. Auto chỉ được tạo intent mới
sau manual rerun/acknowledge đã tạo lifecycle chain mới.

Auto vẫn giữ generation barrier Phase 2 hiện có; StopBarrier chính thức thuộc
Phase 8.

### 6.4 UI và external client

`board.js` tạo một UUID cho mỗi user action và dùng lại key đó nếu cùng action
retry request. Không đổi label, layout hoặc thao tác.

`chay-anh.py` gửi key ổn định cho một logical request, đọc `job_id` khi có và
fallback schema cũ khi server legacy. Client chưa bỏ retry controller cho tới
Phase 9, nhưng HTTP retry của cùng request không tạo duplicate server job.

## 7. Error và concurrency semantics

- `IdempotencyConflict`: HTTP 409, không ghi store/queue/JOBS.
- `ActiveJobConflict`: HTTP 409 khi explicit parallel run không phải multi-copy.
- Validation domain: HTTP 400, không enqueue.
- Legacy delivery lỗi: HTTP 500, intent giữ `delivery_pending`; cùng key retry
  delivery qua action keys, không tạo Job/Batch mới.
- Hai HTTP thread cùng key/fingerprint: một thread tạo/deliver, thread kia replay.
- Hai HTTP thread khác key nhưng cùng active scope: trả cùng active intent trừ
  multi-copy explicit hợp lệ.
- Observer/projection lỗi tiếp tục fail-open đối với legacy write và chỉ tăng
  diagnostic; không đổi response legacy đã commit.

Diagnostics chỉ công bố count, ids typed, state, reason code và delivery status;
không công bố request payload thô.

## 8. Test strategy

Mọi behavior change dùng red-green TDD. Test mặc định chỉ dùng
`MemoryJobStore`, fake adapter actions, `FakeBoard` và Handler harness.

### 8.1 Store/producer tests

- cùng key + fingerprint replay đúng Job/Batch;
- cùng key + payload khác ném conflict;
- hai thread cùng key chỉ một create;
- active-scope dedupe với hai key khác;
- terminal manual rerun tạo Job mới và `rerun_of`;
- auto terminal failure không tạo Job mới;
- create batch atomic; duplicate member reject;
- multi-copy N child có JobId riêng và copy index `0..N-1`.

### 8.2 Adapter/projection tests

- một intent chỉ tạo một legacy enqueue;
- delivery fail/retry không tạo intent mới hoặc lặp action đã xác nhận;
- image group bind member + `LO:` đúng Job;
- multi-copy bind nhiều child;
- adapter exception không làm hỏng store intent;
- legacy mode snapshot/queue tuple không đổi so với characterization.

### 8.3 HTTP/auto/client tests

- double click và hai HTTP thread trả cùng ids;
- response giữ field cũ và thêm field mới;
- header/query key precedence;
- auto-video bỏ cả `queued` lẫn `running` duplicate;
- auto image/video terminal-failed không revive;
- `chay-anh.py` retry cùng key;
- board.js contract tạo key theo action mà không đổi visible UI.

### 8.4 Xfail và gates

Phase 3 chỉ chuyển hai test sau từ `expectedFailure` sang regression xanh:

1. auto-video blocks queued and running duplicates;
2. multi-copy enqueue uses distinct job identity per copy.

Hai `xfail` còn lại không đổi:

1. cancel member resolves physical LO queue identity — Phase 4/8;
2. forced account survives every retry item — Phase 5/9.

Gate cuối:

- targeted producer/store/adapter/projection/HTTP/auto tests xanh;
- full `./test-job-lifecycle.command` xanh với đúng 2 `xfailed`;
- coverage `sfboard.jobs >= 80%`;
- compile gate PASS;
- AST guard: HTTP/auto producer không gọi `_xep`, `_enqueue` hoặc ghi `JOBS`
  ngoài `LegacyEnqueueAdapter` wiring được cho phép;
- không Chrome/provider/credit trong suite mặc định.

Sau gate fake, có thể restart board vì user đã xác nhận queue rỗng. Runtime smoke
chỉ kiểm startup, `/api/chan-doan`, response contract và duplicate request bằng
fake/inert workload; không submit provider nếu chưa cần.

## 9. Rollback

Rollback tức thì nếu duplicate queue action, terminal revive, API cũ mất field,
projection tạo hai Job cho một intent hoặc full gate phase trước fail.

Rollback vận hành:

1. đặt `GROKPIPE_JOB_MODE=legacy`;
2. producer intent/projection binding ngừng chạy;
3. adapter tiếp tục action legacy tương đương;
4. không dùng shadow intent để recovery hoặc execute;
5. nếu adapter equivalence có lỗi, revert riêng commit wiring Phase 3.

Memory intent không sửa asset/media và có thể bỏ khi process dừng. Không cần migrate
dữ liệu để quay về Phase 2.

## 10. Definition of done

1. Tất cả HTTP/auto producer đi qua một producer helper/adapter boundary.
2. Concurrent duplicate tạo đúng một intent và đúng một legacy enqueue.
3. Explicit terminal rerun tạo Job mới với `rerun_of`.
4. Multi-copy có BatchId và N child JobId riêng.
5. Auto không duplicate queued/running và không revive terminal failure.
6. Projection theo đúng command-created Job, không sinh shadow Job thứ hai.
7. Default legacy contract và queue tuple cũ không đổi.
8. Hai xfail Phase 3 thành xanh; còn đúng hai xfail của phase sau.
9. Full lifecycle/compile/static authority gate xanh.
10. Bead `beads-foundation-7lt.8` có evidence và chỉ đóng sau review độc lập không
    còn Critical/Important.

## 11. Ranh giới sang Phase 4

Phase 4 nhận `ProducerResult` và thay delivery target từ legacy queue action sang
Scheduler `execution_id` lease. Phase 3 không được thêm lease, retry scheduling,
account assignment hoặc recovery để “chuẩn bị trước”.
