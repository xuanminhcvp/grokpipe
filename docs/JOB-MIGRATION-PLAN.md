# Kế hoạch migration lifecycle job

Trạng thái: **ĐÃ ĐƯỢC NGƯỜI DÙNG PHÊ DUYỆT**
Ngày phê duyệt: 2026-08-14
Đích đến: `JOB-ARCHITECTURE-TARGET.md` và `JOB-STATE-MACHINE.md`.

## Luật migration

1. Không big-bang rewrite.
2. Mỗi phase có một behavior boundary, test, commit và rollback riêng.
3. Không vừa đổi state model, queue, retry, account và UI trong cùng phase.
4. Logic DOM/provider hiện tại được bọc bằng adapter trước, di chuyển sau.
5. API/UI cũ hoạt động qua compatibility projection cho tới phase cuối.
6. Mọi target behavior change phải có failing regression test trước implementation.
7. Không chạy integration test có thể tiêu credit nếu chưa có opt-in rõ ràng.

## Cổng an toàn chung

### Feature mode

Trong migration dùng một mode nội bộ:

```text
legacy         code hiện tại quyết định; core mới không chạy
shadow         legacy quyết định; core mới mirror và kiểm invariant
authoritative  core mới quyết định; legacy chỉ là projection/adapter
```

Mode không phải feature sản phẩm và phải bị xóa ở phase cuối.

### Điều kiện rollback tức thì

Rollback phase hiện tại nếu có một trong các dấu hiệu:

- một logical run được submit provider hai lần ngoài policy;
- cancel/stop xong job vẫn submit mới;
- terminal state regress;
- queue/store/lease invariant mismatch không tự giải thích được;
- UI/API cũ mất thao tác tạo, huỷ, dừng hoặc xem progress;
- credit attempt không có audit row;
- test suite của phase trước bị fail.

Rollback là revert đúng commit/feature mode của phase; không sửa tiếp trên production
đang sai để “cứu nóng”.

## Chiến lược test

Repo hiện chưa có test suite sống. Phase 0 dùng `unittest` chuẩn của Python để không
thêm dependency. Test được chia:

```text
tests/job_lifecycle/
  helpers.py
  test_queue_characterization.py
  test_current_state_writers.py
  test_cancel_characterization.py
  test_retry_characterization.py
  test_auto_characterization.py
  test_account_characterization.py
  test_models.py
  test_store.py
  test_manager_transitions.py
  test_scheduler.py
  test_retry_policy.py
  test_account_allocator.py
  test_recovery.py
  test_legacy_projection.py
  test_http_contract.py
```

- Test behavior hợp lệ hiện tại phải pass ngay.
- Known bug/target behavior dùng `@unittest.expectedFailure` ở Phase 0.
- Trước phase sửa bug, bỏ `expectedFailure`, chạy thấy fail, rồi mới implement.
- Executor integration dùng fake provider/session; test live Chrome để trong suite
  opt-in riêng, không chạy mặc định.

Lệnh chuẩn ban đầu:

```bash
python3 -m unittest discover -s tests/job_lifecycle -p 'test_*.py'
python3 -m py_compile sfboard/hangdoi.py sfboard/sfboard.py
```

## Phase 0 — Characterization tests, không đổi production

### Mục tiêu

Khóa những behavior cần giữ và ghi executable evidence cho các bug đã audit.

### File thay đổi

- Chỉ thêm `tests/job_lifecycle/*` và test helpers.
- Không sửa `sfboard/sfboard.py`, `sfboard/hangdoi.py`, executors hoặc UI.

### Test phải có

1. `hangdoi.xep/lay/thu_tu_hang/y_trong_hang` và ordering shot.
2. `dat_job` rải state lô/member.
3. Cancel identity bug: member queued nhưng queue có `LO:` và `JOBS` thiếu khóa lô
   — đánh dấu expected failure cho target cancel.
