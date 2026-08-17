# Hồ sơ thiết kế lịch sử — runtime bug journal

> Thiết kế đã triển khai; journal local là tính năng production.

## Ý định thiết kế

Ghi sự cố nặng qua restart theo schema ổn định, redact bí mật, fingerprint/dedupe
và cung cấp bridge tùy chọn sang Beads/Sentry.

## Quyết định còn hiệu lực

- Journal append-only tại `.grokpipe/runtime-bugs/events.jsonl`.
- Payload chứa category, fingerprint, context kỹ thuật đã redact và timestamp.
- Thiếu dependency/integration ngoài không được làm board chết.
- Auto-create Bead và remote alert chỉ bật khi opt-in local.
- Diagnostics phải đọc được mà không lộ token/cookie/profile data.

## Tài liệu thay thế

- [Audit runtime](../../JOB-LIFECYCLE-AUDIT.md#runtime-diagnostics)
- `sfboard/jobs/runtime_service.py`, `runtime_journal.py`
- `tests/runtime_bugs/`
