# Job lifecycle — cửa vào cho AI

Đọc file này trước khi điều tra hoặc sửa job ảnh/video, `JOBS`, queue, state,
retry, cancel/stop, account assignment, auto producer, worker hoặc job API/UI.

## Đọc trong 60 giây

- Current phase: **Phase 4 scheduler/lease đã triển khai; chưa cutover**.
- Production **execution** authority vẫn là legacy: `PriorityQueue`, worker,
  retry timer, cancel/stop và account rotation.
- **Đã đổi chủ:** năm đường tạo HTTP (`/api/generate`, `/api/master`,
  `/api/tao-lo`, `/api/genvideo`, `/api/video-lo`) và auto producer chỉ còn gửi
  ý định qua `ProducerService → LegacyEnqueueAdapter`. Chúng KHÔNG còn gọi
  `_xep`/`_enqueue` hay ghi `JOBS[...]` trực tiếp — có AST guard canh
  (`test_phase3_producers_use_one_compatibility_boundary`).
- Client gửi `Idempotency-Key` (`sfboard/ui/job-request.js`, `chay-anh.py`).
  Gửi lại cùng key trả về đúng job cũ và không xếp thêm; key khác nội dung cùng
  key cũ → 409.
- `GROKPIPE_JOB_MODE=shadow` là opt-in nội bộ; mặc định vẫn là `legacy`. Ở
  `legacy` không có store/producer nào chạy, adapter giao đúng callback cũ.
- **Lịch execution** (`sfboard/jobs/scheduler.py`) chạy ở CẢ HAI mode nhưng chỉ
  QUAN SÁT: nó giữ quan hệ `thành viên ⇢ lô vật lý` và lease của lượt đang chạy.
  `PriorityQueue` legacy vẫn là thứ đưa việc tới thợ.
- `/api/huy-viec` tra lô vật lý bằng HÀNG ĐỢI THẬT + lịch, không quét `JOBS` nữa
  — sửa đúng ca "bấm huỷ báo 0 lô mà ảnh vẫn ra".
- 1 known ambiguity còn khóa bằng `expectedFailure`: forced-account retry mất
  constraint (Phase 5). Ba cái kia (auto-video enqueue trùng, multi-copy
  identity, cancel identity lô) đã sửa và có regression hành vi thật.
- Không refactor production trước khi xác định phase, owner và regression test.

## Quy trình sửa lỗi bắt buộc

1. Phân loại triệu chứng bằng bảng routing bên dưới.
2. Đọc đúng tài liệu được route, không nạp cả năm file nếu không cần.
3. Dùng Serena tìm definition, callers/references và mọi writer liên quan.
4. Dùng `superpowers:systematic-debugging` để xác định nguyên nhân gốc.
5. Viết regression test tái hiện lỗi và chạy thấy fail trước khi sửa.
6. Sửa đúng owner; không thêm writer, retry hoặc re-enqueue authority mới.
7. Chạy full lifecycle suite, compile gate và đọc diff trước khi kết luận.

## Đọc file nào?

| Triệu chứng/công việc | Đọc tiếp |
|---|---|
| State sai, terminal regress, transition mơ hồ | [State machine](JOB-STATE-MACHINE.md) |
| Retry vô hạn, enqueue trùng, job hồi sinh | [Audit](JOB-LIFECYCLE-AUDIT.md) + [Decisions](JOB-LIFECYCLE-DECISIONS.md) |
| Cancel riêng, stop-all, late result | [State machine](JOB-STATE-MACHINE.md) + [Audit](JOB-LIFECYCLE-AUDIT.md) |
| Chọn/xoay/ép sai tài khoản | [Architecture](JOB-ARCHITECTURE-TARGET.md) + [Decisions](JOB-LIFECYCLE-DECISIONS.md) |
| `/api/jobs`, create/cancel response hoặc queue UI | [HTTP characterization tests](../tests/job_lifecycle/test_http_contract.py) + [Migration plan](JOB-MIGRATION-PLAN.md) |
| Refactor, shadow mode, cutover authority | [Migration plan](JOB-MIGRATION-PLAN.md) + [Architecture](JOB-ARCHITECTURE-TARGET.md) |
| Không rõ expected behavior | [Decisions](JOB-LIFECYCLE-DECISIONS.md) |

