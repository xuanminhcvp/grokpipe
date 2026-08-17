# Hồ sơ lịch sử — REF batching và navigation

> Hoàn tất ngày 2026-08-15; behavior đã có regression tests.

## Mục tiêu khi tạo

Cho “Chạy hết” REF gộp các asset tương thích, đồng thời chia UI/sidebar thành
nhân vật, nhân vật phụ, đạo cụ và bối cảnh dễ theo dõi.

## Kết quả

- REF batch giữ JobId/output riêng cho từng asset.
- `*_FULL` từ nhân vật thứ 5 được phân vào nhóm nhân vật phụ.
- Nội dung chính và sidebar dùng cùng quy tắc phân loại.
- Contract backend/UI có test chống chạy lẻ và chống lệch nhóm.

## Nguồn hiện hành

- `tests/job_lifecycle/test_ref_run_all.py`
- `tests/job_lifecycle/test_ref_ui_contract.py`
- [Architecture batch](../../JOB-ARCHITECTURE-TARGET.md)
