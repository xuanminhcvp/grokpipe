# Bước 4 — Chia câu vào shot và gán SF

## Mục lục
- Làm gì ở bước này
- Chia câu vào shot
- Logic không gian liên tục khi chọn SF
- Viết và tinh chỉnh thoại nhân vật chính
- Kiểm trước khi sang bước 5

## Làm gì ở bước này

Cắt `script` của scene thành các shot, mỗi shot một clip video. Gán SF cho từng shot theo
giai đoạn không gian. Chèn nhịp không thoại.

## Chia câu vào shot (mỗi shot = một clip video)

**Thời lượng chuẩn: ~90% số shot dài 10s, chỉ thỉnh thoảng mới dùng 6s.** Đừng chia vụn 3-5s —
vừa nhiều clip phải dựng, vừa cắt liên tục gây mệt mắt. 6s chỉ dành cho câu lẻ thật ngắn hoặc
nhịp chuyển; mặc định luôn là 10s.

**Mỗi shot chứa 2-4 LƯỢT THOẠI (tối đa 4), không phải một câu rồi để trống.** Một câu 5-7 từ chỉ
lấp được 2 giây, còn 8 giây nhân vật đứng im — video đọc ra ngay là bị kéo dài. Cách làm đúng:
gộp trọn một lượt qua lại tự nhiên (A nói → B đáp → A đáp lại → B đáp) vào cùng một shot.

**TẬN DỤNG HẾT SỐ GIÂY: thoại phải lấp gần kín thời lượng, chỉ chừa 1-2 giây, tối đa 3 giây.**
Đây là bước tính bắt buộc trước khi chốt cách chia, không phải kiểm tra cho có:

- Công thức board đang dùng: **giây ≈ số từ ÷ 3**. Suy ra **shot 10s cần 21-30 từ**, **shot 6s
  cần 12-18 từ**. Đếm từ của cụm thoại định gộp rồi mới quyết định gộp mấy câu và chọn 6s hay 10s.
- Thừa quá 3 giây ⟹ gộp thêm câu kế vào, hoặc hạ 10s xuống 6s.
- Vượt quá thời lượng ⟹ tách bớt câu sang shot sau. Chấp nhận tràn tối đa ~0,5s (model đọc nhanh
  chậm chênh nhau chút), nhưng đừng cắt một câu làm đôi giữa chừng chỉ để cho vừa số giây.
- Một câu quá dài (trên 30 từ) thì tách thành hai shot của cùng người nói, cắt ở ranh giới mệnh đề
  tự nhiên, đổi góc giữa chừng — miễn ghép lại không mất chữ nào so với kịch bản.

Ưu tiên khi hai chuẩn xung đột: **lấp kín thời lượng thắng tỷ lệ 10s/6s**. Nếu một cụm thoại chỉ
đủ cho 6s thì dùng 6s, đừng ép lên 10s rồi để trống 4 giây.

**Quy tắc cứng: người NÓI trong một shot phải CÓ MẶT trong khung của SF đó.** Mỗi shot thành một
clip có lip-sync; nếu lời thoại thuộc về ai đó không có trong khung, model dựng video sẽ gán
khẩu hình sai cho người đang thấy.
- **SF hai người trở lên (master, two-shot, OTS qua vai)** → hai người đối đáp trong cùng clip là
  HỢP LỆ, vì cả hai đều trong khung. Đây chính là cách gộp 2-3 lượt thoại cho đủ 10s.
- **SF đơn nhân vật** → chỉ người đó được nói, nên chỉ chứa được một lượt thoại. Xem quy tắc dưới.
- **SF insert không thấy mặt ai** → về mặt lip-sync thì thoại của ai cũng được, nhưng ĐỪNG DÙNG
  loại SF này (xem mục "Bộ góc máy"): khung không người là khung chết khi thành video.

