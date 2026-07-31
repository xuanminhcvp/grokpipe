# Bước 3 — Master, Ảnh neo, và SF con

## Mục lục
- Làm gì ở bước này
- Thứ tự VIẾT PROMPT và thứ tự CHẠY ẢNH
- Chọn địa điểm trước, rồi mới chọn góc máy
- Một master = cả căn phòng
- Cùng phòng, khác thời điểm
- Ảnh neo
- SF là trạng thái, không phải khoảnh khắc
- Ánh mắt và cảm xúc trên khuôn mặt
- Thứ tự làm SF: phủ đủ trạng thái trước
- Bộ góc máy của một scene
- Checklist bắt buộc cho từng prompt SF
- Quy tắc SF trong dữ liệu

## Làm gì ở bước này

Với mỗi scene: chọn địa điểm → dựng **master** cho từng bối cảnh → xác định các **cụm đứng
yên** để dựng **ảnh neo** → dựng **SF con** phủ đủ trạng thái và góc.

## Thứ tự VIẾT PROMPT và thứ tự CHẠY ẢNH — hai thứ khác nhau

**Viết prompt: LÀM CÙNG MỘT LƯỢT.** Master, neo và SF con viết chung một đợt, vì SF con phải
tả được "thứ thấy ở hướng đó" nên cần biết master trông thế nào; và neo phải biết cụm nào
đứng yên nên cần biết trước có những SF con nào.

**Chạy ảnh: BẮT BUỘC TUẦN TỰ.** ① master → ② neo (duyệt xong mới đi tiếp) → ③ SF con. Ảnh sau
đính ảnh trước làm `refs.bg`, nên chạy sai thứ tự là bám vào ảnh chưa có.

Board đã xếp thẻ theo đúng thứ tự này và gắn nhãn `① MASTER` / `② NEO · n`; bộ lọc
`① Ảnh gốc cần chạy TRƯỚC` lọc ra đúng nhóm phải chạy đầu.

## Chọn ĐỊA ĐIỂM trước, rồi mới chọn góc máy

Kịch bản thường chỉ cho thoại, **không ấn định nơi chốn**. Đừng mặc định nhét vào master
sẵn có cho tiện — đó là cách cả phim quanh quẩn một chỗ.

**Bước bắt buộc trước khi dựng SF cho một cụm thoại không ghi rõ địa điểm:** liệt kê 2–3
phương án rồi chọn nơi phục vụ kể chuyện tốt nhất. Hai người giúp việc thì thầm về chủ nhà
→ **bếp** (vừa pha trà vừa nói) tự nhiên hơn đứng giữa sảnh lớn; ai đó nói điều không muốn
người khác nghe → chọn nơi kín.

**Ngưỡng cảnh báo:** đếm số SF con của mỗi master. Một master gánh **quá ~25 SF** trên cả
phim là dấu hiệu đang dồn quá nhiều cảnh vào một chỗ — rà lại xem cụm nào chuyển đi nơi khác
được. Đổi địa điểm còn tạo thêm cơ hội cho ánh sáng và tông màu khác đi.

## Một master = CẢ CĂN PHÒNG, không phải một góc máy

Ảnh master khoá **không gian**, KHÔNG khoá vị trí camera. Hoàn toàn được phép xoay 360° trong
cùng bối cảnh: góc ngược lại, góc từ trên chiếu nghỉ nhìn xuống, góc từ cửa bên nhìn vào.

Tách bạch trong prompt:
- **KHOÁ từ master (bất biến):** màu tường, chất liệu sàn, đồ đạc, chiều cao trần, hướng và
  nhiệt độ ánh sáng, mức sống.
- **TỰ DO đặt:** vị trí camera, hướng nhìn, cỡ cảnh.

Lỗi hay mắc: viết prompt con **mô tả lại đúng bố cục của master** (cùng landmark ở hậu cảnh,
cùng hướng nhìn) — thế là mọi SF của bối cảnh đó nhìn về một phía, xem rất lặp.

**Khi xoay sang hướng mới, PHẢI tả thứ đáng lẽ thấy ở hướng đó** (mảng tường nào, cửa nào,
cửa sổ nào) — không tả thì model bịa ra không gian không khớp master. Giữ trục 180° trong
cùng một cụm hội thoại.

Hệ quả quan trọng: **một bối cảnh khai thác đủ hướng cho 6–8 góc thật sự khác nhau.** Phải
cạn góc rồi mới dùng tới take V2 — phần lớn V2 bị lạm dụng là vì quên rằng còn xoay được.

