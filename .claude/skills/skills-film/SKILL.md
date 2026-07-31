---
name: skills-film
description: Viết/sửa prompt ảnh nhân vật và Start Frame (SF) trong sf-board.json cho các dự án PIPELINE-*.project. Dùng skill này mỗi khi tạo REF nhân vật mới, tạo SF cho một scene, hoặc sửa ngoại hình/trang phục nhân vật trong board — kể cả khi user chỉ nói "tạo SF cho scene X" mà không nhắc rõ kỹ thuật.
---

# Làm phim từ kịch bản — quy trình 5 bước

Bạn soạn prompt tiếng Việt để model tạo ảnh (ChatGPT/CDP) render ảnh nhân vật tham chiếu (REF)
và Start Frame (SF), lưu trong `sf-board.json` của dự án `PIPELINE-*.project`.

**File này chứa QUY TRÌNH và LUẬT CỨNG.** Cách làm chi tiết của từng bước nằm ở file riêng —
mở đúng file của bước đang làm, không cần đọc hết.

## Quy trình — nhận một kịch bản mới thì đi theo đúng thứ tự này

| Bước | Việc | Đọc file |
|---|---|---|
| **1** | Ảnh **portrait** mọi nhân vật trong kịch bản | [1-portrait.md](references/1-portrait.md) |
| **2** | Ảnh **full-body** cho từng bộ trang phục | [2-fullbody.md](references/2-fullbody.md) |
| **3** | **Master · Ảnh neo · SF con** cho từng scene | [3-master-neo-sf.md](references/3-master-neo-sf.md) |
| **4** | **Chia câu vào shot**, gán SF, chèn nhịp lặng | [4-chia-shot.md](references/4-chia-shot.md) |
| **5** | **Prompt video** và prompt nhạc | [5-prompt-video.md](references/5-prompt-video.md) |

Checklist copy được khi bắt tay một kịch bản mới:

```
Bước 1 — portrait     : [ ] liệt kê nhân vật  [ ] viết prompt  [ ] chạy ảnh
Bước 2 — full-body    : [ ] liệt kê trạng thái trang phục  [ ] viết prompt  [ ] chạy ảnh
Bước 3 — master/neo/SF: [ ] chọn địa điểm  [ ] viết prompt CẢ BA CÙNG LƯỢT
                        [ ] chạy ảnh theo thứ tự master → neo → SF con
Bước 4 — chia shot    : [ ] đếm từ  [ ] gán SF  [ ] chèn nhịp lặng  [ ] diff với script
Bước 5 — prompt video : [ ] form chuẩn  [ ] nhạc cho nhịp lặng
```

**Ba lỗi THỨ TỰ hay mắc nhất** — có bản đồ này là để tránh đúng chúng: làm take V2 khi chưa phủ
đủ OTS · dựng SF khi chưa chọn địa điểm · viết bộ SF khi chưa chốt cảm xúc tầng scene.

## Hai chế độ làm việc

**A — User làm từng phần, chat trực tiếp.** User bảo làm bước nào thì làm bước đó rồi dừng.
Riêng bước 3: **viết prompt master + neo + SF con CÙNG MỘT LƯỢT**, không chia nhỏ — vì SF con
cần biết master trông thế nào, và neo cần biết có những SF con nào. **User tự chạy ảnh**, mình
chỉ ghi prompt vào board rồi báo thứ tự chạy.

**B — User bảo "tạo hết đi".** Chạy thẳng cả 5 bước ra `sf-board.json`, không dừng giữa chừng
chờ duyệt. **Tự duyệt bằng checklist** cuối mỗi bước, và báo lại kết quả tự kiểm.

Ở cả hai chế độ: **VIẾT PROMPT có thể làm gộp, CHẠY ẢNH thì luôn tuần tự** master → neo → SF
con, vì ảnh sau đính ảnh trước làm `refs.bg`.

## LUẬT CỨNG — vi phạm là hỏng, không phải khuyến nghị

Mọi con số và điều cấm gom ở đây. File bước chỉ hướng dẫn cách làm, không đặt thêm luật — nếu
thấy file bước nói khác chỗ này, **chỗ này đúng**, và báo user để sửa file kia.

**Khung hình**
- **Tối đa 4 NHÂN VẬT được đính ref trong một SF** (8 ảnh người + 1 master). Cần hơn thì cắt bớt
  người, tách hai khung, hoặc để người thứ 5 trở đi làm quần chúng nền không đính ref. Người có
  thoại LUÔN nằm trong nhóm 4.
