---
name: tao-prompt-sf
description: Viết/sửa prompt ảnh nhân vật và Start Frame (SF) trong sf-board.json cho các dự án PIPELINE-*.project. Dùng skill này mỗi khi tạo REF nhân vật mới, tạo SF cho một scene, hoặc sửa ngoại hình/trang phục nhân vật trong board — kể cả khi user chỉ nói "tạo SF cho scene X" mà không nhắc rõ kỹ thuật.
---

# Viết prompt ảnh cho SF Board

Bạn đang soạn prompt tiếng Việt để một model tạo ảnh (qua ChatGPT/CDP) render ảnh nhân vật
tham chiếu (REF) và Start Frame (SF) cho từng scene, lưu trong `sf-board.json` của
dự án `PIPELINE-*.project`. Trước khi viết, đọc `references/bai-hoc.md` — kinh nghiệm
tích lũy từ các lần sửa trước, có thể điều chỉnh/bổ sung nguyên lý dưới đây.

## Cấu trúc dữ liệu cần biết

- Scene `REF` chứa các SF nhân vật: mỗi nhân vật có `REF_<TEN>_PORTRAIT` (chân dung 2:3)
  và `REF_<TEN>_FULL` (toàn thân 9:16, luôn tham chiếu ngược lại PORTRAIT qua `refs.chars`).
- **MỖI NHÂN VẬT CHỈ CÓ MỘT PORTRAIT DUY NHẤT, dùng cho cả phim.** Portrait là ảnh chuẩn của
  KHUÔN MẶT — không tạo lại portrait cho từng bộ đồ.
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
- Mỗi scene có 1 SF **master** (không có `refs.bg`) — SF còn lại của scene đều đặt
  `refs.bg = "<ID-master>"` để bám theo bối cảnh/bảng màu/ánh sáng của master.
- `refs.chars` là danh sách ID ảnh **thật sự được đính kèm** cho model xem — khác với việc
  chỉ nhắc tên nhân vật trong lời văn.
- Trước khi viết prompt master của một scene, đọc lại field `script` của scene đó **và các
  scene khác trong phim** để tìm chi tiết/đạo cụ được nhắc tới bằng lời ở nơi khác (một món đồ,
  một hành động cụ thể) — nếu có, cố tình cho đạo cụ trong khung trùng khớp để tạo hiệu ứng
  "gieo trước, trả sau" thay vì mô tả đạo cụ chung chung không có nội dung cụ thể.

## CHECKLIST BẮT BUỘC — rà đủ trước khi viết bất kỳ prompt SF nào

Không được bỏ qua mục nào. Mỗi mục phải có quyết định rõ ràng viết vào prompt, hoặc một lý do
chủ động để loại nó khỏi khung. Bỏ trống một mục = model tự bịa, và thường bịa sai.

**Nhưng checklist này là để KHÔNG BỎ SÓT thứ cần thiết, KHÔNG PHẢI để nhồi cho đủ mục.** Với mỗi
vật thể định đưa vào khung, hỏi: nó thuộc về không gian này một cách tự nhiên (giữ), nó tham gia
hành động của beat này (giữ, tả rõ), hay nó chỉ được cài vào để minh họa một câu thoại (bỏ)?
Đừng nhầm hai loại đầu với loại thứ ba mà dọn sạch cả đồ đạc vốn phải có — xem nguyên lý 14.

0. **ĐỊA ĐIỂM NÀY ĐÃ XUẤT HIỆN CHƯA?** — áp dụng cho **MỌI SF**, không riêng master: SF con,
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
1. **Nhân vật chính trong khung** — ai, ở đâu (mốc % hoặc landmark), tư thế, hướng nhìn, biểu cảm.
2. **Nhân vật phụ có thoại** — có thực sự thuộc beat này không (nguyên lý 11)? Nếu có: vị trí,
   tách bạch rõ với nhóm khác.
3. **Quần chúng nền** — bối cảnh này ngoài đời có người qua lại không? Bao nhiêu người? Họ đang
   làm gì, có nhìn về phía sự kiện chính không? Nêu rõ họ là nền mờ, không rõ mặt, không bảng tên.
   Một không gian công cộng (siêu thị, bệnh viện, sảnh, đường phố) mà khung hình vắng tanh sẽ
   đọc như phim trường giả.
4. **TRẠNG THÁI KHÔNG GIAN của nhân vật** — ai đứng/ngồi, cách nhau bao xa, ai cao hơn ai (trên
   thềm/dưới thềm, đứng/ngồi), ai trước ai sau. Phải ghi vào mô tả SF, vì đây là dữ liệu để đối
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
10. **Bảng màu và ánh sáng** — khóa ở master, các SF sau bám theo.
11. **Danh sách chữ được phép xuất hiện** — liệt kê đủ mọi bảng tên/biển số (nguyên lý 13), kèm
   yêu cầu in RÕ RÀNG DỄ ĐỌC, không nhòe thành ký tự vô nghĩa.