## Cùng phòng, KHÁC THỜI ĐIỂM — ánh sáng KHÔNG bám master

Khối "KHÓA LOOK TỪ MASTER" mặc định ghi *giữ nguyên hướng và nhiệt độ ánh sáng*. Khi scene
diễn ra vào **giờ khác với master**, câu đó thành **lệnh trái ngược** với phần mô tả bên
dưới: model vừa nhìn ảnh master có cửa sổ sáng, vừa đọc chữ bảo phòng tối — nó xử lý ngẫu
nhiên, nên cùng một căn phòng mà **khung này cửa sổ sáng, khung kia cửa sổ tối**.

**Cách viết đúng — thay câu khoá ánh sáng bằng khối này:**

```
KHÓA LOOK TỪ MASTER — GIỮ NGUYÊN: đồ đạc, bố cục phòng, màu tường, chất liệu sàn,
mức sống. KHÔNG giữ ánh sáng của master.
THỜI ĐIỂM CỦA CẢNH NÀY LÀ <BAN ĐÊM / RẠNG SÁNG / CHIỀU MUỘN> — khác master.
- Nguồn sáng duy nhất: <đèn bàn vàng ấm ở góc trái>. Không có nguồn nào khác.
- NGOÀI CỬA SỔ LÀ ĐÊM ĐEN: chỉ thấy phản chiếu mờ của đèn trong phòng trên mặt kính.
  TUYỆT ĐỐI KHÔNG có ánh sáng ban ngày, KHÔNG rèm hắt sáng trắng, KHÔNG thấy cây cối
  hay bầu trời qua cửa sổ.
- Vẫn ĐỦ SÁNG để nhìn rõ gương mặt. KHÔNG mảng đen đặc.
```

**Cửa sổ là chỗ lộ nhất** — khán giả bắt lỗi ngay khi hai clip liền nhau cắt vào nhau. Mọi
SF cùng scene phải copy y nguyên khối này, đừng viết lại mỗi cái một kiểu.

**Cách rà:** liệt kê mọi SF của scene, đọc dòng thời điểm — phải giống nhau từng chữ. Quét
theo từ khoá ("ban đêm") là KHÔNG đủ: một SF viết *"phần lớn phòng tối"* mà không nói "đêm"
sẽ lọt lưới trong khi master vẫn đang nói *"ánh sáng qua cửa sổ"*.

## ẢNH NEO — khoá VỊ TRÍ NGƯỜI khi cả cụm đứng yên một chỗ

Master khoá **không gian**, nhưng master **không có người** — nên vị trí và tư thế nhân vật
là chiều KHÔNG được khoá, và mỗi SF con tự bịa một kiểu. Hậu quả: một cuộc gọi điện liên tục
mà nhân vật khi thì đứng giữa hành lang, khi thì ở cuối hành lang — "nhảy" bốn lượt.

**Luật:** một cụm **≥3 shot** mà nhân vật **đứng/ngồi yên một chỗ** → dựng **ẢNH NEO** trước,
các góc còn lại đặt `refs.bg = <ID ảnh neo>` thay vì bám master.

Ảnh neo mang theo ba thứ chữ không tả nổi: **đúng điểm đứng trong phòng · đúng dáng người và
đồ đang cầm · đúng ánh sáng đổ lên người ở vị trí đó.**

**Khối bắt buộc trong SF con bám neo** (thiếu là model copy luôn góc máy của neo, ra 5 khung
giống hệt nhau):

```
KHÓA TỪ ẢNH NEO — GIỮ NGUYÊN: vị trí nhân vật trong phòng, tư thế, tay đang cầm gì,
hướng người, ánh sáng đổ lên người. Nhân vật KHÔNG di chuyển so với ảnh neo.
KHÔNG LẤY GÓC MÁY của ảnh neo — camera khung này đứng ở chỗ khác.
```

**Áp dụng:** gọi điện · đứng nói chuyện tại một điểm · ngồi trên ghế suốt cụm · cảnh 3+ người
cần giữ vị trí tương đối · mặt bàn đã bày sẵn đạo cụ theo một cách cụ thể.

**KHÔNG áp dụng** khi nhân vật đổi trạng thái (đứng → ngồi → nắm tay): mỗi trạng thái là một
khung riêng, neo vào nhau sẽ khoá chết diễn biến.

