# Bài học tích lũy

38 bài rút từ phản hồi của user khi làm phim. Mỗi bài: **bối cảnh một dòng** + **quy tắc
giữ nguyên văn**. Phần thuật lại diễn biến đã cắt — giá trị nằm ở quy tắc.

Ghi bài mới: viết ở tầng nguyên lý (dùng được cho mọi phim), không nhắc tên nhân vật cụ
thể trừ khi cần minh họa. Bài mâu thuẫn bài cũ thì **sửa bài cũ**, đừng thêm bài chồng lên.

## Mục lục

- 1. REF trang phục: cần giống ảnh nào thì ĐÍNH ảnh đó, mỗi bộ đồ một REF
- 2. Ngoại hình nhân vật phải chủ động phủ định tín hiệu cốt truyện chưa nên lộ
- 3. Dặn "không dùng làm mặt" một lần là không đủ trọng số — model vẫn copy mặt
- 4. Master frame mô tả bố cục bằng văn xuôi khiến địa lý bị đọc sai
- 5. Không liệt kê hết bảng tên hợp lệ → model tự bịa tên cho nhân vật còn lại
- 6. Đừng vá triệu chứng — hỏi trước xem nhân vật có cần ở đó không
- 7. Đạo cụ bị bỏ trống mô tả là bỏ lỡ cơ hội nối với chi tiết kịch bản khác
- 8. Thiếu checklist hệ thống → sót thành phần khung hình lần lượt từng cái một
- 9. Sót nội thất cơ bản vì "hiển nhiên", lại thừa đạo cụ vì "khai thác kịch bản"
- 10. Chữ nhỏ trong ảnh wide dễ nhòe thành ký tự vô nghĩa
- 11. Skill dạy viết từng prompt nhưng không dạy thiết kế BỘ góc của cả scene
- 12. Ba ràng buộc của một shot — và đừng phát biểu quy tắc chặt hơn thực tế
- 13. Thoại "gọi/triệu tập" không cùng không gian với phần còn lại của cảnh
- 14. Prompt video có FORM CHUẨN riêng — không được tự chế format
- 15. Sửa thoại sau khi prompt đã viết → prompt lệch âm thầm
- 16. SF insert thuần đạo cụ là khung chết khi thành video
- 17. Tái dùng master trước khi nghĩ tới dựng SF mới
- 18. Thoại phải khớp với BỐ CỤC KHÔNG GIAN mình vừa dựng ra
- 19. Cảnh 3 người cần tầng "rộng vừa", không nhảy thẳng từ master xuống cận
- 20. SF là frame ĐẦU clip → phải bằng trạng thái KẾT THÚC của clip trước
- 21. Nhân vật chính phải LUÔN đẹp — 'nghèo' nằm ở bối cảnh, không ở bộ đồ
- 22. Khối "Nhận diện" tả trang phục càng chi tiết, model vẽ càng láo
- 23. Cùng một không gian thì phải THAM CHIẾU master cũ, kể cả khi là phòng khác
- 24. Nhịp không thoại — vì sao cần, loại nào, bao nhiêu là đủ
- 25. Ghi bài học rồi vẫn vi phạm, vì áp dụng sai phạm vi
- 26. Lạm dụng chữa bằng lệnh cấm là sai, chữa bằng danh sách cũng sai
- 27. Chuyển động không có tác nhân — lỗi phi vật lý trong nhịp không thoại
- 28. Nhạc nền — quyết VAI TRÒ trước, viết prompt sau
- 29. User thay ảnh master thì mọi khối "khóa look" con thành nói dối
- 30. Nhân dạng lệch dù có REF — và một chẩn đoán sai đã bị user sửa lại: REF không có trần
- 31. Kịch bản người viết có hard-cut trong một clip — tách thành hai shot, và nói rõ vì sao
- 32. Khung ba lớp chiều sâu đẩy model lên góc bird's-eye — và câu phủ định vẫn vẽ ra thứ bị cấm
- 33. Thoại nhân vật chính lúc làm việc tốt — người tốt thật không thuyết minh việc tốt của mình
- 34. Hành động đỉnh điểm ở GIỮA chuyển động là thứ model không vẽ nổi — thiết kế khoảnh khắc TRƯỚC hoặc SAU nó
- 35. Tinh chỉnh thoại nhiều vòng sẽ đánh rơi câu gốc — diff bằng máy sau mỗi vòng, đừng tin trí nhớ
- 36. Công thức mật độ SF do user chốt — phút × 4; và góc cận-vật bị hạ cấp
- 37. Người ở tiền cảnh quay lưng / out nét VẪN phải có ref
- 38. SF khoá vào khoảnh khắc thì chỉ dùng được đúng một lần

## Vận hành & gỡ lỗi hạ tầng

Không phải bài học viết prompt, nhưng đủ đắt để ghi lại.

- **Nhiều job lỗi cùng lúc = nghi HẠ TẦNG trước, đừng vội sửa prompt.** Hết RAM, Chrome crash, tab treo đều biểu hiện thành 'ảnh ra sai' hàng loạt. Sửa prompt khi gốc là hạ tầng thì vừa mất công vừa làm hỏng prompt đang đúng.
- **Cơ chế tự chữa im lặng phải kiểm CẢ HAI chiều.** Hàm nhận diện 'tab chết' thiếu đúng một từ khoá (`target crashed`) là mọi job crash chết luôn thay vì tự mở lại phiên — mà nhìn từ ngoài không phân biệt được.
- **`except: return False` biến lỗi lập trình thành trạng thái hợp lệ.** Cổng chặn bị nổ `NameError` vẫn hiện đúng chữ 'ĐANG KHÓA'; user không mở được mà không ai biết vì sao. Với code bảo vệ, log exception trước khi trả về mặc định an toàn.
- **Xoá/đổi tên SF xong PHẢI quét shot mồ côi** — `shots[].sf` trỏ vào id đã chết sẽ hỏng ngay khi render video. Quét lần cuối ngay trước khi render hàng loạt. (Đã lên SKILL.md.)
- **Không tự leo thang khi user chưa yêu cầu.** Gặp lỗi tỉ lệ thấp, đề xuất một cách rồi chờ; đừng tự chuyển sang giải pháp mạnh hơn (crop ảnh, sửa ảnh đã duyệt). Bản user đã duyệt hoặc tự dán vào là **chuẩn tuyệt đối** — nghi sai thì báo, để user quyết.

## 1. REF trang phục: cần giống ảnh nào thì ĐÍNH ảnh đó, mỗi bộ đồ một REF

*Gộp từ 3 lần user bắt cùng một lỗi ở ba mức: nhân vật phụ, nhân vật chính đổi đồ, và trang phục 'hiển nhiên theo bối cảnh'.*

**1. Cần trông giống một ảnh đã có thì phải đính ảnh đó vào `refs.chars`** — không chỉ nhắc tên trong lời văn. Mô tả bằng chữ chỉ là gợi ý mơ hồ, model tự tưởng tượng lại và lệch dần qua mỗi lần tạo.

**2. Mỗi bộ trang phục là một REF riêng.** Rà kịch bản NGAY TỪ ĐẦU liệt kê các trạng thái trang phục của mỗi nhân vật (thường trùng các chặng cốt truyện), tạo cặp `REF_<TÊN>_<TRẠNG THÁI>_PORTRAIT` + `_FULL` cho từng bộ. SF đính đúng REF của trạng thái đó — không bao giờ mô tả bộ đồ mới bằng chữ trên nền REF mặc bộ khác.

Cách tạo REF trang phục mới: đính REF gốc để lấy KHUÔN MẶT + TÓC + TÔNG DA, rồi chống copy trang phục bằng nhiều lớp (xem bài về lệnh cấm nhiều lớp) nhưng đảo chiều — nêu ĐÍCH DANH bộ đồ trong ảnh tham chiếu và cấm dùng nó, mô tả bộ mới bằng đặc điểm TƯƠNG PHẢN cụ thể, nhắc lại lệnh cấm ở cuối prompt.

**3. Áp cho MỌI nhân vật, không riêng nhân vật chính.** Rút ra một quy tắc REF thì phải QUÉT TOÀN BỘ dự án. Cách quét rẻ: grep từ khóa trang phục (tên món đồ, chất liệu, phụ kiện) trong prompt mọi SF — chỗ nào có nghĩa là chỗ đó đang tả bằng chữ thay vì đính REF.