**MẶC ĐỊNH: khung phải có TỪ 2 NGƯỜI TRỞ LÊN. SF chỉ có một nhân vật là ngoại lệ, không phải
lựa chọn thường dùng.** Lý do gắn liền với hai chuẩn trên: shot 10s cần 2-3 lượt thoại, mà muốn
hai người đối đáp trong một clip thì cả hai phải cùng trong khung. Khung một người vừa buộc phải
cắt vụn thoại, vừa mất phản ứng của người nghe, vừa xem chán.
- **Chú ý: góc 3/4 KHÔNG đồng nghĩa với khung một người.** Cái cần là *medium 3/4 hai người* —
  camera lệch ~45° nhưng vẫn ôm trọn cả hai nhân vật. Đừng dựng "3/4 mà chỉ có một người".
- **OTS (qua vai) tính là khung hai người** — một người rõ mặt, người kia làm foreground framing.
  Đây là cách rẻ nhất để có khung hai người mà vẫn nhấn được vào một gương mặt.
- SF thật sự đơn (không có ai khác trong khung) chỉ dùng cho: monologue dài một người nói liên
  tục gần trọn 10s, hoặc beat nội tâm không có ai đối thoại (nhân vật một mình, quay lưng bước
  ra). Ngoài hai trường hợp đó, luôn chọn khung hai người.

Câu thoại quá dài có thể tách làm hai shot của cùng một người, đổi góc giữa chừng — miễn không
mất chữ nào so với kịch bản gốc.

**Sau MỖI vòng gộp/tách/viết lại shot, chạy diff bằng máy so text các shot với script gốc** —
chuẩn hóa rồi kiểm từng dòng gốc còn xuất hiện không. Sửa vòng thứ hai, thứ ba là lúc câu gốc
rơi mất không ai hay; trí nhớ không bắt được lỗi này, script 10 dòng thì bắt được. Câu gốc chỉ
được phép mất khi user chủ động duyệt bỏ. Các câu GIEO-TRẢ (được scene khác trích nguyên văn)
nằm trong danh sách bất khả xâm phạm, diff riêng (bài học 44).

## LOGIC KHÔNG GIAN LIÊN TỤC — quy tắc bắt buộc khi chọn SF

**SF là frame ĐẦU của clip, nên nó phải bằng đúng trạng thái KẾT THÚC của clip trước.** Cả scene
là một dòng không gian liên tục; mỗi prompt video làm thay đổi trạng thái đó, và SF kế tiếp phải
NHẬN trạng thái mới, không được quay về trạng thái cũ.

**Bốn trục phải theo dõi, theo đúng thứ tự ưu tiên:**
1. **XA / GẦN** — hai người đứng cách nhau, prompt cho tiến lại gần ⟹ SF sau phải là khung GẦN.
   Không được trả về khung xa như ban đầu.
2. **TRÊN / DƯỚI** — nhân vật bước lên thềm/bục/bậc, hoặc từ đứng chuyển sang ngồi ⟹ mọi SF sau
   phải giữ đúng cao độ mới.
3. **TRƯỚC / SAU** — ai đứng trước ai, ai đã vượt lên, ai đã lùi ra khỏi nhóm.
4. **TRÁI / PHẢI** — trục 180° (đã nói ở các mục trên).

**Khi viết mỗi SF, PHẢI ghi rõ trạng thái không gian vào phần mô tả**, không chỉ tả cỡ cảnh: ai
đứng/ngồi, cách nhau bao xa, ai cao hơn ai, đã bước qua ranh giới nào chưa. Đây là dữ liệu để đối
chiếu giữa các shot — thiếu nó thì không cách nào phát hiện lệch.

**Lỗi kinh điển phải tự bắt: SF đã ở trạng thái SAU hành động, nhưng prompt video lại bắt nhân vật
làm lại hành động đó.** Ví dụ SF vẽ "đã ngồi xuống ghế" mà prompt viết "bà ngồi xuống ghế" — clip
sẽ có người ngồi hai lần, hoặc model tự dựng lại cảnh đứng lên rồi ngồi. Cách sửa luôn giống nhau:
**đẩy hành động chuyển trạng thái về CUỐI clip TRƯỚC** (nơi SF vẫn còn ở trạng thái cũ), rồi clip
sau mở đầu bằng câu xác nhận trạng thái đã xong — "đã đứng trên thềm (đúng như frame tham chiếu)",
"đã ngồi yên trên sofa (đúng như frame tham chiếu)".

