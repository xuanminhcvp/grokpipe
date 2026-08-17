# Hồ sơ lịch sử — lifecycle AI entrypoint

> Hoàn tất ngày 2026-08-14; đã được thay bằng bộ docs canonical hiện tại.

## Mục tiêu khi tạo

Buộc AI đọc đúng authority, state machine, decisions và migration plan trước khi
sửa queue/job/account/worker.

## Kết quả

- `AGENTS.md` và `CLAUDE.md` trỏ vào một entrypoint.
- Quy trình Serena → systematic debugging → regression test → full gate được
  khóa thành instruction repo.
- Tài liệu canonical tách kiến trúc, state, decisions, migration và audit.

## Nguồn hiện hành

- [Lifecycle entrypoint](../../JOB-LIFECYCLE-README.md)
- [Audit](../../JOB-LIFECYCLE-AUDIT.md)

Không dùng assumption “legacy là production” trong plan cũ.