Trang phục 'bắt buộc theo bối cảnh' (đồng phục bệnh nhân, đồ bảo hộ, áo tù) **cũng là một trạng thái cần REF riêng** — dễ bỏ qua vì cảm giác nó hiển nhiên nên tả bằng chữ là đủ.

**4. Tối đa 1 portrait + 1 full-body cho mỗi nhân vật trong một SF** — đúng bộ đồ của cảnh đó. Board chỉ tự kèm `REF_X_FULL` khi SF chưa chỉ định sẵn bản `REF_X_*_FULL` nào.

---
## 2. Ngoại hình nhân vật phải chủ động phủ định tín hiệu cốt truyện chưa nên lộ

*Bối cảnh:* User yêu cầu một nhân vật (thân phận thật sự giàu có nhưng cần giấu ở đầu phim) phải trông "bình thường" để hành động giúp đỡ của nhân vật chính không bị đọc là "thấy giàu mới giúp".

**Nguyên tắc rút ra:** ngoại hình/trang phục phải được thiết kế để phục vụ đúng thời điểm lộ
thông tin trong cốt truyện. Nếu một sự thật cần giữ kín, prompt phải chủ động liệt kê và cấm
rõ từng tín hiệu thị giác có thể tiết lộ nó ("TUYỆT ĐỐI KHÔNG khăn lụa, không trang sức đắt
tiền..."), không chỉ đơn giản là không nhắc tới — vì không nhắc tới vẫn để model tự suy diễn
theo tuổi tác/chủng tộc/bối cảnh sẵn có.
(Đã đưa vào SKILL.md nguyên lý 4.)

---
## 3. Dặn "không dùng làm mặt" một lần là không đủ trọng số — model vẫn copy mặt

*Bối cảnh:* Áp dụng bài học 1 (đính ảnh nhân vật A làm chuẩn trang phục cho nhân vật B, kèm một câu dặn "không dùng làm khuôn mặt") vẫn ra kết quả khuôn mặt B giống hệt A.

**Nguyên tắc rút ra:** khi một ảnh tham chiếu chỉ được mượn cho MỘT phần (trang phục/đạo cụ)
nhưng có khuôn mặt riêng của người khác, phải chống copy nhầm mặt bằng nhiều lớp cùng lúc,
không chỉ một câu dặn:
1. Nhắc lệnh cấm ở ÍT NHẤT 2 vị trí trong prompt — mở đầu và ngay trước/sau phần mô tả khuôn mặt.
2. Mô tả khuôn mặt nhân vật mới bằng các đặc điểm TƯƠNG PHẢN CỤ THỂ với ảnh tham chiếu (hình
   dáng mặt, hình mắt, tông da, một chi tiết nhận diện riêng như nốt ruồi) — không mô tả chung
   chung kiểu "gương mặt khác biệt", vì model cần input cụ thể để lệch ra khỏi mặc định.
3. Ghi rõ "đây là MỘT NGƯỜI HOÀN TOÀN KHÁC" thay vì chỉ "không copy mặt" — đóng khung nhận thức
   đúng ngay từ đầu thay vì để model tự suy luận ranh giới giữa "giống" và "không giống".
Nếu vẫn lặp lỗi sau khi áp dụng cả 3 lớp, cân nhắc phương án khác: tạo mặt B trước độc lập
(không đính ảnh A), rồi mới tạo bản trang phục bằng cách đính ảnh B đã có mặt riêng + ảnh A
chỉ để đối chiếu trang phục ở bước sau, tách hẳn 2 bước thay vì gộp một lần.
(Đã cập nhật SKILL.md nguyên lý 3.)

---
## 4. Master frame mô tả bố cục bằng văn xuôi khiến địa lý bị đọc sai

*Bối cảnh:* Prompt master chỉ viết bằng câu văn "phía sau [nhân vật chính] có khách xếp hàng" mà không gắn mốc vị trí cụ thể.

**Nguyên tắc rút ra:** bố cục master phải có bản đồ vị trí tường minh (mốc %, số quầy, landmark
cố định) thay vì chỉ mô tả tương đối bằng lời; các nhóm/hàng người dễ gây nhầm lẫn phải được
tách bằng một khoảng trống hoặc landmark trung gian rõ ràng thay vì đặt liền kề mơ hồ.
(Đã đưa vào SKILL.md nguyên lý 11.)

---
## 5. Không liệt kê hết bảng tên hợp lệ → model tự bịa tên cho nhân vật còn lại

*Bối cảnh:* Master có 2 nhân vật đeo bảng tên nhưng câu chặn cuối chỉ nêu "không chữ dễ đọc ngoài bảng tên [nhân vật A]" — không nhắc bảng tên của nhân vật B.

**Nguyên tắc rút ra:** khi master có nhiều nhân vật đeo bảng tên/chữ nhận diện, phải liệt kê
ĐẦY ĐỦ tất cả tên hợp lệ trong cùng một câu "chữ được phép xuất hiện", kèm yêu cầu đánh vần
chính xác — không liệt kê một phần rồi mặc định phần còn lại sẽ tự đúng.
(Đã đưa vào SKILL.md nguyên lý 13.)

---
## 6. Đừng vá triệu chứng — hỏi trước xem nhân vật có cần ở đó không

*Bối cảnh:* Sau khi vá bài học 4 và 5 (thêm bản đồ vị trí + danh sách chữ hợp lệ) cho một master có 3 nhân vật, user chỉ ra gốc rễ: nhân vật thứ ba (một nhân viên khác) CHƯA hề hành động hay được nhắc tới ở đúng khoảnh khắc của master — cô ấy chỉ xuất hiện vài câu thoại sau, và đã có một SF riêng giới thiệu…

**Nguyên tắc rút ra:** khi một SF ra lỗi vì có nhiều nhân vật (nhầm nhóm, nhầm tên...), câu hỏi
đầu tiên không phải "làm sao mô tả rõ hơn để tách họ ra" mà là "nhân vật đó có thực sự cần ở
đây không". Loại bỏ nhân vật thừa khỏi khung luôn rẻ và chắc hơn việc thêm quy tắc bố cục/chữ
để kiểm soát sự có mặt của họ. Chỉ dùng bản đồ vị trí + danh sách chữ hợp lệ (bài học 4, 5) khi
nhân vật đó thật sự phải đồng-hiện diện vì cùng hành động/đối thoại trong đúng SF đó.
(Đã đưa vào SKILL.md nguyên lý 11, đặt trước nguyên lý 12-13 để nhắc kiểm tra điều kiện này trước.)

---
## 7. Đạo cụ bị bỏ trống mô tả là bỏ lỡ cơ hội nối với chi tiết kịch bản khác

*Bối cảnh:* Xe đẩy hàng của một nhân vật chỉ được nhắc chung chung ("xe đẩy hàng của bà") mà không tả nội dung cụ thể.

**Nguyên tắc rút ra:** bất kỳ đạo cụ nào xuất hiện trong khung (giỏ hàng, túi xách, vật cầm
tay...) đều nên được mô tả cụ thể thay vì để chung chung, và trước khi chốt nội dung đạo cụ đó,
rà lại toàn bộ kịch bản xem có chi tiết/thoại nào ở cảnh khác nhắc đến cùng loại đồ vật không —
nếu có, cố tình cho đạo cụ ở cảnh đầu trùng khớp để tạo hiệu ứng "gieo trước, trả sau". Đồng
thời nội dung đạo cụ nên nhất quán với tính cách/hoàn cảnh nhân vật đã chốt (ví dụ: giỏ hàng
vơi, đồ bình dân, không món gì đắt tiền, nếu nhân vật đó cần trông giản dị theo nguyên lý 4).
(Đã ghi nhận là một hạng mục cần rà khi viết master — bổ sung vào phần "Cấu trúc dữ liệu cần
biết" trong SKILL.md.)

---
## 8. Thiếu checklist hệ thống → sót thành phần khung hình lần lượt từng cái một

*Bối cảnh:* User phải chỉ ra từng thứ bị thiếu qua nhiều lượt: khách hàng đứng sai chỗ → đạo cụ giỏ hàng chưa tả → khách xếp hàng không có xe đẩy → nền không có người mua sắm → mức độ đông đúc sai với chi tiết kịch bản.

**Nguyên tắc rút ra:** với loại công việc mà đầu ra có nhiều thành phần độc lập (khung hình có
nhân vật chính, nhân vật phụ, quần chúng nền, đạo cụ từng người, thời điểm, ánh sáng, chữ...),
việc tích lũy bài học rời rạc là không đủ — phải có một CHECKLIST đặt ở đầu skill, rà đủ mọi
mục trước khi viết, mỗi mục hoặc có quyết định rõ hoặc có lý do chủ động loại bỏ. Bỏ trống một
mục nghĩa là giao quyền quyết định cho model, và model thường quyết định sai. Đặc biệt lưu ý
các mục "vô hình" dễ quên vì không ai nhắc: quần chúng nền, đạo cụ của nhân vật phụ, mức độ
đông đúc/thời điểm — những thứ mà đời thực luôn có nhưng prompt thì hay để trống.

Riêng mức độ đông đúc/thời điểm: phải rà kịch bản xem đã có câu thoại nào ẤN ĐỊNH chi tiết đó
chưa (nhân vật nhắc "giờ cao điểm", "sáng sớm", "cuối tuần") — nếu có mà ảnh không khớp thì
mâu thuẫn nội tại giữa hình và lời, khán giả cảm nhận được ngay.
(Đã thêm mục "CHECKLIST BẮT BUỘC" 9 điểm vào đầu SKILL.md, trước phần nguyên lý.)

---
## 9. Sót nội thất cơ bản vì "hiển nhiên", lại thừa đạo cụ vì "khai thác kịch bản"

*Bối cảnh:* master phòng làm việc thiếu GHẾ — cơ bản đến mức không ai nghĩ phải viết ra; một SF con lại yêu cầu nhân vật "ngồi xuống ghế" nên buộc phải bịa ra chiếc ghế không tồn tại.

**Hai nguyên tắc bổ sung cho nhau:**

1. **Nội thất cơ bản của loại bối cảnh phải nằm trong checklist**, tách riêng khỏi mục "đạo
   cụ" — nó thuộc loại kiến thức "hiển nhiên" nên bị bỏ qua theo cơ chế khác. Kèm bước KIỂM
   TRA CHÉO: rà mọi SF con, SF nào cần tư thế dựa vào đồ nội thất (ngồi/tựa/nằm) thì món đó
   phải có sẵn trong master.
2. **Checklist là để không bỏ sót, KHÔNG phải để nhồi cho đủ.** Biến mọi chi tiết trong thoại
   thành vật thể đặt trong khung là minh họa thô, làm phân tán khỏi gương mặt. Nội tâm truyền
   tải mạnh hơn qua ngôn ngữ cơ thể và biểu cảm.

---
## 10. Chữ nhỏ trong ảnh wide dễ nhòe thành ký tự vô nghĩa

*Bối cảnh:* Bảng tên nhân vật trong một ảnh medium-wide render ra thành các ký tự méo mó vô nghĩa, dù prompt đã liệt kê đúng danh sách chữ được phép (bài học 5).

**Nguyên tắc rút ra:** trong câu "chữ được phép xuất hiện", ngoài việc liệt kê đủ và yêu cầu đánh
vần chính xác, phải thêm yêu cầu "in RÕ RÀNG DỄ ĐỌC, không nhòe thành ký tự vô nghĩa". Với khung
càng rộng thì chữ càng nhỏ và rủi ro càng cao — cân nhắc chấp nhận chữ mờ ở master và chỉ đòi chữ
sắc nét ở các SF cận, thay vì kỳ vọng mọi khung đều đọc được chữ.
(Đã bổ sung vào mục 9 của CHECKLIST trong SKILL.md.)

---
## 11. Skill dạy viết từng prompt nhưng không dạy thiết kế BỘ góc của cả scene

*Bối cảnh:* Sau khi render đủ bộ SF một cảnh hội thoại dài (~53s), user nhận xét: các góc đều đúng nhưng phần hội thoại chính chỉ ping-pong giữa 2 góc cận lặp đi lặp lại — cần thêm 2-3 góc bổ sung (gần hơn, hoặc nghiêng 3/4), không cần khác hoàn toàn, và không được cực đoan.

**Nguyên tắc rút ra:** checklist theo từng prompt là chưa đủ — cần một tầng thiết kế trên nó:
BỘ GÓC (coverage) của cả scene, quyết định trước khi viết từng prompt. Ba quy tắc chính:
1. Số góc tỷ lệ với thời lượng cảnh (<20s: khung chuẩn đủ; 20-40s: +1-2; >40s: +3-5). Dấu hiệu
   thiếu góc: một SF hội thoại bị dùng cho 3+ shot.
2. Góc bổ sung nằm trong vùng an toàn (medium 3/4 lệch ~45°, CU chặt hơn một nấc cho câu đắt,
   two-shot nghiêng đổi nhịp) — tuyệt đối không góc cực đoan (bird's-eye, dutch mạnh, fisheye,
   extreme CU) vì phá tông hiện thực của thể loại.
3. Cảnh 3-4+ người cần đủ phổ ba tầng: toàn thể / nhóm 2-3 người / đơn — tầng nhóm trung gian
   là tầng hay bị quên nhất.
(Đã thêm mục "Bộ góc máy (coverage) của một scene" vào SKILL.md, giữa CHECKLIST và Nguyên lý cốt lõi.)

---
## 12. Ba ràng buộc của một shot — và đừng phát biểu quy tắc chặt hơn thực tế

**Ba chuẩn là hệ quả của nhau, không phải ba luật rời:** 10 giây/clip → 2–3 lượt thoại → cần khung hai người. Nắm sợi dây nhân quả thì áp dụng nhất quán; coi là ba luật rời thì rất dễ thỏa mãn cái này mà vi phạm cái kia.

**Ước lượng:** tiếng Anh ~2,5 từ/giây → 10s ≈ 25 từ. Nhắm sát mức đó, không dư quá 2 giây. Phải TÍNH số từ, đừng ước lượng bằng cảm giác.

**Tỉ lệ thời lượng: 70% shot 10s, 30% shot 6s.** Khi tỉ lệ này xung đột với việc lấp kín thời lượng thì **lấp kín thắng** — thà một shot 6s đầy còn hơn 10s có 3 giây nhân vật đứng im.

**Tách một câu dài thành hai shot thì giữ nguyên 100% chữ của kịch bản gốc**, chỉ đổi góc giữa chừng — không cắt bớt, không diễn đạt lại.

**Phân biệt 'một người NÓI' với 'một người TRONG KHUNG'.** Quy tắc cứng chỉ là cái thứ nhất. Two-shot vẫn hợp lệ khi một người nói còn người kia phản ứng im lặng — thường là khung giàu hơn vì thấy được phản ứng người nghe. Nhắm **35–45% số shot** dùng khung từ 2 người trở lên; để dành cận đơn cho câu đắt nhất và khoảnh khắc nội tâm.

*Bài học meta:* khi phát biểu một quy tắc cứng, phát biểu đúng ở mức ràng buộc THẬT SỰ, không chặt hơn cho 'an toàn' — quy tắc quá chặt chặn mất lựa chọn hợp lệ và đẩy sang lỗi khác (ở đây: chia vụn shot, lạm dụng khung solo). Khi một ràng buộc mới làm quy tắc cũ bất khả thi, thường là quy tắc cũ bị phát biểu sai chứ không phải ràng buộc mới sai.

---
## 13. Thoại "gọi/triệu tập" không cùng không gian với phần còn lại của cảnh

*Bối cảnh:* User chỉ ra một câu thoại mở đầu cảnh (kiểu "Vào phòng tôi ngay") bị gán vào SF master của cảnh đó — nhưng câu ấy xảy ra TRƯỚC khi hai nhân vật đối diện nhau, ở một không gian khác (người quản lý gọi vọng từ cửa phòng ra khu làm việc).

**Nguyên tắc rút ra:** trước khi chia thoại vào shot, phải rà xem có câu nào KHÔNG cùng không gian
hoặc thời điểm với phần còn lại của cảnh không. Các dạng hay gặp: câu gọi/triệu tập (xảy ra trước,
ở chỗ khác), thoại qua điện thoại/bộ đàm/loa (người nói không trong khung), thoại vọng từ xa.
Mặc định gom mọi dòng của một scene vào cùng một không gian là sai.

Cách xử lý tốt nhất là tách SF riêng cho đúng khoảnh khắc đó. Với câu gọi/triệu tập, SF riêng này
thường kiêm luôn vai trò CẦU NỐI CHUYỂN CẢNH giữa scene trước và scene sau — nhân vật đứng ở khung
cửa, một nửa thuộc không gian cũ một nửa thuộc không gian mới — vừa đúng logic vừa được thêm một
nhịp hình đẹp. SF loại này phải đính ảnh tham chiếu của CẢ HAI không gian, kèm ghi rõ ảnh nào dùng
cho phần nào (nguyên lý 3), và phải cảnh báo tường minh "KHÔNG dựng thành cảnh hai người đối thoại
trong phòng" vì model sẽ mặc định về bố cục quen thuộc của master.
(Đã thêm vào mục "Chia câu vào shot" trong SKILL.md.)

---
## 14. Prompt video có FORM CHUẨN riêng — không được tự chế format

*Bối cảnh:* Các prompt video đầu tiên được viết theo format tự nghĩ ra (một đoạn mô tả chuyển động + đuôi khóa, thoại để riêng trong field text).

**Nguyên tắc rút ra:** khi làm việc trong một pipeline đã chạy thành công trước đó, phải hỏi/tìm
form chuẩn hiện có TRƯỚC khi tự thiết kế format mới — kể cả khi format tự nghĩ trông hợp lý. Form
đã kiểm chứng chứa những quyết định không hiển nhiên (thoại nhúng trong prompt, nhãn cảm xúc, khối
âm thanh) mà format tự chế sẽ bỏ sót. (Đã thay toàn bộ mục "Prompt video" trong SKILL.md bằng form chuẩn.)

---
## 15. Sửa thoại sau khi prompt đã viết → prompt lệch âm thầm

*Bối cảnh:* User ghép thoại của hai shot làm một rồi xóa shot kia, nhưng prompt video của shot còn lại vẫn là bản viết cho lời thoại cũ (chỉ một câu) — không có gì báo hiệu, chỉ phát hiện khi đọc lại.

**Nguyên tắc rút ra:** dữ liệu do AI sinh ra dựa trên một dữ liệu khác (prompt video sinh từ lời
thoại) cần một MỐC ĐỒNG BỘ để phát hiện lệch — lưu ảnh chụp của nguồn tại thời điểm sinh
(`prompt_text` = bản thoại lúc viết prompt), rồi để giao diện tự so sánh và cảnh báo khi nguồn
thay đổi. Không nên trông chờ người dùng tự nhớ. Khi viết/sửa prompt video, LUÔN cập nhật lại
mốc này cho khớp.
(Đã thêm badge "⚠ thoại đã đổi — prompt video chưa viết lại" trên từng shot, bộ đếm tổng ở thanh
trên, và nút "✓ đã khớp" để đánh dấu thủ công sau khi prompt được viết lại.)

---
## 16. SF insert thuần đạo cụ là khung chết khi thành video

*Bối cảnh:* User xem lại các SF insert (cận màn hình giám sát, cận tờ giấy trên bàn) và chốt: "sau không cần các SF như thế này đâu, chi tiết quá mà không có người".

**Nguyên tắc rút ra:** loại bỏ SF insert thuần đạo cụ khỏi bộ khung chuẩn. Đạo cụ quan trọng thì
đưa VÀO khung có người — dựng two-shot/medium sao cho thấy được cả hành động của bàn tay LẪN gương
mặt nhân vật, giữ được đạo cụ mà không mất phản ứng. Chỉ cân nhắc insert khi đạo cụ mang thông tin
mắt bắt buộc phải đọc rõ (một dòng chữ quyết định, một con số) và không cách nào lồng vào khung có
người — và ngay cả khi đó, ưu tiên biến nó thành một nhịp rất ngắn bên trong shot có người thay vì
một shot riêng.

Bài học meta: tiêu chí đánh giá một SF phải là "nó sẽ thành CLIP như thế nào", không phải "tấm ảnh
này có đẹp không". Một khung tĩnh giàu chi tiết có thể là một clip rỗng.
(Đã sửa mục "Bộ góc máy" và "Chia câu vào shot" trong SKILL.md.)

---
## 17. Tái dùng master trước khi nghĩ tới dựng SF mới

*Bối cảnh:* Sau khi bỏ hai SF insert thuần đạo cụ (bài học 18), phản xạ đầu tiên là dựng HAI SF two-shot mới để thay thế — mỗi cái cho một đạo cụ.

**Nguyên tắc rút ra:** SF mới chỉ dựng khi cần một CỠ CẢNH hoặc GÓC NHÌN mà các SF sẵn có không
có (cận để thấy biểu cảm, đảo phía để shot/reverse, đổi tư thế ngồi/đứng). KHÔNG dựng SF mới chỉ
vì xuất hiện thêm một hành động hay một đạo cụ trong cùng một bố cục — hành động thuộc về prompt
video, không thuộc về SF.

Bài học meta: khi sửa một lỗi (bỏ insert), đừng mặc định phải thay bằng thứ gì đó mới cùng số
lượng. Hỏi trước: những gì đã có có kham được không? Đây là lần thứ ba mắc cùng một dạng lỗi —
phản ứng quá tay khi sửa (xem bài học 9 và 12) — nhưng lần này ở dạng "thêm tài nguyên mới thay
vì tái dùng tài nguyên sẵn có".

---
## 18. Thoại phải khớp với BỐ CỤC KHÔNG GIAN mình vừa dựng ra

*Bối cảnh:* Master của một cảnh được thiết kế là hai không gian THÔNG NHAU không có tường ngăn (để hợp lý hoá việc nhân vật ở phòng bên nghe được tiếng cửa mở).

**Nguyên tắc rút ra:** khi thiết kế bố cục không gian cho master (nhất là khi cố ý cho hai khu vực
thông nhau, hoặc ngược lại ngăn cách nhau), phải rà lại TOÀN BỘ thoại của scene xem có câu nào giả
định một bố cục khác không. Các câu dễ vướng: hỏi vị trí người khác ("X đâu?"), thông báo điều mà
nhân vật lẽ ra tự thấy, gọi vọng sang phòng khác. Kịch bản viết ra khi chưa có bố cục cụ thể, nên
mâu thuẫn kiểu này chỉ lộ sau khi master đã chốt — và người viết prompt phải là người bắt được.

Cách sửa tốt: đổi câu thoại sang một hành vi hợp bố cục mà VẪN GIỮ được thông tin/đạo cụ cần gieo
(ở đây: thay câu hỏi vị trí bằng một câu nhận xét về MÙI món ăn — vừa tự nhiên với người vừa bước
vào, vừa giữ nguyên món ăn đó làm đạo cụ gieo-trả cho cảnh sau). Đừng chỉ xoá câu vướng.

---
## 19. Cảnh 3 người cần tầng "rộng vừa", không nhảy thẳng từ master xuống cận

*Bối cảnh:* User hỏi vì sao cảnh có ba nhân vật mà không có thêm 1-2 góc rộng vừa (nhỏ hơn master nhưng không cận) để có thêm khung hình đủ cả ba người.

**Nguyên tắc rút ra:** cảnh từ 3 nhân vật trở lên phải có thêm 1-2 GÓC RỘNG VỪA lấy đủ cả nhóm —
gần hơn master một nấc (cắt bớt trần và rìa phòng), nhân vật to hơn hẳn nhưng vẫn chưa phải cận.
Hai biến thể đáng có: (a) rộng vừa thẳng, cùng hướng master chỉ tiến camera gần hơn; (b) rộng vừa
QUA VAI một nhân vật — người đó làm tiền cảnh mềm, hai người còn lại nét rõ. Biến thể (b) đặc biệt
đắt khi nhân vật tiền cảnh là người đang IM LẶNG lắng nghe: sự hiện diện câm lặng đó làm khung
hình nặng hơn hẳn một two-shot thường.
(Đã bổ sung vào mục "Bộ góc máy" trong SKILL.md.)

---
## 20. SF là frame ĐẦU clip → phải bằng trạng thái KẾT THÚC của clip trước

**Hệ quả 1: mọi hành động chuyển trạng thái phải nằm ở CUỐI clip TRƯỚC** (nơi SF vẫn còn ở trạng thái cũ), rồi clip sau mở đầu bằng câu xác nhận: *'đã ngồi yên trên sofa, đúng như frame tham chiếu'*.

**Hệ quả 2: mỗi SF phải GHI RÕ trạng thái không gian** — ai đứng/ngồi, cách nhau bao xa, ai cao hơn, quay hướng nào.

**Duyệt theo CẶP SHOT LIỀN NHAU** sau khi chốt SF, hỏi *'ai đổi chỗ giữa hai khung này?'*. Ba cách xử lý theo mức độ:
1. Chèn một shot CHUYỂN khi đổi khu vực — khung rộng thấy trọn đường đi; SF của shot chuyển lấy theo vị trí XUẤT PHÁT (khớp cuối shot trước), rồi tả nhân vật di chuyển tới bố cục của shot kế trong prompt.
2. Cho nhân vật VỪA ĐI VỪA NÓI — mượn luôn thời lượng thoại làm thời lượng di chuyển.
3. Đổi chỗ nhỏ trong cùng khu vực thì chỉ cần mô tả trong prompt clip trước.

---
## 21. Nhân vật chính phải LUÔN đẹp — 'nghèo' nằm ở bối cảnh, không ở bộ đồ

**1. 'Nghèo' ≠ 'xấu và quê'.** Trong melodrama đại chúng, nhân vật chính phải luôn đẹp và cuốn hút — cả gương mặt LẪN trang phục. Cái nghèo thể hiện ở BỐI CẢNH (căn nhà, đồ đạc, khu phố) và ở CỐT TRUYỆN. Người thu nhập thấp ngoài đời vẫn chọn bộ đẹp nhất, chỉn chu nhất khi đi việc quan trọng — mô tả 'vải thường', 'đã sờn', 'giày cũ', 'không có gu' là vừa sai thực tế vừa phản tác dụng.

**2. Đồ ở nhà: ÍT LỚP, VẢI MỎNG, DÁNG THOÁNG** — cotton/linen mỏng, tay ngắn hoặc lỡ, một lớp là đủ. Chỉ thêm lớp dày khi kịch bản có lý do rõ (ngoài trời lạnh, mùa đông có nêu). Ghi thẳng điều cấm vào prompt: *KHÔNG áo len dày, KHÔNG đồ nỉ, KHÔNG đồ nhiều lớp*.

*Bài học meta:* 'ấm áp' là tính từ của KHÔNG KHÍ CẢNH (ánh sáng vàng, khung hình), không phải của QUẦN ÁO — đừng dịch cảm giác cảnh thành chất liệu vải.

---
## 22. Khối "Nhận diện" tả trang phục càng chi tiết, model vẽ càng láo

*Bối cảnh:* Sau khi chuẩn hóa trang phục theo REF, tôi bê luôn mô tả chi tiết đó vào khối "Nhận diện" của prompt video: "blazer camel + blouse lụa kem cổ V + quần âu navy + giày cao gót thấp đen".

**Nguyên tắc rút ra:** Nhận diện là khối CHỐNG NHẦM NGƯỜI, không phải chỗ tả trang phục. Công thức:
`<Tên> = <tuổi + chủng tộc>, <trang phục gói trong MỘT cụm ngắn + (REF_ID)>, <TƯ THẾ> <VỊ TRÍ>.`
Mỗi người ~15-25 từ, cả khối dưới ~300 ký tự. Chi tiết trang phục đã nằm ở ảnh REF và ở prompt SF
rồi — nhắc lại ở đây chỉ làm hại.

Bài học meta: thông tin đúng nhưng đặt SAI TẦNG vẫn gây lỗi. Mỗi tầng của pipeline có một nhiệm vụ
riêng (REF = nhân dạng · SF = bố cục và chi tiết khung · prompt video = chuyển động và phân biệt
người nói) — sao chép thông tin từ tầng này sang tầng khác "cho chắc" thường phản tác dụng.

---
## 23. Cùng một không gian thì phải THAM CHIẾU master cũ, kể cả khi là phòng khác

*Bối cảnh:* Tôi viết master cho Scene 16 (phòng ngủ của con) và Scene 18 (phòng khách) mà không đính ảnh tham chiếu bối cảnh nào, vì nghĩ "phòng ngủ là không gian mới, chưa có master".

**Nguyên tắc rút ra:** trước khi viết master cho một scene, luôn hỏi *"công trình / địa điểm này
đã từng xuất hiện chưa?"* Nếu rồi thì BẮT BUỘC đính master cũ vào `refs.bg`, kèm một khối khóa
đặt ngay đầu prompt, và chọn đúng một trong hai mức:
- **Cùng đúng căn phòng** → "đây CHÍNH LÀ căn phòng đó, dùng lại nguyên vẹn đồ đạc và vị trí,
  chỉ được đổi thời điểm trong ngày và vị trí người". Cấm tự nghĩ ra nội thất mới.
- **Phòng khác trong cùng công trình** → "bố cục khác, NHƯNG cùng màu sơn tường, cùng loại sàn,
  cùng kiểu khung cửa, cùng chiều cao trần, cùng mức độ cũ và cùng đẳng cấp sống".

Kèm theo luôn một khối chặn nâng cấp mức sống: nhà thuê của người lao động thì tường phải có vết
thời gian, đồ đạc mua lẻ nên lệch tông, KHÔNG nội thất đồng bộ kiểu catalog. Model luôn có xu
hướng làm đẹp và làm mới bối cảnh nghèo nếu không bị chặn thẳng.

Bài học meta: một master không chỉ khóa cho các SF trong cùng scene — nó là tài sản dùng chung
cho MỌI scene diễn ra ở cùng địa điểm về sau. Cần rà lại toàn bộ danh sách scene theo ĐỊA ĐIỂM
chứ không theo số thứ tự, để biết cái nào phải neo vào cái nào.

---
## 24. Nhịp không thoại — vì sao cần, loại nào, bao nhiêu là đủ

Một scene hội thoại dựng xong **chưa phải** một cảnh phim hoàn chỉnh. Rà thêm một lượt để chèn nhịp không thoại, gồm bốn loại:
- **Beat cảm xúc** (6s) — sau câu thoại nặng nhất, giữ mặt nhân vật im lặng cho câu đó ngấm.
- **Cầu nối** (6–10s) — nhân vật rời khung, đi qua không gian, nối cảnh này sang cảnh kia.
- **Dựng cảnh** (6s) — ngoại cảnh địa điểm mới trước khi vào thoại.
- **Đối tượng/chi tiết** (6s) — đạo cụ mang nghĩa, nhưng **phải đặt trong khung có người**
  (người cầm/nhìn/đặt nó xuống), không tách thành khung chỉ có bàn tay và vật.

Trong prompt nhịp không thoại, hai khối bắt buộc viết nguyên văn:
`KHÔNG CÓ LỜI THOẠI TRONG CLIP NÀY. Tuyệt đối không ai mở miệng nói, không ai cử động môi như đang nói.` và `Âm thanh: KHÔNG thoại, KHÔNG nhạc, KHÔNG hiệu ứng. Giữ clip IM LẶNG HOÀN TOÀN.` — khác hẳn khối âm thanh của clip có thoại.

**Số lượng: ≈15% số shot có thoại, tính trên TỔNG CẢ PHIM**, không chia đều theo scene. Rải đều mỗi scene 1–2 nhịp cho 'cân đối' là cân về số học nhưng sai về kể chuyện — nhịp phải dồn vào chỗ cảm xúc cần thở.

---
## 25. Ghi bài học rồi vẫn vi phạm, vì áp dụng sai phạm vi

*Bối cảnh:* Hôm trước tôi ghi bài học 31 ("cùng một không gian thì phải tham chiếu master cũ") và thêm hẳn mục 0 vào checklist.

**Nguyên tắc rút ra:** với mỗi công trình trong phim, lập sẵn một danh sách "ảnh gốc" theo GÓC
NHÌN, không theo scene:
`nhà Maya → ngoại thất: SF-S5-MASTER · bếp: SF-S8-MASTER · phòng khách: SF-S3-MASTER`
Trước khi viết bất kỳ SF nào, tra bảng đó theo *công trình + góc nhìn* rồi mới quyết định tạo
mới hay neo. Và khi thêm một loại nội dung mới vào pipeline (nhịp, toàn cảnh, insert…), phải
chạy lại TOÀN BỘ checklist cho loại đó, đừng cho rằng checklist chỉ dành cho thứ mình đã quen.

Bài học meta: viết được nguyên tắc ra giấy không có nghĩa là sẽ áp dụng đúng chỗ. Lỗi lặp lại
không phải vì thiếu nguyên tắc mà vì **phạm vi áp dụng bị hiểu hẹp hơn thực tế** — nên khi ghi
một bài học, phải nói rõ luôn nó áp dụng cho những loại việc nào.

---
## 26. Lạm dụng chữa bằng lệnh cấm là sai, chữa bằng danh sách cũng sai

*Bối cảnh:* 43 nhịp không thoại dựng xong, user xem lại: "cứ thấy lặp lại thở dài mãi".

**Nguyên tắc rút ra:** với diễn xuất, prompt phải mô tả **TRẠNG THÁI**, không mô tả **THAO TÁC**.
Mỗi nhịp viết riêng: nhân vật vừa trải qua chuyện gì, đang ở đâu trong hành trình, trong lòng
đang có gì (càng cụ thể và càng có mâu thuẫn nội tâm càng tốt). Rồi nói thẳng: *hãy để cơ thể
biểu đạt trạng thái đó theo cách tự nhiên nhất trong chính không gian và tư thế của frame này,
tự chọn cử chỉ và nhịp điệu.* Phần diễn biến mình đã nghĩ ra thì để làm **"gợi ý, điều chỉnh
được"** — giữ được ý đồ đạo diễn mà không trói tay.

Khi mỗi nhịp có một trạng thái riêng biệt, cách diễn tự khác nhau theo. Không cần cấm gì cả.

Bài học meta: hai lần sửa của tôi đều là phản xạ **kiểm soát model chặt hơn** — cấm bớt, rồi
liệt kê sẵn. Cả hai đều làm mọi nhịp giống nhau, chỉ khác chỗ giống. Với những thứ cần sự tinh
tế và biến hóa, cách đúng ngược lại: cho model **bối cảnh phong phú hơn** rồi để nó tự quyết chi
tiết. Kiểm soát đúng chỗ là kiểm soát Ý ĐỒ, không phải kiểm soát THAO TÁC.

---
## 27. Chuyển động không có tác nhân — lỗi phi vật lý trong nhịp không thoại

*Bối cảnh:* Nhịp mở phim `V-S1-B1` là mặt tiền siêu thị lúc sáng sớm.

**Nguyên tắc rút ra:** mỗi chuyển động phải có tác nhân **nhìn thấy được trong khung**, chỉ ba
nguồn hợp lệ: người có thật trong ảnh SF (kể cả bóng mờ ở xa), lực tự nhiên đang hiện diện (gió
mà phải thấy lá lay/rèm động, trọng lực, nắng dịch), hoặc máy móc đang chạy (xe có tài xế, đèn
hẹn giờ, màn hình tự tắt).

**Và phải đối chiếu với ẢNH ĐÃ RENDER, không phải với mô tả trong prompt SF.** Prompt SF của
khung này có ghi "hai ba khách hàng mờ nét đi vào" nên trên giấy tờ thì chuyển động nào cũng có
vẻ hợp lý — nhưng ảnh thật lại vắng ở đúng chỗ tôi đặt chuyển động. Viết prompt video mà chỉ đọc
prompt SF là viết mù.

Bài học meta: nỗi sợ "khung hình chán" đẩy tôi tới chỗ thêm chuyển động bằng mọi giá. Nhưng một
mặt tiền yên ắng với nắng dịch chậm và tán lá lay thì thật hơn nhiều so với một khung nhồi vật
thể tự di chuyển. Khi thấy trống, thêm chuyển động của **ánh sáng** — đừng thêm **vật**.

---
## 28. Nhạc nền — quyết VAI TRÒ trước, viết prompt sau

*Bối cảnh:* Tôi viết 43 bộ prompt nhạc Suno cho các nhịp không thoại.

**Nguyên tắc rút ra: bước đầu tiên không phải viết prompt, mà là quyết VAI TRÒ của nhạc trong
đoạn đó** — ĐẨY (cho nhạc chiếm sân khấu, chỉ dành cho một hai đỉnh của cả phim), NÂNG (đi cùng
nhân vật, có đà nhưng không lấn), KÌM (nhạc nhỏ hơn cả cảm xúc đang diễn ra — khi nhân vật đang
gồng để không gãy, nhạc mà gãy hộ là hỏng), NGHỈ (gần như không nhạc, để khán giả thở). Viết vai
trò ra thành một câu kèm lý do, rồi mới viết prompt.

Giữ khoảng **25% không lời** cho đúng những chỗ lời hát sẽ nói hộ quá nhiều: khoảnh khắc sinh tử
đang diễn ra, nhân vật vỡ ra trong im lặng khi không ai nhìn, những khung riêng tư nhất, và các
nhịp NGHỈ.

Về chất lượng prompt: thứ tạo khác biệt không phải danh sách nhạc cụ mà là **cấu trúc theo thời
gian** — mở bằng gì, thêm gì ở giữa, đỉnh ở đâu, và nhất là **cú rút** (*"rồi tất cả cắt đi chỉ
còn giọng và piano"*). Với nhạc có lời thì tả **cách hát** (close to the mic, almost spoken,
cracked at the edges) và **chủ đề lời kèm điều cấm** (*không đắc thắng, không tự thương thân*),
để Suno tự viết lyrics nhưng đúng hướng.

Bài học meta: khi user đưa một ví dụ, đó là **mẫu về ĐỊNH DẠNG, không phải mẫu về NỘI DUNG**.
Lấy ví dụ làm khuôn rồi thay tính từ là cách nhanh nhất để tạo ra 43 thứ giống hệt nhau. Việc
thật sự cần làm là nghe từng đoạn trong đầu và hỏi nó cần gì.

---
## 29. User thay ảnh master thì mọi khối "khóa look" con thành nói dối

*Bối cảnh:* User chốt một ảnh master mới cho Scene 1 (render từ option khác — biển số quầy ĐEN, quầy be, đèn ấm trung tính) và dán vào board.

**Nguyên tắc rút ra:** ảnh master là MỘT NGUỒN SỰ THẬT, và khối khóa look ở mọi SF con là BẢN
SAO CHÉP của nguồn đó bằng chữ. Khi ảnh master ĐỔI (user chọn bản khác, dán bản mới), phải:
1. MỞ ẢNH MỚI RA NHÌN và viết lại khối khóa look theo đúng những gì thấy (màu biển số, chất
   liệu quầy, nhiệt độ đèn) — không đoán từ prompt cũ;
2. Quét TẤT CẢ SF con của scene và thay khối khóa look đồng loạt;
3. Cập nhật luôn prompt của chính master (nếu không, lần render lại sẽ quay về kiểu cũ);
4. Thêm câu "ẢNH ĐÍNH KÈM LÀ CHUẨN TUYỆT ĐỐI — chữ nào xung đột với ảnh thì THEO ẢNH" để tự
   vệ trước những lệch còn sót.

Hai bài kèm theo, cùng phát hiện trong đợt này:
- **Khối bắt buộc chắp vá ở CUỐI prompt là khối yếu nhất.** "Hàng người chờ" tôi nối vào cuối
  → cứ đến khung cận là model bỏ. Thứ gì bắt buộc phải có trong khung thì đặt NGAY SAU câu
  camera, trước cả mô tả nhân vật chính, với chữ "PHẢI CÓ TRƯỚC KHI TÍNH ĐẾN NHÂN VẬT CHÍNH".
- **Prompt video phải khớp trạng thái của frame ảnh.** Ảnh master mới: Maya ĐÃ nghiêng người
  nhìn Helen. Prompt video cũ: "Maya ngẩng phắt lên" (viết cho ảnh cũ khi cô đang cúi ở máy).
  Model nhận frame đã-nhìn + lệnh ngẩng-lên → cho nhân vật đảo mắt lung tung. Sửa: mô tả ánh
  mắt BẮT ĐẦU đúng như frame và chỉ đạo diễn tiến TĂNG DẦN từ đó.

---
## 30. Nhân dạng lệch dù có REF — và một chẩn đoán sai đã bị user sửa lại: REF không có trần

*Bối cảnh:* làm một SF hai nhân vật, đính 4 ảnh REF (2 portrait + 2 full) + master.

**Nguyên tắc rút ra (bản đã sửa theo quyết định của user):**
1. **REF không có trần số ảnh.** Mỗi nhân vật trong khung đính ĐỦ cặp: portrait (khuôn mặt) +
   full-body của đúng bộ đồ cảnh đó, cộng master bối cảnh. Hai nhân vật = 5 ảnh là bình thường.
2. **Khi nhân dạng ra lệch, thứ tự chẩn đoán đúng là:** (a) kiểm tra các ảnh có THẬT SỰ được
   đính kèm không (pipeline có thể rớt ảnh im lặng); (b) render lại vài bản — phương sai giữa
   các lần tạo là nghi phạm số một; (c) thêm dòng khóa chữ NGẮN cho những gì dễ lệch. KHÔNG
   chữa bằng cách bỏ bớt ref.
3. **Phần vẫn đúng của phát hiện cũ:** dòng khóa chữ ngắn cho đặc điểm cốt lõi (chủng tộc,
   kiểu tóc, màu quần áo) đáng giữ ở mọi SF nhiều nhân vật — nó rẻ và chặn được lệch bất kể
   nguyên nhân. Với phim mà tương phản chủng tộc giữa hai nhân vật là điểm cốt truyện, dòng
   khóa đó là bắt buộc.
4. **Bài học meta:** đừng thăng cấp một quan sát 2-mẫu thành luật. Ghi nó là giả thuyết, thử
   thêm, hoặc hỏi user — người đã chạy pipeline này nhiều hơn mình.

---
## 31. Kịch bản người viết có hard-cut trong một clip — tách thành hai shot, và nói rõ vì sao

*Bối cảnh:* user gửi lại bản hook đã tự tinh chỉnh, trong đó *"CLIP 8 — 10 GIÂY"* được viết thành hai nửa: 0–5s hai người dưới sàn có thoại, rồi *"Hard cut sang tủ mát"* cho 5–10s Maya chạy đi lấy nước cam.

**Nguyên tắc rút ra:**
1. **Một clip = một start frame = một shot liền.** Đổi góc, đổi cỡ cảnh, đổi địa điểm đều phải
   sang SF mới và shot mới. Không có ngoại lệ nào cho công cụ image-to-video này.
2. **Kịch bản do người viết sẽ có hard-cut, và đó là bình thường** — họ nghĩ theo lối dựng phim
   thật, nơi cắt trong một cảnh là chuyện hiển nhiên. Giới hạn nằm ở công cụ, không ở kịch bản.
   Việc của mình là dịch sang cấu trúc mà công cụ dựng được, không phải bắt user viết lại.
3. **Chia lại thời lượng theo lượng thoại của từng nửa, đừng cố giữ tổng.** Một clip 10s bị tách
   thường thành 6s + 6s chứ không phải 5s + 5s — nửa không thoại cần đủ giây để hành động diễn ra
   trọn vẹn.
4. **Luôn báo lại việc tách và lý do.** Đây là thay đổi so với cái user viết ra; im lặng làm khác
   đi thì lần sau họ vẫn viết như cũ, và họ mất quyền quyết định chia ở đâu.
5. **Rà bằng máy trước khi render**: quét toàn bộ prompt video tìm `hard cut` / `cắt sang` /
   `0-5 GIÂY` / `5-10 GIÂY`, và xác nhận footer nào cũng còn câu khóa "MỘT SHOT LIỀN DUY NHẤT".
   Sót một chữ là hỏng một clip, mà lỗi này chỉ lộ ra sau khi đã tốn lượt render.

---
## 32. Khung ba lớp chiều sâu đẩy model lên góc bird's-eye — và câu phủ định vẫn vẽ ra thứ bị cấm

*Bối cảnh:* làm SF cầu nối S1→S2, tôi thiết kế một khung ba lớp: tiền cảnh là chỗ sàn trống nơi bà cụ vừa ngồi, lớp giữa là Maya đã quay lại quầy làm việc, lớp sâu là quản lý đứng ở cửa văn phòng cuối cửa hàng nhìn về phía cô. Ý đồ: khán giả thấy mối đe dọa mà nhân vật không thấy.

**Nguyên tắc rút ra:**
1. **Tối đa HAI lớp chiều sâu trong một SF.** Muốn lớp thứ ba (một người ở rất xa, một không
   gian khác) thì tách thành SF riêng và shot riêng. Lớp thứ ba gần như luôn là thứ khiến model
   phải đổi góc máy để "nhét cho vừa" — và góc nó chọn sẽ là góc mình không muốn.
2. **Khóa góc máy bằng một khối riêng ĐẶT TRƯỚC phần bố cục, không phải một cụm từ lẫn trong
   câu tả cảnh.** Viết thẳng điều kiện phủ định: "camera ngang tầm ngực người đứng, TUYỆT ĐỐI
   KHÔNG góc cao, KHÔNG nhìn từ trên xuống, KHÔNG toàn cảnh". Một chữ "medium-wide" đứng lẻ
   không đủ sức giữ góc khi bố cục đang kéo model đi hướng khác.
3. **Đừng mô tả một vật thể bằng cách nhắc tới thứ đang bị cấm.** "Chỗ sàn nơi bà cụ vừa ngồi",
   "chiếc ghế của người đã đi khỏi" — model đọc ra hình ảnh, không đọc ra ngữ pháp phủ định.
   Viết thuần bằng cái CÒN LẠI: "khoảng sàn vinyl trống, chỉ có một chai nước rỗng nằm nghiêng".
   Ý nghĩa "ai đó vừa ở đây" do khán giả tự hiểu từ mạch phim, không cần prompt nói ra.
4. Lệnh cấm nhân vật đặt ở **ba chỗ**: ngay sau khối góc máy, trong phần bố cục, và ở khối chống
   lỗi cuối — nhưng chỉ hiệu quả khi đã dọn sạch mọi câu mô tả gợi ra nhân vật đó (điểm 3).

---
## 33. Thoại nhân vật chính lúc làm việc tốt — người tốt thật không thuyết minh việc tốt của mình

*Bối cảnh:* viết cảnh nhân vật chính cứu giúp người lạ, tôi cho cô nói những câu nghe "hay": giải thích động cơ (*"I know what it looks like when someone's about to go down and nobody around them is paying attention"*), tuyên bố sẽ ở lại (*"I'm not going anywhere"*, *"Not while I'm here"* — lặp…

**Nguyên tắc rút ra:**
1. **Người đang thật lòng giúp thì HỎI và LÀM, không GIẢI THÍCH và không HỨA.** Câu giải thích
   động cơ ("tôi giúp vì tôi từng thấy...") và câu tuyên bố phẩm chất ("tôi sẽ không đi đâu")
   là dấu hiệu kể công — cắt thẳng tay, thay bằng câu ngắn + một hành động tiếp theo.
2. **Trước câu hỏi cảm xúc nặng, phản ứng chân thành nhất là NÉ**: trả lời tối giản rồi đổi
   chủ đề sang việc thực tế, hoặc lúng túng hạ thấp ("It's just juice"). Sự vụng về khi được
   cảm ơn thuyết phục hơn mọi câu đáp trôi chảy.
3. **Phân biệt với thoại TRẤN AN — loại này hợp lệ.** "I've got you. I'm right here" nói MỘT
   LẦN, đúng lúc chạm vào người đang hoảng, là kỹ năng sơ cứu chứ không phải kể công (chính
   user giữ lại câu này trong bản họ tự viết). Nó thành lố khi lặp lại hoặc khi nói mà không
   gắn với hành động chạm/đỡ cụ thể.
4. **Đức tính của nhân vật chính thể hiện bằng HÀNH ĐỘNG KHÔNG AI CHỨNG KIẾN, không bằng lời**
   — ví dụ lặng lẽ tự trả tiền món đồ đã lấy, và KHÔNG ngẩng lên xem có ai nhìn thấy không.
   Một nhịp không thoại như vậy nói được điều mà mọi câu thoại tự nói ra đều làm hỏng.
5. Kiểm tra nhanh khi rà thoại: câu nào của nhân vật chính mà NỘI DUNG là "tôi tốt / tôi sẽ
   tốt / lý do tôi tốt" thì đó là ứng viên cắt đầu tiên.

---
## 34. Hành động đỉnh điểm ở GIỮA chuyển động là thứ model không vẽ nổi — thiết kế khoảnh khắc TRƯỚC hoặc SAU nó

*Bối cảnh:* khoảnh khắc bản lề "nhân vật vượt qua ranh giới quầy để cứu người" — tôi dựng SF cô đang LAO NGƯỜI giữa sải chân.

**Nguyên tắc rút ra:**
1. **Ba vùng của một hành động: TRƯỚC (dợm/quyết định) — GIỮA (đang bay/đang lao) — SAU (đã
   tới/đã chạm). Model vẽ tốt vùng TRƯỚC và SAU, gần như luôn hỏng vùng GIỮA.** SF nên chọn
   một trong hai vùng an toàn; chuyển động thật để prompt video lo, vì video đi TỪ một tư thế
   tĩnh chứ không cần bắt đầu giữa không trung.
2. **Cách né sang trọng nhất: kể bằng DẤU VẾT** — thứ bị bỏ lại (máy quét nằm nghiêng, dây còn
   đung đưa, hàng tính dở) trong khi nhân vật đã ở nơi khác. Khán giả tự dựng cú vượt trong
   đầu, và bản trong đầu luôn đẹp hơn bản render hỏng.
3. **Khi một khoảnh khắc quan trọng khó render, đưa NHIỀU PHƯƠNG ÁN cho user chọn thay vì cố
   đấm một phương án** — và chuẩn bị tinh thần là user nghĩ ra phương án tốt hơn cả 5 cái của
   mình. Các option nên KHÁC NHAU VỀ CHIẾN LƯỢC (né bằng cỡ cảnh / né bằng điểm tựa / né bằng
   đồ vật / bỏ hẳn khoảnh khắc), không phải 5 biến thể của cùng một ý.

---
## 35. Tinh chỉnh thoại nhiều vòng sẽ đánh rơi câu gốc — diff bằng máy sau mỗi vòng, đừng tin trí nhớ

*Bối cảnh:* sau vài vòng gộp/tách/viết lại shot theo feedback, tôi làm rơi mất một câu thoại gốc của kịch bản (*"Tanya, orange juice from the cooler.

**Nguyên tắc rút ra:**
1. **Sau MỖI vòng sửa thoại, chạy diff bằng máy**: chuẩn hóa (bỏ nhãn tên, bỏ dấu câu, thường
   hóa) rồi kiểm tra từng dòng script gốc có còn xuất hiện trong text các shot không. Việc này
   một script 10 dòng làm được — trí nhớ thì không, nhất là khi sửa vòng thứ ba.
2. **Câu gốc chỉ được phép mất khi user chủ động duyệt việc bỏ nó** (như khi user tự viết lại
   cả đoạn hook). Mất do sơ suất và mất do quyết định là hai chuyện khác nhau — script diff
   phân biệt được: nó báo thiếu, còn quyết định giữ hay bỏ là của người.
3. Các câu gieo-trả (câu được scene khác trích lại nguyên văn) phải nằm trong danh sách BẤT KHẢ
   XÂM PHẠM: rà mọi scene tìm câu được nhắc lại ở nơi khác TRƯỚC khi tinh chỉnh, và diff riêng
   danh sách đó sau mỗi vòng.

---
## 36. Công thức mật độ SF do user chốt — phút × 4; và góc cận-vật bị hạ cấp

*Bối cảnh:* phim 44 phút chia SF không theo chuẩn nào — scene 4,9 phút chỉ có 11 SF (một khung gánh 7-8 shot liên tiếp).

**Công thức user đã duyệt:** SF ≈ **phút × 4** (cứ 15 giây ≈ 1 SF) · sàn **5 SF** cho cảnh
~1 phút · **không SF nào quá 3 shot** · cảnh >3 phút cần **≥2 góc rộng** làm góc thở · shot
thoại **chỉ dùng khung có người**.

**Đánh giá thẩm mỹ kèm theo:** góc cận bàn tay / cận vật thể *"không hay lắm"* ngay cả khi
hình đẹp — người xem muốn thấy mặt người. Hệ quả: **khung cận-vật bị RÚT khỏi MỌI shot, kể
cả nhịp không thoại.** Đạo cụ muốn nhấn thì đặt vào khung đã có người.

**Lưu ý thi hành:** tỉ lệ đo bằng SỐ SF ĐƯỢC DÙNG trong shot list, không phải số SF tồn tại
trong board.

---
## 37. Người ở tiền cảnh quay lưng / out nét VẪN phải có ref

*Bối cảnh:* dựng bộ SF cho một phim, các khung OTS và CU đều mô tả kiểu *"rìa trái tiền cảnh là vai và gáy của Edmund, out nét mạnh, chỉ làm khung viền"* — và tôi chỉ đính ref của người nét rõ.

**Nguyên tắc rút ra:**
1. **Tên nhân vật nào xuất hiện trong prompt thì phải có ref trong `refs.chars`** — đủ cặp
   portrait + full của đúng bộ đồ cảnh đó. Không có ngoại lệ cho "chỉ thấy vai", "out nét",
   "quay lưng", "mờ ở rìa khung".
2. **Vì sao quan trọng dù mờ:** màu áo và dáng người ở tiền cảnh vẫn đọc được. Khung OTS đi
   theo cặp với khung đối diện; nếu vai out nét mặc áo màu khác thì hai khung ghép lại lộ ngay.
   Model không có ref sẽ bịa một bộ đồ bất kỳ.
3. **Cách rà bằng máy:** so danh sách tên riêng xuất hiện trong prompt với `refs.chars`; loại
   trừ các câu "X KHÔNG có trong khung" và master ghi "KHÔNG CÓ NGƯỜI TRONG KHUNG NÀY".
   Chạy kiểm này sau mỗi đợt sinh SF, trước khi render — rẻ hơn nhiều so với render lại.
4. Liên quan bài học 39 (REF không có trần): đừng tiếc ref, cứ đính đủ.

---
## 38. SF khoá vào khoảnh khắc thì chỉ dùng được đúng một lần

Scene 5 dài 5:18 với 29 SF (thừa so với công thức 22), nhưng user vẫn phải **tự cắt 5 frame
từ video và kéo thêm 2 ảnh ngoài vào** để có khung mà dùng. Nghịch lý đó lộ ra hai lỗi cùng gốc:

**a. SF bị viết ở đỉnh hành động.** `SF-S5-COUGH` vẽ sẵn ông gập người ôm ngực ho và bé đã đưa
tay ra; `SF-S5-MAYA-CU` vẽ sẵn Maya che miệng. Dùng lại ở shot sau thì nhân vật ho mãi / che
miệng mãi, và video không còn gì để diễn vì hành động đã hoàn tất ngay trong ảnh tĩnh.

**b. Làm take V2 khi chưa phủ đủ trạng thái.** Có V2 cho 3 góc, trong khi cụm hội thoại
Edmund–Lily thiếu hẳn các trạng thái cơ bản (bé ngồi sàn vẽ / đứng cạnh xe lăn / nắm tay ông)
và thiếu OTS tương ứng cho từng trạng thái.

**Nguyên tắc:** SF mô tả **trạng thái** (ai ở đâu, đứng/ngồi, gần/xa, cầm gì, hướng nào), diễn
xuất để prompt video lo. Phép thử: một SF phải phục vụ được ≥2–3 câu thoại khác nhau. Thứ tự
làm: đủ trạng thái → OTS → góc rộng → take V2 chỉ khi một SF còn gánh >3 shot. Dấu hiệu làm
sai thứ tự: phải đi cắt frame từ video ra vá.

**OTS theo ĐỘ DÀI trạng thái, không rải đều:** trạng thái chỉ gánh 1–2 shot (kiểu màn giằng co
*"Ngồi xuống." — "Tôi đứng được."*) thì OTS là thừa; trạng thái gánh **≥3 shot** thì bắt buộc
phải có, nếu không khán giả nhìn y một khung suốt 30 giây.

---
