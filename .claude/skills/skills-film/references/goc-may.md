# Bộ góc máy và logic không gian

## Mục lục
- Bộ góc máy (coverage) của một scene
- LOGIC KHÔNG GIAN LIÊN TỤC — quy tắc bắt buộc khi chọn SF

## Bộ góc máy (coverage) của một scene

Checklist ở trên là cho TỪNG prompt; mục này là cho CẢ BỘ SF của một scene — quyết định cần
bao nhiêu góc và những loại góc nào trước khi viết từng cái.

**Bộ khung chuẩn** (hầu hết scene hội thoại đều cần): 1 master + cặp shot/reverse-shot cho hai
phía đối thoại + góc riêng cho beat chuyển trạng thái (ngồi sụp, đứng dậy, bước ra cửa...).

**KHÔNG dùng SF insert thuần đạo cụ — khung không có người là khung chết.**
Cận cảnh một tờ giấy, một màn hình, một nồi thức ăn thì trông rất "có nghề" khi đứng yên, nhưng
khi thành clip 10s thì nó không có gương mặt, không có lip-sync, không có cảm xúc — chỉ
là một vật thể nằm im trong khi giọng nói vọng đâu đó ngoài khung. Người xem rơi ra khỏi câu
chuyện ngay lập tức.

**NHỊP KHÔNG THOẠI CŨNG VẬY — không có ngoại lệ.** Clip im lặng vẫn phải có **người trong
khung**: cảm xúc nằm trên gương mặt và dáng người, không nằm ở đồ vật. Một khung cận bàn tay
hay cận đạo cụ dù đẹp vẫn là khung chết — khán giả muốn thấy mặt người, kể cả khi không ai nói.

Muốn nhấn một đạo cụ trong nhịp lặng thì **để nó trong khung có người**: người cầm nó, nhìn nó,
đặt nó xuống — thấy cả vật lẫn phản ứng. Đừng tách thành khung riêng chỉ có bàn tay và vật.

**Đạo cụ quan trọng thì đưa VÀO khung có người, đừng tách ra khung riêng.** Muốn nhấn tờ giấy
được đẩy qua bàn thì để hành động đó diễn ra trong một khung đã có sẵn cả hai người — vừa giữ
được đạo cụ, vừa giữ được phản ứng.

**Và trước khi tạo SF mới cho một đạo cụ/hành động, kiểm tra xem MASTER hoặc một góc rộng đã có
sẵn có kham được không — thường là có.** Master đã chứa toàn bộ bàn làm việc, đạo cụ trên bàn và
cả hai nhân vật; một hành động như "chỉ vào màn hình", "đẩy tờ giấy", "với lấy chiếc cốc" hoàn
toàn diễn ra được ngay trong khung đó, chỉ cần mô tả ở PROMPT VIDEO. Việc dựng thêm một SF riêng
cho từng chi tiết nhỏ (một SF cho màn hình, một SF cho tờ giấy) là phức tạp hóa: tốn thêm ảnh
phải render và duyệt, thêm rủi ro lệch continuity, mà không được gì hơn so với việc tái dùng
master. Quy tắc: **SF mới chỉ dựng khi cần một CỠ CẢNH hoặc GÓC NHÌN mà các SF sẵn có không có
(cận để thấy biểu cảm, đảo phía để shot/reverse, đổi tư thế ngồi/đứng) — không dựng SF mới chỉ
vì có thêm một hành động hay một đạo cụ mới trong cùng bố cục.**

Vì mặc định khung phải có từ 2 người (xem mục "Chia câu vào shot"), bộ góc của một scene hội
thoại chủ yếu gồm các biến thể HAI NGƯỜI: master, two-shot thẳng, two-shot 3/4 lệch 45°,
two-shot cận, và các góc OTS qua vai từng phía. Góc đơn chỉ thêm khi scene có monologue dài
hoặc beat một mình.

**TỈ LỆ SỐ SF THEO THỜI LƯỢNG — CÔNG THỨC CỨNG USER ĐÃ CHỐT (2026-07-30):**

> **Số SF của một scene ≈ số phút × 4 (làm tròn lên) — tức cứ 15 giây phim ≈ 1 SF.**
> - Sàn tối thiểu **5 SF** cho cảnh ~1 phút: master + cặp shot/reverse + 1 góc chuyển trạng thái
> - **Không SF nào gánh quá 3 shot** (SF xuất hiện quá ~30s màn hình là khán giả thấy lặp)
> - Cảnh trên 3 phút: trong số SF phải có **ít nhất 2 góc rộng/3-4** để làm góc thở, không chỉ
>   toàn cận
> - **Mọi shot đều phải có người trong khung** — cả shot thoại lẫn nhịp không thoại. Khung
>   cận tay / cận vật thể là "không hay lắm" ngay cả khi hình đẹp; đạo cụ muốn nhấn thì đặt
>   vào khung đã có người

Cách thi hành khi chia shot: gán SF theo GIAI ĐOẠN KHÔNG GIAN tuần tự (shot không lùi về SF của
giai đoạn trước), trong mỗi giai đoạn luân phiên và ưu tiên SF ít dùng, người nói phải có mặt
trong khung.

