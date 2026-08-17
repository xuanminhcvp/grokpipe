# Hồ sơ lịch sử — authoritative lifecycle cutover

> Hoàn tất ngày 2026-08-16; authoritative hiện là mode production mặc định.

## Mục tiêu khi tạo

Chuyển source of truth từ state/queue legacy sang SQLite + `LifecycleRuntime`
mà vẫn giữ API/UI tương thích và có rollback.

## Kết quả

- Durable execution identity, CAS/transaction và scheduler recovery.
- SQLite repository dùng chung cho intent, job, event, execution, attempt.
- Runtime nắm transition/retry/account/result authority.
- Startup fail rõ nếu authoritative init lỗi.
- Legacy/shadow nằm sau compatibility boundary.

## Nguồn hiện hành

- [Architecture](../../JOB-ARCHITECTURE-TARGET.md)
- [Migration record](../../JOB-MIGRATION-PLAN.md)
- `sfboard/jobs/runtime.py`, `sqlite_store.py`