## Invariant không được phá

- Mỗi lifecycle fact có đúng một authority quyết định.
- `COMPLETED`, `FAILED`, `CANCELLED` không chuyển state nữa.
- Cancel/stop xong không có timer, watchdog hoặc auto snapshot nào được hồi sinh job.
- Outcome sau submit không chắc chắn phải vào `NEEDS_ATTENTION`, không tự submit lại.
- Forced account áp dụng cho mọi retry trừ khi job cho phép fallback rõ ràng.
- Explicit rerun tạo Job mới và giữ `rerun_of`; không revive terminal Job.
- Asset ID không phải Job, Execution hoặc Attempt ID.
- Queue token/state text không được dùng thay durable identity/version.

## Dùng Serena và Superpowers

Serena dùng cho code navigation, không phải nguồn kiến trúc riêng:

1. Tìm symbol định nghĩa hành vi.
2. Tìm callers/references và call path.
3. Tìm mọi writer của `JOBS`, queue, retry state và account assignment.
4. Xác nhận không còn writer/re-enqueue authority thứ hai sau thay đổi.

Superpowers workflow:

- Bug/unexpected behavior → `systematic-debugging`.
- Bugfix/behavior change → `test-driven-development`.
- Nhiều bước → `writing-plans`, rồi `executing-plans` hoặc subagent workflow.
- Trước kết luận hoàn tất → `verification-before-completion`.

## Verification

Cài dependency test một lần cho worktree:

```bash
./.venv/bin/python3 -m pip install -r requirements-test.txt
```

Sau mỗi thay đổi lifecycle, chạy gate chuẩn:

```bash
./test-job-lifecycle.command
```

Gate này chạy `tests/job_lifecycle`, `tests/runtime_bugs` và `tests/executors`,
rồi compile legacy runtime và domain package. Nó không mở browser, gọi provider
hoặc tiêu credit.

⚠ **Con số coverage CHỈ đo `sfboard/jobs`** (`--cov=sfboard.jobs`). Nó KHÔNG đo
`sfboard/sfboard.py` — file lớn nhất, nơi nằm phần lớn vòng đời job — cũng không
đo `grokpipe/executors`. Nên "coverage 91%" đọc là "gói domain mới được phủ
tốt", tuyệt đối không đọc thành "cả board được phủ 91%". Đừng nới ngưỡng 80% rồi
tưởng mình đã tăng độ an toàn của board.

Kết quả hiện tại: **499 pass và đúng 1 `xfailed`** (Phase 4 scheduler/lease +
sổ lỗi runtime + lưới property-based Hypothesis + test executor). Con số pass sẽ còn tăng khi thêm test;
cái PHẢI giữ nguyên là **đúng 1 `xfailed`** cho tới Phase 5 (forced-account).
Một expected
failure biến thành unexpected success cũng phải được giải thích: chỉ bỏ decorator ở
phase sửa lỗi tương ứng và sau khi đã xác minh target behavior. Không được thêm
expected failure mới chỉ để làm gate xanh.

## Sổ lỗi runtime (`.grokpipe/runtime-bugs/`)

Lỗi NẶNG của thợ ảnh/video được ghi thành JSONL đã lọc bí mật, nằm ngoài Git, đọc
lại được sau khi board restart. Không có prompt, cookie, token, DSN, base64, ảnh
hay video trong đó.

```bash
python -m sfboard.jobs.bugtool --root . status
python -m sfboard.jobs.bugtool --root . list
python -m sfboard.jobs.bugtool --root . show <event-id>
python -m sfboard.jobs.bugtool --root . sync
```

