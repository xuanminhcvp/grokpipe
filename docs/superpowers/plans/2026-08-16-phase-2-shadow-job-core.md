# Hồ sơ lịch sử — Phase 2 shadow job core

> Hoàn tất ngày 2026-08-16; shadow không còn là production target.

## Mục tiêu khi tạo

Xây store/manager/projection mới ở chế độ quan sát để so state với legacy mà
không nắm quyền điều khiển.

## Kết quả

- Memory store và manager khóa transition/idempotent event.
- Legacy shadow projection phát hiện mismatch.
- Shadow init failure quay về legacy sạch, không để observer nửa khởi tạo.
- Core này tạo nền cho producer và SQLite authoritative về sau.

## Nguồn hiện hành

- `sfboard/jobs/store.py`, `manager.py`, `projection.py`
- `tests/job_lifecycle/test_store.py`
- [Migration record](../../JOB-MIGRATION-PLAN.md)

Không bật shadow để thay thế diagnostics authoritative hiện tại.
