# Tạo ảnh SF — phần kỹ thuật

> Phần dành cho người sửa code. Bản dành cho người dùng: [`SO-DO-TAO-ANH.md`](SO-DO-TAO-ANH.md).

## Các ngưỡng — chỉnh ở đâu

| Ngưỡng | Giá trị | Chỉnh ở | Cân nhắc trước khi đổi |
|---|---|---|---|
| Ảnh tối đa khi **user tích** | **không giới hạn** | — | Tích bao nhiêu gửi bấy nhiêu, luôn đúng một tin |
| Ảnh tối đa khi **máy tự gom** | **10** | `sfboard/hangdoi.py` · `TRAN_MAY_TU_GOM` | Chỉ áp cho auto quét và người gác — để máy đừng tự dồn cả scene vào một tin khi không ai nhìn |
| Lệch bao nhiêu ảnh thì vẫn giữ | **2** | `sfboard/sfboard.py` · `PL_LECH_TOI_DA` | Nới rộng = ít gửi lại hơn nhưng phải chọn tay nhiều hơn |
| Số lần gửi lại cả tin | **3** | `sfboard/sfboard.py`, tìm `_gr = "GR:"` | Tăng = tốn lượt; giảm = tách chạy lẻ sớm |
| Giữ bao nhiêu lượt trong hộp chờ | **40** | `sfboard/sfboard.py` · `PL_GIU_TOI_DA` | Giữ nhiều tốn đĩa, ít thì mất chỗ dịch ảnh sang thẻ khác |
| Giây trang phải yên trước khi chốt thứ tự | **25** | `image_chatgpt.py`, tìm `YEN = 25.0` | Giảm là gắn ảnh lộn thẻ |
| Hạn tổng chờ một lượt | **300s** | `image_chatgpt.py` · `gen_timeout` | |
| Tab tối đa một tài khoản | **6** | `sfboard/sfboard.py` · `MAX_TABS` | Mỗi tab thêm là thêm RAM; nhiều tab **không** nhân được hạn mức |
| Người gác quét mỗi | **30s** | `sfboard/sfboard.py` · `_gac_hang_doi` | |
| Ref nặng hơn thì thu nhỏ | **1200 KB / cạnh 1600** | `image_chatgpt.py` · `_REF_TRAN_KB`, `_REF_CANH_MAX` | |

## Chỉnh hành vi — tra ở đây

| Muốn đổi | Sửa ở |
|---|---|
| Thứ tự chạy trong hàng đợi | `hangdoi.py` · `uu_tien()` / `thu_tu_shot()` |
| Luật "một lần một địa điểm" | `sfboard.py` · `_lan_dia_diem()` |
| Trần khi máy tự gom | `sfboard/hangdoi.py` · `TRAN_MAY_TU_GOM` |
| Nút "Tạo ảnh đã chọn" và thanh chọn | `ui/board.js` · `loChay()`, `veLoBar()` |
| Cổng chặn "thẻ địa điểm phải có ảnh trước" | `sfboard.py` · `_cong_master()` |
| Xử lý khi số ảnh lệch | `sfboard.py` · `_generate_lo_ruot()`, đoạn "LƯỢT LỆCH" |
| Cứu việc rơi khỏi hàng | `sfboard.py` · `_gac_hang_doi()` |
| Nhận diện lỗi hết lượt / tab chết | `sfboard.py` · `_is_quota_error()`, `_is_dead_session_error()` |
| Selector, mọi đoạn JS chạy trong trang (ChatGPT) | `grokpipe/executors/dom_chatgpt.py` |
| Selector và JS của **Grok** | `grokpipe/executors/dom_grok.py` (tách 2026-08-12) |
| Cách đính ref, gửi prompt, chờ ảnh | `image_chatgpt.py` · `generate_lo()` |
| Gắn ảnh từ hộp chờ vào thẻ | `sfboard.py` · `_pl_gan()`, route `/api/gan-anh`, `/api/luot`, `/pl/…` |
| Dải ảnh chờ trên thẻ | `ui/board.js` · `luotStrip()`, `coAnhCho()` |
| Hộp lỗi 🐞 | `sfboard.py` · `_ThuLoi`, `LOI_SO` · `ui/board.js` · `veLoi()` |
| Ghi log mỗi khi một việc chuyển sang lỗi | `hangdoi.py` · lớp `_Jobs` (một chỗ cho tất cả các nhánh) |
| Giao diện hàng đợi | `sfboard/ui/board.js`, `board.css` |

## Soi hàng đợi bằng API

```bash
curl -s http://localhost:8782/api/chan-doan | python3 -m json.tool
```

| Trường | Đọc thế nào |
|---|---|
| `hang_doi.anh` | Số việc **thật** trong hàng. Lệch với số "chờ" trên giao diện = có việc mồ côi |
| `tho` | `cổng·loại·slot: true` = thợ còn sống |
| `chet` | Tài khoản bị đánh dấu chết và lý do |
| `lo_dang_hoan` | Việc nào đang phải thử lại, và bao nhiêu lần |
| `da_huy` | Việc user đã huỷ |
| `dung_gen` | Số lần đã bấm "Dừng tất cả" |

**Đứng im mà `tho` đủ và `chet` rỗng** → nghi việc mồ côi: nhãn "chờ" còn mà hàng đợi
rỗng. Người gác sẽ cứu trong 30 giây; không cứu được thì bấm chạy lại.

## Vài điểm dễ hỏng đã trả giá

- **Đính ĐỦ ref mỗi lần.** Chat trắng thì model không có trí nhớ gì; thiếu ref là nó tự
  bịa mặt và trang phục — hỏng câm. Mỗi nhân vật cần cả `_PORTRAIT` (neo mặt) lẫn
  `_FULL` (neo trang phục).
- **Phải chờ trang yên liên tục 25 giây** rồi mới đọc thứ tự ảnh. Đủ ảnh + hết nút stop
  vẫn chưa xong: lúc ChatGPT đang chốt lượt, thumbnail còn sắp xếp lộn xộn. Đọc sớm là
  gắn ảnh lộn thẻ.
- **Không tin phép đếm 300 giây**: nút Stop không tồn tại xuyên suốt lúc ChatGPT nghĩ
  ngầm. Im lặng lâu mà không có chữ từ chối rõ ràng thì vẫn chờ tiếp.
- **Thứ tự lấy từ DOM, số lượng lấy từ mạng.** Sự kiện mạng bắn lúc ảnh TẢI XONG chứ
  không phải lúc vẽ xong — ảnh nhẹ về trước ảnh nặng, nên thứ tự mạng là thứ tự kích
  thước file, không phải thứ tự khung hình.
- **Thừa id thì KHÔNG đoán.** ChatGPT thi thoảng vẽ thêm một biến thể ngoài số prompt đã
  xin, và nó có thể nằm ở giữa — cắt "N id cuối" là cả lô lệch một nấc.
- **Hàng đợi xếp theo `shots[]`, không suy từ tên SF.** Suy từ tên thì mọi thẻ có hậu tố
  chữ (`SF-S3-B1`) rơi xuống cuối.
