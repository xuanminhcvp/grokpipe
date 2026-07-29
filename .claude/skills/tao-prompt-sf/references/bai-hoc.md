# Bài học tích lũy

File này chứa kinh nghiệm rút ra từ việc viết/sửa prompt ảnh SF Board và phản hồi của user.
Quy tắc ghi: mỗi bài học viết ở tầng nguyên lý (dùng được cho mọi nhân vật/scene), kèm ngày
và lý do ngắn gọn. Không nhắc tên nhân vật/dự án cụ thể trừ khi cần minh họa.

## Bài học 1 — 2026-07-25: Mô tả bằng chữ không đủ để đồng bộ trang phục giữa các nhân vật

User phát hiện REF của một nhân vật phụ (đồng nghiệp cùng nghề với nhân vật chính) chỉ được
viết "mặc đồng phục giống [nhân vật chính]" bằng lời, không đính kèm ảnh nhân vật chính làm
tham chiếu. Ảnh ra ổn ở lần đó nhưng thuần túy may rủi — không có cơ chế nào ép đúng tông màu/
kiểu dáng, sẽ lệch dần qua các lần tạo lại.

**Nguyên tắc rút ra:** bất cứ khi nào cần một nhân vật/đạo cụ trông "giống" một ảnh đã tạo
trước đó, phải đính ảnh đó vào `refs.chars` (không chỉ nhắc tên trong lời văn), và khi ảnh
tham chiếu đó phục vụ nhiều mục đích khác nhau (ví dụ vừa là chuẩn trang phục vừa có khuôn
mặt của người khác), phải ghi rõ trong prompt: dùng ảnh này cho phần nào, KHÔNG dùng cho phần
nào (đặc biệt là khuôn mặt — nguy cơ model copy nhầm mặt của ảnh tham chiếu chéo).
(Đã đưa vào SKILL.md nguyên lý 2 và 3.)

## Bài học 2 — 2026-07-25: Ngoại hình nhân vật phải chủ động phủ định tín hiệu cốt truyện chưa nên lộ

User yêu cầu một nhân vật (thân phận thật sự giàu có nhưng cần giấu ở đầu phim) phải trông
"bình thường" để hành động giúp đỡ của nhân vật chính không bị đọc là "thấy giàu mới giúp".
Prompt gốc mô tả nhân vật này quá sang trọng (trang sức đắt tiền, chất liệu cao cấp, dáng vẻ
quý phái) — vô tình làm lộ twist trước khi cần.