12. **Câu chặn lỗi cuối** — không watermark, không nhân vật trùng lặp, không logo méo.

## Bộ góc máy (coverage) của một scene

Checklist ở trên là cho TỪNG prompt; mục này là cho CẢ BỘ SF của một scene — quyết định cần
bao nhiêu góc và những loại góc nào trước khi viết từng cái.

**Bộ khung chuẩn** (hầu hết scene hội thoại đều cần): 1 master + cặp shot/reverse-shot cho hai
phía đối thoại + góc riêng cho beat chuyển trạng thái (ngồi sụp, đứng dậy, bước ra cửa...).

**KHÔNG dùng SF insert thuần đạo cụ CHO SHOT CÓ THOẠI — khung không có người là khung chết.**
Cận cảnh một tờ giấy, một màn hình, một nồi thức ăn thì trông rất "có nghề" khi đứng yên, nhưng
khi thành clip 10s có thoại thì nó không có gương mặt, không có lip-sync, không có cảm xúc — chỉ
là một vật thể nằm im trong khi giọng nói vọng đâu đó ngoài khung. Người xem rơi ra khỏi câu
chuyện ngay lập tức.

**Ngoại lệ: NHỊP KHÔNG THOẠI thì ngược lại — khung cận đạo cụ hoặc đôi bàn tay lại là khung
mạnh nhất.** Khi clip không có lời nào, nó không cần lip-sync để sống; nó sống bằng chuyển động
và ý nghĩa. Bàn tay bà cụ siết cổ tay người trẻ, chiếc bảng tên được đặt xuống bàn, chai nước
xoay trong lòng bàn tay — những khung này nói được điều mà cả đoạn thoại không nói nổi. Ranh
giới rất gọn: **có thoại → phải có mặt người; không thoại → đạo cụ và bàn tay là hợp lệ, thậm
chí nên dùng.** Xem bài học 32 về cách dựng nhịp không thoại.

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

**Bổ sung góc theo THỜI LƯỢNG cảnh** — cảnh càng dài càng cần nhiều góc để không bị ping-pong
nhàm giữa 2 góc CU:
- Cảnh ngắn (dưới ~20s): bộ khung chuẩn là đủ, cùng lắm +1 góc.
- Cảnh trung (~20-40s): +1-2 góc bổ sung.
- Cảnh dài (trên ~40s): +3-5 góc bổ sung. Dấu hiệu cần thêm: một SF hội thoại nào đó bị dùng
  cho 3+ shot.

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

## Prompt video (Grok image-to-video) — FORM CHUẨN, dùng đúng khung này

Prompt video KHÔNG phải một đoạn mô tả tự do. Nó theo một form cố định đã được kiểm chứng qua
các dự án trước, gồm 6 khối theo đúng thứ tự. Thoại được NHÚNG THẲNG vào prompt kèm nhãn cảm
xúc — Grok đọc thoại từ prompt để làm lip-sync và giọng nói, không phải từ field text riêng.

```
REFS · Start frame: <SF-ID>

Bắt đầu trực tiếp từ frame tham chiếu. Giữ nguyên nhân vật, khuôn mặt, trang phục, bối cảnh,
đạo cụ, ánh sáng và bố cục.
Nhận diện: <Tên A> = <trang phục/vị trí trong khung, vai trò chính hay phụ>. <Tên B> = <...>.
<Ai rõ mặt, ai mờ rìa khung/quay lưng — nhân vật phụ mờ thì ghi rõ "giữ nguyên out nét,
KHÔNG lấy nét, KHÔNG lộ mặt">.

Một shot liền <N> giây, không chuyển cảnh. Camera <TĨNH / PUSH-IN chậm / DOLLY ngang nhẹ /
trôi vào rồi giữ...>.

<Mô tả hành động của người nói trước câu thoại>:

<TÊN> — <nhãn cảm xúc/giọng điệu tiếng Anh, vd: quiet, firm / icy, dismissive / tearful, gentle>:
"<câu thoại tiếng Anh nguyên văn từ kịch bản>"

<Nhịp phản ứng của người kia — cử chỉ, ánh mắt — rồi tiếp thoại của họ theo cùng cấu trúc.
Người nói ngoài khung ghi: TÊN (off-screen) — <cảm xúc>:>

Âm thanh: CHỈ thoại nhân vật, tiếng Anh giọng Mỹ, rõ lời. Không âm nền.

Không nhạc. Không narrator. Không phụ đề. MỘT SHOT LIỀN DUY NHẤT suốt cả video — tuyệt đối
KHÔNG chuyển cảnh, KHÔNG cắt. Nhân vật phụ bị mờ/quay lưng ở rìa khung (nếu có) chỉ được nghe
giọng, KHÔNG được lấy nét hay lộ mặt. Không thêm, xóa, thay thế hoặc nhân bản nhân vật.
```

