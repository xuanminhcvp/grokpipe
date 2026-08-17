# Hồ sơ thiết kế lịch sử — live DOM worker cutover

> Thiết kế đã triển khai và đã qua controlled live canary.

## Ý định thiết kế

Biến image/video browser automation thành executor của đúng một attempt, có
phase/fact rõ, để lifecycle runtime quản lý retry, account và commit.

## Quyết định còn hiệu lực

- Worker không re-enqueue hoặc tự transition terminal.
- Submit callback là credit boundary.
- Request mang job/execution/account/source identity đến downloader/saver.
- Historical Grok post phải được seed/ledger; chỉ post mới thuộc attempt được
  tải và commit.
- Live Grok submit dùng budget bền vững theo project/scope.
- Provider canary luôn có quyền người dùng và credit cap.

## Tài liệu thay thế

- [Video/image audit](../../JOB-LIFECYCLE-AUDIT.md)
- `sfboard/live_executor.py`, `sfboard/jobs/executor_adapter.py`
- `tests/executors/`, `tests/job_lifecycle/test_live_*.py`
