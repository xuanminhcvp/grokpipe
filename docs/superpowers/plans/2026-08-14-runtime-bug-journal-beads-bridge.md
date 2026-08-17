# Hồ sơ lịch sử — runtime bug journal và Beads bridge

> Hoàn tất ngày 2026-08-14; journal local đã được production wiring.

## Mục tiêu khi tạo

Lưu lỗi runtime qua restart, redact dữ liệu nhạy cảm, dedupe bằng fingerprint và
có thể chuyển incident sang Beads mà không làm board phụ thuộc integration.

## Kết quả

- `.grokpipe/runtime-bugs/events.jsonl` là journal local bền vững.
- Classifier, redaction, fingerprint, diagnostics và crash-tail recovery có test.
- Beads bridge và Sentry chỉ hoạt động khi opt-in/cấu hình rõ.

## Nguồn hiện hành

- `sfboard/jobs/runtime_*.py`, `beads_bridge.py`, `bugtool.py`
- `tests/runtime_bugs/`
- [Audit runtime](../../JOB-LIFECYCLE-AUDIT.md#runtime-diagnostics)

Không chạy bridge/remote command chỉ vì plan lịch sử có nhắc đến nó.
