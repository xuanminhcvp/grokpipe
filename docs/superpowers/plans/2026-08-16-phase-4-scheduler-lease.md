# Hồ sơ lịch sử — Phase 4 scheduler và lease

> Hoàn tất ngày 2026-08-16; scheduler/lease đã nằm trong runtime production.

## Mục tiêu khi tạo

Tách execution vật lý khỏi JobId và ngăn hai worker cùng lấy một việc.

## Kết quả

- Ready/waiting/leased/finished execution state.
- Lease TTL, member lookup và `not_before` cho retry.
- Cancel tìm đúng execution theo member thay vì queue label.
- Scheduler persistence/rollback/recovery có tests.

## Nguồn hiện hành

- `sfboard/jobs/scheduler.py`, `persistence.py`, `sqlite_store.py`
- `tests/job_lifecycle/test_scheduler.py`
- [Architecture](../../JOB-ARCHITECTURE-TARGET.md)
