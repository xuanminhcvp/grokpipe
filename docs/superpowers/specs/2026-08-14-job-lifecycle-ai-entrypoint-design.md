# Job Lifecycle AI Entrypoint Design

Ngày: 2026-08-14
Trạng thái: Đã duyệt thiết kế hội thoại, chờ duyệt written spec

## Mục tiêu

Giúp Codex, Serena, Superpowers và Claude Code xử lý lỗi lifecycle job ảnh/video
mà không phải nạp toàn bộ khoảng 2.700 dòng tài liệu trong mọi task.

AI phải xác định được trong khoảng một phút:

1. Production đang ở migration phase nào.
2. Authority hiện tại nằm ở legacy hay kiến trúc mới.
3. Component nào sở hữu hành vi đang lỗi.
4. Tài liệu chi tiết và test nào cần đọc tiếp.
5. Những invariant nào không được phá khi sửa.

## Không nằm trong phạm vi

- Không rút gọn hoặc xoá năm tài liệu nguồn hiện có.
- Không tạo custom skill mới.
- Không sửa production, queue, retry, account hoặc API.
- Không ghi lại cùng một bản hướng dẫn dài trong nhiều file.
- Không buộc AI đọc mọi tài liệu chi tiết cho một lỗi nhỏ.

## Phương án được chọn

Dùng một tài liệu cửa vào duy nhất:

`docs/JOB-LIFECYCLE-README.md`

Hai adapter ngắn dẫn AI tới tài liệu này:

- `AGENTS.md` cho Codex, Serena và Superpowers.
- Một section nhỏ trong `CLAUDE.md` cho Claude Code.

Nội dung lifecycle chỉ được duy trì ở README. Hai adapter không sao chép state
machine, routing table hoặc invariant chi tiết để tránh drift.

## Luồng đọc

```text
AGENTS.md ─────┐
               ├─> docs/JOB-LIFECYCLE-README.md
CLAUDE.md ─────┘                 │
                                 ├─ state/transition
                                 ├─ retry/re-enqueue
                                 ├─ cancel/stop
                                 ├─ account assignment
                                 ├─ API/UI compatibility
                                 └─ migration/refactor
```

README định tuyến đến đúng source of truth; AI không đọc tuần tự cả năm file.

## File và trách nhiệm

### `docs/JOB-LIFECYCLE-README.md`

Tối đa 150 dòng, gồm đúng các phần:

1. **Đọc trong 60 giây**
   - Phase hiện tại.
   - Production authority hiện tại.
   - Năm known ambiguity đang là `expectedFailure`.
   - Khẳng định domain package mới chưa điều khiển runtime.

2. **Quy trình sửa lỗi bắt buộc**
   - Phân loại triệu chứng.
   - Đọc tài liệu theo routing.
   - Dùng Serena tìm symbol, caller và writer.
   - Dùng Superpowers systematic debugging xác định nguyên nhân.
   - Viết regression test tái hiện lỗi.
   - Sửa đúng owner, không thêm authority mới.
   - Chạy full lifecycle suite và compile gate.

3. **Routing table**
   - State sai → state machine.
   - Retry/enqueue trùng → audit + decisions.
   - Cancel/stop → state machine + audit.
   - Account sai → architecture + decisions.
   - API/UI schema → characterization tests + migration plan.
   - Refactor/cutover → migration plan + architecture.
   - Không rõ expected behavior → decisions.

4. **Invariant ngắn**
   - Một lifecycle authority.
   - Terminal state không regress.
   - Retry không tự hồi sinh cancelled job.
   - Outcome không chắc chắn không tự submit lại.
   - Forced account không tự mất khi retry.
   - Explicit rerun tạo Job mới.
   - Asset ID không phải Job/Execution/Attempt ID.

5. **Lệnh kiểm tra**
   - `python3 -m unittest discover -s tests/job_lifecycle -p 'test_*.py'`
   - `python3 -m py_compile` cho legacy và domain package.
   - Giải thích expected result gồm năm `expectedFailure` cho đến phase sửa lỗi.