**Ba điều phải nhớ:**
1. **Neo render và duyệt TRƯỚC**, không chạy song song — neo sai thì cả cụm sai theo.
2. **Chuỗi chỉ MỘT tầng**: master → neo → góc con. Sâu hơn thì ảnh gốc bị pha loãng.
3. Kỹ thuật: `refs.bg` chỉ là ID, đính ảnh của SF đó — trỏ vào SF thường hay master đều chạy.

## SF là TRẠNG THÁI, không phải KHOẢNH KHẮC

SF là ảnh tĩnh **đứng yên** — video mới là chỗ diễn. Viết SF ở trạng thái trung tính:
**ai ở đâu, đứng hay ngồi, gần hay xa, cầm gì, quay hướng nào.** TUYỆT ĐỐI không khoá
vào đỉnh cảm xúc hay hành động: đang ho, che miệng, khóc, đưa tay ra, gập người.

Sai: *"Edmund gập người trong cơn ho, tay ôm ngực; Lily đưa tay ra"*
→ dùng lại ở shot sau thì ông **ho mãi**, và video không còn gì để diễn vì hành động đã xong.
Đúng: *"Edmund ngồi xe lăn, Lily đứng cạnh tay vịn"* — cơn ho và cái chạm tay để **prompt
video** diễn ra từ trạng thái đó.

**Phép thử:** một SF phải dùng được cho **ít nhất 2–3 câu thoại khác nhau** trong cùng trạng
thái. Chỉ hợp đúng một câu = đang khoá vào hành động, viết lại.

Hệ quả: mô tả biểu cảm trong SF chỉ được ở mức **nền** (mệt, điềm tĩnh, tò mò), không phải
**đỉnh** (òa khóc, sững người, bụm miệng).

## Ánh mắt và cảm xúc trên khuôn mặt SF

**Hướng nhìn theo số người trong khung:**
- **2 người → NHÌN THẲNG VÀO MẮT NHAU.** Viết rõ trong prompt: *"hai người NHÌN THẲNG VÀO MẮT
  NHAU, đường nhìn nối liền giữa hai gương mặt"*. Đây là mặc định, không phải tuỳ chọn.
- **1 người** → tuỳ cảnh: nhìn vào vật đang cầm, nhìn ra cửa sổ, nhìn về phía người ngoài khung.
- **≥3 người** → tuỳ dàn cảnh: thường một cặp nhìn nhau, người còn lại nhìn về cặp đó hoặc nhìn
  đi chỗ khác để tạo tầng.

**Cảm xúc trên mặt = CẢM XÚC CHUNG CỦA CẢ SCENE, không phải của một câu thoại.**
Trước khi viết bộ SF, chốt một câu: *scene này nhân vật X đang ở trạng thái tinh thần nào?*
(nghi ngại · kiệt sức · phòng thủ · vừa nhận ra điều gì). Đưa đúng trạng thái đó lên mặt mọi
SF của scene. Diễn xuất theo từng câu là việc của **prompt video** — SF chỉ dựng cái nền.

**Miệng: TRẠNG THÁI TỰ NHIÊN, KHÔNG MỞ, KHÔNG đang nói.** SF là frame đứng yên trước khi
thoại bắt đầu; miệng đang mở làm khung khó tái dùng và làm video mở đầu bằng khẩu hình sai.
Nhưng **đừng viết "khép"** — môi mím lại trông gồng và giả. Viết: *"môi ở trạng thái TỰ NHIÊN,
thả lỏng — KHÔNG mở miệng, KHÔNG đang nói, KHÔNG mím chặt"*.

## Thứ tự làm SF: PHỦ ĐỦ TRẠNG THÁI TRƯỚC, take sau cùng

Scene dài (>3 phút) làm đúng bậc thang này, xong bậc trên mới xuống bậc dưới:

1. **Đủ mọi TRẠNG THÁI** — mỗi lần nhân vật đổi tư thế/vị trí/khoảng cách là một trạng thái
   riêng. Ví dụ cụm hội thoại hai người: *bé ngồi sàn vẽ · bé đứng cạnh xe lăn · bé nắm tay ông*.
2. **OTS / reverse — theo ĐỘ DÀI của trạng thái, không phải mặc định cho mọi trạng thái.**
   Đếm số shot mà một trạng thái phải gánh:
   - **1–2 shot** (kiểu *"Ngồi xuống." — "Tôi đứng được."*): **không cần OTS**, thêm vào là thừa.
   - **≥3 shot cùng một trạng thái**: **bắt buộc** có OTS/reverse, nếu không khán giả nhìn y
     một khung suốt 30 giây. Đây là chỗ luôn bị bỏ quên.
