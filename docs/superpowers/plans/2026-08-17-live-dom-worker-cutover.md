# Hồ sơ lịch sử — live DOM worker cutover

> Hoàn tất ngày 2026-08-17; live executor được bật mặc định cùng authoritative.

## Mục tiêu khi tạo

Đưa Chrome/DOM image và video worker thật sau one-attempt boundary, để runtime
quyết định retry/cancel/result thay vì worker tự xử lý lifecycle.

## Kết quả

- Phase callbacks từ preparing đến saving/finished.
- Image batch/partial/download/save mapping có regression.
- Video submit/credit boundary, source identity và post ledger chống tải nhầm.
- Live Grok budget bền vững giới hạn 1–20 theo scope.
- Authority guard, diagnostics và controlled live canary đã qua.

## Nguồn hiện hành

- `sfboard/live_executor.py`, `sfboard/jobs/executor_adapter.py`
- `tests/executors/`, `tests/job_lifecycle/test_live_*.py`
- [Audit live paths](../../JOB-LIFECYCLE-AUDIT.md)
