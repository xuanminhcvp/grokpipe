# Bước 2 — Ảnh toàn thân theo trang phục (FULL BODY)

## Mục lục
- Làm gì ở bước này
- Quy tắc REF trang phục
- Kiểm trước khi sang bước 3

## Làm gì ở bước này

Rà kịch bản **ngay từ đầu** liệt kê mọi **trạng thái trang phục** của từng nhân vật — thường
trùng với các chặng của cốt truyện (đi làm · ở nhà · bệnh viện · ngày bị bắt · lễ...).

Mỗi bộ tạo một `REF_<TÊN>_<TRẠNG THÁI>_FULL` (9:16), luôn đính `REF_<TÊN>_PORTRAIT` vào
`refs.chars` để lấy khuôn mặt rồi thay phần trang phục.

Đặt tên trạng thái theo NGHĨA chứ không theo số scene (`_HOME`, `_UNIFORM`, `_DAY2`) — scene
có thể đổi số, nghĩa thì không.

## Quy tắc REF trang phục

- **Nhân vật đổi trang phục theo chặng truyện thì mỗi bộ chỉ cần THÊM MỘT ẢNH FULL**
  (`REF_<TEN>_<TRẠNG THÁI>_FULL`, vd. `_HOME`, `_OFFICE`, `_SCRUBS`), luôn đính portrait gốc để
  lấy khuôn mặt rồi thay phần trang phục. Rà kịch bản ngay từ đầu để liệt kê đủ các trạng thái này.
- **SF của một cảnh đính CẢ HAI**: portrait gốc (khuôn mặt) + FULL của đúng bộ đồ cảnh đó
  (trang phục), và ghi rõ trong prompt ảnh nào dùng cho phần nào. Tuyệt đối KHÔNG đính REF bộ cũ
  rồi mô tả bộ mới bằng chữ — model sẽ vẽ lại bộ trong ảnh (xem bài học 24).
- Quy tắc trên áp dụng cho **MỌI nhân vật**, kể cả vai phụ và kể cả trang phục "bắt buộc theo bối
  cảnh" (áo bệnh nhân, đồ bảo hộ...). Khi rút ra một quy tắc REF mới, quét lại cả dự án để áp dụng
  đồng loạt, đừng chỉ sửa nhân vật đang làm dở (bài học 27).
- **Nhưng CHỈNH NHỎ có chủ đích kể chuyện thì viết thẳng trong SF, không cần REF mới**: tháo/nới
  cà vạt, xắn tay áo, tháo bảng tên (còn vệt vải và lỗ ghim), cởi blazer vắt ghế... Ranh giới:
  **thêm/bớt MỘT món để nói một điều → viết trong SF; đổi TOÀN BỘ bộ đồ → tạo REF.**

## Kiểm trước khi sang bước 3

- [ ] Mọi trạng thái trang phục trong kịch bản đều có một FULL
- [ ] Mỗi FULL đều đính portrait gốc để lấy mặt
- [ ] Nhãn của FULL ghi rõ nó dùng cho scene nào