4. Auto-video không được enqueue duplicate queued job — expected failure.
5. Stop-all vs retry timer/auto snapshot — expected failure bằng fake clock/barrier.
6. Retry worker, `_HOAN`, auto counter và video inner reconnect hiện tại.
7. Multi-copy state collision — expected failure.
8. Forced account lần đầu rồi retry về queue chung — characterization.
9. API response schema `/api/jobs`, create/cancel endpoints bằng Handler harness giả.

### Rollback

Xóa riêng test commit; production không đổi.

### Definition of done

- Test hợp lệ hiện tại pass.
- Mỗi P0/P1 issue trong audit có ít nhất một expected-failure test hoặc lý do vì
  sao cần fake boundary ở phase sau.
- Test không mở Chrome, không ghi project thật, không gọi provider.

## Phase 1 — Domain model và error taxonomy thuần

### Mục tiêu

Định nghĩa identity/state/event/error class mà chưa nối vào production.

### File/symbol thay đổi

- Thêm `sfboard/jobs/__init__.py`.
- Thêm `sfboard/jobs/models.py`: `JobState`, `Job`, `Batch`, `Execution`, `Attempt`,
  `JobEvent`, `AccountLease`, command/fact dataclasses.
- Thêm `sfboard/jobs/errors.py`: `ErrorClass`, `ErrorFact`.
- Thêm `tests/job_lifecycle/test_models.py`.
- Không import package mới từ `sfboard.py`.

### Test trước implementation

- Identity serialization/validation.
- Terminal-state predicate.
- Attempt phase và `submitted_at/consumes_credit` invariants.
- Batch mode/member validation.
- Không cho asset id được dùng làm job/attempt id.

### Compatibility

Không có runtime impact.

### Rollback

Xóa package/test mới.

### Definition of done

- Models không phụ thuộc `Board`, Playwright, HTTP Handler hoặc global hiện tại.
- Không có method thực thi transition trong model mutable.

## Phase 2 — JobStore/JobManager in-memory ở shadow mode

### Mục tiêu

Xây transaction/CAS/event semantics và mirror legacy state để đo mismatch, chưa
thay quyền quyết định production.

### File/symbol thay đổi

- Thêm `sfboard/jobs/store.py`: `JobStore` protocol, `MemoryJobStore`.
- Thêm `sfboard/jobs/manager.py`: transition table, command skeleton.
- Thêm `sfboard/jobs/projection.py`: map legacy state/reason sang shadow Job/Event.
- Sửa `sfboard/hangdoi.py::_Jobs.__setitem__` để gọi optional shadow observer sau
  legacy write; observer failure tuyệt đối không đổi legacy behavior.
- Sửa startup `sfboard/sfboard.py:main` để khởi tạo shadow core khi mode=`shadow`.
- Thêm `test_store.py`, `test_manager_transitions.py`, `test_legacy_projection.py`.

### Test trước implementation

- Full legal/illegal transition table.
- CAS conflict; idempotent event key; atomic event + state.
- Hai thread complete/cancel cùng version chỉ một bên thắng.
- Shadow observer exception không làm hỏng `JOBS` write.

### Compatibility

`JOBS`, queue, retry, API và UI vẫn là authority. Shadow chỉ log mismatch.

### Rollback

Đặt mode `legacy`; observer optional không chạy. Có thể revert phase không ảnh hưởng
dữ liệu asset.

### Definition of done

- Chạy shadow trên workload giả không mismatch ngoài các bug đã biết.
- Mỗi direct `JOBS` write tạo được event shadow có actor/reason tạm thời.
- Chưa có code mới enqueue hoặc gọi executor.

## Phase 3 — Producer commands và idempotency

### Mục tiêu

Tất cả đường tạo job đi qua một command API thống nhất nhưng vẫn enqueue bằng legacy
adapter. Sửa duplicate creation trước khi đổi queue.

### File/symbol thay đổi