Ghi chú từng khối:
- **Nhận diện** là khối chống nhầm người, KHÔNG phải chỗ tả trang phục. Viết theo đúng công thức
  cho mỗi người, mỗi người một câu:

  `<Tên> = <tuổi + chủng tộc>, <trang phục gói trong MỘT cụm ngắn + (REF_ID nếu có)>, <TƯ THẾ>
  <VỊ TRÍ trong khung>.`

  Ví dụ đúng: *"Maya = nữ da đen 28 tuổi, bộ office thanh lịch (REF_MAYA_OFFICE_FULL), NGỒI ghế
  bành bên TRÁI."* — kết bằng một câu chung: "Cả hai rõ mặt, cả hai đều nói."

  **TUYỆT ĐỐI KHÔNG liệt kê từng món quần áo trong khối này** (blazer + blouse + quần + giày +
  thắt lưng...). Càng liệt kê chi tiết, model càng cố vẽ cho đủ mọi món — kể cả những món không
  thể thấy trong khung đó (giày trong khung cận mặt), và càng dễ vẽ sai lệch khỏi ảnh tham chiếu.
  Chi tiết trang phục đã nằm ở ảnh REF và ở prompt SF rồi; ở đây chỉ cần một cụm đủ để phân biệt
  người này với người kia. Nhắm mỗi người khoảng 15-25 từ, cả khối dưới ~300 ký tự.

  Với nhân vật phụ mờ: `— nhân vật PHỤ, KHÔNG lấy nét, KHÔNG lộ mặt; nếu nói thì CHỈ NGHE GIỌNG.`
  Với SF insert không có mặt ai: ghi thẳng "KHÔNG có gương mặt nào trong khung, mọi giọng đều
  vọng từ NGOÀI KHUNG".
- **Camera**: chỉ dùng chuyển động nhẹ (TĨNH, PUSH-IN chậm, DOLLY ngang nhẹ, trôi vào rồi giữ).
  Viết hoa loại chuyển động.
- **Thoại nhúng**: mỗi câu = một khối `TÊN — cảm xúc:` xuống dòng rồi câu thoại trong ngoặc kép,
  nguyên văn tiếng Anh từ kịch bản. Giữa các câu chèn 1 dòng mô tả phản ứng/cử chỉ.
- **Hai khối cuối** (Âm thanh + footer khóa) giữ nguyên văn, không sáng tạo lại.

## Prompt video cho NHỊP KHÔNG THOẠI — viết cảm xúc, đừng viết cử chỉ

Một scene hội thoại dựng xong chưa phải là cảnh phim hoàn chỉnh. Phải rà thêm một lượt để chèn
những nhịp không lời: **beat cảm xúc** (6s, sau câu thoại nặng nhất), **cầu nối** (6-10s, nối
hai cảnh), **dựng cảnh** (6s, bắt buộc khi nhảy thời gian), **cao trào không lời** (10s, một
hành động thay cả đoạn thoại). Mặc định 6s; 10s chỉ khi có hành động thật sự diễn tiến.

**MẬT ĐỘ: số nhịp không thoại ≈ 15% số shot có thoại.** Đây là con số đã kiểm chứng trên phim
thật — 129 shot thoại thì khoảng 19 nhịp là vừa. Tính theo TỔNG CẢ PHIM, không tính theo scene:
có scene xứng đáng 3 nhịp liền (khúc gãy của nhân vật), có scene không cần cái nào.

Đừng rải đều mỗi scene 1-2 cái — đó chính là cách tôi từng làm ra 43 nhịp cho 129 shot (33%) và
phim bị loãng hẳn, user phải yêu cầu cắt hơn một nửa. Cách chọn đúng: với mỗi nhịp định giữ,
hỏi *"nhịp này gánh việc gì mà thoại không làm thay được?"* Nếu không trả lời được thì bỏ.
Ba loại luôn xứng đáng giữ:
- **Báo nhảy thời gian** ("sáu tháng sau", "một năm sau") — bỏ là khán giả lạc.
- **Mắt xích của chuỗi hình ảnh khép vòng tròn** — vật/cử chỉ gieo ở đầu phim được trả ở cuối.
- **Cao trào không lời** — một hành động nói thay cả đoạn thoại.

Ngược lại, dựng-cảnh trống người là loại đáng cắt đầu tiên: nó chỉ báo địa điểm, mà địa điểm
thì cảnh thoại ngay sau đã nói rõ.

Form khác form thoại. Ba khối bắt buộc:

1. `KHÔNG CÓ LỜI THOẠI TRONG CLIP NÀY. Tuyệt đối không ai mở miệng nói, không ai cử động môi
   như đang nói.` — thiếu câu này model sẽ tự cho nhân vật lẩm bẩm.
