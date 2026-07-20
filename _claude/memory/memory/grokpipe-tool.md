---
name: grokpipe-tool
description: CLI Python grokpipe chạy pipeline ChatGPT-tạo-ảnh + Grok-tạo-video; quyết định kiến trúc của user
metadata: 
  node_type: memory
  type: project
  originSessionId: d2baf317-13b2-4d75-a82f-ac86b71ad4b9
  modified: 2026-07-20T06:25:38.985Z
---

User xây tool CLI Python `grokpipe` (tại `/Users/may1/Desktop/minh/grokpipe/`) đọc file pipeline dạng `PIPELINE-BANHMI-VID001-028.txt` và chạy tuần tự IMAGE→VIDEO→EXTRACT, có state.json + resume, cắt frame bằng ffmpeg.

Ba quyết định kiến trúc user đã chọn (2026-07-19):
- **Ảnh (ChatGPT)**: tự động hóa trình duyệt bằng Playwright (không dùng OpenAI API).
- **Video (Grok)**: cổng thủ công — tool in prompt + start-frame, user thả .mp4 vào `inbox/`, tool kiểm tra thời lượng. (Grok image-to-video chưa có API công khai ổn định.)
- **Chấm frame khi EXTRACT**: bỏ AI vision, chỉ heuristic OpenCV (mắt/blur) + duyệt tay.

**Why:** ảnh hưởng toàn bộ thiết kế executor; user ưu tiên không tốn API/không lo ToS ở bước đắt (video).
**How to apply:** lõi chỉ dùng stdlib + ffmpeg; Playwright & opencv là tùy chọn, thiếu thì tự xuống thủ công. Selector ChatGPT gom ở `grokpipe/executors/image_chatgpt.py` biến `SELECTORS`. Máy user: Python 3.14, macOS, ffmpeg 8 có sẵn (opencv có thể chưa có wheel cho 3.14).

Đã cài `.venv` trong project với Playwright + Chromium — chạy tool bằng `./.venv/bin/python -m grokpipe`, KHÔNG dùng python3 hệ thống.

Test thật (2026-07-19): chatgpt.com bị **Cloudflare Turnstile "Verify you are human"** chặn ở chế độ headless. Claude KHÔNG được giải CAPTCHA/né bot và KHÔNG đăng nhập bằng mật khẩu user (user từng dán 3 tài khoản ChatGPT có 2FA — đã từ chối dùng). Bước qua Cloudflare + login + 2FA phải do user tự làm trong cửa sổ headed. Đã thêm chế độ **CDP** (`grokpipe chrome` mở Chrome remote-debugging; `run --chrome-cdp http://localhost:9222` nối vào) — tái dùng phiên user đã login, close() không tắt Chrome của user. CDP plumbing đã test OK.

Grok: SAU CÙNG ĐÃ TỰ ĐỘNG ĐƯỢC (2026-07-19). Cloudflare Grok gắt: captcha fail liên tục khi Chrome mở cờ debug. GIẢI PHÁP (mẹo 2 bước): tắt Chrome debug → mở CÙNG profile (~/.grokpipe-chrome) KHÔNG cờ debug → user đăng nhập Grok qua accounts.x.ai (captcha qua được vì không có cờ debug) → tắt, mở lại CÓ cờ debug → cookie còn nguyên, không cần captcha nữa. Đã test THẬT: video 10.04s / 720p render ~48s, tải về 5.7MB, cắt frame 7-8s đẹp (mắt mở, đúng nhân dạng).

Executor Grok AUTO trong video_grok.py (class GrokSession), kỹ thuật dò từ UI thật: grok.com/imagine; upload input[type=file]; chip "Video"/"720p"/"10s"/"6s" phải CLICK BẰNG JS theo text chính xác (locator click trượt → từng tạo nhầm ẢNH thay vì video); prompt vào [contenteditable] last; Submit qua get_by_role; video xong = <video src="assets.grok.com/.../generated_video.mp4"> với duration>=3; TẢI BẰNG ctx.request.get (KHÔNG fetch-in-page: khác origin, đuôi ?cache= rỗng làm server trả lỗi 81 bytes); trước Submit chụp src video cũ, chỉ nhận src MỚI. Fallback thủ công nếu auto lỗi. Cờ --manual-video để ép thủ công. Tài khoản Grok của user đã dùng ~85% credit.

Config cuối: ảnh AUTO (ChatGPT, CDP) + video AUTO (Grok, CDP, fallback thủ công) + extract tự cắt. gen_timeout ảnh = 120s.

QUAN TRỌNG về EXTRACT (user làm rõ thiết kế 2026-07-20): mọi GÓC MÁY MỚI được khai sinh ở đoạn 5–10s của video (sau quick-cut giây 5); prompt txt đã ghi shot 2 là góc gì. Nên EXTRACT cắt CỐ ĐỊNH giây 7.5, dùng luôn, KHÔNG cắt nhiều ứng viên/không chọn tay/không AI. Đã viết lại extract_frame.py: run_extract chỉ cắt 1 frame ở EXTRACT_AT=7.5 (fallback 7.0/8.0/... nếu lỗi), lưu assets/<OUTPUT_ID>.png. Đừng "mở rộng khoảng cắt" — user bác bỏ hướng đó. Thêm cờ --auto (RunOptions.auto) bỏ mọi cổng duyệt (ảnh+video tự nhận) để "chạy thuần". Đã test: run --only T012..T018 --auto → 6/6 DONE, 0 lỗi, ~5 phút, không nhập phím nào.