- Thêm `sfboard/jobs/compat.py`: `LegacyEnqueueAdapter`.
- Mở rộng `JobManager.create_job/create_batch/rerun_job`.
- Sửa `Handler.do_POST` các nhánh:
  - `/api/generate`
  - `/api/tao-lo`
  - `/api/master`
  - `/api/genvideo`
  - `/api/video-lo`
- Sửa `_auto_scene` chỉ gửi idempotent create command.
- Sửa `sfboard/chay-anh.py` chấp nhận `job_id` trả về nhưng vẫn đọc schema cũ.
- Endpoint trả thêm `job_id/batch_id`; field cũ giữ nguyên.

### Test trước implementation

- Bỏ expectedFailure duplicate click/auto-video ở Phase 0.
- Hai HTTP request cùng idempotency key trả cùng active job.
- Explicit rerun terminal tạo job mới.
- Auto không tạo job mới trên failed-unacknowledged asset.
- Multi-copy tạo N child Job khác id.

### Compatibility

Legacy adapter vẫn ghi `JOBS` và `_xep` như trước. Mode `shadow` so sánh intent mới
với item legacy.

### Rollback

Feature flag đưa endpoint về producer legacy. Job shadow tạo trong phase này không
được dùng để recovery/execute.

### Definition of done

- Không producer production nào gọi `_xep/_enqueue` trực tiếp ngoài
  `LegacyEnqueueAdapter`.
- Duplicate create target tests pass.
- UI cũ không cần đổi để thao tác.

## Phase 4 — Scheduler và execution lease abstraction

### Mục tiêu

Queue thao tác bằng `execution_id`; một lease atomic thay nhịp `dequeue` rồi mới ghi
`running`. Ban đầu Scheduler có backend in-memory bọc PriorityQueue.

### File/symbol thay đổi

- Thêm `sfboard/jobs/scheduler.py`: `Scheduler`, `MemoryScheduleBackend`, ready heap,
  `not_before`, lease/version.
- Sửa `LegacyEnqueueAdapter` map `execution_id <-> legacy ident`.
- Sửa `sfboard/sfboard.py::_worker` phần `_lay`, `_dat_job(...running...)`,
  `task_done` thành lease API trong mode mới.
- Thay caller `_xep` từ producer bằng Scheduler thông qua adapter.
- Giữ `hangdoi.xep/lay` làm backend compatibility trong phase này.

### Test trước implementation

- Bỏ expectedFailure cancel identity: queue token theo execution id.
- Hai worker không lease cùng execution.
- Lease expiry, heartbeat, stale token/version.
- `not_before` và priority/fairness.
- Image group lease chuyển tất cả member atomically trong shadow store.

### Compatibility

Legacy `JOBS` projection vẫn dùng asset id; `/api/jobs.hang` được dựng từ Scheduler
và map ra legacy ident cho UI.

### Rollback

Mode `legacy` dùng trực tiếp PriorityQueue. Không xóa `hangdoi.py`.

### Definition of done

- Trong authoritative-scheduler test mode, queue chỉ chứa `execution_id`.
- Không còn cửa sổ “đã dequeue nhưng state vẫn queued”.
- Queue ordering cũ vẫn pass.

## Phase 5 — Attempt và AccountAllocator

### Mục tiêu

Ghi assignment trước execute; tách account health/capability khỏi `enabled`; giảm
blast radius nhiều tab.

### File/symbol thay đổi

- Thêm `sfboard/jobs/accounts.py`: `AccountAllocator`, capability, health/cooldown,
  `AccountLease`.
- Sửa `_pool`, `_ke_tiep_trong`, `_tk_ke_tiep`, `_xoay_chrome`, `_supervisor` thành
  compatibility adapter quanh allocator trong mode mới.
- Sửa `_worker` nhận `Attempt + AccountLease` từ Manager thay vì suy hoàn toàn từ
  thread-local.
