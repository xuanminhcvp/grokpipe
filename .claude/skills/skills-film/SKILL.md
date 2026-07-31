---
name: skills-film
description: Viết/sửa prompt ảnh nhân vật và Start Frame (SF) trong sf-board.json cho các dự án PIPELINE-*.project. Dùng skill này mỗi khi tạo REF nhân vật mới, tạo SF cho một scene, hoặc sửa ngoại hình/trang phục nhân vật trong board — kể cả khi user chỉ nói "tạo SF cho scene X" mà không nhắc rõ kỹ thuật.
---

# Viết prompt ảnh cho SF Board

Bạn đang soạn prompt tiếng Việt để một model tạo ảnh (qua ChatGPT/CDP) render ảnh nhân vật
tham chiếu (REF) và Start Frame (SF) cho từng scene, lưu trong `sf-board.json` của
dự án `PIPELINE-*.project`.

Mọi **luật đang có hiệu lực** nằm trong file này và 3 file `references/` bên dưới — làm theo
đó là đủ. `references/bai-hoc.md` là **kho lịch sử 40 bài** (~15k token): chỉ mở khi (a) gặp
lỗi lạ muốn tra đã từng gặp chưa, (b) cuối việc để ghi bài mới. **Đừng đọc nó trước mỗi lần
viết prompt** — luật đã được chưng cất lên đây rồi.

## Cấu trúc dữ liệu cần biết

- Scene `REF` chứa các SF nhân vật: mỗi nhân vật có `REF_<TEN>_PORTRAIT` (chân dung 2:3)
  và `REF_<TEN>_FULL` (toàn thân 9:16, luôn tham chiếu ngược lại PORTRAIT qua `refs.chars`).
- **MỖI NHÂN VẬT CHỈ CÓ MỘT PORTRAIT DUY NHẤT, dùng cho cả phim.** Portrait là ảnh chuẩn của
  KHUÔN MẶT — không tạo lại portrait cho từng bộ đồ.
- Trang phục trong ảnh portrait có thể rò sang SF ở một tỉ lệ nhỏ. **User đã quyết KHÔNG xử lý việc này** — tỉ lệ lỗi thấp, không đáng đổi cả quy trình. TUYỆT ĐỐI KHÔNG tự ý crop ảnh portrait đã duyệt và không ép portrait về 1:1 cận mặt (xem bài học 46).
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
- **MỌI NHÂN VẬT XUẤT HIỆN TRONG KHUNG ĐỀU PHẢI CÓ REF — KỂ CẢ NGƯỜI Ở TIỀN CẢNH QUAY LƯNG,
  OUT NÉT, HAY CHỈ THẤY VAI/GÁY.** Đây là chỗ cực dễ sót: khung OTS hay CU thường mô tả "rìa
  trái là vai và gáy của X, out nét làm khung viền" rồi chỉ đính ref của người nét rõ. Sai —
  cái vai out nét đó vẫn phải ĐÚNG NGƯỜI và ĐÚNG BỘ ĐỒ, nếu không model tự bịa ra một người
  khác với quần áo khác, và khung OTS lộ ngay vì màu áo lệch với khung đối diện.
  Quy tắc rà: **tên nhân vật nào xuất hiện trong prompt thì phải có cặp portrait + full của
  đúng bộ đồ cảnh đó trong `refs.chars`** — trừ khi prompt ghi rõ "X KHÔNG có trong khung".
  REF không có trần số ảnh (bài học 39) nên cứ đính đủ.
- **REF KHÔNG CÓ TRẦN SỐ ẢNH — đính ĐỦ, không đính thiếu** (quyết định của user, ghi đè thử
  nghiệm "trần 3 ảnh" cũ). Mỗi nhân vật trong khung đính CẢ portrait (khuôn mặt) LẪN full-body
  của đúng bộ đồ cảnh đó, cộng thêm master bối cảnh — bao nhiêu nhân vật thì bấy nhiêu cặp.
  Khi nhân dạng ra lệch, KHÔNG chữa bằng cách bỏ bớt ref: chữa bằng render lại, kiểm tra ảnh
  có thật sự được đính không, và dòng khóa chữ ngắn (xem bài học 39).
- Luôn kèm **một dòng ngắn** khóa những gì ảnh không tự nói nổi: chủng tộc, kiểu tóc, màu
  quần áo. Phim này Maya da đen / Helen da trắng là điểm cốt lõi — dòng khóa chủng tộc phải
  có ở mọi SF có hai người, kể cả khi ref đang ra đúng.
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

## MỘT CLIP = MỘT SHOT LIỀN. KHÔNG BAO GIỜ có chuyển cảnh bên trong một clip.

Đây là quy tắc CỨNG của cả pipeline, không phải khuyến nghị. Grok dựng mỗi clip từ ĐÚNG MỘT start
frame; nó không cắt được giữa chừng. Ép nó cắt thì hoặc nó bỏ qua yêu cầu, hoặc nó biến dạng cả
clip (nhân vật morph giữa hai không gian, bối cảnh trôi).

**Hệ quả bắt buộc: mỗi lần đổi góc máy, đổi cỡ cảnh hoặc đổi địa điểm là PHẢI có một SF riêng và
một shot riêng.** Không có cách nào khác. Muốn hai không gian thì phải hai clip.

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

## Tích lũy bài học

Khi user chỉnh sửa hoặc phát hiện lỗi trong cách viết prompt: sau khi sửa xong, chưng cất
thành bài học **ở tầng nguyên lý** (áp dụng cho mọi nhân vật/scene, không nhắc chi tiết của
dự án cụ thể) và ghi vào `references/bai-hoc.md`. Nếu bài học mâu thuẫn với một nguyên lý ở
trên, báo user và đề xuất sửa nguyên lý thay vì chỉ ghi chồng lên.

## Xoá hay đổi tên SF — phải quét shot mồ côi

Xoá/đổi id một SF xong **bắt buộc** quét lại toàn bộ `shots[].sf` đối chiếu danh sách SF
còn sống. Shot trỏ vào id đã chết sẽ hỏng ngay khi render video. Shot mồ côi thì gán lại
góc cùng pha không gian, hoặc dựng lại SF. Chạy lượt quét này **lần cuối ngay trước khi
render video hàng loạt**.

Cùng lúc đó, kiểm luôn media mồ côi: ảnh trong `assets/` và video trong `videos/` không
thuộc SF/shot nào là tàn dư của kịch bản cũ.

## Tài liệu chi tiết — đọc khi cần

Đọc **trước khi** làm việc tương ứng, đừng đoán:

- **Chọn góc máy cho scene, kiểm tra tụt pha không gian** → [references/goc-may.md](references/goc-may.md)
- **Viết prompt video (có thoại / nhịp lặng) và prompt nhạc Suno** → [references/prompt-video.md](references/prompt-video.md)
- **Nguyên lý nền: ref, tham chiếu chéo, ngoại hình phục vụ kể chuyện** → [references/nguyen-ly.md](references/nguyen-ly.md)
- **Mẫu prompt Suno đã được user duyệt** → [references/mau-suno.md](references/mau-suno.md)
- **Bài học tích lũy (40 bài + mục vận hành)** → [references/bai-hoc.md](references/bai-hoc.md)
