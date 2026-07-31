# Bước 1 — Ảnh chân dung nhân vật (PORTRAIT)

## Mục lục
- Làm gì ở bước này
- Quy tắc portrait
- Kiểm trước khi sang bước 2

## Làm gì ở bước này

Rà **toàn bộ kịch bản** liệt kê mọi nhân vật có tên hoặc có thoại, kể cả vai phụ chỉ xuất hiện
một cảnh. Mỗi nhân vật tạo **đúng một** `REF_<TÊN>_PORTRAIT` (2:3).

Đặt trong scene `REF` của `sf-board.json`. Portrait KHÔNG có `refs.bg` và KHÔNG đính ref nào
khác — nó là ảnh gốc của cả phim.

## Quy tắc portrait

- **MỖI NHÂN VẬT CHỈ CÓ MỘT PORTRAIT DUY NHẤT, dùng cho cả phim.** Portrait là ảnh chuẩn của
  KHUÔN MẶT — không tạo lại portrait cho từng bộ đồ.
- Trang phục trong ảnh portrait có thể rò sang SF ở một tỉ lệ nhỏ. **User đã quyết KHÔNG xử lý việc này** — tỉ lệ lỗi thấp, không đáng đổi cả quy trình. TUYỆT ĐỐI KHÔNG tự ý crop ảnh portrait đã duyệt và không ép portrait về 1:1 cận mặt (xem bài học 46).

- **Nhìn thẳng vào camera.** Không ngẩng cằm, không cúi, không nghiêng đầu — đây là ảnh chuẩn
  để mọi SF sau bám theo, lệch hướng đầu là mọi SF lệch theo.
- **Chụp kiểu studio, SÁNG RÕ.** Ảnh tối thì các SF phái sinh cũng tối và khó bám nhân dạng.
- **Khóa chủng tộc, kiểu tóc, tuổi bằng chữ** ngay trong prompt — ảnh không tự nói được những
  thứ này, và đây là chỗ model hay tự ý đổi.

## Kiểm trước khi sang bước 2

- [ ] Mọi nhân vật có tên trong kịch bản đều có portrait
- [ ] Không nhân vật nào có hai portrait
- [ ] Ảnh nhìn thẳng, sáng rõ, thấy rõ đường nét mặt
