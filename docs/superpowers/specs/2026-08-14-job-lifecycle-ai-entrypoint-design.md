# Hồ sơ thiết kế lịch sử — lifecycle AI entrypoint

> Thiết kế đã triển khai và được thay bằng docs canonical.

## Ý định thiết kế

Tạo một đường đọc ngắn để AI luôn xác định authority/phase/invariant trước khi
đụng vào queue, retry, account, worker hoặc API/UI.

## Quyết định còn hiệu lực

- Một entrypoint trỏ tới architecture, state, decisions, migration và audit.
- Serena dùng cho symbol/reference; ast-grep cho writer; `rg` cho text/docs.
- Bugfix đi qua systematic debugging và regression test.
- Kết luận cần full lifecycle + compile gate.

## Tài liệu thay thế

- [Lifecycle entrypoint](../../JOB-LIFECYCLE-README.md)
- `AGENTS.md`, `CLAUDE.md`
