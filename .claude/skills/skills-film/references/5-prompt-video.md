# Bước 5 — Prompt video và prompt nhạc

## Mục lục
- Prompt video (Grok image-to-video) — FORM CHUẨN, dùng đúng khung này
- Prompt video cho NHỊP KHÔNG THOẠI — viết cảm xúc, đừng viết cử chỉ
- Prompt nhạc nền Suno cho nhịp không thoại

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

**Trước khi viết bất kỳ prompt Suno nào, mở `references/mau-suno.md`** — 4 prompt thật đã qua
vòng sửa và được user chốt "đang làm ok, cứ giữ như vậy", mỗi vai trò một mẫu. Viết theo đúng
chất lượng và cấu trúc đó.

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
