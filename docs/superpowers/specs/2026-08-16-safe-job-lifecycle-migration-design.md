# Hồ sơ thiết kế lịch sử — safe lifecycle migration

> Trạng thái: migration đã hoàn tất; file này chỉ giữ rationale nền.

## Ý định thiết kế

Thay kiến trúc legacy theo từng lát nhỏ có characterization test, shadow,
feature mode, cutover gate và rollback thay vì big-bang rewrite.

## Quyết định còn hiệu lực

- Mỗi phase chỉ thêm một authority khi authority cũ đã bị vô hiệu tương ứng.
- Typed identity và event/fact đi trước live worker cutover.
- SQLite/recovery đi trước bật production default.
- Credit/cancel semantics phải được khóa trước video live.
- Legacy chỉ xóa theo consumer audit và soak, không xóa hàng loạt.

## Tài liệu thay thế

- [Migration record](../../JOB-MIGRATION-PLAN.md)
- [Audit](../../JOB-LIFECYCLE-AUDIT.md)

Các phase/checklist tương lai trong bản gốc không còn là TODO.