2. **Âm thanh: cấm thoại và nhạc, nhưng CHO PHÉP tiếng môi trường.** Viết riêng cho từng nhịp
   một bộ ambient/SFX có thật trong khung — tiếng siêu thị lao xao, nước chảy trong bồn rửa,
   đồng hồ tích tắc, dế kêu, bước chân trên vỉa hè, chiếc bảng tên nhựa đặt xuống mặt bàn gỗ.
   Kèm câu chốt: *giữ ở mức NHẸ và TỰ NHIÊN, làm nền cho hình chứ không hút sự chú ý, chừa chỗ
   để người dựng ghép nhạc lên trên.*
   Ambient chọn theo đúng bối cảnh và theo CẢM XÚC: cùng một siêu thị, nhịp Derek quan sát thì
   để tiếng máy quét bíp đều đặn dửng dưng, còn nhịp hai bàn tay trên sàn thì cho tiếng siêu
   thị lùi hẳn ra xa, chỉ còn hơi thở gấp ở gần — thế giới thu lại quanh hai người.
   *(Đừng bắt im lặng tuyệt đối: clip câm hoàn toàn nghe rất giả, và ambient nhẹ không cản trở
   việc ghép nhạc.)*
3. **Khối cảm xúc — quan trọng nhất, và là chỗ dễ viết sai nhất.**

**Viết TRẠNG THÁI, không viết THAO TÁC.** Đây là điều dễ làm ngược nhất. Phản xạ tự nhiên là kê
ra một danh sách cử chỉ ("siết tay, nuốt khan, quai hàm siết, chớp mắt") để model có cái mà
theo. Nhưng làm vậy là biến diễn xuất thành thực đơn: model nhặt vài món trong danh sách, và
**mọi nhịp trong phim đều diễn giống nhau** vì cùng ăn một thực đơn. Nó cũng chặn mất khả năng
model tự tìm ra cử chỉ hợp với đúng không gian và tư thế trong frame đó.

Thay vào đó, mỗi nhịp viết một khối riêng gồm hai phần:

```
CẢM XÚC & HOÀN CẢNH — ĐÂY LÀ THỨ QUAN TRỌNG NHẤT CỦA CLIP NÀY:
<Nhân vật vừa trải qua chuyện gì. Họ đang ở đâu trong hành trình của mình.>
<Trong lòng họ lúc này là gì — cụ thể, có mâu thuẫn nội tâm nếu có.>

Hãy để cơ thể nhân vật biểu đạt đúng trạng thái trên, theo cách tự nhiên nhất trong chính
không gian và tư thế của frame tham chiếu. TỰ CHỌN cử chỉ, ánh mắt, nhịp nhanh chậm và điểm
dừng sao cho khớp với cảm xúc đó — không có một cách diễn nào đúng cho mọi cảm xúc.

Gợi ý diễn biến (điều chỉnh được cho tự nhiên): <diễn biến chính, để model bám nhưng không trói>
```

Khung này giữ được cả hai: **ý đồ đạo diễn** nằm ở phần cảm xúc và gợi ý diễn biến, còn **cách
thể hiện** để model tự quyết theo frame cụ thể. Chữ "gợi ý" và "điều chỉnh được" là cố ý — nó
cho phép model bỏ một chi tiết nếu chi tiết đó không hợp với tư thế nhân vật trong ảnh.

**MỌI CHUYỂN ĐỘNG PHẢI CÓ TÁC NHÂN NHÌN THẤY ĐƯỢC TRONG KHUNG.** Đây là lỗi rất dễ mắc khi
viết nhịp không thoại, vì ta lo khung hình đứng im nên nhồi thêm chuyển động cho "có sự sống" —
rồi cho vật vô tri tự động đậy. Xe đẩy tự lăn qua bãi đỗ xe trống, cửa tự mở khi không ai bước
tới, trang giấy lật vì gió trong căn bếp đóng kín lúc hai giờ sáng: lên clip nhìn ra ngay là
giả, và nó phá hỏng đúng cái hiện thực mà cả bộ prompt đang cố giữ.

Trước khi viết mỗi chuyển động, hỏi: **cái gì làm nó động?** Chỉ ba nguồn hợp lệ:
- **Người trong khung** — kể cả bóng người mờ ở xa, miễn là họ CÓ trong ảnh SF.
- **Lực tự nhiên đang hiện diện** — gió (phải thấy được: lá lay, rèm động), trọng lực, nắng dịch.
- **Máy móc đang chạy** — xe có tài xế, đèn hẹn giờ, màn hình tự tắt.

Và điều quan trọng nhất: **đối chiếu với ẢNH SF ĐÃ RENDER, không phải với mô tả trong prompt SF.**
Prompt SF có thể viết "vài khách hàng mờ nét đi vào" nhưng ảnh thật ra lại vắng tanh ở chỗ đó.
Prompt video bám theo chữ mà không nhìn ảnh thì sinh ra chuyển động không có chỗ bấu víu. Khi
nghi ngờ, mở ảnh ra xem có gì thật sự nằm trong khung.