- Giữ `_TL` cho executor session, nhưng không dùng làm source assignment/history.
- Mở rộng account JSON/UI với capability `allow_video` và forced/fallback policy.

### Test trước implementation

- Forced account áp mọi retry.
- Video không dùng account ảnh chưa opt-in.
- Validation error không cooldown/rotate account.
- Session fatal vs job error có blast radius khác nhau.
- N slot account, lease sibling và browser loss.
- Hai account lỗi đồng thời không chọn/toggle sai.

### Compatibility

`enabled`, `tabs`, account endpoint cũ giữ nguyên; field health/capability thêm vào
response. `_nhan_tk` đọc Attempt assignment khi có, fallback thread-local khi legacy.

### Rollback

Mode legacy dùng `_pool/_xoay_chrome` cũ; schema account mới phải backward-compatible
và field thiếu có default an toàn (`allow_video=false`).

### Definition of done

- Mọi Attempt mode mới có `account_id` trước executor call.
- Một job error thường không tự đóng toàn browser.
- Browser fatal tạo fact cho từng sibling lease.

## Phase 6 — Image executor adapter và batch result

### Mục tiêu

Ảnh chỉ phát phase/result/error facts; không ghi lifecycle hoặc queue trực tiếp.

### File/symbol thay đổi

- Thêm `sfboard/executors/image.py` adapter quanh logic hiện có.
- Sửa `_generate_lo` và `_generate_lo_ruot`:
  - thay direct `JOBS[...]` bằng progress/result facts;
  - thay `_HOAN`/`_xep` retry bằng `ErrorFact`/batch result;
  - giữ logic prompt/ref/generate/download/copy nguyên vẹn.
- Sửa `_pl_gan`, `_ht_lui` gửi asset mutation command/event thay vì direct state.
- `TAY_SF` chỉ còn compatibility, không quyết định job mới.

### Test trước implementation

- Fake session cho 0/N, thiếu giữa lô, thừa, text, copy lỗi, cancel.
- Whole-execution retry budget 2 nằm trong policy/history thống nhất.
- Partial terminal state từng member; completed không regress.
- Multi-copy child progress độc lập.
- Late output sau user upload/delete không đè current.

### Compatibility

Trong shadow mode adapter còn dựng legacy message/projection. Có thể bật executor
adapter cho một test project trước khi bật toàn app.

### Rollback

Feature flag chọn đường gọi `_generate_lo_ruot` legacy. Không thay format output
assets/versions nên artifact có thể dùng lại.

### Definition of done

- Không symbol ảnh nào gọi `_xep`, `_dat_job` hoặc ghi `JOBS/_HOAN` trong mode mới.
- Mọi provider submit có Attempt phase/event.
- Logic hình ảnh hiện có pass characterization tests.

## Phase 7 — Video executor adapter và credit boundary

### Mục tiêu

Video ghi ranh giới submit/credit; outcome không chắc chắn không bị auto retry.

### File/symbol thay đổi

- Thêm `sfboard/executors/video.py` adapter quanh `_gen_video`/Grok session.
- Sửa `_gen_video` phát phase/result/error facts, bỏ direct `JOBS` writes.
- Sửa `_worker` bỏ nhánh `VID_MAX_TRY` và để RetryPolicy quyết định.
- Gắn provider request/clip variants vào Attempt artifacts.
- Đồng bộ `_dem_cong` với `submitted_at/consumes_credit`, không đếm hai lần khi
  fact được gửi lại.

### Test trước implementation

- Pre-submit reconnect không tăng credit attempt.
- Post-submit download/session loss -> `NEEDS_ATTENTION`, không resubmit.
- Cap 5 submitted attempts.
- Nhiều clip một submit đều được lưu dưới cùng Attempt.
- Cancel pre-submit và từ chối safe cancel post-submit.

### Compatibility

Video files/versions và endpoint giữ nguyên. UI cũ thấy projection `running/error/done`
cho tới phase UI mới; `NEEDS_ATTENTION` chiếu thành `error` có reason rõ.

