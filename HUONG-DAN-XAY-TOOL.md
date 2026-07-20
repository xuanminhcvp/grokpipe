# HƯỚNG DẪN XÂY TOOL CHẠY PIPELINE (lý thuyết, không code)

Tool đọc file pipeline (vd `PIPELINE-BANHMI-VID001-028.txt`) và tự động chạy toàn bộ
chuỗi: tạo ảnh → tạo video → cắt frame → tạo video tiếp theo, đến hết file.

## 1. Kiến trúc tổng thể

```
File pipeline (.txt)
      │
      ▼
 [1] PARSER ──────► danh sách task theo thứ tự
      │
      ▼
 [2] BỘ CHẠY TUẦN TỰ (task runner)
      │
      ├─► TYPE=IMAGE   → [3a] Executor ảnh   (ChatGPT)
      ├─► TYPE=VIDEO   → [3b] Executor video (Grok)
      └─► TYPE=EXTRACT → [3c] Executor cắt frame (Python + AI kiểm tra)
      │
      ▼
 [4] KHO ASSET (thư mục + sổ trạng thái)
```

## 2. Parser — đọc file pipeline

- Tách task theo dòng mở đầu: dòng bắt đầu bằng `=== [T`.
  Regex ý tưởng: `=== \[(T\d+)\] (IMAGE|VIDEO|EXTRACT) -> (\S+) \| (.*) ===`
  → bắt được: TASK_ID, TYPE, OUTPUT_ID, tên gợi nhớ.
- Trong block, đọc các dòng dạng `KEY : value` (KEY viết hoa, có thể có khoảng
  trắng canh lề — trim trước khi so khớp): `BASE_IMAGE`, `REF_IMAGES`,
  `START_FRAME`, `DURATION`, `SRT_RANGE`, `SOURCE_VIDEO`, `FRAME_CẦN_CÓ`.
- Prompt là toàn bộ text giữa `--- PROMPT ---` và `--- HẾT PROMPT ---`, giữ nguyên văn.
- Mọi dòng ngoài block task (banner, mục lục, chú thích) bỏ qua khi parse.

## 3. Kho asset + sổ trạng thái (quan trọng nhất để chạy ổn định)

- Một thư mục project, file đặt tên đúng bằng OUTPUT_ID:
  `REF_ANDREA_PORTRAIT.png`, `FRM_S1_WIDE.png`, `VID_003.mp4`...
- Một file trạng thái (JSON/CSV) ghi mỗi task: `PENDING / RUNNING / DONE / FAILED`
  kèm đường dẫn kết quả.
- **Luật chạy:** task chỉ được chạy khi mọi input ID (BASE_IMAGE, REF_IMAGES,
  START_FRAME, SOURCE_VIDEO) đã có file và task tạo ra nó ở trạng thái DONE.
  Chạy tuần tự từ trên xuống là tự thỏa điều kiện này.
- **Resume:** tool khởi động lại thì đọc sổ trạng thái, bỏ qua task DONE, chạy tiếp
  từ task đầu tiên chưa xong. Không bao giờ làm lại từ đầu.

## 4. Executor ảnh (ChatGPT)

- Input: prompt + (nếu có) BASE_IMAGE và REF_IMAGES.
- Thứ tự đính ảnh khi gọi: **BASE_IMAGE trước** (ảnh nền — với keyframe), rồi đến
  các REF_IMAGES theo đúng thứ tự liệt kê. Prompt đã viết theo thứ tự này
  ("ảnh nền đính kèm", "ảnh tham chiếu thứ hai"...).
- Lưu kết quả thành `<OUTPUT_ID>.png`.
- Nên có **cổng duyệt tay (human gate)** cho ảnh: hiện ảnh ra, người bấm
  OK / Retry. Ảnh sai mặt, sai trang phục mà lọt qua sẽ hỏng cả chuỗi video sau nó
  — chặn ở đây rẻ nhất. (Có thể thay bằng AI vision tự chấm: "mặt có khớp ảnh
  tham chiếu không, trang phục đúng không, có chữ/watermark không" — nhưng
  giai đoạn đầu nên duyệt tay.)

## 5. Executor video (Grok)

