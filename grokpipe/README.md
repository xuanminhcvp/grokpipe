# grokpipe

CLI Python chạy file pipeline (vd `PIPELINE-BANHMI-VID001-028.txt`) theo đúng
tài liệu `HUONG-DAN-XAY-TOOL.md`: đọc pipeline → chạy tuần tự
**IMAGE → VIDEO → EXTRACT** đến hết, có **sổ trạng thái + resume**, kiểm tra
phụ thuộc, cổng duyệt tay, log, và cắt frame nối video bằng ffmpeg.

- **Ảnh (ChatGPT)**: TỰ ĐỘNG qua CDP (nối Chrome thật đã đăng nhập), *tự rơi
  về thủ công* nếu lỗi. Đã test thật: ~60s/ảnh, tải full-res PNG.
- **Video (Grok Imagine)**: TỰ ĐỘNG qua CDP — upload start-frame, chọn Video
  + 720p + 10s, dán prompt, Submit, chờ render, tải mp4. Đã test thật:
  video 10s render ~48s. *Tự rơi về cổng thủ công* (thả mp4 vào `inbox/`)
  nếu lỗi; ép thủ công bằng `--manual-video`.
- **Cắt frame**: ffmpeg cắt ứng viên giây 7–8 (mỗi 0.1s), OpenCV chấm sơ bộ
  (mặt / mắt mở / độ nét) nếu có, rồi bạn chọn tay. Không đạt → nới 6–9.5s.

## Yêu cầu

- Python 3.10+ và **ffmpeg/ffprobe** trong PATH (`brew install ffmpeg`).
- Lõi chạy **không cần cài gì thêm**.
- Đã tạo sẵn virtualenv `.venv` với Playwright + Chromium. Chạy tool bằng:
  ```bash
  ./.venv/bin/python -m grokpipe ...
  ```
  (Dùng `python3` hệ thống sẽ KHÔNG thấy Playwright — nó nằm trong `.venv`.)
- Cài lại từ đầu nếu cần:
  ```bash
  python3 -m venv .venv
  ./.venv/bin/python -m pip install -r requirements.txt
  ./.venv/bin/python -m playwright install chromium
  ```
  > Nếu bản Python quá mới chưa có wheel `opencv-python`, cứ bỏ qua — tool vẫn
  > cắt frame và cho bạn chọn tay, chỉ không chấm điểm tự động.

## Dùng

```bash
# xem pipeline parse ra sao (debug)
python3 -m grokpipe parse PIPELINE-BANHMI-VID001-028.txt

# in kế hoạch, không chạy
python3 -m grokpipe run PIPELINE-BANHMI-VID001-028.txt --dry-run

# chạy thật (resume tự động — chạy lại là tiếp từ chỗ dở)
python3 -m grokpipe run PIPELINE-BANHMI-VID001-028.txt

# ép tạo ảnh thủ công (không dùng trình duyệt tự động)
python3 -m grokpipe run PIPELINE-BANHMI-VID001-028.txt --manual-image

# chỉ chạy vài task / bắt đầu từ một task
python3 -m grokpipe run PIPELINE-BANHMI-VID001-028.txt --only T012,T013
python3 -m grokpipe run PIPELINE-BANHMI-VID001-028.txt --from T028

# xem trạng thái
python3 -m grokpipe status PIPELINE-BANHMI-VID001-028.txt

# reset để làm lại (giữ nguyên file asset)
python3 -m grokpipe reset PIPELINE-BANHMI-VID001-028.txt --task T013
```

### Cờ chạy chính

| Cờ | Ý nghĩa |
|----|---------|
| `--from ID` | bắt đầu từ TASK_ID/OUTPUT_ID này |
| `--only IDS` | chỉ chạy các id (phân tách bằng dấu phẩy) |
| `--manual-image` | tạo ảnh thủ công, không mở Playwright |
| `--max-retry N` | số lần retry mỗi task (mặc định 3) |
| `--gate-extract` | duyệt lại frame sau khi cắt |
| `--stop-on-fail` | dừng hẳn khi gặp FAILED (mặc định: bỏ qua, phụ thuộc tự chờ) |
| `--headless` | trình duyệt ẩn (đừng dùng lần đầu — cần đăng nhập tay) |
| `--dry-run` | chỉ in kế hoạch |

## Thư mục project

Tạo cạnh file pipeline: `<tên>.project/`