### Rollback

Feature flag chọn `_gen_video` legacy. Attempt rows shadow không điều khiển queue.

### Definition of done

- Không retry video nào dựa trên số exception mơ hồ.
- Mọi submit/credit risk có event bền vững.
- Không đường video mode mới ghi `JOBS` trực tiếp.

## Phase 8 — Cancel, safe stop và emergency stop

### Mục tiêu

Thay `DA_HUY`, `DUNG_RIENG`, `GEN` bằng job/version/cancellation token và StopBarrier.

### File/symbol thay đổi

- Mở rộng `JobManager.cancel_job/stop_all`.
- Sửa Handler:
  - `/api/huy-viec`
  - `/api/huy`
  - `/api/dung-viec`
  - `/api/dung-het`
- Sửa image/video adapters đọc cancellation token theo execution lease.
- Thêm endpoint/parameter phân biệt `safe` và `emergency` nhưng giữ `/api/dung-het`
  mặc định map sang safe.
- UI thêm xác nhận dừng cả image group và cảnh báo emergency.

### Test trước implementation

- Bỏ expectedFailure cancel/timer/auto races.
- Cancel queued/retry-wait trước/sau heap pop.
- Image group cancel trong running.
- Video pre/post submit.
- Stop barrier đua producer, retry_due, lease và late event.
- Emergency -> `NEEDS_ATTENTION` khi outcome không chắc chắn.

### Compatibility

Endpoint cũ vẫn tồn tại. Legacy flags có thể được mirror trong shadow mode nhưng
không còn authority khi mode mới bật.

### Rollback

Chỉ rollback khi không còn active job mode mới; emergency/safe stop state đã ghi
không được map ngược tùy tiện sang legacy queue.

### Definition of done

- Cancel target tests pass không cần quét queue theo `LO:`.
- Sau stop barrier không execution cũ nào được lease/submit.
- Không cần `bo_co_huy` cho run mới.

## Phase 9 — RetryPolicy và loại bỏ retry authorities trùng

### Mục tiêu

Một retry policy, một budget và durable `RETRY_WAIT/not_before`.

### File/symbol thay đổi

- Thêm/hoàn thiện `sfboard/jobs/retry.py`.
- Sửa `_worker` bỏ `_xep_lai_sau`, `tries` tuple và direct account rotation policy.
- Xóa đường `_HOAN` khỏi executor mới.
- Sửa `_auto_allow/_auto_scene` bỏ retry counter/cooldown; auto chỉ create.
- Sửa `chay-anh.py` bỏ `thu/lan_loi/bat_dau` làm retry controller; chỉ monitor job
  terminal và có thể request explicit rerun nếu user bật option riêng.
- Watchdog không còn counter `cuu` để enqueue.

### Test trước implementation

- Error-class matrix D08.
- Ảnh cap 8 submitted attempts; video cap 5.
- Image incomplete whole-execution max 2 trong cùng policy.
- Fair backoff/not_before; cancel retry wait.
- Manual rerun tạo budget mới.

### Compatibility

Projection dựng message “thử lại lần x/y sau Ns” từ structured state. Các constant
cũ có thể map vào config mới một phase rồi mới xóa.

### Rollback

Feature flag chọn policy legacy chỉ khi không có active job dùng budget mới. Không
trộn counter hai policy trên cùng job.

### Definition of done

- Không còn `threading.Timer` cho job retry.
- Không còn `_HOAN`, `AUTO["try"]`, watchdog `cuu` hoặc external retry counter làm
  authority.
- `JOBS.lan` chỉ là projection từ Attempt count.

## Phase 10 — SQLite authoritative và recovery

### Mục tiêu

Chuyển MemoryJobStore/Schedule sang SQLite, bật recovery và loại nhu cầu rescue
enqueue.

### File/symbol thay đổi