3. **Wide / góc rộng** để thở, phục vụ nhịp không thoại — vẫn phải có người trong khung.
4. **Take V2/V3** — CHỈ khi một SF ở trên vẫn gánh **>3 shot**.

Chưa xong bậc 1–2 mà đã làm V2 là sai thứ tự: thiếu trạng thái thì buộc phải đi **cắt frame
từ video** ra chắp vá, còn V2 chỉ là cùng một khung render lại — không thêm góc nào.

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

## CHECKLIST BẮT BUỘC — rà đủ trước khi viết bất kỳ prompt SF nào

Không được bỏ qua mục nào. Mỗi mục phải có quyết định rõ ràng viết vào prompt, hoặc một lý do
chủ động để loại nó khỏi khung. Bỏ trống một mục = model tự bịa, và thường bịa sai.

**Nhưng checklist này là để KHÔNG BỎ SÓT thứ cần thiết, KHÔNG PHẢI để nhồi cho đủ mục.** Với mỗi
vật thể định đưa vào khung, hỏi: nó thuộc về không gian này một cách tự nhiên (giữ), nó tham gia
hành động của beat này (giữ, tả rõ), hay nó chỉ được cài vào để minh họa một câu thoại (bỏ)?
Đừng nhầm hai loại đầu với loại thứ ba mà dọn sạch cả đồ đạc vốn phải có — xem nguyên lý 14.

0. **ĐỊA ĐIỂM NÀY LÀ ĐÂU, VÀ ĐÃ XUẤT HIỆN CHƯA?** Kịch bản không ghi rõ nơi chốn thì
   **chọn có chủ đích** trước (xem mục "Chọn ĐỊA ĐIỂM trước"), đừng mặc định dùng lại
   master gần nhất. Chọn xong mới hỏi tiếp: địa điểm đó đã xuất hiện chưa?

   **ĐÃ XUẤT HIỆN RỒI?** — áp dụng cho **MỌI SF**, không riêng master: SF con,
   nhịp không thoại, toàn cảnh, cầu nối — tất cả. Rà theo ĐỊA ĐIỂM, không theo số scene. Nếu
   công trình này (ngôi nhà, siêu thị, bệnh viện…) đã có ảnh ở BẤT KỲ scene nào trước đó thì
   BẮT BUỘC đính ảnh đó vào `refs.bg` kèm khối khóa đặt ngay đầu prompt.
   Chọn một trong ba mức khóa:
   - **Cùng đúng căn phòng / đúng góc nhìn** → "dùng lại nguyên vẹn, chỉ đổi thời điểm trong
     ngày và vị trí người".
   - **Phòng khác trong cùng công trình** → "bố cục khác, nhưng cùng màu sơn, cùng loại sàn,
     cùng khung cửa, cùng chiều cao trần, cùng mức sống".
   - **Cùng khu phố / cùng quần thể** → "mọi công trình trong khung cùng một họ kiến trúc, cùng
     chất liệu, cùng mật độ, cùng mức sống".

   Luôn kèm khối chặn nâng cấp mức sống — bỏ mục này là model vẽ ra một ngôi nhà đẹp hơn nhà
   thật của nhân vật (bài học 31).

   **Ngoại cảnh là chỗ dễ sót nhất.** Mặt tiền nhà, con phố, sân, lối vào — master của scene
   thường là ảnh NỘI THẤT, nên khi dựng một khung ngoại cảnh ta quét danh sách master, không
   thấy cái nào là "mặt tiền", rồi kết luận nhầm là chưa có. Phải hỏi ngược lại: *công trình
   này đã từng lên hình TỪ BÊN NGOÀI ở scene nào chưa?* Cách chắc chắn: lập sẵn bảng ảnh gốc
   theo **công trình + góc nhìn** (`nhà Maya → ngoại thất: SF-S5-MASTER · bếp: SF-S8-MASTER ·
   phòng khách: SF-S3-MASTER`) và tra bảng đó trước khi viết (bài học 33).
1. **Nhân vật chính trong khung** — ai, ở đâu (mốc % hoặc landmark), tư thế, **hướng nhìn**
   (2 người thì NHÌN THẲNG VÀO MẮT NHAU), biểu cảm ở mức **cảm xúc chung của scene**, và
   **môi tự nhiên thả lỏng, không mở miệng**. Xem mục "Ánh mắt và cảm xúc".
