# ⛔ KHÔNG ĐƯỢC TỰ BẬT CỔNG VIDEO — luật do user đặt, áp dụng cho MỌI phiên

**Ngày đặt:** 2026-07-30 · **Người đặt:** user (Minh)

> *"thêm 1 nút bật tắt có thể tạo video trên giao diện, nút này chỉ được tôi click,
> bạn không được bật nhé, tôi bật thì lúc đó mới có thể làm video."*

## Luật

**Claude / AI TUYỆT ĐỐI KHÔNG ĐƯỢC MỞ CỔNG VIDEO.** Chỉ user tự bấm nút trên giao diện board.

Cấm cụ thể, không có ngoại lệ nào:

- Không ghi/sửa/xóa file `.video-gate`.
- Không gọi `POST /api/video-gate?on=1` bằng `curl`, script, hay bất kỳ cách nào.
- Không giả header (`Sec-Fetch-Site`, `Referer`…) để lách lớp kiểm tra của server.
- Không sửa `sfboard.py` để bỏ hoặc làm yếu cổng này.
- Không viết script/guard/cron tự bật cổng, kể cả "chỉ để thử".
- Không nhờ đường vòng nào khác (sửa hằng số mặc định, đổi `PROJ`, tạo file ở đường dẫn khác…).

Khi cần render video: **báo user và chờ user tự bấm nút.** Không tự xử lý.

## Cách cổng hoạt động

| Thành phần | Vai trò |
|---|---|
| `<project>/.video-gate` | Cờ. Nội dung `on` = mở; thiếu file hoặc nội dung khác = **KHÓA** |
| `video_gate_on()` | Hàm đọc cờ, dùng ở mọi đường dẫn tạo video |
| `POST /api/genvideo` | Trả **403** khi cổng đóng |
| `_auto_scene()` (auto-run) | Bỏ qua toàn bộ phần video khi cổng đóng |
| `POST /api/video-gate?on=1|0` | Đổi cờ. **Từ chối** nếu request không mang đủ `Sec-Fetch-Site: same-origin`, `Sec-Fetch-Mode: cors` và `Referer` — tức là chỉ cú bấm từ trang web mới qua được |
| Nút `#vgate` trên thanh công cụ | Đỏ 🔒 KHÓA / xanh 🎬 MỞ. Tự làm mới mỗi 5 giây |
| Log board | Ghi lại mỗi lần đổi cổng kèm nguồn: `CỔNG VIDEO MỞ/ĐÓNG (nguồn: …)` |

## Nói thẳng về giới hạn kỹ thuật

Lớp kiểm tra header chặn được **mọi lệnh tự động, mọi script, mọi cú `curl`** — kể cả do sơ suất.
Nhưng Claude có quyền chạy shell trên máy này, nên **về mặt kỹ thuật không tồn tại rào cản tuyệt
đối** ngăn Claude sửa file cờ hoặc sửa chính đoạn kiểm tra. Không nên tin rằng đây là mật mã.

Thứ thực sự bảo đảm là **luật trong file này** cùng cam kết tuân thủ. File này được đọc ở mọi
phiên làm việc trên dự án. Nếu một phiên nào đó thấy mình đang định bật cổng — dừng lại, đó là
vi phạm.

Kiểm tra trạng thái cổng (chỉ ĐỌC, luôn được phép):

```bash
cat /Users/may1/Desktop/grokpipe/PIPELINE-RUTHS-HOUSE.project/.video-gate 2>/dev/null || echo "KHÓA"
```