- Thêm `SQLiteJobStore` và schema migrations trong `sfboard/jobs/store.py` hoặc
  `sfboard/jobs/sqlite_store.py`.
- Thêm `sfboard/jobs/recovery.py`.
- Sửa `main` startup/shutdown để open DB, migrate, recover, flush/close.
- Scheduler dùng durable schedule table; in-memory heap là cache.
- Thêm backup path/config cạnh project lifecycle DB, không nhét vào `sf-board.json`.

### Cutover

1. Chạy shadow SQLite đủ một chu kỳ workload giả/thật không credit.
2. So invariant projection với legacy.
3. Chọn lúc không có active legacy job.
4. Backup DB và `sf-board.json`.
5. Bật `authoritative`.
6. Có nút/command quay về legacy chỉ khi DB không chứa active job mới.

### Test trước implementation

- Crash/restart ở mọi state/attempt phase.
- WAL/concurrent CAS/locked DB.
- Schema migration lên/xuống trong phạm vi hỗ trợ.
- Pre-submit expired lease retry; post-submit -> `NEEDS_ATTENTION`.
- Schedule rebuild không duplicate.

### Compatibility

Projection giữ API/UI cũ. Nếu DB không mở được, app phải fail rõ hoặc vào read-only
diagnostic; không âm thầm chạy legacy và duplicate job.

### Rollback

Restore backup DB/schema và binary phase trước. Không xóa DB khi rollback; dữ liệu
attempt cần giữ để điều tra.

### Definition of done

- Restart không mất queued/retry-wait.
- Running recovery tuân phase/credit policy.
- Store/schedule/lease invariant tests pass dưới concurrency.

## Phase 11 — Auto Producer, Invariant Monitor và external client

### Mục tiêu

Auto chỉ là producer idempotent; watchdog chỉ quan sát; client ngoài không retry
ngầm trái server.

### File/symbol thay đổi

- Sửa `_auto_runner/_auto_scene` gọi query/command JobManager và check StopBarrier
  transactionally.
- Thay `_gac_hang_doi` bằng `InvariantMonitor` đọc store/scheduler/lease, chỉ log/
  metrics/UI alert.
- Sửa `chay-anh.py` dùng job ids/terminal states; bỏ “treo thì xếp lại”.
- `/api/jobs` thêm invariant/attention summaries.

### Test trước implementation

- Auto off/stop đua scan không tạo job.
- Auto không revive failed/cancelled/attention job.
- Monitor phát hiện mismatch nhưng không mutate.
- External client restart/network retry không duplicate create.

### Compatibility

Các nút auto và CLI arguments cũ giữ được; tham số retry cũ báo deprecated trước
khi xóa.

### Rollback

Auto có thể tắt hoàn toàn; monitor không mutate nên revert an toàn. Không bật lại
watchdog enqueue trong mode authoritative.

### Definition of done

- Không còn producer nào có retry authority.
- Không còn cơ chế rescue enqueue dựa trên projection.
- Các bug auto-video duplicate và stop-all race có regression pass.

## Phase 12 — UI/API mới, xóa legacy authority và tách file

### Mục tiêu

Chuyển consumer cuối sang structured lifecycle, xóa projection write/feature modes
và chỉ lúc này mới tách `sfboard.py` sâu hơn.

### File/symbol thay đổi

- Sửa `sfboard/ui/board.js`:
  - local `submitting` thay optimistic `JOBS=running`;
  - hiển thị `RETRY_WAIT`, `CANCELLED`, `NEEDS_ATTENTION`;
  - command theo `job_id`, batch confirmation, safe/emergency stop;
  - archive/history/attempt/account/credit view.
- Handler trả structured Job/Batch/Attempt; endpoint cũ vẫn proxy trong một thời
  gian deprecation đã định.