2. **Nhân vật phụ có thoại** — có thực sự thuộc beat này không (nguyên lý 11)? Nếu có: vị trí,
   tách bạch rõ với nhóm khác.
3. **Quần chúng nền** — bối cảnh này ngoài đời có người qua lại không? Bao nhiêu người? Họ đang
   làm gì, có nhìn về phía sự kiện chính không? Nêu rõ họ là nền mờ, không rõ mặt, không bảng tên.
   Một không gian công cộng (siêu thị, bệnh viện, sảnh, đường phố) mà khung hình vắng tanh sẽ
   đọc như phim trường giả.
4. **TRẠNG THÁI KHÔNG GIAN của nhân vật** — ai đứng/ngồi, cách nhau bao xa, ai cao hơn ai (trên
   thềm/dưới thềm, đứng/ngồi), ai trước ai sau. Cụm ≥3 shot mà người đứng yên một chỗ thì
   khoá bằng **ẢNH NEO** (xem mục dưới), đừng để mỗi SF tự tả vị trí một kiểu. Phải ghi vào mô tả SF, vì đây là dữ liệu để đối
   chiếu continuity giữa các shot (xem mục "LOGIC KHÔNG GIAN LIÊN TỤC").
5. **NỘI THẤT CƠ BẢN của loại bối cảnh này** — thứ dễ sót nhất vì "hiển nhiên đến mức không ai
   nghĩ phải viết ra". Phòng làm việc phải có GHẾ (ghế của chủ phòng + ghế khách); phòng ăn phải
   có bàn ghế; phòng ngủ phải có giường; lớp học phải có bàn học. Thiếu món nội thất cơ bản là
   khung hình đọc ra ngay như phim trường dựng tạm. Kiểm tra chéo: nếu BẤT KỲ SF con nào của
   scene yêu cầu một tư thế cần đồ nội thất (ngồi, tựa, nằm), món đồ đó BẮT BUỘC phải có sẵn
   trong master — nếu không SF con sẽ bịa ra một cái không tồn tại, phá continuity.
6. **Vật dụng THUỘC VỀ bối cảnh** — thứ loại không gian này ngoài đời luôn có dù thoại không nhắc:
   giấy tờ/hồ sơ trên bàn làm việc, hàng trên kệ siêu thị, nồi niêu trong bếp. Phải có, tả khái
   quát và cho lùi ra nền. Thiếu chúng thì không gian trống rỗng giả tạo (nguyên lý 14a).
7. **Đạo cụ của TỪNG người trong khung** — không chỉ nhân vật chính. Người xếp hàng ở siêu thị
   phải có xe đẩy/giỏ; người ở bệnh viện phải có hồ sơ/túi xách; người đi làm phải có cặp. Người
   đứng tay không trong ngữ cảnh cần đạo cụ sẽ trông sai.
8. **Nội dung cụ thể của đạo cụ THAM GIA HÀNH ĐỘNG** — trong giỏ có gì, vật nào được đưa/đẩy/cầm.
   Tả cụ thể và đặt tách bạch khỏi nhóm vật dụng nền để mắt nhận ra ngay. Rà kịch bản các scene
   khác xem có món đồ nào được nhắc bằng lời để cố ý cho trùng khớp (nguyên lý gieo-trả) — nhưng
   chỉ khi món đó thật sự có vai trò trong hành động, không phải mọi chi tiết thoại đều cần biến
   thành vật thể trong khung (nguyên lý 14c).
9. **Thời điểm và mức độ đông đúc** — giờ nào trong ngày, ngày thường hay cuối tuần, vắng hay
   đông. **Rà kịch bản xem có câu thoại nào đã ấn định chi tiết này chưa** (vd. nhân vật nhắc
   "giờ cao điểm", "sáng sớm") — nếu có thì bắt buộc khớp, đây là chi tiết dễ bỏ sót nhất.
10. **Bảng màu và ánh sáng** — bảng màu/chất liệu khóa ở master. NHƯNG **thời điểm trong
   ngày là của SCENE, không của master** — nếu scene diễn ra vào giờ khác master, xem mục
   "Cùng phòng, khác thời điểm" bên dưới. Mỗi scene khai MỘT thời điểm duy nhất và mọi SF
   trong scene ghi giống nhau từng chữ.
11. **Danh sách chữ được phép xuất hiện** — liệt kê đủ mọi bảng tên/biển số (nguyên lý 13), kèm
   yêu cầu in RÕ RÀNG DỄ ĐỌC, không nhòe thành ký tự vô nghĩa.
