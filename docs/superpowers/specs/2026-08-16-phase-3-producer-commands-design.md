# Hồ sơ thiết kế lịch sử — producer commands

> Thiết kế Phase 3 đã triển khai và được mở rộng trong runtime authoritative.

## Ý định thiết kế

Đưa mọi nguồn tạo việc qua một command service có durable identity, fingerprint,
idempotency và active-scope constraint.

## Quyết định còn hiệu lực

- Transport retry giữ idempotency key.
- Intent mới/rerun thật dùng key mới và JobId mới.
- Replay key giống payload trả cùng record; payload khác conflict.
- Delivery state được ghi atomic với schedule boundary.
- Compatibility adapter là một lối ra có kiểm soát, không phải producer thứ hai.

## Tài liệu thay thế

- [Architecture — producer](../../JOB-ARCHITECTURE-TARGET.md#luồng-producer)
- `sfboard/jobs/producer.py`, `runtime.py`
- `tests/job_lifecycle/test_producer.py`