- `status`, `list`, `show` **chỉ đọc** — không sửa sổ, không gọi `bd`.
- `sync` là lệnh **thủ công và chỉ chạy cục bộ**. Nó chỉ gọi `bd` khi
  `.grokpipe/runtime-bugs/config.json` ghi rõ `{"mode": "auto-create"}`; mặc định là
  `journal-only`, tức Beads không bao giờ bị đụng tới. Không có remote sync,
  không có provider, không có GitHub Issue.
- Bridge chỉ **tạo mới hoặc cập nhật** một Bead cho mỗi fingerprint, và mở lại
  Bead đã đóng nếu lỗi tái phát. Nó không claim, không gán người, không đóng,
  không đổi priority.
- Quay về `journal-only` là rollback đủ: sự kiện vẫn được ghi, chỉ ngừng phần Beads.
- `/api/chan-doan` có thêm khối `bug_bridge` (mode · pending · last_sync_at ·
  last_error · created · updated) để nhìn nhanh trên board.
- AI **chỉ điều tra khi user mở/nhắc một Bead**, không tự đi lục sổ lỗi rồi sửa.

### Cảnh báo từ xa (tuỳ chọn)

Đặt `GROKPIPE_SENTRY_DSN` (hoặc `SENTRY_DSN`) thì mỗi sự kiện đã lọc được gửi
thêm lên Sentry, gom nhóm theo đúng `fingerprint` của sổ. **Không đặt DSN thì
không có gì xảy ra** — không init, không mạng, không lỗi. Sentry hỏng cũng không
làm hỏng việc ghi sổ: sổ JSONL cục bộ mới là nguồn AI đọc.

### Lưới property-based

`tests/job_lifecycle/test_queue_properties.py` dùng Hypothesis sinh chuỗi
xếp/nhấc/huỷ/ghi-trạng-thái ngẫu nhiên trên chính `hangdoi.py`, đối chiếu với một
mô hình song song. Nó KHÔNG thay các `xfail` đang khoá — vẫn phải sửa từng bug
bằng TDD, mỗi lần chỉ hạ đúng một expected failure ở đúng phase của nó.

## File map

- [Decisions](JOB-LIFECYCLE-DECISIONS.md): expected behavior đã được duyệt.
- [State machine](JOB-STATE-MACHINE.md): legal/illegal transitions.
- [Architecture](JOB-ARCHITECTURE-TARGET.md): owner và dependency direction.
- [Audit](JOB-LIFECYCLE-AUDIT.md): writer, re-enqueue, ambiguity và duplicated responsibility.
- [Migration plan](JOB-MIGRATION-PLAN.md): current/cutover phase và rollback gate.
- [Domain models](../sfboard/jobs/models.py): identity và immutable facts Phase 1.
- [Producer](../sfboard/jobs/producer.py): cửa DUY NHẤT tạo Job/Batch + idempotency.
- [Legacy adapter](../sfboard/jobs/compat.py): nơi DUY NHẤT ý định chạm hàng đợi cũ.
- [Scheduler](../sfboard/jobs/scheduler.py): lịch theo `execution_id`, lease atomic,
  và quan hệ thành viên ⇢ lô vật lý.
- [Lifecycle tests](../tests/job_lifecycle/): executable legacy/domain contract.
- [Legacy queue/state](../sfboard/hangdoi.py) và [runtime/API](../sfboard/sfboard.py):
  production authority hiện tại.

## Khi phải dừng hỏi người dùng

- Expected behavior chưa có trong Decisions hoặc mâu thuẫn giữa hai quyết định.
- Cần đổi retry budget, credit semantics, overwrite asset hoặc stop policy.
- Fix cần mở rộng sang production subsystem ngoài lifecycle đã audit.
- Cần chạy live integration có thể mở Chrome, submit provider hoặc tiêu credit.
