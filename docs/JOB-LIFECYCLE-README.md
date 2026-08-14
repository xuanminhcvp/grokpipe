# Job lifecycle — cửa vào cho AI

Đọc file này trước khi điều tra hoặc sửa job ảnh/video, `JOBS`, queue, state,
retry, cancel/stop, account assignment, auto producer, worker hoặc job API/UI.

## Đọc trong 60 giây

- Current phase: **Phase 0–1 đã triển khai trên branch lifecycle**.
- Production authority vẫn là legacy: `JOBS`, `PriorityQueue`, worker, retry và auto.
- `sfboard/jobs` mới chỉ là immutable domain model; production chưa import nó.
- 5 known ambiguity đang được khóa bằng `expectedFailure`, chưa được coi là đã sửa:
  cancel identity lô, auto-video enqueue trùng, auto/stop race, multi-copy identity,
  và forced-account retry mất constraint.
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

Gate này chạy toàn bộ lifecycle tests, yêu cầu coverage `sfboard/jobs` tối thiểu
80%, rồi compile legacy runtime và domain package. Nó không mở browser, gọi provider
hoặc tiêu credit.

Kết quả Phase 0–1 hiện tại: 35 tests, 30 pass và đúng 5 `xfailed`. Một expected
failure biến thành unexpected success cũng phải được giải thích: chỉ bỏ decorator ở
phase sửa lỗi tương ứng và sau khi đã xác minh target behavior. Không được thêm
expected failure mới chỉ để làm gate xanh.

## File map

- [Decisions](JOB-LIFECYCLE-DECISIONS.md): expected behavior đã được duyệt.
- [State machine](JOB-STATE-MACHINE.md): legal/illegal transitions.
- [Architecture](JOB-ARCHITECTURE-TARGET.md): owner và dependency direction.
- [Audit](JOB-LIFECYCLE-AUDIT.md): writer, re-enqueue, ambiguity và duplicated responsibility.
- [Migration plan](JOB-MIGRATION-PLAN.md): current/cutover phase và rollback gate.
- [Domain models](../sfboard/jobs/models.py): identity và immutable facts Phase 1.
- [Lifecycle tests](../tests/job_lifecycle/): executable legacy/domain contract.
- [Legacy queue/state](../sfboard/hangdoi.py) và [runtime/API](../sfboard/sfboard.py):
  production authority hiện tại.

## Khi phải dừng hỏi người dùng

- Expected behavior chưa có trong Decisions hoặc mâu thuẫn giữa hai quyết định.
- Cần đổi retry budget, credit semantics, overwrite asset hoặc stop policy.
- Fix cần mở rộng sang production subsystem ngoài lifecycle đã audit.
- Cần chạy live integration có thể mở Chrome, submit provider hoặc tiêu credit.
