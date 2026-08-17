# Hồ sơ thiết kế lịch sử — REF batching và navigation

> Thiết kế đã triển khai; UI/backend contract hiện nằm trong tests.

## Ý định thiết kế

Gộp REF tương thích để chạy hiệu quả, đồng thời giúp người dùng phân biệt nhân
vật chính/phụ, đạo cụ và bối cảnh ở nội dung lẫn sidebar.

## Quyết định còn hiệu lực

- Grouping chỉ đổi execution vật lý, không nhập JobId/output.
- Nhân vật thứ 1–4 là nhóm chính; `*_FULL` từ thứ 5 vào nhóm nhân vật phụ.
- Đạo cụ và bối cảnh có section riêng.
- Sidebar và main panel dùng cùng classifier/order.
- “Chạy hết” gửi một intent/batch phù hợp, không loop các request lẻ nếu có thể
  gộp.

## Tài liệu thay thế

- `tests/job_lifecycle/test_ref_run_all.py`
- `tests/job_lifecycle/test_ref_ui_contract.py`
- [Batch architecture](../../JOB-ARCHITECTURE-TARGET.md)