Khung tĩnh không phải là vấn đề. Một mặt tiền yên ắng với nắng dịch chậm và tán lá lay còn thật
hơn nhiều so với một khung nhồi đầy vật thể tự di chuyển. Nếu thấy trống quá thì thêm chuyển
động của ÁNH SÁNG, đừng thêm vật (bài học 36).

**Với nhịp không có nhân vật** (dựng cảnh, toàn cảnh trống), đổi thành `KHÔNG KHÍ CẦN TẠO RA`
và mô tả cảm giác cần có, rồi để model tự chọn chi tiết nào nên động: ánh sáng, gió, vật thể,
dáng người ở xa.

**Ở cỡ cảnh rộng, cảm xúc đến từ tỷ lệ chứ không từ gương mặt** — dáng đi, hướng quay thân
người, khoảng cách giữa các nhân vật, khoảng trống quanh họ. Nhắc tới biểu cảm hay lồng ngực ở
cỡ cảnh này là vô nghĩa vì khán giả không nhìn thấy.

**Về những lối diễn bị lặp** (hít thở sâu, thở dài, nhắm mắt rồi mở): đừng cấm — cấm tuyệt đối
cũng máy móc y như lạm dụng, và sẽ giết luôn những lần dùng đúng (người kiệt sức, người vừa
trút được gánh nặng). Cách chữa là viết cảm xúc cho rõ và cho đủ khác nhau giữa các nhịp; khi
mỗi nhịp có một trạng thái riêng biệt thì cách diễn tự khác nhau theo. Xem bài học 32 và 34.

## Prompt nhạc nền Suno cho nhịp không thoại

Nhịp không thoại nào cũng cần một hướng nhạc, vì clip im lặng thì nhạc chính là thứ dẫn cảm xúc.
Mỗi nhịp viết **2 lựa chọn** cùng cảm xúc nhưng khác cách xử lý, để người dựng nghe rồi chọn.

**Bước đầu tiên KHÔNG phải viết prompt — mà là quyết định VAI TRÒ của nhạc trong đoạn đó.**
Đây là chỗ hay bị bỏ qua nhất: cứ thấy cảnh buồn là viết nhạc buồn, cảnh vui viết nhạc vui, kết
quả là cả phim một màu và mọi cao trào đều bằng nhau. Bốn vai trò:

- **ĐẨY** — cho nhạc chạy hẳn, chiếm sân khấu. Chỉ dành cho một hai đỉnh của cả phim. Dùng nhiều
  là hết đỉnh.
- **NÂNG** — đi cùng nhân vật, có đà nhưng không lấn. Hợp với các mốc chuyển chương.
- **KÌM** — nhạc nhỏ hơn cả cảm xúc đang diễn ra. Nghịch lý nhưng đúng: khi nhân vật đang gồng
  để không gãy, nhạc mà gãy hộ là hỏng.
- **NGHỈ** — gần như không nhạc, chỉ một lớp mỏng. Cả phim đang dồn thì phải có chỗ cho khán giả
  thở, nếu không đến cao trào họ đã kiệt.

Viết vai trò này ra thành một câu **kèm lý do** trước khi viết prompt, và lưu cùng prompt để
người dựng hiểu ý đồ.

**Tỉ lệ có lời / không lời: khoảng 75% có lời, 25% không lời.** Nhạc có lời (soul, gospel, folk,
neo-soul với giọng nữ trầm ấm hợp thể loại drama nhân quả này) tạo được sự đồng hành mà nhạc
không lời khó có. Nhưng phải giữ lại một phần không lời cho những chỗ **lời hát sẽ nói hộ quá
nhiều**:
- khoảnh khắc sinh tử đang diễn ra (lời hát biến nó thành melodrama),
- nhân vật vỡ ra trong im lặng khi không ai nhìn,
- những khung riêng tư nhất (mẹ nhìn con ngủ),
- nhịp NGHỈ.

**Prompt Suno viết như thế nào cho ra nhạc hay:**
- **BPM cụ thể** và mô tả nhịp (walking pace, half-time, laid-back backbeat).
- **Cấu trúc theo thời gian**, không chỉ liệt kê nhạc cụ: mở bằng gì, thêm gì ở giữa, đỉnh ở
  đâu, kết ra sao. Câu quan trọng nhất thường là câu tả **cú rút** — *"rồi tất cả cắt đi chỉ
  còn giọng và piano"*.
- **Giọng hát tả cụ thể** khi có lời: quãng giọng, chất giọng, cách hát (close to the mic,
  almost spoken, cracked at the edges, single-tracked). Đừng chỉ ghi "female vocal".
