# Hồ sơ thiết kế lịch sử — authoritative cutover

> Thiết kế đã triển khai; authoritative + live là production default.

## Ý định thiết kế

Đặt SQLite/runtime làm source of truth mà vẫn giữ compatibility API/UI và một
rollback path rõ.

## Quyết định còn hiệu lực

- Startup authoritative phải atomic và fail rõ khi repository/recovery lỗi.
- Runtime điều phối producer, scheduler, account, retry và result trong
  transaction boundary.
- Recovery dựa vào submit fact; post-submit không resubmit.
- Shadow/legacy không được cùng nắm writer authority.
- Không hạ mode khi còn authoritative execution active.

## Tài liệu thay thế

- [Architecture](../../JOB-ARCHITECTURE-TARGET.md)
- [State machine](../../JOB-STATE-MACHINE.md)
- [Migration record](../../JOB-MIGRATION-PLAN.md)