- Input: file ảnh `<START_FRAME>.png` + prompt.
- Thao tác: upload ảnh làm frame khởi đầu (image-to-video), dán prompt, đặt
  thời lượng 10s, chạy, tải video về, lưu thành `<OUTPUT_ID>.mp4`.
- Kiểm tra sau khi tải: file tồn tại, thời lượng ~10s.
- Cổng duyệt tay khuyến nghị ở các video quan trọng (video có keyframe mới,
  video đỉnh cảm xúc); các video giữa chuỗi có thể để chạy thẳng rồi duyệt theo lô.
- Nếu video hỏng (sai mặt, sai bố cục, thoại chồng tiếng): chạy lại cùng prompt
  cùng frame (kết quả Grok mỗi lần mỗi khác). Giới hạn số lần retry (vd 3) rồi
  báo người xử lý.

## 6. Executor cắt frame (Python + AI kiểm tra)

Đây là bước nối hai video — frame cắt ra sẽ là frame khởi đầu của video sau,
nên chất lượng frame quyết định continuity.

**Bước 1 — Cắt ứng viên:**
- Dùng ffmpeg/OpenCV cắt frame trong khoảng **giây 7.0 → 8.0** của video nguồn
  (lúc này cú chuyển cảnh ở giây 5 đã ổn định, và còn cách đoạn cuối đủ xa).
- Cắt dày: mỗi 0.1s một frame → ~10 ảnh ứng viên.

**Bước 2 — AI vision chấm từng ứng viên (gửi ảnh cho model vision kèm checklist):**
1. **MẮT NHÂN VẬT ĐANG MỞ** và nhìn đúng hướng — đây là tiêu chí quan trọng nhất.
   Frame bắt mắt nhắm/nửa nhắm (giữa cú chớp mắt) sẽ làm video sau mở đầu bằng
   ánh mắt sai, nhân vật như vừa "giật mình mở mắt".
2. Miệng khép hoặc ở trạng thái nghỉ (không đang giữa một từ, không há nửa chừng).
3. Tay, ngón tay, đạo cụ không biến dạng, không lỗi AI.
4. Khớp mô tả `FRAME_CẦN_CÓ` của task EXTRACT (ai rõ nét, ai out nét, bố cục gì).
5. Không motion blur nặng.

**Bước 3 — Chọn và lưu:**
- Chọn ứng viên điểm cao nhất, lưu thành `<OUTPUT_ID>.png`.
- Nếu KHÔNG ứng viên nào đạt (cả 10 frame đều nhắm mắt/lỗi): nới khoảng cắt ra
  6.0 → 9.5s và thử lại một lần; vẫn không đạt → đánh dấu FAILED, báo người chọn tay.

## 7. Xử lý lỗi & nguyên tắc chung

- **Fail thì dừng nhánh, không chạy tiếp mù:** task FAILED thì mọi task phụ thuộc
  nó phải chờ — chạy tiếp với input hỏng chỉ tốn tiền sinh video sai.
- **Không ghi đè:** retry lưu thành bản mới (`VID_003_try2.mp4`), bản được duyệt
  mới gắn tên chuẩn. Giữ lịch sử để so.
- **Log mỗi task:** giờ chạy, số lần retry, ai duyệt. Khi phim dài trăm video,
  log là thứ duy nhất cho biết đang ở đâu.
- **Chi phí:** mỗi retry video là tiền thật — ưu tiên chặn lỗi ở tầng ảnh (rẻ)
  trước khi đến tầng video (đắt).
- Mở rộng về sau: các task ảnh REF độc lập nhau (T001–T011) có thể chạy song song;
  phần còn lại giữ tuần tự cho an toàn.

## 8. Tóm tắt vòng đời một video

```
FRM_X.png (đã có) ─► Grok(image-to-video, prompt) ─► VID_N.mp4
                                                        │
                              Python cắt giây 7–8 (10 ứng viên)
                                                        │
                              AI vision chấm: mắt MỞ? miệng nghỉ? tay/đạo cụ sạch?
                              khớp FRAME_CẦN_CÓ?
                                                        │
                                                   FRM_Y.png ─► video tiếp theo
```