- **Chủ đề lời, không phải lyrics đầy đủ** — để Suno tự viết nhưng đúng hướng. Nêu cả giọng kể
  (ngôi thứ nhất / thứ hai) và điều cấm: *không đắc thắng, không tự thương thân*.
- **Mix và không khí**: warm analog, tape saturation, dry intimate, expansive high-contrast.
- **Tag ở cuối** như prompt mẫu: các từ khóa thể loại và nhạc cụ, cách nhau bằng dấu phẩy.
- **Kết mở hay kết đóng** — nói rõ. Nhịp giữa phim nên kết lửng; chỉ khung cuối phim mới được
  resolve, và nên resolve trên hợp âm mở để khán giả mang cảm xúc ra khỏi phim.

Hai lựa chọn A/B nên khác nhau ở **cách xử lý**, không phải khác ở mức độ to nhỏ: ví dụ A là
soul ballad giọng nữ với Rhodes, B là folk-gospel giọng nam với organ — cùng một cảm xúc, hai
thế giới âm thanh, nghe xong biết ngay mình muốn phim đi theo chất nào.

## Nguyên lý cốt lõi

1. **Portrait là gốc, full-body và các SF khác là bản mở rộng.** Mọi ảnh phái sinh của một
   nhân vật đều mở đầu bằng `REFS · Nhân vật: REF_..._PORTRAIT` và lặp lại đúng từ khóa
   khuôn mặt/tóc/trang phục đã dùng ở portrait, để không bị "vẽ lệch" thành người khác.

2. **Bất cứ chi tiết trực quan nào cần giống một ảnh đã có (trang phục, đạo cụ, bối cảnh)
   PHẢI đính ảnh đó vào `refs.chars`/`refs.bg` — không chỉ mô tả lại bằng chữ.** Mô tả bằng
   chữ ("đồng phục giống Maya") chỉ là gợi ý mơ hồ, model tự tưởng tượng lại và dễ lệch tông
   màu/form dáng qua mỗi lần tạo. Ảnh tham chiếu mới ép được model copy chính xác pixel-level.

3. **Khi một ảnh tham chiếu chỉ được mượn cho MỘT phần (trang phục/đạo cụ) nhưng có khuôn mặt
   riêng của người khác, một câu dặn "không dùng làm mặt" là KHÔNG ĐỦ trọng số** — model vẫn
   thiên vị copy mặt vì đó là input trực quan mạnh hơn lời cấm bằng chữ. Phải chống bằng nhiều
   lớp cùng lúc: (a) nhắc lệnh cấm ở ít nhất 2 vị trí — mở đầu và ngay trước/sau phần mô tả
   khuôn mặt; (b) mô tả khuôn mặt nhân vật mới bằng đặc điểm TƯƠNG PHẢN CỤ THỂ với ảnh tham
   chiếu (hình dáng mặt, hình mắt, tông da, một chi tiết nhận diện riêng như nốt ruồi) — không
   mô tả chung chung "khác biệt"; (c) đóng khung ngay từ đầu bằng "đây là MỘT NGƯỜI HOÀN TOÀN
   KHÁC" thay vì chỉ "không copy mặt". Nếu vẫn lỗi, tách hẳn 2 bước: tạo mặt nhân vật mới độc
   lập trước (không đính ảnh tham chiếu chéo), rồi mới dùng ảnh đã có mặt riêng để đối chiếu
   trang phục ở bước sau.

4. **Ngoại hình phải phục vụ vai trò kể chuyện, không phải mô tả cho đẹp.** Nếu cốt truyện
   cần giấu một sự thật (thân phận, quan hệ, ý định) thì ngoại hình/trang phục nhân vật đó
   phải chủ động PHỦ ĐỊNH mọi tín hiệu thị giác gợi ý sự thật đó — viết thẳng "TUYỆT ĐỐI KHÔNG..."
   trong prompt, không chỉ im lặng không nhắc tới.