**Khi góc máy đã cạn mà cảnh còn dài — dùng TAKE 2 của cùng góc (user chốt 2026-07-30).**
"Cạn góc" nghĩa là đã XOAY HẾT các hướng khả dĩ trong bối cảnh đó (xem "Một master = cả
căn phòng" trong SKILL.md), không phải mới dùng 3 góc quen thuộc. Take V2: không
cần bịa thêm góc mới gượng ép; tạo `<SF-ID>-V2` là CHÍNH GÓC ĐÓ render lại — giữ nguyên bố cục,
cỡ cảnh, trục máy, chỉ để vi sai tự nhiên về tư thế/ánh mắt/nhịp cơ thể giữa hai lần render. Ví
dụ medium v2, OTS v2 — và được phép lên V3, V4 khi cảnh rất dài, nhưng **TỐI ĐA 4 VER cho một
góc**. Trong prompt V2+ ghi rõ: "đây là TAKE THỨ <n> của cùng một góc máy — giữ nguyên toàn bộ
bố cục và góc, chỉ thay đổi vi mô tư thế và biểu cảm cho tự nhiên". Mỗi ver tính là một SF riêng
khi đếm theo công thức phút × 4; một 'góc' 4 ver gánh được tới ~8-10 shot mà không shot nào phải
dùng lại đúng một frame.

**Loại góc bổ sung nên nằm trong VÙNG AN TOÀN** — đa dạng nhưng không cực đoan:
- Medium 3/4: camera lệch ~45° khỏi trục nhìn của nhân vật, thấy 3/4 gương mặt, cỡ trung
  (thắt lưng trở lên) — không quá cận, không quá rộng. Đây là góc bổ sung giá trị nhất cho
  hội thoại dài.
- CU chặt hơn một nấc so với MCU sẵn có, dành cho đúng 1-2 câu thoại đắt nhất của cảnh.
- Two-shot nghiêng từ đầu bàn/cạnh không gian: thấy cả hai profile, dùng đổi nhịp giữa các
  đợt shot/reverse.
- TUYỆT ĐỐI TRÁNH góc cực đoan: bird's-eye thẳng đứng, dutch angle mạnh, fisheye, extreme
  close-up chỉ có mắt/môi, góc từ dưới cằm hắt lên. Chúng phá tông hiện thực của thể loại.
- Mọi góc bổ sung vẫn phải khóa look từ master và tôn trọng trục 180°.

**Hai giới hạn cứng khi THIẾT KẾ một khung — vi phạm là ảnh hỏng dù prompt viết hay:**
- **Không dựng SF ở tư thế GIỮA chuyển động** (đang lao người, giữa sải nhảy, giữa cú vung tay).
  Model vẽ tốt khoảnh khắc TRƯỚC (dợm, quyết định) và SAU (đã tới, đã chạm) nhưng gần như luôn
  hỏng khoảnh khắc GIỮA. Chọn một trong hai vùng an toàn; chuyển động thật để prompt video lo.
  Cách né sang trọng nhất: kể bằng DẤU VẾT — thứ bị bỏ lại trong khi nhân vật đã ở nơi khác.
  Khoảnh khắc quan trọng mà khó render thì đưa NHIỀU phương án khác chiến lược cho user chọn
  (bài học 43).
- **Tối đa HAI lớp chiều sâu trong một khung.** Đòi lớp thứ ba (một người ở rất xa, không gian
  khác ở cuối hành lang) là ép model lùi camera lên góc cao/toàn cảnh để "nhét cho vừa" — đúng
  loại góc cực đoan bị cấm ở trên. Lớp thứ ba tách thành SF riêng. Và khi cần một khoảng trống
  mang nghĩa "ai đó vừa rời đi", mô tả thuần bằng cái CÒN LẠI ("khoảng sàn trống, sạch"), tuyệt
  đối không nhắc tới người đã đi trong câu tả — câu phủ định không xóa được hình ảnh mà chính
  mình vừa gieo (bài học 41).

**Cảnh đông người (3+ nhân vật cùng có mặt) cần THÊM 1-2 GÓC RỘNG VỪA lấy đủ cả nhóm** — nhỏ hơn
master một nấc nhưng chưa phải cận. Đây là tầng hay bị bỏ sót nhất: nếu chỉ có master (rất rộng)
rồi nhảy thẳng xuống two-shot/cận, cả scene chỉ có đúng MỘT khung thấy được cả nhóm, và khung đó
lại quá rộng để đọc biểu cảm. Góc rộng vừa lấp đúng chỗ trống đó: nhân vật to hơn hẳn master
(cắt bớt trần và rìa phòng) nhưng vẫn đủ cả 3 người và vẫn đọc được mặt.

Hai biến thể nên có:
- **Rộng vừa thẳng**: cùng hướng với master, chỉ tiến camera gần hơn một nấc.
- **Rộng vừa qua vai**: một nhân vật làm tiền cảnh mềm (thấy đầu/vai), hai người còn lại là chủ
  thể nét rõ. Khung này đắt vì vừa lấy đủ nhóm vừa tạo được lớp chiều sâu — và khi nhân vật tiền
  cảnh là người đang IM LẶNG nghe (một đứa trẻ, một người bị nói về), sự hiện diện đó làm khung
  nặng hơn hẳn một two-shot thường.

Vẫn giữ đủ phổ ba tầng: toàn thể (master) → **rộng vừa cả nhóm** → two-shot/cận đơn.

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