```
<pipeline>.project/
  assets/       ← kết quả chuẩn: REF_ANDREA_PORTRAIT.png, VID_001.mp4, FRM_S1_WIDE.png...
  tries/        ← mọi bản thử (VID_001_try1.mp4, _try2...) — không ghi đè, giữ lịch sử
  candidates/   ← ứng viên frame khi EXTRACT (candidates/FRM_S1_WIDE/cand_7.3s.png...)
  inbox/        ← NƠI BẠN THẢ file tải về từ ChatGPT/Grok; tool tự nhận rồi dọn
  state.json    ← sổ trạng thái (PENDING/RUNNING/DONE/FAILED + đường dẫn + số lần)
  run.log       ← log mọi task
  .chatgpt_profile/  ← phiên đăng nhập Playwright (đăng nhập một lần)
```

## Luồng làm việc thực tế

1. `python3 -m grokpipe run pipeline.txt`
2. **Task IMAGE**: nếu bật auto, cửa sổ ChatGPT mở — đăng nhập lần đầu rồi Enter.
   Tool đính ảnh (BASE trước, REF sau), dán prompt, chờ ảnh, tải về. Bạn duyệt
   OK/Retry. (Auto gãy → tự chuyển thủ công: thả ảnh vào `inbox/`.)
3. **Task VIDEO**: tool in prompt + mở ảnh start-frame. Bạn qua grok.com:
   upload frame, dán prompt, đặt 10s, chạy, tải video, **thả vào `inbox/`**,
   quay lại Enter. Tool kiểm tra thời lượng rồi cho bạn duyệt.
4. **Task EXTRACT**: tool cắt ~11 ứng viên giây 7–8, mở thư mục ứng viên, bạn
   gõ số frame muốn giữ (Enter = tốt nhất theo điểm). Frame này thành start-frame
   cho video sau.
5. Đóng máy giữa chừng cũng được — chạy lại là tiếp tục từ task chưa xong.

## Tự động hóa ChatGPT — 3 cách (chọn 1)

chatgpt.com nằm sau **Cloudflare "Verify you are human" + đăng nhập + 2FA**.
Bước xác minh người thật/đăng nhập **phải do bạn tự làm** (tool không tự vượt).
Chromium **headless bị Cloudflare chặn** — luôn chạy có cửa sổ.

**Cách A — Nối vào Chrome thật (CDP, ổn định nhất, khuyến nghị):**
```bash
# 1) mở Chrome riêng có remote-debugging (tự tìm Google Chrome)
./.venv/bin/python -m grokpipe chrome
# 2) trong cửa sổ Chrome: tự qua Cloudflare + đăng nhập ChatGPT (kể cả 2FA) — MỘT LẦN
# 3) giữ Chrome mở, chạy pipeline nối vào phiên đó:
./.venv/bin/python -m grokpipe run PIPELINE-BANHMI-VID001-028.txt \
    --chrome-cdp http://localhost:9222
```
Vì bạn đã đăng nhập & qua Cloudflare, tool chỉ tái dùng phiên — không đụng gì
tới bước xác minh. Đóng tool KHÔNG tắt Chrome của bạn.

> **Đăng nhập Grok (một lần):** captcha Grok thường TRƯỢT khi Chrome mở cờ
> debug. Mẹo: tắt Chrome debug → mở lại CÙNG profile KHÔNG cờ debug:
> ```bash
> "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
>     --user-data-dir="$HOME/.grokpipe-chrome" "https://accounts.x.ai/sign-in"
> ```
> đăng nhập Grok xong, tắt Chrome, mở lại bằng `grokpipe chrome` — cookie còn
> nguyên, không cần captcha nữa. (Với ChatGPT thì đăng nhập thẳng trong cửa sổ
> debug thường vẫn qua được.)

**Cách B — Profile riêng do tool mở:**
```bash
./.venv/bin/python -m grokpipe run PIPELINE-BANHMI-VID001-028.txt
```
Tool mở cửa sổ Chromium riêng; lần đầu bạn tự qua Cloudflare + đăng nhập, phiên
lưu ở `<project>/.chatgpt_profile/`. Cloudflare có thể làm phiền hơn cách A.

**Cách C — Thủ công hoàn toàn (không automation):**
```bash
./.venv/bin/python -m grokpipe run PIPELINE-BANHMI-VID001-028.txt --manual-image
```
Tool in prompt + ảnh cần đính, bạn tự tạo trên ChatGPT rồi thả vào `inbox/`.

Web UI ChatGPT hay đổi. Nếu auto không lấy được ảnh, tool **tự rơi về thủ công**
nên pipeline không bao giờ đứng. Muốn chỉnh selector cho khớp UI mới: sửa
`grokpipe/executors/image_chatgpt.py` (biến `SELECTORS`).

Grok video hiện chưa có API image-to-video công khai ổn định nên bước video cố
tình để thủ công — đây là phần đắt tiền (mỗi lần sinh là tiền thật), duyệt tay
trước khi nối là rẻ nhất.
