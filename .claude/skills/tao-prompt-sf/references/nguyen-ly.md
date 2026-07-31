# Nguyên lý cốt lõi

## Mục lục
- Nguyên lý cốt lõi

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