12. **Câu chặn lỗi cuối** — không watermark, không nhân vật trùng lặp, không logo méo.

- [ ] **SF là TRẠNG THÁI, không phải khoảnh khắc** — không ho, không che miệng, không khóc,
      không đưa tay ra. Phép thử: khung này dùng được cho ≥2–3 câu thoại khác nhau không?
- [ ] **Đã phủ đủ trạng thái chưa, rồi mới tới OTS và take V2** — nếu còn phải cắt frame từ
      video ra vá thì bậc 1 chưa xong. OTS chỉ bắt buộc cho trạng thái gánh ≥3 shot.

## Quy tắc SF trong dữ liệu

- Scene `REF` chứa các SF nhân vật: mỗi nhân vật có `REF_<TEN>_PORTRAIT` (chân dung 2:3)
  và `REF_<TEN>_FULL` (toàn thân 9:16, luôn tham chiếu ngược lại PORTRAIT qua `refs.chars`).
- `refs.chars` là danh sách ID ảnh **thật sự được đính kèm** cho model xem — khác với việc
  chỉ nhắc tên nhân vật trong lời văn.
- **MỌI NHÂN VẬT XUẤT HIỆN TRONG KHUNG ĐỀU PHẢI CÓ REF — KỂ CẢ NGƯỜI Ở TIỀN CẢNH QUAY LƯNG,
  OUT NÉT, HAY CHỈ THẤY VAI/GÁY.** Đây là chỗ cực dễ sót: khung OTS hay CU thường mô tả "rìa
  trái là vai và gáy của X, out nét làm khung viền" rồi chỉ đính ref của người nét rõ. Sai —
  cái vai out nét đó vẫn phải ĐÚNG NGƯỜI và ĐÚNG BỘ ĐỒ, nếu không model tự bịa ra một người
  khác với quần áo khác, và khung OTS lộ ngay vì màu áo lệch với khung đối diện.
  Quy tắc rà: **tên nhân vật nào xuất hiện trong prompt thì phải có cặp portrait + full của
  đúng bộ đồ cảnh đó trong `refs.chars`** — trừ khi prompt ghi rõ "X KHÔNG có trong khung".
- **TRẦN CỨNG: TỐI ĐA 4 NHÂN VẬT được đính ref trong một SF** (= 8 ảnh người + 1 master ≈ 9
  ảnh). Mỗi nhân vật đính CẢ portrait (khuôn mặt) LẪN full-body của đúng bộ đồ cảnh đó — đủ
  cặp, không đính thiếu, nhưng KHÔNG quá 4 người.
  **Khung cần hơn 4 người thì xử lý theo thứ tự:**
  1. **Cắt bớt người khỏi khung** — hỏi lại từng người có thật sự thuộc beat này không.
  2. **Tách thành hai khung**, mỗi khung ≤4 người, rồi dựng thành hai shot.
  3. **Chỉ khi buộc phải giữ đủ**: đính ref cho 4 người ĐỨNG GẦN/RÕ MẶT nhất; những người còn
     lại mô tả bằng chữ như QUẦN CHÚNG NỀN — mờ, không rõ mặt, không phải nhân vật có tên.
     Người có thoại thì LUÔN nằm trong nhóm 4 được đính ref.
  Khi nhân dạng ra lệch, KHÔNG chữa bằng cách bỏ bớt ref của người vẫn còn trong khung: chữa
  bằng render lại, kiểm tra ảnh có thật sự được đính không, và dòng khóa chữ ngắn.
- Luôn kèm **một dòng ngắn** khóa những gì ảnh không tự nói nổi: chủng tộc, kiểu tóc, màu
  quần áo. Phim này Maya da đen / Helen da trắng là điểm cốt lõi — dòng khóa chủng tộc phải
  có ở mọi SF có hai người, kể cả khi ref đang ra đúng.

- Mỗi scene có 1 SF **master** (không có `refs.bg`) — SF còn lại của scene đều đặt
  `refs.bg = "<ID-master>"` để bám theo bối cảnh/bảng màu/ánh sáng của master.
- Trước khi viết prompt master của một scene, đọc lại field `script` của scene đó **và các
  scene khác trong phim** để tìm chi tiết/đạo cụ được nhắc tới bằng lời ở nơi khác (một món đồ,
  một hành động cụ thể) — nếu có, cố tình cho đạo cụ trong khung trùng khớp để tạo hiệu ứng
  "gieo trước, trả sau" thay vì mô tả đạo cụ chung chung không có nội dung cụ thể.