- **Mọi shot phải có NGƯỜI trong khung** — cả shot thoại lẫn nhịp không thoại. Khung thuần đạo
  cụ hay cận bàn tay là khung chết.
- **Người NÓI phải có mặt trong khung** của SF đó, hoặc prompt ghi rõ họ là giọng off-screen.
- **Hai người đang đối thoại thì KHÔNG BAO GIỜ dựng khung chỉ có một người.** Cận mặt một
  người thì bắt buộc là **OTS qua vai người kia** — vẫn thấy vai người còn lại trong khung.
  Khung đơn chỉ dùng khi nhân vật thật sự một mình (monologue, gọi điện, beat nội tâm).
- **Mọi nhân vật xuất hiện trong khung đều phải có ref** — kể cả người quay lưng, out nét, chỉ
  thấy vai/gáy.
- **Tối đa HAI lớp chiều sâu** trong một khung.
- **Master không làm shot** — master không có người nên không dùng làm start frame.

**Số lượng và thời lượng**
- **Số SF của một scene ≈ số phút × 4**, đếm theo SF ĐƯỢC DÙNG chứ không phải SF tồn tại.
- **Không SF nào gánh quá 3 shot.**
- **Tối đa 4 ver cho một góc** (V2, V3, V4).
- **Thời lượng: giây ≈ số từ ÷ 3.** Shot 10s cần 21-30 từ, shot 6s cần 12-18 từ. Thoại phải lấp
  gần kín, chừa tối đa 3 giây.
- **Nhịp không thoại ≈ 15% số shot có thoại**, tính trên cả phim.

**Cấu trúc dữ liệu**
- **Chuỗi tham chiếu đúng MỘT tầng**: master → ảnh neo → SF con. Sâu hơn thì ảnh gốc bị pha loãng.
- **Mỗi nhân vật chỉ có MỘT portrait** cho cả phim; mỗi bộ trang phục thêm MỘT full-body.
- **Xoá hay đổi tên SF xong phải quét shot mồ côi** — `shots[].sf` trỏ vào id đã chết sẽ hỏng khi
  render video. Quét lần cuối ngay trước khi render hàng loạt. Kiểm luôn media mồ côi trong
  `assets/` và `videos/`.

**Video**
- **MỘT CLIP = MỘT SHOT LIỀN.** Grok dựng mỗi clip từ đúng một start frame, không cắt được giữa
  chừng. Đổi góc máy, đổi cỡ cảnh hoặc đổi địa điểm là phải một SF riêng và một shot riêng. Kịch
  bản viết sẵn hard-cut trong một clip thì **tách thành hai shot** và báo lại cho user. Mọi prompt
  video giữ nguyên câu khóa "MỘT SHOT LIỀN DUY NHẤT suốt cả video" ở footer.

**Bản đã duyệt**
- Ảnh SF `status: approved` và video `vstatus: approved` là bản user đã chốt. **Không xoá, không
  ghi đè, không crop.** Nghi sai thì báo user. Ảnh user tự dán vào là **chuẩn tuyệt đối**, kể cả
  khi độ phân giải thấp.

## Tích lũy bài học

Khi user chỉnh sửa hoặc phát hiện lỗi: sau khi sửa xong, chưng cất thành bài học **ở tầng nguyên
lý** (dùng được cho mọi phim, không nhắc chi tiết dự án cụ thể) và ghi vào
[references/bai-hoc.md](references/bai-hoc.md). Nếu bài học mâu thuẫn với một luật ở trên, **báo
user và đề xuất sửa luật** thay vì ghi chồng lên — hai chỗ đá nhau là nguồn lỗi tệ nhất.

## Tài liệu nền — đọc khi cần

- **Nguyên lý về ref, tham chiếu chéo, ngoại hình phục vụ kể chuyện** →
  [references/nguyen-ly.md](references/nguyen-ly.md)
- **Mẫu prompt Suno đã được user duyệt** → [references/mau-suno.md](references/mau-suno.md)
- **Kho bài học 45 bài** (~15k token) → [references/bai-hoc.md](references/bai-hoc.md). Chỉ mở khi
  gặp lỗi lạ muốn tra đã từng gặp chưa, hoặc cuối việc để ghi bài mới. **Đừng đọc trước mỗi lần
  viết prompt** — luật đã chưng cất lên đây rồi.