- Xóa direct writer cuối trong `sfboard.py`/`hangdoi.py`.
- Xóa legacy `JOBS`, `_HOAN`, `DA_HUY`, `DUNG_RIENG`, `GEN`, `CHO_RIENG`, retry
  timer và watchdog enqueue sau khi `rg`/AST guard xác nhận không còn caller.
- Di chuyển Handler/API, scheduler startup, account API và executor adapter ra module
  nhỏ theo ownership trong target architecture.

### Test trước implementation

- Browser/UI contract test cho mọi state/action.
- Optimistic rollback/network error/click đôi.
- Compatibility API snapshot so với API mới.
- AST/static guard: cấm `JOBS[...]`, queue `.put()`, direct transition ngoài module
  jobs.
- Full fake-provider E2E ảnh/video, batch, multi-copy, retry, cancel, recovery.

### Compatibility

Giữ endpoint cũ ít nhất một release/mốc vận hành đã chốt; log caller deprecated.
Chỉ xóa khi UI và `chay-anh.py` không còn dùng.

### Rollback

UI có thể quay về bundle cũ trong lúc compatibility API còn tồn tại. Việc xóa
legacy globals là commit riêng cuối cùng, chỉ thực hiện sau mốc không còn caller.

### Definition of done

- JobStore là nguồn sự thật duy nhất.
- Chỉ JobManager transition lifecycle.
- Scheduler queue chỉ execution id; RetryPolicy/AccountAllocator không mutate state.
- Không watchdog/retry/auto/client nào tự enqueue ngoài Scheduler command.
- UI/API cũ được deprecate có kiểm soát hoặc đã xóa sau xác nhận caller.
- `sfboard.py` không còn chứa lifecycle core; việc tách file không đổi behavior.

## Ma trận phase và behavior change

| Phase | Production behavior | Source of truth | Có thể tiêu credit khi test mặc định |
|---|---|---|---|
| 0 | Không đổi | Legacy | Không |
| 1 | Không đổi | Legacy | Không |
| 2 | Không đổi, shadow observability | Legacy | Không |
| 3 | Chống duplicate/idempotency có chủ ý | Legacy + shadow | Không |
| 4 | Lease/scheduler có feature gate | Legacy hoặc shadow core | Không |
| 5 | Assignment/health có feature gate | Core cho mode mới | Không |
| 6 | Image lifecycle facts | Core cho image mode mới | Fake provider mặc định |
| 7 | Video credit boundary | Core cho video mode mới | Fake provider mặc định |
| 8 | Cancel/stop semantics mới | Core | Không |
| 9 | Retry policy mới | Core | Không |
| 10 | Persistence/recovery | SQLite core | Không |
| 11 | Auto/monitor/client mới | SQLite core | Không |
| 12 | UI/API mới, bỏ legacy | SQLite core | Không |

## Thứ tự commit đề xuất trong mỗi phase

1. Test target chuyển từ expected-failure sang failing test thật.
2. Pure types/interfaces.
3. Implementation nhỏ nhất để test pass.
4. Compatibility adapter/feature gate.
5. Integration/contract tests.
6. Verification toàn suite và syntax.
7. Một commit phase có message/rollback note rõ.

Không gom cleanup hoặc tách file không liên quan vào commit behavior.

## Definition of done toàn chương trình

1. 40 regression scenarios trong audit được tự động hóa hoặc được thay bằng test
   target tương đương mạnh hơn.
2. State/transition/ownership đúng tài liệu đã duyệt.
3. Không direct writer legacy còn lại theo AST guard.
4. Restart/recovery, cancel/stop, retry và credit tests pass.
5. Fake-provider E2E ảnh/video pass; live smoke test chỉ chạy khi user opt-in.
6. API/UI compatibility có mốc deprecation rõ.
7. Mỗi phase có commit độc lập và rollback đã được thử ở môi trường test.
8. Tài liệu AGENTS/architecture liên kết tới source-of-truth mới, không sao chép
   policy thành nhiều bản dễ lệch.