Quy trình rà: sau khi chốt SF cho cả scene, đọc tuần tự từ shot 1 tới shot cuối và ghi ra trạng
thái không gian ở CUỐI mỗi clip, rồi so với trạng thái ở ĐẦU clip kế. Chỗ nào lệch thì hoặc chèn
nhịp chuyển, hoặc đẩy hành động sang clip trước.

**Rà VỊ TRÍ NHÂN VẬT giữa hai shot liền nhau — đổi chỗ mà không có nhịp chuyển là video bị khựng.**
SF là ảnh TĨNH quyết định vị trí đầu clip, nên nếu shot trước kết thúc với nhân vật ở chỗ A mà
shot sau bắt đầu với họ đã ở chỗ B, người xem thấy họ "nhảy" tức thì. Sau khi chốt SF cho từng
shot, duyệt các cặp liền nhau và hỏi: **ai đổi chỗ giữa hai khung này?**

Ba cách xử lý, chọn theo mức độ:
1. **Chèn một shot CHUYỂN** khi khoảng cách xa hoặc đổi khu vực (từ bếp ra bàn, từ phòng này sang
   phòng kia). Dùng khung rộng đủ thấy trọn đường đi, và cho SF của shot chuyển là **vị trí XUẤT
   PHÁT** (khớp với cuối shot trước), rồi mô tả trong prompt việc nhân vật di chuyển tới vị trí
   mới, kết thúc clip đúng ở bố cục của shot kế tiếp.
2. **Cho nhân vật vừa đi vừa nói** — tận dụng luôn một câu thoại ngắn (thường là câu mở đầu của
   lượt kế) làm lời cho nhịp chuyển, khỏi tốn một shot câm.