**Nguyên tắc rút ra:** ngoại hình/trang phục phải được thiết kế để phục vụ đúng thời điểm lộ
thông tin trong cốt truyện. Nếu một sự thật cần giữ kín, prompt phải chủ động liệt kê và cấm
rõ từng tín hiệu thị giác có thể tiết lộ nó ("TUYỆT ĐỐI KHÔNG khăn lụa, không trang sức đắt
tiền..."), không chỉ đơn giản là không nhắc tới — vì không nhắc tới vẫn để model tự suy diễn
theo tuổi tác/chủng tộc/bối cảnh sẵn có.
(Đã đưa vào SKILL.md nguyên lý 4.)

## Bài học 3 — 2026-07-25: Dặn "không dùng làm mặt" một lần là không đủ trọng số — model vẫn copy mặt

Áp dụng bài học 1 (đính ảnh nhân vật A làm chuẩn trang phục cho nhân vật B, kèm một câu dặn
"không dùng làm khuôn mặt") vẫn ra kết quả khuôn mặt B giống hệt A. Một câu cấm ở đầu prompt
không đủ mạnh để thắng độ bám ảnh tham chiếu của model khi ảnh đó là input trực quan còn lời
cấm chỉ là văn bản.

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

## Bài học 4 — 2026-07-25: Master frame mô tả bố cục bằng văn xuôi khiến địa lý bị đọc sai

Prompt master chỉ viết bằng câu văn "phía sau [nhân vật chính] có khách xếp hàng" mà không
gắn mốc vị trí cụ thể. Kết quả: ảnh ra nhóm khách bị đặt lệch sang cạnh MỘT NHÂN VẬT PHỤ khác
(một nhân viên đứng quầy kế bên) thay vì đúng ngay sau nhân vật chính — khiến chi tiết "khách
phía sau giục nhân vật chính" trong thoại không khớp với ảnh, đọc như hai nhóm không liên quan.

**Nguyên tắc rút ra:** bố cục master phải có bản đồ vị trí tường minh (mốc %, số quầy, landmark
cố định) thay vì chỉ mô tả tương đối bằng lời; các nhóm/hàng người dễ gây nhầm lẫn phải được
tách bằng một khoảng trống hoặc landmark trung gian rõ ràng thay vì đặt liền kề mơ hồ.
(Đã đưa vào SKILL.md nguyên lý 11.)

## Bài học 5 — 2026-07-25: Không liệt kê hết bảng tên hợp lệ → model tự bịa tên cho nhân vật còn lại

Master có 2 nhân vật đeo bảng tên nhưng câu chặn cuối chỉ nêu "không chữ dễ đọc ngoài bảng tên
[nhân vật A]" — không nhắc bảng tên của nhân vật B. Kết quả: model tự tạo MỘT TÊN NGẪU NHIÊN
khác cho bảng tên của B thay vì để trống hoặc dùng đúng tên, gây sai lệch nhận diện nhân vật
cho toàn bộ SF con dùng lại master này.

**Nguyên tắc rút ra:** khi master có nhiều nhân vật đeo bảng tên/chữ nhận diện, phải liệt kê
ĐẦY ĐỦ tất cả tên hợp lệ trong cùng một câu "chữ được phép xuất hiện", kèm yêu cầu đánh vần
chính xác — không liệt kê một phần rồi mặc định phần còn lại sẽ tự đúng.
(Đã đưa vào SKILL.md nguyên lý 13.)

## Bài học 6 — 2026-07-25: Đừng vá triệu chứng — hỏi trước xem nhân vật có cần ở đó không

Sau khi vá bài học 4 và 5 (thêm bản đồ vị trí + danh sách chữ hợp lệ) cho một master có 3
nhân vật, user chỉ ra gốc rễ: nhân vật thứ ba (một nhân viên khác) CHƯA hề hành động hay được
nhắc tới ở đúng khoảnh khắc của master — cô ấy chỉ xuất hiện vài câu thoại sau, và đã có một SF
riêng giới thiệu cô ấy rồi. Nhét thêm vào master chỉ để "cho đủ mặt nhân vật" đã tự tạo ra toàn
bộ lớp rủi ro (bố cục hai nhóm dễ nhầm, bảng tên phải quản lý) mà đáng lẽ không cần tồn tại.

**Nguyên tắc rút ra:** khi một SF ra lỗi vì có nhiều nhân vật (nhầm nhóm, nhầm tên...), câu hỏi
đầu tiên không phải "làm sao mô tả rõ hơn để tách họ ra" mà là "nhân vật đó có thực sự cần ở
đây không". Loại bỏ nhân vật thừa khỏi khung luôn rẻ và chắc hơn việc thêm quy tắc bố cục/chữ
để kiểm soát sự có mặt của họ. Chỉ dùng bản đồ vị trí + danh sách chữ hợp lệ (bài học 4, 5) khi
nhân vật đó thật sự phải đồng-hiện diện vì cùng hành động/đối thoại trong đúng SF đó.
(Đã đưa vào SKILL.md nguyên lý 11, đặt trước nguyên lý 12-13 để nhắc kiểm tra điều kiện này trước.)

## Bài học 7 — 2026-07-25: Đạo cụ bị bỏ trống mô tả là bỏ lỡ cơ hội nối với chi tiết kịch bản khác

Xe đẩy hàng của một nhân vật chỉ được nhắc chung chung ("xe đẩy hàng của bà") mà không tả nội
dung cụ thể. User hỏi lại mới phát hiện: kịch bản có một câu thoại ở cảnh SAU nhắc đích danh
một món đồ nhân vật đó tự đi mua (ví dụ: tự đi chọn một loại rau/quả cụ thể) — nếu xe đẩy ở
cảnh đầu có đúng món đó, đó là một sự lặp lại có chủ đích nối hai cảnh, nhưng vì đạo cụ bị bỏ
trống mô tả nên cơ hội này suýt bị bỏ lỡ.

**Nguyên tắc rút ra:** bất kỳ đạo cụ nào xuất hiện trong khung (giỏ hàng, túi xách, vật cầm
tay...) đều nên được mô tả cụ thể thay vì để chung chung, và trước khi chốt nội dung đạo cụ đó,
rà lại toàn bộ kịch bản xem có chi tiết/thoại nào ở cảnh khác nhắc đến cùng loại đồ vật không —
nếu có, cố tình cho đạo cụ ở cảnh đầu trùng khớp để tạo hiệu ứng "gieo trước, trả sau". Đồng
thời nội dung đạo cụ nên nhất quán với tính cách/hoàn cảnh nhân vật đã chốt (ví dụ: giỏ hàng
vơi, đồ bình dân, không món gì đắt tiền, nếu nhân vật đó cần trông giản dị theo nguyên lý 4).
(Đã ghi nhận là một hạng mục cần rà khi viết master — bổ sung vào phần "Cấu trúc dữ liệu cần
biết" trong SKILL.md.)

## Bài học 8 — 2026-07-25: Thiếu checklist hệ thống → sót thành phần khung hình lần lượt từng cái một

User phải chỉ ra từng thứ bị thiếu qua nhiều lượt: khách hàng đứng sai chỗ → đạo cụ giỏ hàng
chưa tả → khách xếp hàng không có xe đẩy → nền không có người mua sắm → mức độ đông đúc sai với
chi tiết kịch bản. Mỗi lần đều được vá riêng lẻ. User chỉ ra vấn đề THẬT: skill chỉ có các
nguyên lý phản ứng (rút ra sau mỗi lỗi) mà không có một danh sách hệ thống các thành phần bắt
buộc phải quyết định trong mỗi khung hình — nên lỗi cứ tái diễn ở một hạng mục khác.

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

## Bài học 9 — 2026-07-25: Sót NỘI THẤT CƠ BẢN vì "hiển nhiên", lại thừa đạo cụ vì "khai thác kịch bản"

Master một cảnh diễn ra trong phòng làm việc bị user chỉ ra thiếu GHẾ — thứ cơ bản đến mức không
ai nghĩ phải viết ra, nhưng thiếu nó thì khung hình đọc như phim trường dựng tạm. Nghiêm trọng hơn:
một SF con của cùng scene yêu cầu nhân vật "ngồi xuống ghế", trong khi master không hề có ghế →
SF con buộc phải bịa ra một chiếc ghế không tồn tại, phá continuity mà không ai phát hiện cho tới
khi render.

Cùng lúc, user yêu cầu BỎ một đạo cụ mà trước đó đã cố ý đưa vào để "gieo-trả" với thoại của cảnh
khác, với lý do: nó không cần thiết, chỉ làm rối khung hình, nên tập trung vào cảm xúc nhân vật và
bố cục chuẩn.

**Hai nguyên tắc rút ra (bổ sung cho nhau, không mâu thuẫn):**

1. **Nội thất cơ bản của loại bối cảnh phải nằm trong checklist**, tách riêng khỏi mục "đạo cụ"
   — vì nó thuộc loại kiến thức "hiển nhiên" nên bị bỏ qua theo một cơ chế khác với đạo cụ thường.
   Kèm một bước KIỂM TRA CHÉO bắt buộc: rà mọi SF con của scene, nếu SF nào yêu cầu tư thế cần đồ
   nội thất (ngồi/tựa/nằm) thì món đó phải có sẵn trong master.

2. **Checklist là để không bỏ sót, KHÔNG phải để nhồi cho đủ.** Việc học được nguyên lý gieo-trả
   (bài học 7) dễ dẫn tới thái cực ngược lại: biến mọi chi tiết trong thoại thành một vật thể đặt
   trong khung. Đó là minh họa thô và làm phân tán khỏi gương mặt nhân vật. Chi tiết nội tâm được
   truyền tải mạnh hơn nhiều qua ngôn ngữ cơ thể và biểu cảm (dáng ngồi sụp, ánh mắt né tránh, vai
   xuôi) so với một vật thể chỉ trỏ vào nó.

**Đính chính quan trọng (cùng ngày, sau khi sửa lần đầu):** lần sửa đầu tiên đã phản ứng quá tay —
dọn luôn cả GIẤY TỜ trên bàn làm việc cùng với vật thừa. User đính chính: giấy tờ trên bàn làm việc
là chuyện hiển nhiên của loại không gian đó, không phải thứ thừa; thứ thừa chỉ là vật được cố ý cài
vào để minh họa lời thoại. Từ đó rút ra ranh giới BA LOẠI vật thể (đã thành nguyên lý 14):
   - (a) vật THUỘC VỀ bối cảnh (giấy tờ trên bàn làm việc, hàng trên kệ) → bắt buộc có, tả khái quát,
     cho lùi ra nền. Thiếu là không gian giả tạo.
   - (b) đạo cụ THAM GIA HÀNH ĐỘNG (vật được cầm/đưa/đẩy trong beat) → giữ, tả cụ thể, tách bạch
     khỏi nhóm (a) để mắt nhận ra.
   - (c) đạo cụ MINH HỌA lời thoại/nội tâm (khung ảnh con cái để nói "tôi có con") → đây MỚI là thừa,
     loại bỏ, và phải viết lệnh cấm tường minh vì model sẽ tự thêm theo mô-típ quen thuộc.
Bài học meta: khi user chê "thừa", phải xác định CHÍNH XÁC vật nào thừa và vì lý do gì, đừng suy
rộng thành "dọn sạch mọi thứ" — phản ứng quá tay theo hướng ngược lại cũng là một lỗi.

(Đã thêm nguyên lý 14 ba-loại-vật-thể vào SKILL.md, tách mục 4 "nội thất cơ bản" và mục 5 "vật dụng
thuộc về bối cảnh" thành hai mục riêng trong checklist. Đây là điều chỉnh cho cách diễn giải quá đà
của bài học 7, không phải phủ định nó.)

## Bài học 10 — 2026-07-25: Chữ nhỏ trong ảnh wide dễ nhòe thành ký tự vô nghĩa

Bảng tên nhân vật trong một ảnh medium-wide render ra thành các ký tự méo mó vô nghĩa, dù prompt
đã liệt kê đúng danh sách chữ được phép (bài học 5). Liệt kê đúng chữ chỉ chặn được việc model
BỊA TÊN KHÁC, không đảm bảo chữ được render SẮC NÉT.

**Nguyên tắc rút ra:** trong câu "chữ được phép xuất hiện", ngoài việc liệt kê đủ và yêu cầu đánh
vần chính xác, phải thêm yêu cầu "in RÕ RÀNG DỄ ĐỌC, không nhòe thành ký tự vô nghĩa". Với khung
càng rộng thì chữ càng nhỏ và rủi ro càng cao — cân nhắc chấp nhận chữ mờ ở master và chỉ đòi chữ
sắc nét ở các SF cận, thay vì kỳ vọng mọi khung đều đọc được chữ.
(Đã bổ sung vào mục 9 của CHECKLIST trong SKILL.md.)

## Bài học 11 — 2026-07-25: Skill dạy viết từng prompt nhưng không dạy thiết kế BỘ góc của cả scene

Sau khi render đủ bộ SF một cảnh hội thoại dài (~53s), user nhận xét: các góc đều đúng nhưng
phần hội thoại chính chỉ ping-pong giữa 2 góc cận lặp đi lặp lại — cần thêm 2-3 góc bổ sung
(gần hơn, hoặc nghiêng 3/4), không cần khác hoàn toàn, và không được cực đoan. User cũng nêu
quy tắc tỷ lệ: cảnh diễn ra nhanh thì +1 góc, cảnh dài thì +3-5 góc; cảnh đông người (3-4 người
cùng giao tiếp) phải có góc lấy được nhóm 2-3 người, không chỉ toàn thể + đơn.

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

## Bài học 12 — 2026-07-25: Mỗi shot chỉ được một người nói, nhưng đừng vì thế mà lạm dụng khung solo

Sau khi bổ sung các góc đơn nhân vật, user chỉ ra hai điều liên tiếp:

1. **Shot gán vào SF chỉ có một người thì chỉ người đó được nói.** Rà lại thì có 6 shot đang nhét
   thoại của hai người vào một SF đơn. Vì mỗi shot sẽ thành một clip video có lip-sync, việc này
   khiến model dựng video không biết ai đang nói — khẩu hình sai, hoặc nhân vật vắng mặt vẫn có tiếng.
2. **Nhưng sửa xong lại lạm dụng khung solo** — bản chia lại có tới 16/18 shot chỉ một người trong
   khung, user nhận xét ngay là "chán".

**Nguyên tắc rút ra:** phân biệt rõ "một người NÓI" với "một người TRONG KHUNG". Quy tắc cứng chỉ
là cái thứ nhất. Two-shot vẫn hợp lệ khi một người nói còn người kia phản ứng im lặng — và thường
là khung giàu hơn vì thấy được cả phản ứng người nghe. Nhắm khoảng 35-45% số shot dùng khung từ
2 người trở lên; để dành cận đơn cho câu đắt nhất và khoảnh khắc nội tâm. Khi phải tách một câu
dài thành hai shot, giữ nguyên 100% chữ của kịch bản gốc, chỉ đổi góc giữa chừng.

Đây lại là một lần phản ứng quá tay theo hướng ngược lại (xem thêm bài học 9) — sửa một lỗi rồi
đẩy sang thái cực đối diện. Khi nhận một quy tắc cứng, phải hỏi thêm: quy tắc này ràng buộc CHÍNH
XÁC cái gì, và cái gì vẫn còn tự do?
(Đã thêm mục "Chia câu vào shot" và "Prompt video (Grok image-to-video)" vào SKILL.md.)

## Bài học 13 — 2026-07-25: Chia shot quá vụn; và quy tắc lip-sync đúng là "người nói phải trong khung"

User chốt chuẩn thời lượng: **70% shot 10s, 30% shot 6s**. Bản chia trước đó toàn shot 3-5s —
quá vụn, vừa nhiều clip phải dựng vừa cắt liên tục gây mệt mắt.

Quan trọng hơn, việc phải gộp thoại cho đủ 10s làm lộ ra rằng bài học 12 đã phát biểu quy tắc
lip-sync CHẶT HƠN MỨC CẦN THIẾT ("một shot chỉ một người nói"). Ràng buộc thật của lip-sync là:
**người NÓI phải CÓ MẶT trong khung của SF đó** — chứ không phải mỗi clip chỉ được một người nói.
Từ đó:
- SF đơn nhân vật → đúng là chỉ người đó được nói (bài học 12 vẫn đúng cho trường hợp này).
- SF hai người trở lên → hai người đối đáp trong cùng một clip hoàn toàn hợp lệ, và đây chính là
  cách gộp thoại cho đủ 10s mà không phải chia vụn.
- SF insert không thấy mặt ai (bàn tay, màn hình) → thoại của bất kỳ ai cũng được, chỉ cần ghi rõ
  giọng vang lên ngoài khung.

**Nguyên tắc rút ra:** khi phát biểu một quy tắc cứng, phải phát biểu đúng ở mức ràng buộc THẬT SỰ
của nó, không phát biểu ở mức chặt hơn cho "an toàn" — vì một quy tắc quá chặt sẽ chặn mất những
lựa chọn hợp lệ và đẩy công việc sang một lỗi khác (ở đây: chia vụn shot, lạm dụng khung solo).
Khi một ràng buộc mới (thời lượng) làm quy tắc cũ trở nên bất khả thi, đó thường là dấu hiệu quy
tắc cũ bị phát biểu sai chứ không phải hai yêu cầu mâu thuẫn nhau.
(Đã sửa mục "Chia câu vào shot" trong SKILL.md: thêm chuẩn thời lượng và phát biểu lại quy tắc.)

## Bài học 14 — 2026-07-25: Thoại "gọi/triệu tập" không cùng không gian với phần còn lại của cảnh

User chỉ ra một câu thoại mở đầu cảnh (kiểu "Vào phòng tôi ngay") bị gán vào SF master của cảnh đó
— nhưng câu ấy xảy ra TRƯỚC khi hai nhân vật đối diện nhau, ở một không gian khác (người quản lý
gọi vọng từ cửa phòng ra khu làm việc). Trong khi master là lúc cả hai đã đứng đối mặt, cửa đã đóng.
Hình và lời đá nhau.

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

## Bài học 15 — 2026-07-25: Prompt video có FORM CHUẨN riêng — không được tự chế format

Các prompt video đầu tiên được viết theo format tự nghĩ ra (một đoạn mô tả chuyển động + đuôi khóa,
thoại để riêng trong field text). User chỉ ra form chuẩn đã kiểm chứng từ dự án trước, khác hẳn:
THOẠI PHẢI NHÚNG THẲNG VÀO PROMPT, mỗi câu kèm nhãn cảm xúc tiếng Anh (`TÊN — quiet, firm:`), vì
model video đọc thoại từ prompt để làm lip-sync và giọng — không phải từ field text.

Form 6 khối cố định: (1) `REFS · Start frame: <ID>`, (2) câu "Bắt đầu trực tiếp từ frame tham chiếu..."
+ khối "Nhận diện:" nêu từng người bằng trang phục/vị trí và phân rõ chính/phụ (phụ mờ = "giữ nguyên
out nét, KHÔNG lộ mặt"), (3) "Một shot liền N giây... Camera <LOẠI>", (4) hành động + thoại nhúng
xen kẽ nhịp phản ứng, off-screen ghi `TÊN (off-screen) —`, (5) khối "Âm thanh: CHỈ thoại nhân vật,
tiếng Anh giọng Mỹ...", (6) footer khóa nguyên văn "Không nhạc. Không narrator... Không thêm, xóa,
thay thế hoặc nhân bản nhân vật."

**Nguyên tắc rút ra:** khi làm việc trong một pipeline đã chạy thành công trước đó, phải hỏi/tìm
form chuẩn hiện có TRƯỚC khi tự thiết kế format mới — kể cả khi format tự nghĩ trông hợp lý. Form
đã kiểm chứng chứa những quyết định không hiển nhiên (thoại nhúng trong prompt, nhãn cảm xúc, khối
âm thanh) mà format tự chế sẽ bỏ sót. (Đã thay toàn bộ mục "Prompt video" trong SKILL.md bằng form chuẩn.)

## Bài học 16 — 2026-07-25: Ba chuẩn ràng buộc lẫn nhau — 10s, 2-3 lượt thoại, khung hai người

User siết lại ba chuẩn cùng lúc, và chúng thực chất là MỘT hệ quả dây chuyền chứ không phải ba
yêu cầu rời rạc:
1. **~90% shot dài 10s** (trước đó là 70%), 6s chỉ dùng thỉnh thoảng.
2. **Mỗi shot 10s phải có 2-3 lượt thoại**, không để một câu ngắn rồi thừa 7 giây nhân vật đứng im.
3. **Mặc định khung phải có từ 2 người**; SF một nhân vật là ngoại lệ, không phải lựa chọn thường dùng.

Dây chuyền: chuẩn 10s ⟹ cần 2-3 lượt thoại để lấp đủ ⟹ hai người phải đối đáp trong cùng clip
⟹ cả hai buộc phải cùng có mặt trong khung (vì quy tắc lip-sync: người nói phải trong khung).
Nghĩa là khung một người vừa buộc phải cắt vụn thoại, vừa mất phản ứng người nghe, vừa xem chán.

User cũng đính chính một hiểu nhầm cụ thể: **góc 3/4 KHÔNG đồng nghĩa với khung một người** —
cái cần là *medium 3/4 hai người* (camera lệch ~45° nhưng vẫn ôm trọn cả hai), chứ không phải
"3/4 mà chỉ có một người trong khung". OTS qua vai cũng tính là khung hai người.

**Nguyên tắc rút ra:** khi nhận nhiều yêu cầu cùng lúc, tìm xem chúng có phải hệ quả của nhau
không — nắm được sợi dây nhân quả thì áp dụng đúng và nhất quán, còn coi chúng là ba luật rời
rạc thì rất dễ thỏa mãn luật này mà vi phạm luật kia. Ước lượng thời lượng thoại: tiếng Anh
~2,5 từ/giây, nên 10s ≈ 25 từ; nhắm sát mức đó, không dư quá 2 giây.
(Đã cập nhật mục "Chia câu vào shot" và "Bộ góc máy" trong SKILL.md.)

## Bài học 17 — 2026-07-25: Sửa thoại sau khi prompt đã viết → prompt lệch âm thầm

User ghép thoại của hai shot làm một rồi xóa shot kia, nhưng prompt video của shot còn lại vẫn là
bản viết cho lời thoại cũ (chỉ một câu) — không có gì báo hiệu, chỉ phát hiện khi đọc lại.

**Nguyên tắc rút ra:** dữ liệu do AI sinh ra dựa trên một dữ liệu khác (prompt video sinh từ lời
thoại) cần một MỐC ĐỒNG BỘ để phát hiện lệch — lưu ảnh chụp của nguồn tại thời điểm sinh
(`prompt_text` = bản thoại lúc viết prompt), rồi để giao diện tự so sánh và cảnh báo khi nguồn
thay đổi. Không nên trông chờ người dùng tự nhớ. Khi viết/sửa prompt video, LUÔN cập nhật lại
mốc này cho khớp.
(Đã thêm badge "⚠ thoại đã đổi — prompt video chưa viết lại" trên từng shot, bộ đếm tổng ở thanh
trên, và nút "✓ đã khớp" để đánh dấu thủ công sau khi prompt được viết lại.)

## Bài học 18 — 2026-07-25: SF insert thuần đạo cụ là khung chết khi thành video

User xem lại các SF insert (cận màn hình giám sát, cận tờ giấy trên bàn) và chốt: "sau không cần
các SF như thế này đâu, chi tiết quá mà không có người". Những khung này rất đẹp khi đứng yên như
một tấm ảnh, nhưng khi thành clip 10s thì không có gương mặt, không lip-sync, không cảm xúc — chỉ
là vật thể nằm im trong lúc giọng nói vọng từ ngoài khung, người xem rơi ra khỏi câu chuyện.

**Nguyên tắc rút ra:** loại bỏ SF insert thuần đạo cụ khỏi bộ khung chuẩn. Đạo cụ quan trọng thì
đưa VÀO khung có người — dựng two-shot/medium sao cho thấy được cả hành động của bàn tay LẪN gương
mặt nhân vật, giữ được đạo cụ mà không mất phản ứng. Chỉ cân nhắc insert khi đạo cụ mang thông tin
mắt bắt buộc phải đọc rõ (một dòng chữ quyết định, một con số) và không cách nào lồng vào khung có
người — và ngay cả khi đó, ưu tiên biến nó thành một nhịp rất ngắn bên trong shot có người thay vì
một shot riêng.

Bài học meta: tiêu chí đánh giá một SF phải là "nó sẽ thành CLIP như thế nào", không phải "tấm ảnh
này có đẹp không". Một khung tĩnh giàu chi tiết có thể là một clip rỗng.
(Đã sửa mục "Bộ góc máy" và "Chia câu vào shot" trong SKILL.md.)

## Bài học 19 — 2026-07-25: Tái dùng master trước khi nghĩ tới dựng SF mới

Sau khi bỏ hai SF insert thuần đạo cụ (bài học 18), phản xạ đầu tiên là dựng HAI SF two-shot mới
để thay thế — mỗi cái cho một đạo cụ. User bác: "không cần thiết phải phức tạp như vậy, dùng góc
rộng (master cũng được mà)... góc rộng/master đáp ứng được thì không cần phức tạp hoá đi đến từng
góc nhỏ như vậy."

Master vốn đã chứa toàn bộ bàn làm việc, mọi đạo cụ trên đó và cả hai nhân vật. Những hành động
như chỉ vào màn hình, đẩy một tờ giấy, với lấy một vật đều diễn ra được ngay trong khung ấy —
chỉ cần mô tả ở PROMPT VIDEO, không cần một khung hình mới. Dựng thêm SF cho từng chi tiết nhỏ
chỉ tốn thêm ảnh phải render và duyệt, thêm rủi ro lệch continuity, mà không được gì hơn.

**Nguyên tắc rút ra:** SF mới chỉ dựng khi cần một CỠ CẢNH hoặc GÓC NHÌN mà các SF sẵn có không
có (cận để thấy biểu cảm, đảo phía để shot/reverse, đổi tư thế ngồi/đứng). KHÔNG dựng SF mới chỉ
vì xuất hiện thêm một hành động hay một đạo cụ trong cùng một bố cục — hành động thuộc về prompt
video, không thuộc về SF.

Bài học meta: khi sửa một lỗi (bỏ insert), đừng mặc định phải thay bằng thứ gì đó mới cùng số
lượng. Hỏi trước: những gì đã có có kham được không? Đây là lần thứ ba mắc cùng một dạng lỗi —
phản ứng quá tay khi sửa (xem bài học 9 và 12) — nhưng lần này ở dạng "thêm tài nguyên mới thay
vì tái dùng tài nguyên sẵn có".

## Bài học 20 — 2026-07-25: Phải TÍNH số từ trước khi chia shot, không ước lượng bằng cảm giác

User nhìn badge ước lượng trên board và chỉ ra hàng loạt shot lãng phí thời lượng: 3.3s/10s,
3.0s/10s, 1.7s/6s, 1.3s/6s — có shot chỉ dùng 1/3 số giây, phần còn lại là nhân vật đứng im.
Yêu cầu: thoại phải lấp gần kín, chỉ chừa 1-2 giây, tối đa 3 giây. Và một shot được phép chứa
tối đa 4 lượt thoại (trước đó tôi tự giới hạn ở 2-3).

Nguyên nhân: tôi chia shot theo cảm nhận về "nhịp cảnh" rồi mới gán thời lượng, thay vì ĐẾM TỪ
trước. Công thức board dùng là `giây = số từ ÷ 3`, tức shot 10s cần 21-30 từ và shot 6s cần 12-18
từ — có sẵn một phép tính chính xác mà tôi không dùng.

**Nguyên tắc rút ra:** khi hệ thống đã có sẵn một công thức định lượng (ở đây là hàm ước lượng
thời lượng ngay trong code giao diện), phải ĐỌC và DÙNG ĐÚNG công thức đó làm ràng buộc khi thiết
kế, thay vì ước lượng bằng cảm giác rồi để người dùng phát hiện lệch. Quy trình đúng: đếm từ của
cụm thoại → suy ra thời lượng → mới quyết định gộp mấy câu và chọn 6s hay 10s.

Khi hai chuẩn xung đột (tỷ lệ 90% shot 10s vs. lấp kín thời lượng) thì **lấp kín thắng** — thà
dùng 6s cho một cụm thoại ngắn còn hơn ép lên 10s rồi để trống 4 giây.
(Đã viết lại mục "Chia câu vào shot" trong SKILL.md với công thức số từ và ngưỡng cụ thể.)

## Bài học 21 — 2026-07-25: Thoại phải khớp với BỐ CỤC KHÔNG GIAN mình vừa dựng ra

Master của một cảnh được thiết kế là hai không gian THÔNG NHAU không có tường ngăn (để hợp lý hoá
việc nhân vật ở phòng bên nghe được tiếng cửa mở). Nhưng thoại mở cảnh giữ nguyên kịch bản gốc:
nhân vật vừa vào cửa đã hỏi "X đâu rồi?" và được trả lời "Ở bếp." — trong khi theo đúng bố cục
mình vừa dựng, cô ấy nhìn thẳng vào là thấy người kia đang đứng nấu.

**Nguyên tắc rút ra:** khi thiết kế bố cục không gian cho master (nhất là khi cố ý cho hai khu vực
thông nhau, hoặc ngược lại ngăn cách nhau), phải rà lại TOÀN BỘ thoại của scene xem có câu nào giả
định một bố cục khác không. Các câu dễ vướng: hỏi vị trí người khác ("X đâu?"), thông báo điều mà
nhân vật lẽ ra tự thấy, gọi vọng sang phòng khác. Kịch bản viết ra khi chưa có bố cục cụ thể, nên
mâu thuẫn kiểu này chỉ lộ sau khi master đã chốt — và người viết prompt phải là người bắt được.

Cách sửa tốt: đổi câu thoại sang một hành vi hợp bố cục mà VẪN GIỮ được thông tin/đạo cụ cần gieo
(ở đây: thay câu hỏi vị trí bằng một câu nhận xét về MÙI món ăn — vừa tự nhiên với người vừa bước
vào, vừa giữ nguyên món ăn đó làm đạo cụ gieo-trả cho cảnh sau). Đừng chỉ xoá câu vướng.

## Bài học 22 — 2026-07-25: Cảnh 3 người cần tầng "rộng vừa", không nhảy thẳng từ master xuống cận

User hỏi vì sao cảnh có ba nhân vật mà không có thêm 1-2 góc rộng vừa (nhỏ hơn master nhưng không
cận) để có thêm khung hình đủ cả ba người. Rà lại thì đúng: cả scene chỉ có MASTER là khung duy
nhất thấy đủ ba người, mà master lại quá rộng để đọc biểu cảm — các góc còn lại đều là two-shot
hoặc cận, tức nhân vật thứ ba biến mất khỏi câu chuyện hình ảnh.

**Nguyên tắc rút ra:** cảnh từ 3 nhân vật trở lên phải có thêm 1-2 GÓC RỘNG VỪA lấy đủ cả nhóm —
gần hơn master một nấc (cắt bớt trần và rìa phòng), nhân vật to hơn hẳn nhưng vẫn chưa phải cận.
Hai biến thể đáng có: (a) rộng vừa thẳng, cùng hướng master chỉ tiến camera gần hơn; (b) rộng vừa
QUA VAI một nhân vật — người đó làm tiền cảnh mềm, hai người còn lại nét rõ. Biến thể (b) đặc biệt
đắt khi nhân vật tiền cảnh là người đang IM LẶNG lắng nghe: sự hiện diện câm lặng đó làm khung
hình nặng hơn hẳn một two-shot thường.
(Đã bổ sung vào mục "Bộ góc máy" trong SKILL.md.)

## Bài học 23 — 2026-07-25: Nhân vật đổi chỗ giữa hai shot mà không có nhịp chuyển → video khựng

User phát hiện: shot trước nhân vật còn đứng ở khu bếp, shot sau đã ngồi nắm tay nhân vật khác ở
bàn ăn — nhảy vị trí tức thì, mắt người xem vấp. Rà lại cả scene thì có tới hai chỗ như vậy.

Nguyên nhân gốc: SF là ảnh TĨNH quyết định vị trí ĐẦU clip. Khi chia shot, rất dễ chỉ nghĩ tới
"khung này hợp với câu thoại này" mà quên rằng vị trí cuối shot trước phải nối được với vị trí
đầu shot sau. Lỗi này không lộ ra khi đọc bảng shot — chỉ lộ khi hình dung chuỗi video chạy liền.

**Nguyên tắc rút ra:** sau khi chốt SF cho từng shot, phải duyệt các CẶP SHOT LIỀN NHAU và hỏi
"ai đổi chỗ giữa hai khung này?". Ba cách xử lý theo mức độ:
1. Chèn một shot CHUYỂN khi đổi khu vực — dùng khung rộng thấy trọn đường đi, SF của shot chuyển
   lấy theo vị trí XUẤT PHÁT (khớp cuối shot trước), rồi mô tả nhân vật di chuyển tới bố cục của
   shot kế tiếp trong prompt.
2. Cho nhân vật VỪA ĐI VỪA NÓI — mượn luôn câu mở đầu của lượt thoại kế làm lời cho nhịp chuyển,
   khỏi tốn một shot câm (user gợi ý chính cách này).
3. Với quãng ngắn cùng khung: chỉ cần mô tả bước di chuyển ở CUỐI prompt shot trước.

Kèm một ngoại lệ quan trọng: **shot chuyển được miễn quy tắc lấp kín thời lượng** (bài học 20),
vì nội dung của nó là hành động di chuyển chứ không phải thoại — 6s mà chỉ có 3-5 từ là hợp lệ,
phần còn lại dành cho việc đi, kéo ghế, ngồi xuống. Đừng nhồi thoại vào cho đủ giây.
(Đã thêm vào mục "Chia câu vào shot" trong SKILL.md.)

## Bài học 24 — 2026-07-25: Nhân vật đổi trang phục qua các cảnh → phải tạo REF RIÊNG cho từng bộ

Một nhân vật chính đổi trang phục theo mốc thời gian của phim (đồng phục lúc đi làm → đồ ở nhà sau
khi mất việc → đồ lịch sự đi gặp đối tác → đồng phục nghề mới...). Khi viết SF cho cảnh có bộ đồ
mới, tôi vẫn đính REF cũ (mặc đồng phục) rồi MÔ TẢ BẰNG CHỮ bộ đồ mới trong prompt, kèm câu cấm
"chỉ lấy mặt, không lấy trang phục". User bắt ngay: "thế phải tạo nhân vật nữ chính trong trang
phục khác chứ?"

Đây đúng là lỗi bài học 1 và 3 lặp lại ở một dạng khác — ảnh tham chiếu là input trực quan mạnh
hơn hẳn lời cấm bằng văn bản, model sẽ vẽ lại bộ đồ trong ảnh.

**Nguyên tắc rút ra:** rà toàn bộ kịch bản NGAY TỪ ĐẦU để liệt kê các "trạng thái trang phục" của
mỗi nhân vật chính (thường tương ứng với các chặng của cốt truyện), rồi tạo một cặp
`REF_<TÊN>_<TRẠNG THÁI>_PORTRAIT` + `_FULL` cho từng bộ. SF của mỗi cảnh đính đúng REF của trạng
thái đó — không bao giờ mô tả bộ đồ mới bằng chữ trên nền một REF mặc bộ khác.

Cách tạo REF trang phục mới: đính REF gốc để lấy KHUÔN MẶT + TÓC + TÔNG DA, và chống copy trang
phục bằng nhiều lớp giống bài học 3 nhưng đảo chiều — (a) cảnh báo ở đầu prompt nêu ĐÍCH DANH bộ
đồ trong ảnh tham chiếu và cấm dùng nó; (b) mô tả bộ đồ mới bằng đặc điểm TƯƠNG PHẢN cụ thể
(không cổ áo, không cúc, không màu đó, không bảng tên); (c) nhắc lại lệnh cấm ở cuối prompt. Đóng
khung bằng "CÙNG MỘT NGƯỜI nhưng mặc đồ hoàn toàn khác" — ngược với bài học 3 là "MỘT NGƯỜI HOÀN
TOÀN KHÁC nhưng mặc đồ giống".

**ĐÍNH CHÍNH NGAY SAU ĐÓ (cùng ngày) — hai điểm user sửa tiếp:**

1. **Kiến trúc REF gọn hơn nhiều: mỗi nhân vật chỉ cần MỘT portrait cho cả phim.** Portrait là ảnh
   chuẩn của KHUÔN MẶT, dùng mãi. Mỗi bộ trang phục mới chỉ cần thêm MỘT ảnh FULL (đính portrait
   gốc để lấy mặt, thay phần trang phục). Không tạo lại portrait cho từng bộ đồ — vừa tốn ảnh phải
   render, vừa tạo thêm nguy cơ khuôn mặt trôi dần qua các bản. SF của cảnh thì đính CẢ HAI:
   portrait (mặt) + FULL của đúng bộ đồ (trang phục).

2. **TUYỆT ĐỐI KHÔNG hạ nhan sắc nhân vật chính để "hợp hoàn cảnh".** Bản đầu tiên tôi thêm vào
   REF: quầng thâm dưới mắt, ánh mắt trĩu xuống, tóc xuề xòa, "không trang điểm" — user bác thẳng:
   "sao lại biến nhân vật chính thành xấu như này, dù hoàn cảnh nào cũng không được như kiểu này".
   Đây là quy tắc cứng của thể loại: khán giả phải muốn nhìn và muốn bênh nhân vật chính suốt phim.
   Hoàn cảnh khó khăn kể bằng BỐI CẢNH + TRANG PHỤC + DIỄN XUẤT TỪNG KHUNG, không bao giờ bằng
   cách làm xấu ảnh nhân vật gốc.

   Phân vai rõ để lần sau không lẫn: **REF giữ NHÂN DẠNG CHUẨN (luôn đẹp, bất biến cả phim);
   SF và prompt video mới là nơi diễn TRẠNG THÁI CẢM XÚC** (vai sụp, mắt đỏ, tóc rối trong đúng
   một khung). Nhét cảm xúc vào REF là nhét sai tầng — nó sẽ dính vào mọi cảnh dùng REF đó.
(Đã đưa vào SKILL.md: mục "Cấu trúc dữ liệu cần biết" và nguyên lý 4b.)

## Bài học 25 — 2026-07-25: "Nghèo" không có nghĩa là "xấu và quê" — trang phục nhân vật chính vẫn phải đẹp

Viết REF trang phục công sở cho nữ chính (một người thu nhập thấp đi gặp nhân vật giàu), tôi mô tả:
"bộ đồ tử tế nhất cô có", "vải thường", "giày đã đi nhiều", "KHÔNG phải đồ hiệu", "phải đọc ra ngay
là người bình thường mặc đồ đẹp nhất mình có". User bác: trang phục đó khiến nữ chính "ăn mặc xấu,
quê mùa", và tự viết lại — bộ office smart-casual thanh lịch: blazer camel phom đẹp, blouse lụa mờ
cổ V sơ vin, quần âu navy có ly, giày cao gót mũi nhọn, túi tote gọn.

Đây là **lần thứ hai cùng một dạng lỗi** (lần trước: thêm quầng thâm/hốc hác vào REF — bài học 24).
Cùng một gốc: tôi cố "diễn hoàn cảnh nghèo" bằng cách hạ thấp ngoại hình nhân vật chính.

**Nguyên tắc rút ra:** trong melodrama đại chúng, nhân vật chính phải LUÔN đẹp và cuốn hút — cả
gương mặt LẪN trang phục. "Nhân vật nghèo" thể hiện ở BỐI CẢNH (căn nhà, đồ đạc, khu phố) và ở
CỐT TRUYỆN, không phải ở việc cho cô ấy mặc đồ xấu. Người thu nhập thấp ngoài đời vẫn chọn bộ đẹp
nhất và chỉn chu nhất khi đi việc quan trọng — mô tả "vải thường", "đã sờn", "giày cũ", "không có
gu" là vừa sai thực tế vừa phản tác dụng thẩm mỹ.

Cách viết đúng: mô tả trang phục bằng từ ngữ TÍCH CỰC (thanh lịch, phom đẹp, có gu, chuyên nghiệp,
tôn dáng), rồi chỉ dùng lệnh cấm để chặn phía TRÊN (không đồ hiệu phô trương, không trang sức lớn,
không suit may đo kiểu tài phiệt) — chứ KHÔNG chặn phía dưới bằng cách mô tả sự cũ kỹ. Luôn kèm
một câu cấm tường minh: "TUYỆT ĐỐI KHÔNG để trang phục trông cũ kỹ, rẻ tiền hay luộm thuộm."
(Đã bổ sung vào nguyên lý 4b trong SKILL.md.)

## Bài học 26 — 2026-07-25: SF là frame ĐẦU clip → phải bằng trạng thái KẾT THÚC của clip trước

User nêu quy tắc chọn SF mà tôi chưa hệ thống hóa: logic không gian phải liên tục theo diễn biến
kịch bản, trên bốn trục **XA/GẦN → TRÊN/DƯỚI → TRƯỚC/SAU → TRÁI/PHẢI**. Ví dụ user đưa: hai người
đang đứng xa, prompt cho tiến lại gần nói chuyện, rồi SF sau lại trả về khung đứng xa — phi lý.
Hoặc prompt nói nhân vật bước lên thềm, mà SF sau vẫn vẽ họ đứng dưới thềm.

Rà lại thì phát hiện chính mình đang mắc **một biến thể tinh vi hơn**: SF đã vẽ trạng thái SAU
hành động, nhưng prompt video của chính shot đó lại bắt nhân vật LÀM LẠI hành động ấy —
"SF: đã ngồi trên sofa" + "prompt: bà cụ ngồi xuống sofa"; "SF: đã bước ra đứng trên thềm" +
"prompt: cô bước hẳn ra khỏi khung cửa". Clip sẽ có người ngồi/bước hai lần, hoặc model tự dựng
thêm đoạn đứng lên rồi ngồi xuống.

**Nguyên tắc rút ra:** SF là frame ĐẦU của clip, nên nó phải bằng đúng trạng thái KẾT THÚC của
clip trước. Suy ra hai hệ quả:
1. **Mọi hành động chuyển trạng thái phải nằm ở CUỐI clip TRƯỚC** (nơi SF vẫn còn ở trạng thái cũ),
   rồi clip sau mở đầu bằng câu xác nhận: "đã ngồi yên trên sofa (đúng như frame tham chiếu)".
2. **Mỗi SF phải GHI RÕ trạng thái không gian vào mô tả** — ai đứng/ngồi, cách nhau bao xa, ai cao
   hơn ai, đã qua ranh giới nào chưa. Không ghi thì không có dữ liệu để đối chiếu, và lệch chỉ lộ
   ra khi đã render xong.

Quy trình rà bắt buộc sau khi chốt SF cho cả scene: đọc tuần tự từ shot đầu tới shot cuối, ghi ra
trạng thái không gian ở CUỐI mỗi clip, so với trạng thái ở ĐẦU clip kế. Lệch thì hoặc chèn nhịp
chuyển, hoặc đẩy hành động sang clip trước.
(Đã thêm mục "LOGIC KHÔNG GIAN LIÊN TỤC" vào SKILL.md và mục 4 "trạng thái không gian" vào CHECKLIST.)

## Bài học 27 — 2026-07-25: Quy tắc REF trang phục áp dụng cho MỌI nhân vật, không riêng nhân vật chính

Vừa ghi bài học 24 (đổi trang phục thì phải tạo REF riêng, không mô tả bằng chữ) và áp dụng cho
nữ chính, nhưng ngay scene kế tiếp lại mô tả bộ đồ mới của một nhân vật PHỤ bằng chữ trong prompt
SF — user bắt lại lần nữa: "nếu cần thì tạo 1 biến thể nhân vật mới, chứ đừng tự ý mô tả trong
text như này".

Quét lại cả dự án thì thấy nhân vật đó có tới HAI trạng thái trang phục đang bị mô tả bằng chữ
(một bộ theo bối cảnh đặc thù, một bộ sau khi cốt truyện lộ thân phận) — nghĩa là lỗi đã âm thầm
lan qua nhiều scene trước khi bị phát hiện.

**Nguyên tắc rút ra:** khi rút ra một quy tắc về REF, phải QUÉT TOÀN BỘ dự án để áp dụng cho mọi
nhân vật, không chỉ nhân vật đang làm dở. Cách quét rẻ: grep các từ khóa trang phục
(tên món đồ, chất liệu, phụ kiện) trong prompt của mọi SF — chỗ nào có nghĩa là chỗ đó đang mô tả
bằng chữ thay vì đính REF.

Lưu ý thêm: trang phục "bắt buộc theo bối cảnh" (đồng phục bệnh nhân, đồ bảo hộ, áo tù...) cũng là
một trạng thái cần REF riêng — dễ bị bỏ qua vì cảm giác "nó hiển nhiên theo bối cảnh nên tả bằng
chữ là đủ". Và với những bộ đồ gắn với hoàn cảnh tiêu cực, vẫn phải giữ nguyên tắc 4b: nhân vật
được khán giả yêu quý thì luôn phải trông sáng sủa, có thần thái — áo bệnh nhân thì phẳng phiu
sạch sẽ chứ không nhàu nát, dáng đang hồi phục chứ không phải hấp hối.

**NGOẠI LỆ ĐƯỢC PHÉP — chỉnh nhỏ có chủ đích kể chuyện (user xác nhận là hay, nên dùng):**
Quy tắc "phải tạo REF" áp dụng cho việc ĐỔI CẢ BỘ trang phục. Còn việc BỎ BỚT hoặc nới lỏng một
món phụ kiện ngay trong prompt SF thì hoàn toàn nên làm, khi nó mang một ý nghĩa cụ thể cho beat
đó — vì đây là điều chỉnh nhỏ trên nền REF, không phải thay bộ:
- tháo/nới cà vạt, mở cúc cổ → nhân vật vừa phóng từ chỗ làm tới, hoặc cố ý làm buổi gặp bớt
  trang trọng;
- xắn tay áo → đang chịu áp lực, đang "xuống tay" làm việc;
- tháo bảng tên (còn lại vệt vải sáng và lỗ ghim) → vừa bị tước mất danh phận nghề nghiệp;
- cởi blazer vắt lên ghế → đã thả lỏng, cuộc nói chuyện chuyển sang thân mật.

Ranh giới: **thêm/bớt MỘT món để nói một điều → viết thẳng trong SF; đổi TOÀN BỘ bộ đồ → tạo REF.**
Dạng chỉnh nhỏ này không xảy ra thường xuyên, nhưng khi hợp cảnh thì nó kể chuyện rất hiệu quả mà
không tốn thêm ảnh nào.

## Bài học 28 — 2026-07-25: Board TỰ ĐỘNG kèm _FULL → đính thêm FULL trạng thái gây thừa ảnh

User phát hiện tạo ảnh bị chậm và chỉ ra nguyên nhân: mỗi nhân vật đang bị đính TỚI 2 ảnh full-body.
Truy ra là do hàm gom ảnh tham chiếu của board (`_sf_attachments`) có cơ chế tiện lợi: thấy
`REF_X_PORTRAIT` thì tự kèm luôn `REF_X_FULL`. Cơ chế này đúng khi mỗi nhân vật chỉ có một bộ đồ,
nhưng từ khi có REF theo trạng thái trang phục (`REF_X_OFFICE_FULL`, `REF_X_HOSPITAL_FULL`), việc
đính tay bản trạng thái + việc board tự thêm bản mặc định = 3 ảnh cho một nhân vật, trong đó có
một ảnh mặc BỘ ĐỒ SAI HOÀN TOÀN so với cảnh.

Hậu quả kép: ảnh tạo lâu hơn (nhiều input hơn), và tăng nguy cơ model lẫn trang phục giữa hai bộ.

**Nguyên tắc rút ra:** mỗi nhân vật trong một SF chỉ được đính TỐI ĐA 1 portrait + 1 full-body —
đúng bộ đồ của cảnh đó. Đã sửa `_sf_attachments`: chỉ tự kèm `REF_X_FULL` khi SF CHƯA chỉ định sẵn
bất kỳ bản `REF_X_*_FULL` nào cho nhân vật đó.

Bài học meta: khi thêm một khái niệm mới vào dữ liệu (ở đây là "REF theo trạng thái"), phải rà lại
các cơ chế TỰ ĐỘNG cũ đang chạy trên dữ liệu đó — chúng được viết cho mô hình cũ và sẽ hành xử sai
trong mô hình mới, nhưng sai một cách âm thầm vì không báo lỗi. Dấu hiệu để nghi ngờ: hệ thống bỗng
chậm đi hoặc kết quả lẫn lộn mà không rõ lý do.

## Bài học 29 — 2026-07-25: Khối "Nhận diện" tả trang phục càng chi tiết, model vẽ càng láo

Sau khi chuẩn hóa trang phục theo REF, tôi bê luôn mô tả chi tiết đó vào khối "Nhận diện" của
prompt video: "blazer camel + blouse lụa kem cổ V + quần âu navy + giày cao gót thấp đen". User
bác: "phần nhận diện không cần chi tiết như vậy đâu, ngắn gọn thôi không AI nó vẽ vào linh tinh
đấy" — và đưa ví dụ đúng: mỗi người chỉ một cụm trang phục ngắn kèm mã REF, rồi tới tư thế và
vị trí.

Cơ chế gây lỗi: khối Nhận diện càng liệt kê nhiều món, model càng cố vẽ cho ĐỦ mọi món — kể cả
những món không thể nhìn thấy trong khung đó (đôi giày trong một khung cận mặt), và mỗi món được
tả bằng chữ lại là một cơ hội để nó vẽ lệch khỏi ảnh tham chiếu.

**Nguyên tắc rút ra:** Nhận diện là khối CHỐNG NHẦM NGƯỜI, không phải chỗ tả trang phục. Công thức:
`<Tên> = <tuổi + chủng tộc>, <trang phục gói trong MỘT cụm ngắn + (REF_ID)>, <TƯ THẾ> <VỊ TRÍ>.`
Mỗi người ~15-25 từ, cả khối dưới ~300 ký tự. Chi tiết trang phục đã nằm ở ảnh REF và ở prompt SF
rồi — nhắc lại ở đây chỉ làm hại.

Bài học meta: thông tin đúng nhưng đặt SAI TẦNG vẫn gây lỗi. Mỗi tầng của pipeline có một nhiệm vụ
riêng (REF = nhân dạng · SF = bố cục và chi tiết khung · prompt video = chuyển động và phân biệt
người nói) — sao chép thông tin từ tầng này sang tầng khác "cho chắc" thường phản tác dụng.

## Bài học 30 — 2026-07-26: Trang phục nhân vật chính phải MÁT và NHẸ, không chỉ "đẹp"

Bộ `REF_MAYA_HOME2_FULL` tôi viết là "áo len mỏng cổ tròn nâu ấm/xám khói + bên trong lộ cổ áo
thun trắng + quần jogger vải mềm + tất len". Về mặt thẩm mỹ thì không sai, nhưng user bác:
"trang phục home 2 hơi nóng và xấu".

Hai lỗi trong một:
1. **Nóng** — áo len + lớp lót + jogger + tất len là bốn lớp vải dày cho một cảnh trong nhà. Lên
   ảnh nó đọc ra là "mùa đông", trong khi cả phim không có mốc thời tiết nào như vậy. Nhân vật
   trông bí bách, nặng nề.
2. **Xấu** — nhiều lớp vải dày làm mất dáng, và jogger + tất len là ngôn ngữ hình ảnh của sự
   xuề xòa. Đây lại rơi đúng vào lỗi cũ ở nguyên lý 4b (làm nữ chính kém đẹp đi).

**Nguyên tắc rút ra:** với trang phục ở nhà của nhân vật chính, mặc định chọn **ÍT LỚP, VẢI MỎNG,
DÁNG THOÁNG** — cotton/linen mỏng, tay ngắn hoặc tay lỡ, một lớp là đủ. Chỉ thêm lớp dày khi
kịch bản có lý do rõ ràng (ngoài trời lạnh, mùa đông có nêu). Trong prompt nên ghi thẳng cả điều
CẤM: "KHÔNG áo len dày, KHÔNG đồ nỉ, KHÔNG đồ nhiều lớp".

Bài học meta: "ấm áp" là tính từ của KHÔNG KHÍ CẢNH (ánh sáng vàng, khung hình gần, diễn xuất),
không phải của VẢI. Tôi đã dịch nhầm cảm xúc muốn có sang chất liệu quần áo. Sự ấm cúng của một
cảnh gia đình phải đến từ đèn và bố cục, chứ không phải từ việc mặc thêm áo len cho nhân vật.

## Bài học 31 — 2026-07-26: Cùng một không gian thì phải THAM CHIẾU master cũ, kể cả khi là phòng khác

Tôi viết master cho Scene 16 (phòng ngủ của con) và Scene 18 (phòng khách) mà không đính ảnh
tham chiếu bối cảnh nào, vì nghĩ "phòng ngủ là không gian mới, chưa có master". Kết quả: model
tự vẽ ra một ngôi nhà đẹp hơn, rộng hơn, mới hơn hẳn ngôi nhà thuê đã dựng ở Scene 3. User bác:
"cùng 1 nhà mà không được tham chiếu bối cảnh nhà như master 3 à... cùng bối cảnh/ không gian
cần tham chiếu lại nhé, trừ khi là không gian mới".

Sai lầm nằm ở chỗ tôi định nghĩa "không gian" quá hẹp — theo CĂN PHÒNG, trong khi đơn vị đúng là
CÔNG TRÌNH. Phòng ngủ và phòng khách là hai phòng khác nhau nhưng cùng một ngôi nhà: cùng màu
sơn, cùng loại sàn, cùng khung cửa, cùng chiều cao trần, cùng mức sống. Không neo lại thì mỗi
scene model lại rút một ngôi nhà khác từ dữ liệu huấn luyện của nó — và mặc định của nó luôn là
nhà đẹp hơn nhà thật của nhân vật.

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

## Bài học 32 — 2026-07-26: Phim toàn thoại là phim không có nhịp thở

Dựng xong toàn bộ 129 shot, user ghép lại và phản hồi: "các scene chuyển gấp quá, không có đoạn
chuyển, và không có những đoạn cảm xúc cao trào... video từ đầu đến cuối cứ đối thoại liên tục".

Nguyên nhân nằm ngay trong cách tôi làm: mọi quy tắc trong skill này đều xoay quanh việc **chia
thoại vào shot** — lấp kín thời lượng, 2-4 lượt thoại mỗi shot, người nói phải trong khung. Làm
đúng hết các quy tắc đó thì được 100% shot có thoại, và kết quả là một chuỗi đối đáp không ngắt.
Quy tắc không sai; nó chỉ không nói gì về những chỗ **cố tình không có thoại**.

**Nguyên tắc rút ra:** một scene hội thoại dựng xong chưa phải là một cảnh phim hoàn chỉnh. Phải
rà thêm một lượt nữa để chèn NHỊP KHÔNG THOẠI, gồm bốn loại:

- **Beat cảm xúc** (6s) — sau câu thoại nặng nhất, giữ mặt nhân vật im lặng cho câu đó ngấm.
- **Cầu nối** (6-10s) — nhân vật rời khung, đi qua không gian, nối cảnh này sang cảnh kia.
- **Dựng cảnh** (6s) — ngoại cảnh địa điểm mới trước khi vào thoại; bắt buộc khi nhảy thời gian
  ("sáu tháng sau", "một năm sau"), vì nếu không khán giả không có tín hiệu nào để hiểu.
- **Cao trào không lời** (10s) — một hành động cụ thể mang nghĩa, thay cho cả đoạn thoại.

Mật độ tham khảo: khoảng **1,5-2 nhịp cho mỗi scene**, và luôn có một nhịp ở mỗi chỗ đổi địa
điểm hoặc nhảy thời gian.

**Prompt video cho nhịp phải theo form khác form thoại**, ba điểm bắt buộc:
1. `KHÔNG CÓ LỜI THOẠI TRONG CLIP NÀY. Tuyệt đối không ai mở miệng nói, không ai cử động môi như
   đang nói.` — thiếu câu này model sẽ tự cho nhân vật lẩm bẩm.
2. `Âm thanh: KHÔNG thoại, KHÔNG nhạc, KHÔNG hiệu ứng. Giữ clip IM LẶNG HOÀN TOÀN.` — khác hẳn
   footer của shot thoại; để người dựng ghép nhạc mà không phải chống ambient.
3. **Mỗi nhịp chỉ một hành động duy nhất.** Nhồi hai việc vào 6s là thành vội — đúng cái bệnh
   đang muốn chữa.

Mặc định nhịp là **6s**; 10s chỉ dành cho nhịp có hành động thật sự diễn tiến. Nhịp 10s mà không
có gì xảy ra thì thành lê thê, đổi bệnh này lấy bệnh khác.

Bài học meta: tôi tối ưu đúng từng đơn vị (mỗi shot lấp kín thoại, mỗi scene đủ góc) nhưng chưa
bao giờ kiểm tra đơn vị lớn hơn — **nhịp của cả phim**. Sau khi dựng xong toàn bộ scene, phải
xem lại ở tầng tổng thể: chỗ nào chuyển gấp, chỗ nào cảm xúc chưa kịp lắng, chỗ nào khán giả bị
quăng sang cảnh mới mà không được báo trước.

## Bài học 33 — 2026-07-27: Ghi bài học rồi vẫn vi phạm, vì áp dụng sai phạm vi

Hôm trước tôi ghi bài học 31 ("cùng một không gian thì phải tham chiếu master cũ") và thêm hẳn
mục 0 vào checklist. Hôm sau dựng 43 nhịp không thoại, tôi tạo năm khung ngoại cảnh nhà Maya —
mặt tiền chiều muộn, ngôi nhà về đêm, xe đỗ trước nhà, con phố cô đi bộ về, khu phố lúc 2 giờ
sáng — **tất cả đều `bg=None`**. Kết quả: năm căn nhà khác nhau cho cùng một gia đình. User phải
chỉ ra: "có bối cảnh căn nhà của Maya làm từ trước rồi (scene 5) nên các cảnh khác xuất hiện
trước nhà cần phải tham chiếu từ đó ra chứ".

Hai lỗi chồng nhau:

1. **Áp dụng sai phạm vi.** Tôi viết mục 0 dưới tiêu đề "rà đủ trước khi viết prompt SF" nhưng
   trong đầu chỉ gắn nó với việc *viết master của một scene mới*. Khi dựng nhịp — một loại nội
   dung mới, quy trình mới — tôi không chạy lại checklist đó lần nào.
2. **Sót vì master là ảnh nội thất.** Scene 3, 8, 11, 16, 18 đều diễn ra TRONG nhà Maya, master
   của chúng là bếp và phòng khách. Nên khi cần một khung NGOẠI CẢNH của chính ngôi nhà đó, tôi
   quét qua danh sách master, không thấy cái nào là "mặt tiền nhà", và kết luận nhầm là chưa có.
   Thực ra `SF-S5-MASTER` (hiên trước nhà, Scene 5) chính là ảnh gốc cần neo vào.

**Nguyên tắc rút ra:** với mỗi công trình trong phim, lập sẵn một danh sách "ảnh gốc" theo GÓC
NHÌN, không theo scene:
`nhà Maya → ngoại thất: SF-S5-MASTER · bếp: SF-S8-MASTER · phòng khách: SF-S3-MASTER`
Trước khi viết bất kỳ SF nào, tra bảng đó theo *công trình + góc nhìn* rồi mới quyết định tạo
mới hay neo. Và khi thêm một loại nội dung mới vào pipeline (nhịp, toàn cảnh, insert…), phải
chạy lại TOÀN BỘ checklist cho loại đó, đừng cho rằng checklist chỉ dành cho thứ mình đã quen.

Bài học meta: viết được nguyên tắc ra giấy không có nghĩa là sẽ áp dụng đúng chỗ. Lỗi lặp lại
không phải vì thiếu nguyên tắc mà vì **phạm vi áp dụng bị hiểu hẹp hơn thực tế** — nên khi ghi
một bài học, phải nói rõ luôn nó áp dụng cho những loại việc nào.

## Bài học 34 — 2026-07-27: Lạm dụng chữa bằng lệnh cấm là sai, chữa bằng danh sách cũng sai

43 nhịp không thoại dựng xong, user xem lại: "cứ thấy lặp lại thở dài mãi". Tôi sửa hai lần và
sai cả hai:

**Lần 1 — cấm tuyệt đối.** Viết khối "CẤM DÙNG HÍT THỞ SÂU LÀM CÁCH DIỄN" nhét vào cả 43 prompt.
User bác: *"không phải là cấm thở dài mà là đang bị lạm dụng ấy, tuỳ trường hợp cảm xúc thôi
chứ"*. Đúng — người vừa trút được gánh nặng thì thở hắt ra là phản ứng thật, người ngủ gục vì
kiệt sức mà lồng ngực bất động thì thành xác chết.

**Lần 2 — thay bằng thực đơn cử chỉ.** Tôi liệt kê một bảng hành động phân theo bộ phận cơ thể
(bàn tay: siết rồi nới, miết ngón cái…; ánh mắt: cụp xuống rồi ngước lên…) và dán vào cả 43
prompt. User bác tiếp: *"phần này không cố định thế này được đâu, phải tuỳ cảnh cơ, đừng cố định
cho AI còn suy nghĩ và làm ra cho phù hợp… quan trọng của các cảnh này là cảm xúc của nhân vật
nên như thế nào / đang trong hoàn cảnh như thế nào"*. Cũng đúng: một danh sách dùng chung cho
mọi nhịp thì model sẽ nhặt vài món trong đó, và mọi nhịp lại diễn giống nhau — y hệt bệnh cũ,
chỉ đổi từ "thở dài" sang "siết tay". Tệ hơn, nó chặn mất khả năng model tự tìm cử chỉ hợp với
đúng tư thế và không gian trong frame.

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

## Bài học 35 — 2026-07-27: Nhịp không thoại ≈ 15% số shot thoại, tính theo cả phim

Sau khi user yêu cầu thêm nhịp không thoại vì "phim cứ đối thoại liên tục", tôi dựng 43 nhịp cho
129 shot thoại — **33%**. Ghép xong user phản hồi: "nhịp không thoại nhiều quá, bằng 15% cảnh có
thoại thôi là được". Cắt xuống 19 nhịp thì phim gọn hẳn.

Sai lầm không nằm ở ý tưởng mà ở **cách phân bổ**: tôi rải đều mỗi scene 1-2 nhịp cho "cân đối".
Cân đối về mặt số học, nhưng sai về mặt kể chuyện — vì các scene không bằng nhau về sức nặng.
Kết quả là hàng loạt nhịp không gánh việc gì, đặc biệt là các khung dựng-cảnh trống người: chúng
chỉ báo địa điểm, mà địa điểm thì cảnh thoại ngay sau đã nói rõ.

**Con số để dùng lại: số nhịp không thoại ≈ 15% số shot có thoại**, tính trên TỔNG CẢ PHIM chứ
không chia đều theo scene. Có scene xứng đáng 3 nhịp liền (đúng khúc gãy của nhân vật — mất
việc, rời đi, về nhà báo tin), có scene không cần cái nào.

**Bộ lọc để quyết định giữ hay bỏ:** với mỗi nhịp, hỏi *"nhịp này gánh việc gì mà thoại không
làm thay được?"* Không trả lời được thì bỏ. Ba loại luôn xứng đáng giữ: (a) báo nhảy thời gian —
bỏ là khán giả lạc; (b) mắt xích của chuỗi hình ảnh khép vòng tròn — vật gieo ở đầu phim được
trả ở cuối; (c) cao trào không lời — một hành động nói thay cả đoạn thoại.

Khi cắt, đừng xóa: đánh dấu `rejected` kèm lý do, giữ nguyên prompt và ảnh SF. Người dựng xem
lại thấy tiếc cái nào thì bật lại một nút là xong, không phải làm lại từ đầu.

Bài học meta: khi được yêu cầu "thêm X vào", phản xạ của tôi là thêm cho đều và cho nhiều. Nhưng
với những thứ mang tính nhịp điệu — khoảng lặng, nhịp nghỉ, khoảng trống — **thêm quá tay thì
tác dụng đảo chiều**: khoảng lặng đặt đúng chỗ làm câu chuyện nặng thêm, đặt tràn lan thì làm nó
loãng ra. Cần hỏi lại người dựng một tỉ lệ mục tiêu trước khi làm hàng loạt.


## Bài học 36 — 2026-07-28: Chuyển động không có tác nhân — lỗi phi vật lý trong nhịp không thoại

Nhịp mở phim `V-S1-B1` là mặt tiền siêu thị lúc sáng sớm. Tôi viết vào prompt video: *"một chiếc
xe đẩy lăn chậm vào khung ở tiền cảnh"*. User bác: *"SF không thấy có người nào mà xe đẩy chạy
qua, trông sẽ rất giả"*. Mở ảnh SF đã render ra xem thì đúng — tiền cảnh là bãi đỗ xe trống
hoàn toàn, dãy xe đẩy xếp chồng đứng yên cạnh cửa, người chỉ là vài bóng nhỏ ở xa. Một chiếc xe
đẩy tự lăn ngang bãi xe vắng là chuyện không thể có.

Nguyên nhân: khi viết nhịp không thoại tôi sợ khung hình đứng im quá nên nhồi thêm chuyển động
cho "có sự sống", và nhồi bằng cách cho **vật vô tri tự động đậy**. Rà lại cả 43 nhịp thì còn
một cái nữa cùng loại: *"trang giấy khẽ lật vì luồng gió"* trong căn bếp đóng kín lúc hai giờ
sáng — gió ở đâu ra?

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

## Bài học 37 — 2026-07-28: Nhạc nền — quyết VAI TRÒ trước, viết prompt sau

Tôi viết 43 bộ prompt nhạc Suno cho các nhịp không thoại. User nghe rồi bác: *"prompt nhạc chưa
hay lắm... prompt suno tôi gửi bạn chỉ là mẫu thôi, còn việc bạn phải cảm nhận đoạn có nên dùng
nhạc như thế nào, cao trào hay không"* — và chốt tỉ lệ **75% có lời, 25% không lời**.

Hai lỗi:

**1. Bám mẫu thay vì cảm nhận đoạn.** User đưa một prompt mẫu, tôi lấy đó làm khuôn rồi thay
tính từ cho từng cảnh: cảnh buồn thì "somber", cảnh vui thì "hopeful". Kết quả là 43 bản nhạc
cùng một dáng, và mọi cao trào bằng nhau — nghĩa là không có cao trào nào.

**2. Gần như toàn nhạc không lời.** Với drama nhân quả, nhạc có lời (soul/gospel/folk giọng nữ
trầm ấm) tạo được sự đồng hành mà nhạc không lời khó có. Tôi né vì sợ lời hát cạnh tranh với
thoại — nhưng đây là các nhịp KHÔNG THOẠI, chẳng có gì để cạnh tranh cả.

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

## Bài học 38 — 2026-07-28: User thay ảnh master thì mọi khối "khóa look" con thành nói dối

User chốt một ảnh master mới cho Scene 1 (render từ option khác — biển số quầy ĐEN, quầy be,
đèn ấm trung tính) và dán vào board. Tôi rà cập nhật số khách trong master, nhưng KHÔNG cập
nhật khối "khóa look" của các SF con — chúng vẫn tả master cũ ("quầy viền xanh dương, đèn ngả
xanh"). Kết quả: mỗi SF con nhận một ảnh ref nói một đằng và một đoạn chữ nói một nẻo, model
tự dung hòa mỗi khung một kiểu — ba khung ra ba cái quầy khác nhau. User: "SF đồng bộ còn yếu,
trông bối cảnh khác master lắm".

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

## 39. Nhân dạng lệch dù có REF — và một chẩn đoán sai đã bị user sửa lại: REF không có trần

**Chuyện:** làm một SF hai nhân vật, đính 4 ảnh REF (2 portrait + 2 full) + master. Bản 1 ra
sai chi tiết (tóc, quần), bản 2 sai cả chủng tộc của cả hai người. Tôi hạ xuống 2 portrait +
master thì ra đúng, và vội kết luận "đính càng nhiều ref model càng loãng, trần thực dụng là
3 ảnh" — rồi ghi thành luật.

**User bác bỏ luật đó:** *"REF phải đủ tất cả portrait và full body nhé, không dùng trần 3 ảnh
được đâu, ref không có trần đâu nhé, ref bao nhiêu cũng được."* Mẫu thử của tôi quá nhỏ (2 bản
hỏng, 2 bản đúng) để đổ lỗi cho số ảnh — lệch render hoàn toàn có thể là phương sai giữa các
lần tạo, và thiếu ảnh FULL thì trang phục toàn thân lại phải tả bằng chữ, đúng cái mà bài học
2 và 24 đã cấm.

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

## 40. Kịch bản người viết có hard-cut trong một clip — tách thành hai shot, và nói rõ vì sao

**Chuyện:** user gửi lại bản hook đã tự tinh chỉnh, trong đó *"CLIP 8 — 10 GIÂY"* được viết
thành hai nửa: 0–5s hai người dưới sàn có thoại, rồi *"Hard cut sang tủ mát"* cho 5–10s Maya
chạy đi lấy nước cam. Tôi tách thành `8A` (SF sàn, 6s) + `8B` (SF tủ mát, 6s) và ghi rõ lý do
trong phần bàn giao. User sau đó nhắn lại xác nhận đúng nguyên tắc: *"tôi làm không chuyển cảnh
đâu nhé... nếu bạn cần cảnh nào khác, bắt buộc có SF khác."*

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

## 41. Khung ba lớp chiều sâu đẩy model lên góc bird's-eye — và câu phủ định vẫn vẽ ra thứ bị cấm

**Chuyện:** làm SF cầu nối S1→S2, tôi thiết kế một khung ba lớp: tiền cảnh là chỗ sàn trống nơi
bà cụ vừa ngồi, lớp giữa là Maya đã quay lại quầy làm việc, lớp sâu là quản lý đứng ở cửa văn
phòng cuối cửa hàng nhìn về phía cô. Ý đồ: khán giả thấy mối đe dọa mà nhân vật không thấy.

Ảnh ra hỏng hai lần cùng lúc:
1. **Model lùi camera lên góc BIRD'S-EYE toàn cảnh siêu thị** — thấy cả chục dãy quầy từ trên
   trần xuống. Vì ba lớp của tôi trải quá xa nhau theo chiều sâu (sàn ngay trước mặt → quầy →
   cuối cửa hàng), cách duy nhất để lấy đủ cả ba vào một khung là bay lên cao. Model làm đúng
   thứ tôi yêu cầu, và kết quả vi phạm chính quy tắc "tránh góc cực đoan" của skill này.
2. **Bà cụ vẫn nằm chình ình dưới sàn** — dù tôi đã viết "TUYỆT ĐỐI KHÔNG có bà cụ trong khung".
   Vì ngay phía trên đó tôi mô tả tiền cảnh là *"khoảng sàn nơi bà cụ vừa ngồi"*. Câu phủ định
   không xóa được hình ảnh mà chính tôi vừa gieo vào.

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

## 42. Thoại nhân vật chính lúc làm việc tốt — người tốt thật không thuyết minh việc tốt của mình

**Chuyện:** viết cảnh nhân vật chính cứu giúp người lạ, tôi cho cô nói những câu nghe "hay":
giải thích động cơ (*"I know what it looks like when someone's about to go down and nobody
around them is paying attention"*), tuyên bố sẽ ở lại (*"I'm not going anywhere"*, *"Not while
I'm here"* — lặp ý tới ba lần). User chê hai lần liên tiếp: *"nói dư dư, cố ghép vào cho voice
nhiều hơn... nói cứ kiểu kể công kiểu gì ấy, không phải kiểu chân thành"*, rồi chốt nguyên tắc:
*"nhân vật chính khiêm tốn thôi, đừng để nói lố, nói thừa, nói khoe mẽ, tự nhiên thôi."*

Bản sửa được duyệt:
- *"Why are you helping me?"* → **"You needed help."** — ba chữ, rồi LẢNG NGAY sang việc thực
  tế ("Is there somebody I can call for you?"), tay vẫn bận, không nhìn vào mắt người kia.
- *"You're going to lose your job because of me."* → **"Maybe. Drink."** — không phủ nhận,
  không trấn an, quay lại việc đang làm.
- Được cảm ơn nặng lời (*"I will never forget that name"*) → **lúng túng và hạ thấp chuyện
  xuống**: *"It's just juice, ma'am."* — người ngại được cảm ơn tìm cách thoát khỏi khoảnh
  khắc đó.

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

## 43. Hành động đỉnh điểm ở GIỮA chuyển động là thứ model không vẽ nổi — thiết kế khoảnh khắc TRƯỚC hoặc SAU nó

**Chuyện:** khoảnh khắc bản lề "nhân vật vượt qua ranh giới quầy để cứu người" — tôi dựng SF
cô đang LAO NGƯỜI giữa sải chân. Render nhiều lần đều giả: tư thế giữa-bước-nhảy là thứ model
image gần như không làm ra tự nhiên được (khớp vặn, đà sai, mặt biến dạng). User cũng thấy:
*"nhảy qua quầy để ra chỗ Helen e là AI làm ra hơi khó, xem có phương án nào khác không."*

Tôi đưa 5 phương án né (cận đôi chân qua ranh giới; bàn tay bấu mép quầy; kể bằng đồ vật bị bỏ
lại — máy quét nằm nghiêng, màn hình còn sáng; ...). User nghĩ ra phương án thứ 6 tốt hơn cả:
**bỏ hẳn khoảnh khắc di chuyển, vào thẳng khoảnh khắc ĐÃ TỚI NƠI** — cô đã đứng sau lưng bà cụ,
hai tay vừa đặt lên vai. Cảm xúc nằm ở cái chạm, không nằm ở cú nhảy.

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

## 44. Tinh chỉnh thoại nhiều vòng sẽ đánh rơi câu gốc — diff bằng máy sau mỗi vòng, đừng tin trí nhớ

**Chuyện:** sau vài vòng gộp/tách/viết lại shot theo feedback, tôi làm rơi mất một câu thoại
gốc của kịch bản (*"Tanya, orange juice from the cooler. Small bottle."*) mà không hề hay —
câu đó nằm trong shot bị viết lại và bản mới quên mang nó theo. Chỉ phát hiện ra khi chạy một
script so khớp toàn bộ text các shot với script gốc của scene.

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
