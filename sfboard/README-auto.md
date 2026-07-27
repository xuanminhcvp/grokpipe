# Chạy tự động cả scene (nút ▶ Chạy hết)

Bật cho một scene rồi để đó. Board tự làm nốt phần còn thiếu của scene đó và tự tắt khi xong.

## Dùng

Trên header mỗi scene (cả chế độ **Board** lẫn **Kịch bản**) có nút:

- `▶ Chạy hết` — bấm để bật
- `⏳ 5/7 ảnh · 3/7 video` — đang chạy, nút xanh nhấp nháy, hiện tiến độ. Bấm lại để dừng.

Khi scene đủ cả ảnh lẫn video, nút tự tắt về `▶ Chạy hết`.

Bật được nhiều scene cùng lúc — chúng dùng chung hàng đợi và số tài khoản đang mở.

## Nó làm gì, mỗi 20 giây một vòng

1. **Ảnh SF nào chưa có** → xếp việc tạo ảnh
2. **Shot nào chưa có video mà ảnh SF của nó đã có** → xếp việc dựng video
3. Việc nào **lỗi** → tự xếp lại

Điểm chính là bước 2: video chỉ dựng được khi ảnh SF đã xong, mà ảnh xong rải rác không theo
thứ tự. Auto bám sát nên ảnh xong tới đâu đẩy video tới đó, không phải ngồi đợi ảnh xong hết
rồi mới bắt đầu dựng video.

Việc đang chạy (`state = running`) thì bỏ qua, nên không bao giờ xếp trùng.

## Giới hạn tự bảo vệ

| Hằng số | Mặc định | Ý nghĩa |
|---|---|---|
| `AUTO_PERIOD` | 20s | một vòng quét |
| `AUTO_MAX_TRY` | 40 | số lần bắn lại tối đa cho một ảnh/video |
| `AUTO_COOLDOWN` | 6 vòng (~2 phút) | phải chờ bấy nhiêu trước khi bắn lại cùng một thứ |

Cooldown là thứ quan trọng nhất. Lỗi hay gặp của ChatGPT/Grok (`set_input_files timeout`,
`click timeout`) thường là kẹt nhất thời — thử lại sau vài phút là chạy. Nếu bắn lại dồn dập
thì vừa đốt hết số lần thử vừa không giải quyết được gì.

## Khi nó không cứu được

Auto chỉ xếp lại việc, không sửa được nguyên nhân. Nếu một scene mãi không nhích:

- **Tài khoản đăng xuất** — hay gặp nhất, và nhìn trạng thái tài khoản không thấy được: cột
  `chrome`/`worker` vẫn xanh vì Chrome vẫn mở, chỉ là trang đang hiện màn hình đăng nhập. Mở
  tab đó ra xem tận mắt.
- **Hết lượt tạo ảnh/video trong ngày** — tài khoản free hết nhanh hơn Plus nhiều.
- **Hết 40 lần thử** — xem log server, dòng có `[auto <scene>]`. Tắt/bật lại nút để reset bộ đếm.

## API (nếu cần gọi tay)

```
POST /api/auto?op=toggle&scene=S12    # bật/tắt một scene
POST /api/auto?op=on&scene=S12
POST /api/auto?op=off&scene=S12
POST /api/auto?op=offall              # tắt tất cả
GET  /api/jobs                        # trường "auto" chứa tiến độ từng scene
```

Trạng thái auto nằm trong bộ nhớ, khởi động lại board là mất — bật lại nếu cần.
Việc đã nằm trong hàng đợi thì vẫn chạy tiếp kể cả khi đã tắt auto.

---

# Lọc video (chế độ Kịch bản)

Ô lọc bên cạnh nút chuyển chế độ. Chọn một nhóm thì **chỉ hiện đúng những dòng cần xử lý**,
scene nào không còn gì thì ẩn luôn — không phải cuộn qua 129 dòng để tìm.

| Nhóm | Dùng khi |
|---|---|
| ⬜ Chưa duyệt | ngồi duyệt lần lượt; duyệt xong dòng nào là nó biến mất |
| ✓ Đã duyệt · ✕ Bị loại | xem lại cái đã quyết |
| Chưa có video | còn thiếu gì |
| ⧉ Nhiều bản — cần chọn | shot có 2+ bản, bấm v1/v2 để chọn |
| ⚠ Lỗi khi tạo | cái nào chết giữa chừng |
| ⏱ Trống thời lượng | thoại ngắn hơn độ dài clip quá 3,2s |
| ⚠ Prompt lệch thoại | đã sửa thoại nhưng prompt chưa viết lại |
| Thiếu ảnh SF | shot chưa có start frame nên chưa dựng được |

## Nút "↻ Tạo lại N video đang hiện"

Chỉ xuất hiện ở **ba nhóm**: *chưa có video*, *lỗi khi tạo*, *bị loại* — là ba trường hợp mà
render lại đúng là việc cần làm. Có hỏi xác nhận, bản cũ vẫn giữ thành version.

Cố tình **không** cho ở các nhóm khác:

- *chưa duyệt / đã duyệt / nhiều bản* — nhóm để XEM. Một cú bấm nhầm là 91 clip vào hàng đợi.
- *trống thời lượng* — nguyên nhân nằm ở cách chia thoại vào shot. Render lại chỉ dựng lại
  đúng cái trống cũ; phải gộp thoại hoặc hạ 10s→6s trước.
- *prompt lệch thoại* — cờ này nghĩa là prompt CHƯA được viết lại. Render ngay là dùng lại
  prompt cũ. Viết lại prompt, bấm ✓ đã khớp, rồi mới tạo.

## Màu viền trái mỗi dòng

xanh = đã duyệt · đỏ = bị loại · cam = có video nhưng chưa quyết · không viền = chưa có video