Test SCENE 3 (T039–T048, VID_017→021, 2026-07-20): chạy thuần --auto thành công 10/10 DONE 0 lỗi ~8 phút. Gồm mắt xích KHÓ NHẤT là T040 thêm nhân vật mới (base=FRM_S3_MASTER + ref=REF_ELEANOR_PORTRAIT, đính 2 ảnh) → kết quả CHUẨN: giữ nguyên 100% phòng + Victoria, thêm Eleanor đứng ở KHUNG CỬA (đúng lối vào, không đụp sát). ChatGPT đính nhiều ảnh (base trước rồi ref) hoạt động tốt.

Bài học + fix thêm lần này: ChatGPT image gen đôi lúc CHẬM/lỗi nhất thời (scene master phức tạp + ref có lúc >120s hoặc kết thúc lượt mà không ra ảnh) — KHÔNG phải hết cap (test ảnh quả táo đơn giản vẫn OK 28s cùng account ChatGPT Plus). Đã: (1) tăng gen_timeout ảnh 120→300s; (2) run_image khi có session: AUTO lỗi thì RAISE để runner tự retry chat mới (không rớt thủ công dead-end trong --auto); (3) generate() fast-fail khi nút stop tắt mà vẫn không có ảnh sau ~12s (báo "có thể hết lượt tạo ảnh"). Nếu gặp chuỗi fail, cứ chạy lại (resume) — thường lần sau qua. Lưu ý: profile Chrome có thể có nhiều tab/tài khoản ChatGPT (có thể nhiều tài khoản) — nên giữ 1 tab sạch.

HOÀN THÀNH TRỌN PHIM (2026-07-20): chạy full pipeline `run --auto` → 61/61 task DONE, 0 FAILED, ~41 phút, tự động hoàn toàn không nhập phím. Sản phẩm: 28/28 video (mỗi 10.0s) + 33 ảnh (11 REF + 22 FRM master/keyframe/extract), tổng 167MB trong project/assets. Frame cuối VID_028 quy tụ đủ 4 nhân vật đúng nhận diện. Tool đã chứng minh chạy end-to-end trọn vẹn cho cả phim 5 phút. Lệnh chạy trọn: `./.venv/bin/python -m grokpipe run <pipeline.txt> --chrome-cdp http://localhost:9222 --auto`.

Chạy pipeline THẬT (2026-07-20) tìm & sửa 2 bug quan trọng:
1. XUNG ĐỘT PLAYWRIGHT: ChatGPT session + Grok session mỗi cái gọi sync_playwright().start() riêng trong 1 tiến trình → lỗi "using Playwright Sync API inside the asyncio loop". FIX: runner tạo 1 kết nối CDP dùng chung (_get_hub_ctx: 1 sync_playwright + 1 connect_over_cdp), truyền shared_ctx cho cả ChatGPTSession và GrokSession; close() của session bỏ qua nếu dùng shared_ctx, runner đóng hub 1 lần.
2. SELECTOR MODE VIDEO SAI: nút chuyển Image→Video là ICON role=radio aria-label='Video' KHÔNG có text → _jclick theo text không bấm trúng → Grok tạo ẢNH thay vì video (tool chờ <video> 10 phút vô ích). FIX: thêm _click_radio(name) khớp aria-label HOẶC text; 480p/720p/6s/10s cũng là role=radio (có text). Đã verify: Video/720p/10s đều aria-checked=true. Thêm _out_of_credits() để fail nhanh.

ĐÃ TEST TRỌN CHUỖI THÀNH CÔNG (2026-07-20, sau khi user đổi sang tài khoản Grok mới còn credit): chạy `grokpipe run --only T012..T018 --chrome-cdp` → 6/6 task DONE, 0 FAILED, ~4 phút, HOÀN TOÀN TỰ ĐỘNG. VID_001..004 mỗi video Grok render ~45-55s ra đúng 10.04s/720p, tự tải + cắt frame nối (VID_002/003/004 đều xuất phát từ FRM_S1_WIDE cắt từ VID_001 — continuity đúng). Nội dung video khớp prompt sản xuất (bà cụ tìm ví, thu ngân liếc đồng hồ...). Tool đã hoạt động end-to-end thật cho cả ChatGPT ảnh + Grok video + cắt frame. Cần credit Grok để chạy hết 28 video. Mẹo đổi tài khoản Grok: đăng nhập bằng Chrome KHÔNG cờ debug rồi mở lại CÓ cờ debug (như đăng nhập lần đầu).

Test sinh ảnh THẬT (2026-07-19, tài khoản ChatGPT Plus): luồng ChatGPT chạy được end-to-end — CDP + tái dùng login + gửi prompt + ChatGPT sinh ảnh + nhận diện + tải full-res PNG (ảnh Andrea T001 xác nhận đúng). Đã sửa selector ảnh sinh ra thành `img[alt^='Generated image']` (ảnh nằm ở khối riêng, không trong `data-message-author-role='assistant'`); src là `chatgpt.com/backend-api/estuary/content?...` cùng origin nên `_download` fetch-in-page kèm cookie tải được. Khối `[data-testid='image-gen-overlay-actions']` = ảnh đã xong. generate() đổi sang `goto(url)` để mở chat mới (nút new-chat cũ không khớp). Tăng gen_timeout mặc định 240→600s vì ChatGPT sinh ảnh có lúc rất chậm hoặc TREO ("One last tweak..." đứng >14 phút) — đây là flaky phía ChatGPT (có thể do gửi lệnh tạo ảnh liên tiếp quá nhanh), không phải lỗi tool; tool xử lý bằng timeout→retry. Nên chèn delay giữa các task ảnh.
