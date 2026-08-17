# Hồ sơ thiết kế lịch sử — Beads foundation

> Thiết kế đã triển khai; không phải tài liệu authority hiện hành.

## Ý định thiết kế

Dùng Beads local làm issue graph bền vững cho công việc nhiều phiên, ast-grep
cho structural search và giữ remote sync tách khỏi thao tác local mặc định.

## Quyết định còn hiệu lực

- Issue nằm trong local Dolt DB; export JSONL không phải writer chính.
- `bd` quản lý task, blocker và memory; Markdown không làm TODO tracker.
- Agent phải claim/close rõ và không tự chạy pull/push/sync.
- Dữ liệu runtime/project nhạy cảm không được đưa lên remote.

## Tài liệu thay thế

- `AGENTS.md`
- `.agents/skills/beads/SKILL.md`

Chi tiết cài đặt/version ban đầu đã bỏ để tránh hướng dẫn lỗi thời.
