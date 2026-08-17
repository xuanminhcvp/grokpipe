# Hồ sơ lịch sử — Phase 3 producer commands

> Hoàn tất ngày 2026-08-16; producer command là boundary hiện hành.

## Mục tiêu khi tạo

Đưa mọi UI/API/auto producer qua một contract idempotent trước khi chạm queue.

## Kết quả

- Atomic intent/job/batch creation và payload fingerprint.
- Replay cùng key/payload, conflict khi payload đổi.
- Active-scope constraint và rerun identity mới.
- Một compatibility adapter giao việc legacy trong giai đoạn migration.
- HTTP producers và auto producer đã được migrate.

## Nguồn hiện hành

- `sfboard/jobs/producer.py`, `compat.py`
- `tests/job_lifecycle/test_producer.py`, `test_create_endpoint.py`
- [Decisions D05–D07](../../JOB-LIFECYCLE-DECISIONS.md)