3. **Mô tả bước di chuyển ở CUỐI prompt shot trước** ("nói xong, cô quay người bước về phía quầy
   bếp — clip kết thúc khi cô đã tới sát quầy") nếu quãng đường ngắn và cùng khung. Cách rẻ nhất,
   dùng cho các dịch chuyển nhỏ.

**Shot chuyển được MIỄN quy tắc lấp kín thời lượng.** Nội dung chính của nó là HÀNH ĐỘNG di
chuyển chứ không phải lời thoại, nên một shot 6s chỉ có 3-5 từ là hoàn toàn hợp lệ — thời gian
còn lại dành cho việc nhân vật đi, kéo ghế, ngồi xuống. Đừng cố nhồi thoại vào cho "đủ giây".

**Rà thoại tìm câu KHÔNG cùng không gian/thời điểm với phần còn lại của cảnh.** Không phải mọi
dòng trong một scene đều diễn ra ở cùng một chỗ và cùng một lúc. Các dạng hay gặp:
- **Câu gọi/triệu tập** ("Vào phòng tôi ngay", "Ra đây") — xảy ra TRƯỚC khi hai người đối diện
  nhau, ở một không gian khác (cửa phòng, đầu hành lang).
- **Thoại qua thiết bị** — điện thoại, bộ đàm, loa nội bộ: người nói không có mặt trong khung.
- **Thoại vọng từ xa** — nhân vật gọi với sang khu vực khác.

Nhét những câu này vào master (nơi mọi người đã tụ lại đối thoại trực tiếp) là sai không gian —
hình và lời đá nhau. Xử lý: **tách thành SF riêng cho đúng khoảnh khắc đó**. Với câu gọi/triệu
tập, SF riêng này thường kiêm luôn vai trò **cầu nối chuyển cảnh** giữa scene trước và scene sau
(nhân vật đứng ở khung cửa, một nửa thuộc không gian cũ một nửa thuộc không gian mới) — vừa đúng
logic vừa được thêm một nhịp hình đẹp. SF loại này cần đính ảnh tham chiếu của CẢ HAI không gian
và ghi rõ ảnh nào dùng cho phần nào (nguyên lý 3).

Nếu không muốn thêm SF, hai lựa chọn còn lại: chuyển câu đó thành giọng ngoài khung trên một SF
insert, hoặc bỏ/đổi thoại. Nhưng thường tách SF là phương án cho chất lượng cao nhất.

## Viết và tinh chỉnh thoại nhân vật chính — khiêm tốn là quy tắc cứng

Khi tự viết thêm hoặc sửa thoại (user cho phép "sửa cho hay"), nhân vật chính lúc làm việc tốt
phải KHIÊM TỐN: không nói lố, không nói thừa, không khoe mẽ — người tốt thật không thuyết minh
việc tốt của mình.

- **Cắt thẳng tay hai loại câu**: giải thích động cơ ("tôi giúp vì tôi từng thấy...") và tuyên
  bố phẩm chất/lời hứa ("I'm not going anywhere", "Not while I'm here" lặp nhiều lần). Nội dung
  câu nào là "tôi tốt / tôi sẽ tốt / lý do tôi tốt" → ứng viên cắt đầu tiên.
- **Người thật lòng giúp thì HỎI và LÀM**: thay câu hay bằng câu ngắn + hành động kế tiếp.
  "Why are you helping me?" → "You needed help." rồi lảng ngay sang việc thực tế.
- **Trước lời cảm ơn nặng, phản ứng chân thành nhất là NÉ hoặc HẠ THẤP**: lúng túng, "It's just
  juice, ma'am." — sự vụng về khi được cảm ơn thuyết phục hơn mọi câu đáp trôi chảy.
- **Ngoại lệ hợp lệ — thoại TRẤN AN**: "I've got you. I'm right here" nói MỘT LẦN, đúng lúc
  chạm vào người đang hoảng, là kỹ năng sơ cứu chứ không phải kể công. Thành lố khi lặp lại
  hoặc tách rời khỏi hành động chạm/đỡ cụ thể.
- **Đức tính thể hiện bằng hành động KHÔNG AI CHỨNG KIẾN**, không bằng lời — một nhịp không
  thoại (lặng lẽ trả tiền, không ngẩng lên xem ai thấy) nói được điều mà thoại tự nói ra sẽ
  làm hỏng. Xem bài học 42.

## Kịch bản viết sẵn hard-cut trong một clip — cách xử lý

Luật gốc ở `SKILL.md` (MỘT CLIP = MỘT SHOT LIỀN). Đây là quy trình thi hành:

**Tình huống hay gặp nhất: kịch bản viết sẵn một hard-cut bên trong một clip** — dạng
*"CLIP 8 — 10 GIÂY · 0–5s: hai người dưới sàn · 5–10s: hard cut sang tủ mát"*. Đừng cố dựng
nguyên si. Cách xử lý duy nhất đúng:
1. **Tách thành hai shot**, mỗi shot một SF riêng đúng với không gian của nó.
2. Chia lại thời lượng theo lượng thoại của từng nửa (thường 6s + 6s, không phải cố giữ tổng 10s).
3. Thoại nằm ở nửa nào thì ở nguyên shot đó; nửa không thoại viết theo form nhịp không thoại.
4. **Báo lại cho user rằng đã tách và vì sao** — họ viết kịch bản theo lối dựng phim thật, nơi
   hard-cut là chuyện bình thường; giới hạn nằm ở công cụ, nên đây là thông tin họ cần biết chứ
   không phải chuyện tự ý sửa kịch bản.

Kiểm tra trước khi render: quét prompt tìm "hard cut", "cắt sang", "0–5 giây / 5–10 giây" — còn
sót chữ nào là còn một clip sẽ hỏng. Và mọi prompt video đều phải giữ nguyên câu khóa
"MỘT SHOT LIỀN DUY NHẤT suốt cả video" ở footer.

## Kiểm trước khi sang bước 5

- [ ] Diff bằng máy: mọi câu trong `script` còn nguyên trong các shot
- [ ] Mọi shot lệch thời lượng ≤3 giây
- [ ] Không SF nào gánh quá 3 shot
- [ ] Người nói đều có mặt trong khung, hoặc prompt ghi rõ off-screen
- [ ] Không shot nào tụt về SF của giai đoạn không gian trước