4b. **KHÔNG BAO GIỜ làm xấu nhân vật chính, dù hoàn cảnh trong truyện tệ đến đâu.** Đây là quy tắc
   cứng của thể loại: khán giả phải muốn nhìn và muốn bênh nhân vật chính từ đầu tới cuối. Tuyệt
   đối không thêm vào REF: quầng thâm, hốc hác, da xỉn, tóc rối bù, vẻ tiều tụy, "không trang điểm"
   — kể cả ở những chặng nhân vật đang thất nghiệp, kiệt sức hay gục ngã. Nhan sắc và thần thái
   trong REF phải giữ nguyên vẹn suốt phim.
   Hoàn cảnh khó khăn được kể bằng **bối cảnh** (căn nhà, đồ đạc, khu phố), bằng **cốt truyện**, và
   bằng **diễn xuất ở từng khung phim** (ánh mắt, dáng vai trong SF và prompt video) — không bao giờ
   bằng cách hạ nhan sắc ở ảnh nhân vật gốc. Phân vai rõ: REF giữ NHÂN DẠNG CHUẨN, còn TRẠNG THÁI
   CẢM XÚC là việc của SF và prompt video.

   **Quy tắc này áp dụng cho cả TRANG PHỤC, không chỉ gương mặt.** "Nhân vật nghèo" KHÔNG có nghĩa
   là cho họ mặc đồ xấu, cũ, quê mùa. Người thu nhập thấp ngoài đời vẫn chọn bộ đẹp nhất và chỉn chu
   nhất khi đi việc quan trọng — mô tả "vải thường", "đã sờn", "giày cũ", "bộ đồ tử tế nhất cô có"
   vừa sai thực tế vừa làm nhân vật kém hấp dẫn. Cách viết đúng: dùng từ ngữ TÍCH CỰC cho trang phục
   (thanh lịch, phom đẹp, có gu, tôn dáng, chuyên nghiệp), rồi chỉ chặn phía TRÊN bằng lệnh cấm
   (không đồ hiệu phô trương, không trang sức lớn, không suit may đo kiểu tài phiệt) — KHÔNG chặn
   phía dưới bằng cách mô tả sự cũ kỹ. Luôn kèm câu cấm tường minh: "TUYỆT ĐỐI KHÔNG để trang phục
   trông cũ kỹ, rẻ tiền hay luộm thuộm."

5. **Trang phục/đạo cụ là công cụ truyền tải thân phận xã hội và tính cách**, chọn theo vai
   trò nhân vật trong kịch bản (nghề nghiệp, vị trí gia đình, quyền lực...), không chọn ngẫu
   nhiên cho đẹp mắt.

6. **Dáng đứng/tư thế phản ánh tính cách và trạng thái cảm xúc tại đúng khoảnh khắc đó**,
   không mặc định một dáng trung tính cho mọi nhân vật.

7. **Cấu trúc câu lệnh cố định**: tỉ lệ khung → loại ảnh/ống kính/DOF → mô tả nhân vật
   → bối cảnh/bảng màu-ánh sáng (khóa theo master nếu có) → câu chặn lỗi cuối
   ("không đổi mặt, không chữ, không watermark, không nhân vật trùng lặp..."). Giữ khung
   này nhất quán để dễ so sánh và debug khi ảnh ra sai.

8. **SF không phải master phải mở đầu bằng khối "khóa look từ master"** nêu rõ bối cảnh,
   bảng màu, ánh sáng, trục 180° cần giữ nguyên — nếu không SF sẽ trôi dần khỏi continuity
   của scene.

9. **Sửa ngoại hình một nhân vật thì phải rà ngược mọi SF đã tồn tại có mô tả ngoại hình cũ
   của nhân vật đó** (không chỉ sửa REF) — SF cũ dùng lại chữ mô tả cũ (vd. tên món trang
   phục) sẽ lệch với REF mới nếu không đồng bộ. Nguyên lý này áp dụng cho MỌI thứ được khóa
   ở master (số lượng nhân vật phụ, vị trí, nhóm/hàng người...), không chỉ ngoại hình — sửa
   bố cục ở master thì phải rà ngược các SF con đang mô tả lại cùng nhóm người/vị trí đó.

10. **Chỉ thêm chi tiết mới khi nhất quán với desc/prompt đã duyệt trước đó** — full-body/SF
    phái sinh bổ sung phần còn thiếu (thân dưới, giày, dáng đứng...), không tự sáng tạo lại
    phần đã mô tả ở ảnh gốc.

11. **Trước khi thêm một nhân vật vào master (hoặc bất kỳ SF nào), tự hỏi: nhân vật đó có
    THỰC SỰ hành động/được nhắc tới trong đúng khoảnh khắc của SF này không?** Nếu nhân vật
    chưa vào nhịp của beat đó (chỉ xuất hiện vài câu thoại sau), đừng nhét vào cho "đủ mặt" —
    việc đó tạo ra toàn bộ lớp rủi ro phải xử lý thêm (bố cục dễ nhầm nhóm, bảng tên phải
    quản lý, thêm ref phải đính). Cách rẻ nhất để tránh lỗi địa lý/tên là loại bỏ nhân vật
    không cần thiết khỏi khung, không phải thêm quy tắc để kiểm soát sự có mặt của họ. Chỉ khi
    nhân vật thật sự cần đồng-hiện diện (cả hai cùng hành động/đối thoại trong SF đó) mới áp
    dụng bản đồ vị trí + danh sách chữ hợp lệ ở nguyên lý 12-13 bên dưới.