6. **File map có link tương đối**
   - `JOB-LIFECYCLE-DECISIONS.md`.
   - `JOB-STATE-MACHINE.md`.
   - `JOB-ARCHITECTURE-TARGET.md`.
   - `JOB-LIFECYCLE-AUDIT.md`.
   - `JOB-MIGRATION-PLAN.md`.
   - `sfboard/jobs/*`, `tests/job_lifecycle/*`, `hangdoi.py`, `sfboard.py`.

### `AGENTS.md`

File ngắn ở repo root, không quá 25 dòng. Scope áp dụng toàn repo nhưng chỉ kích
hoạt routing lifecycle khi task liên quan một trong các khái niệm:

- image/video job;
- `JOBS` hoặc queue;
- state/retry/cancel/stop;
- account assignment;
- auto producer/worker/watchdog;
- job API hoặc queue UI.

Instruction bắt buộc:

1. Đọc `docs/JOB-LIFECYCLE-README.md` trước.
2. Xác định migration phase trước khi giả định authority.
3. Dùng Serena lần symbol/caller/writer trước khi sửa.
4. Dùng `superpowers:systematic-debugging` khi có lỗi.
5. Dùng TDD cho bugfix.
6. Không tạo writer, retry hoặc re-enqueue authority mới.
7. Trả lời người dùng bằng tiếng Việt.

### `CLAUDE.md`

Thêm một section ngắn gần phần mô tả repo hoặc “Khi khâu render hỏng”. Section
chỉ chứa trigger và link tới README; không chép routing table.

Claude Code được yêu cầu làm cùng chuỗi:

`README → tài liệu được route → symbol/writer → regression test → fix → full gate`.

Phần hiện có của `CLAUDE.md` về `.venv`, tài khoản, dữ liệu phim và Git giữ nguyên.

## Quy tắc dành cho công cụ

### Serena

Serena không phải nguồn sự thật về kiến trúc. Sau khi README chọn vùng cần kiểm
tra, Serena được dùng để:

- tìm definition;
- tìm referencing symbols/callers;
- tìm mọi writer của state/retry/account/queue;
- kiểm tra call path trước khi thay đổi.

Không lưu một bản kiến trúc riêng trong Serena memory vì có thể lệch tài liệu Git.

### Superpowers

- Lỗi hoặc hành vi bất ngờ: `systematic-debugging` trước khi đề xuất fix.
- Bugfix/behavior change: `test-driven-development` trước implementation.
- Công việc nhiều bước: `writing-plans` rồi `executing-plans` hoặc
  `subagent-driven-development`.
- Trước tuyên bố hoàn tất: `verification-before-completion`.

README chỉ định workflow; không sửa skill hoặc sao chép nội dung skill.

## Trạng thái phase phải hiển thị

Tại thời điểm triển khai entrypoint:

- Phase 0–1 đã được triển khai trên branch `codex/job-lifecycle-phase-0-1`.
- Legacy `JOBS`, `PriorityQueue`, worker/retry/auto vẫn là production authority.
- `sfboard/jobs` mới là domain model thuần, chưa được production import.
- Năm known ambiguity vẫn phải tồn tại dưới `expectedFailure` cho đến đúng phase
  sửa tương ứng.

Khi migration sang phase mới, chỉ cập nhật block “Current phase” trong README;
adapter `AGENTS.md` và `CLAUDE.md` không đổi.

## Điều kiện thành công

- Một AI mới vào repo tìm đúng tài liệu chi tiết mà không đọc cả năm file.
- Codex và Claude Code nhận cùng instruction lifecycle từ một nguồn.
- Serena được dùng cho code navigation, không làm architectural memory riêng.
- AI không nhầm domain model Phase 1 là production authority.
- Lệnh test và số expected failure được ghi rõ.
- README không vượt 150 dòng; AGENTS không vượt 25 dòng.
- Không có production file nào thay đổi.

## Kiểm tra triển khai

1. Kiểm số dòng README và AGENTS.
2. Kiểm mọi link tương đối trỏ tới file tồn tại.
3. Tìm nội dung routing bị sao chép vào adapter; adapter chỉ được giữ pointer.
4. Chạy full lifecycle suite và compile gate.
5. `git diff --name-only` chỉ gồm README, AGENTS và CLAUDE.
