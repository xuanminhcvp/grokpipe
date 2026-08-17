# Hồ sơ lịch sử — lifecycle Phase 0–1

> Hoàn tất ngày 2026-08-14; characterization và domain model đã vào production.

## Mục tiêu khi tạo

Khóa hành vi cũ bằng tests trước khi đưa vào typed model và error taxonomy.

## Kết quả

- Characterization cho queue, cancel, retry, auto, account và HTTP.
- Typed identity cho asset/job/batch/execution/attempt.
- Job state, attempt phase, event, lease và error facts bất biến.
- Test inventory bảo vệ các writer/authority quan trọng.

## Nguồn hiện hành

- `sfboard/jobs/models.py`, `sfboard/jobs/errors.py`
- `tests/job_lifecycle/`
- [State machine](../../JOB-STATE-MACHINE.md)

Code mẫu và pass-count giai đoạn đầu đã bỏ; implementation hiện tại là chuẩn.
