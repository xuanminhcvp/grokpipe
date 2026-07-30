# PIPELINE-RUTHS-HOUSE — luật của dự án

## ⛔ KHÔNG TỰ BẬT CỔNG VIDEO
Video chỉ được tạo khi **user tự bấm nút** "Cho phép tạo video" trên giao diện board.
Claude/AI **tuyệt đối không** ghi file `.video-gate`, không gọi `/api/video-gate?on=1`,
không giả header để lách, không sửa `sfboard.py` để bỏ cổng.
Cần render video thì **báo user và chờ user bấm nút**.
Chi tiết: [KHONG-TU-BAT-VIDEO.md](KHONG-TU-BAT-VIDEO.md)

## Board
`python3 sfboard/sfboard.py PIPELINE-RUTHS-HOUSE.project --port 8779`
(8DOLLARS dùng 8778, HOOK-DUESENBERG dùng 8777)

## Ảnh REF
Ảnh user tự dán vào là **bản chuẩn tuyệt đối** — không "nâng cấp" lên bản nét hơn trong
`versions/`, không tự crop ảnh đã duyệt. Xem bài học 46 trong skill `tao-prompt-sf`.