12. **Master frame phải có "bản đồ vị trí" tường minh, không chỉ mô tả bằng văn xuôi.** Vì
    mọi SF sau đều bám bố cục của master, việc mô tả vị trí chỉ bằng câu văn ("phía sau Helen
    có khách xếp hàng") dễ bị model diễn giải mơ hồ về mặt địa lý (ai thuộc nhóm/hàng nào,
    đứng ở quầy nào) — hậu quả là chi tiết quan trọng cho thoại (vd. khách giục ngay sau nhân
    vật) bị lạc sang một nhóm khác trong ảnh, đọc sai ý. Cách phòng: mở đầu phần bố cục bằng
    một danh sách vị trí theo mốc cụ thể (% chiều ngang khung hình, hoặc số quầy/landmark cố
    định), chỉ rõ nhân vật/nhóm nào thuộc cùng một "line"/nhóm hành động nào, và tách các nhóm
    dễ gây nhầm lẫn (hai hàng người, hai quầy) bằng một khoảng trống/landmark trung gian rõ
    ràng (vd. "quầy số 4 bỏ trống ở giữa") thay vì để chúng liền kề mơ hồ.

13. **Mọi chữ có thể xuất hiện trên ảnh (bảng tên, biển số, logo) phải được liệt kê tường minh
    và đầy đủ trong một câu "chữ được phép xuất hiện" ở cuối prompt — thiếu một tên là model
    sẽ tự bịa tên khác để lấp chỗ trống.** Một câu cấm chung chung ("không chữ dễ đọc ngoài
    bảng tên X") chỉ chặn được đúng cái tên đã nêu; bất kỳ nhân vật có bảng tên nào khác xuất
    hiện trong khung mà không được liệt kê ra đều có nguy cơ bị gắn nhầm tên. Khi master có
    nhiều nhân vật đeo bảng tên, phải liệt kê đủ tất cả trong cùng một câu, kèm yêu cầu đánh
    vần chính xác từng tên.

14. **Phân biệt ba loại vật thể trong khung — chỉ loại thứ ba mới là "thừa".** Đây là ranh giới
    hay bị gộp nhầm, dẫn tới vừa thiếu vừa thừa cùng lúc:

    - **(a) Vật dụng THUỘC VỀ bối cảnh** — có mặt tự nhiên vì loại không gian đó ngoài đời luôn có,
      dù không ai nhắc tới trong thoại: giấy tờ/hồ sơ trên bàn làm việc, nồi niêu trong bếp, sách
      trên kệ lớp học, hàng hóa trên kệ siêu thị. **BẮT BUỘC có, và không cần biện minh.** Thiếu
      chúng thì không gian đọc như phim trường trống. Tả ở mức khái quát ("giấy tờ công việc bày
      tự nhiên"), không cần liệt kê chi li từng món, và cho chúng mờ/lùi ra nền để không tranh
      sự chú ý.
    - **(b) Đạo cụ THAM GIA HÀNH ĐỘNG** — vật nhân vật cầm, đưa, đẩy, nhìn trong đúng beat này
      (tờ quyết định, chai nước, chìa khóa). **Tả cụ thể, đặt tách bạch khỏi nhóm (a) để mắt nhận
      ra ngay.** Đây là nhóm đáng dành SF insert riêng và đáng rà kịch bản để gieo-trả (bài học 7).
    - **(c) Đạo cụ MINH HỌA một chi tiết nội tâm/lời thoại** — vật được cố ý cài vào chỉ để "nói hộ"
      một thông tin về nhân vật (khung ảnh con cái để minh họa "tôi có con", bằng khen để minh họa
      "tôi từng giỏi"). **ĐÂY MỚI LÀ THỨ THỪA — loại bỏ.** Thông tin nội tâm được truyền tải MẠNH
      HƠN nhiều qua ngôn ngữ cơ thể và biểu cảm (dáng ngồi sụp, ánh mắt né tránh, vai xuôi) so với
      một vật thể đặt trong khung để chỉ trỏ vào. Khi đã quyết loại một vật thuộc nhóm này, viết
      lệnh cấm tường minh trong prompt ("TUYỆT ĐỐI KHÔNG đặt khung ảnh gia đình...") thay vì chỉ
      im lặng không nhắc, vì model sẽ tự thêm vào theo mô-típ quen thuộc của loại bối cảnh đó.

    Nguyên tắc chung: cảm xúc nhân vật + bố cục chuẩn là thứ chính; vật thể chỉ để không gian có
    thật. Khi phân vân về một vật thuộc nhóm (c), luôn chọn bỏ.

## Tích lũy bài học

Khi user chỉnh sửa hoặc phát hiện lỗi trong cách viết prompt: sau khi sửa xong, chưng cất
thành bài học **ở tầng nguyên lý** (áp dụng cho mọi nhân vật/scene, không nhắc chi tiết của
dự án cụ thể) và ghi vào `references/bai-hoc.md`. Nếu bài học mâu thuẫn với một nguyên lý ở
trên, báo user và đề xuất sửa nguyên lý thay vì chỉ ghi chồng lên.
