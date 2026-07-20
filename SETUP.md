# SETUP — Khôi phục trên máy mới

Repo này chứa tool **grokpipe** (tự động hoá ChatGPT tạo ảnh + Grok tạo video theo
file pipeline) + toàn bộ asset đã tạo + memory bối cảnh. Làm theo các bước dưới
để có lại môi trường hoàn chỉnh. **AI (Claude Code) có thể đọc file này và tự chạy.**

> Máy nguồn: macOS, Python 3.14, ffmpeg 8, Google Chrome. Project gốc ở
> `/Users/may1/Desktop/minh`.

---

## 0. Chạy nhanh (khuyến nghị)

```bash
cd <thư-mục-repo-này>
bash setup_new_machine.sh      # tạo .venv + cài deps + Chromium + phục hồi memory
```

Rồi làm mục **4 (đăng nhập)** và **5 (chạy)**.

---

## 1. Yêu cầu hệ thống
- **Python 3.10+** và **ffmpeg/ffprobe** trong PATH — macOS: `brew install ffmpeg`
- **Google Chrome** (cho tự động ChatGPT + Grok qua CDP)

## 2. Môi trường Python (KHÔNG có trong git — phải tạo lại)
```bash
cd grokpipe
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m playwright install chromium
```
> Nếu Python quá mới chưa có wheel `opencv-python`, bỏ qua — tool KHÔNG cần opencv
> nữa (extract cắt cố định 7.5s bằng ffmpeg).

## 3. Phục hồi MEMORY của Claude Code (để AI máy mới hiểu bối cảnh)
Memory nằm ngoài repo, ở `~/.claude/projects/<mã-đường-dẫn>/`. Mã đường dẫn = đường
dẫn tuyệt đối của project, thay mọi `/` thành `-`.
Ví dụ project ở `/Users/nam/Desktop/minh` → thư mục `-Users-nam-Desktop-minh`.
Script `setup_new_machine.sh` tự tính và copy. Làm tay thì:
```bash
ENC="$(cd "$(dirname "$0")" && pwd | sed 's#/#-#g')"
mkdir -p "$HOME/.claude/projects/$ENC/memory"
cp -R _claude/memory/* "$HOME/.claude/projects/$ENC/memory/"
```

## 4. Đăng nhập ChatGPT + Grok (làm 1 lần trên máy mới)
Chrome + Cloudflare chặn cờ debug, nên dùng **mẹo 2 bước**:
```bash
# 4a. mở Chrome cùng profile NHƯNG KHÔNG cờ debug (để qua captcha)
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --user-data-dir="$HOME/.grokpipe-chrome" "https://chatgpt.com/"
#   -> đăng nhập ChatGPT. Mở tab https://accounts.x.ai/sign-in -> đăng nhập Grok.
#   -> đóng Chrome hẳn.

# 4b. mở lại CÓ cờ debug (phiên đăng nhập còn nguyên, không cần captcha lại)
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 --user-data-dir="$HOME/.grokpipe-chrome" \
    "https://grok.com/imagine"
```
Giữ cửa sổ Chrome này mở suốt lúc chạy. **Cần tài khoản Grok còn credit** (mỗi
video tốn credit) và tài khoản ChatGPT còn lượt tạo ảnh.

## 5. Chạy pipeline
```bash
cd grokpipe
./.venv/bin/python -m grokpipe run ../PIPELINE-BANHMI-VID001-028.txt \
    --chrome-cdp http://localhost:9222 --auto
```
- Tự **resume**: các task đã DONE (asset còn trong `*.project/assets/`) sẽ bỏ qua.
- `--auto`: chạy thuần, không hỏi duyệt.
- Kết quả: `PIPELINE-BANHMI-VID001-028.project/assets/VID_*.mp4`.

## 6. Làm lại 1 video chưa ưng
```bash
./.venv/bin/python -m grokpipe reset ../PIPELINE-BANHMI-VID001-028.txt --task T041
# rồi chạy lại lệnh mục 5 -> Grok tạo clip mới cho task đó
```

---

## Ghi chú kiến trúc (đọc `_claude/memory/grokpipe-tool.md` để đầy đủ)
- Ảnh: ChatGPT qua CDP (chọn ảnh sinh ra bằng `img[alt^='Generated image']`, tải
  qua fetch-in-page). Timeout 300s, lỗi thì tự retry chat mới.
- Video: Grok Imagine qua CDP — upload start-frame, chip **Video/720p/10s** click
  bằng `role=radio` theo aria-label, tải mp4 qua `ctx.request`.
- Extract: cắt cố định **giây 7.5** (góc máy mới sinh ở đoạn 5–10s của video).
- Cả ChatGPT + Grok **dùng chung 1 kết nối CDP** (tránh lỗi sync-playwright).
- Selector ChatGPT/Grok có thể đổi theo UI — sửa trong
  `grokpipe/grokpipe/executors/image_chatgpt.py` (SELECTORS) và `video_grok.py`.

## KHÔNG có trong repo (cố ý)
- `.venv/` — tạo lại (mục 2).
- Phiên đăng nhập Chrome (`~/.grokpipe-chrome`) — đăng nhập lại (mục 4).
- File chat thô `.jsonl` — chứa mật khẩu đã dán, không commit. Muốn lịch sử chat
  thì chép riêng qua AirDrop.
