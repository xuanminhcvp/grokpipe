# Thiết kế gộp lô và điều hướng REF

## Bối cảnh

Nút **Chạy hết** của scene `REF` hiện dùng `_nhom_cua()` để chia mọi thẻ theo
từng nhân vật. Ở vòng đầu, mỗi nhân vật thường chỉ có một portrait sẵn sàng nên
board tạo nhiều job `LO:` một ảnh. Cách này đúng thứ tự phụ thuộc nhưng không đạt
kỳ vọng “chạy hết theo lô”. Giao diện cũng đang trình bày toàn bộ 67 REF trong
một khối và sidebar chỉ có một dòng `REF`, khiến nhân vật, đạo cụ và bối cảnh khó
quét nhanh.

Production authority vẫn là legacy `JOBS`, `IMG_QUEUE`, `_auto_scene()` và
`_generate_lo_ruot()`. Thay đổi này không tạo writer, retry hay re-enqueue
authority mới.

## Mục tiêu

- Gom các REF độc lập thành lô tối đa theo `TRAN_MAY_TU_GOM` và `TRAN_REF`.
- Giữ portrait chạy trước mọi `_FULL` đang phụ thuộc vào portrait đó.
- Giữ riêng `_FULL` của bốn nhân vật chính; gom `_FULL` của nhân vật phụ.
- Chia nội dung REF thành **Nhân vật**, **Đạo cụ** và **Bối cảnh**.
- Sidebar giữ dòng cha `REF` và thêm ba dòng con có tiến độ riêng.
- Không tự chạy provider trong test hoặc trong bước triển khai.

## Phân loại REF

Phân loại chỉ dựa trên ID hiện có, không thêm schema vào `sf-board.json`:

- **Nhân vật:** ID kết thúc bằng `_PORTRAIT` hoặc `_FULL`.
- **Đạo cụ:** ID bắt đầu bằng `REF_PROP_`.
- **Bối cảnh:** mọi thẻ còn lại trong scene `REF`.

Thứ tự nhân vật lấy theo thứ tự xuất hiện của các thẻ `*_PORTRAIT` trong scene
`REF`. Bốn portrait đầu là nhân vật chính; từ portrait thứ năm trở đi là nhân vật
phụ. `_FULL` được gắn về nhân vật qua tiền tố `REF_<TÊN>_` như logic hiện tại.

## Thiết kế chia lô

`_auto_scene()` tiếp tục là nơi duy nhất quyết định enqueue. Bước xác định “sẵn
sàng” hiện tại vẫn giữ nguyên: một thẻ chỉ được xếp khi toàn bộ `refs.bg` và
`refs.chars` của nó đã có file.

Khóa nhóm cho scene REF được tính như sau:

1. Portrait độc lập dùng chung khóa `REF:PORTRAIT`, vì chúng chưa cần ảnh ref và
   có thể sinh chung một tin.
2. `_FULL` của bốn nhân vật chính dùng khóa `NV:<TÊN>` như hiện tại.
3. `_FULL` của nhân vật từ thứ năm dùng chung khóa `NV:PHU`.
4. Đạo cụ dùng khóa `PROP`.
5. Bối cảnh dùng khóa `REF:BOI_CANH`.

Mỗi nhóm tiếp tục đi qua `_chia_lo()`, do đó vẫn bị cắt khi đạt trần số ảnh,
trần ref hoặc gặp quan hệ phụ thuộc nội bộ. Portrait và `_FULL` không thể lọt
vào cùng vòng đầu: `_FULL` chưa sẵn sàng khi portrait chưa có file. Ở vòng sau,
`_FULL` chỉ được gom khi portrait của chính nó đã tồn tại.

Luồng stop-generation, `AUTO_LOCK`, trạng thái `JOBS` và định dạng queue item
`("img", "LO:" + ids, 0, False)` không thay đổi.

## Thiết kế giao diện REF

### Nội dung chính

Scene REF có ba section có anchor ổn định:

- `ref-nhan-vat`: nhóm các thẻ nhân vật.
- `ref-dao-cu`: lưới thẻ đạo cụ.
- `ref-boi-canh`: lưới thẻ bối cảnh.

Section Nhân vật giữ mẫu portrait làm thẻ chính và dải `_FULL` hiện tại. Bốn
nhân vật đầu có nhãn nhỏ **Chính**; các nhân vật còn lại có nhãn **Phụ**. Mỗi
section hiển thị số đã có ảnh trên tổng số và số đã duyệt trên tổng số. Section
rỗng không được render.

### Sidebar

Dòng cha `REF` vẫn ở cùng cấp với `S1`, `S2` và hiển thị tiến độ tổng như hiện
tại. Ngay dưới nó là ba dòng con thụt vào:

- `Nhân vật`
- `Đạo cụ`
- `Bối cảnh`

Mỗi dòng con hiển thị hai tỷ lệ: đã có ảnh và đã duyệt. Bấm dòng con cuộn tới
anchor tương ứng; dòng cha cuộn tới đầu scene REF. Dòng con dùng phần tử có thể
focus bằng bàn phím, có nhãn truy cập rõ ràng và trạng thái focus nhìn thấy.
Sidebar vẫn dùng một cây DOM cho desktop/responsive, không nhân đôi nội dung ở
breakpoint khác. Z-index và khoảng bù của sidebar giữ theo hệ hiện tại để không
che nội dung.

## Kiểm thử

### Backend regression

- Ba portrait độc lập phải tạo đúng một queue item `LO:` chứa cả ba ID.
- `_FULL` không được enqueue trước portrait phụ thuộc.
- Khi portrait đã có file, `_FULL` của bốn nhân vật đầu vẫn chia theo từng người.
- Khi portrait đã có file, `_FULL` của nhân vật thứ năm trở đi được gom chung.
- Lô phụ vẫn tôn trọng `TRAN_MAY_TU_GOM`, `TRAN_REF` và không enqueue trùng.
- Test stop-generation và full lifecycle gate hiện có phải tiếp tục qua.

### UI verification

- REF render đúng ba section theo quy tắc ID.
- Sidebar REF có đúng ba dòng con và tỷ lệ của từng nhóm khớp dữ liệu.
- Click và keyboard focus đưa người dùng tới đúng section.
- Kiểm tra ở chiều rộng desktop và breakpoint sidebar hiện có; không phát sinh
  cuộn ngang hoặc che nội dung.

## Triển khai và rollback

Sau khi test và compile gate qua, restart board để tiến trình Python nạp logic
mới. Không tự bấm **Chạy hết REF** vì đó là live provider và có thể tiêu credit.
Rollback chỉ cần hoàn nguyên thay đổi trong `sfboard.py`, `board.js`, `board.css`
và các regression test liên quan; không có migration dữ liệu.
