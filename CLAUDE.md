# grokpipe — quy trình làm phim AI

Repo này sản xuất phim drama ngắn bằng pipeline hai chặng:
**ChatGPT vẽ ảnh Start Frame → Grok biến ảnh thành video**, duyệt qua SF Board.

## ⛔ LUẬT CỨNG — CỔNG VIDEO

Video **chỉ** được tạo khi **user tự bấm nút** "Cho phép tạo video" trên board.
AI **tuyệt đối không**: ghi file `.video-gate`, gọi `/api/video-gate?on=1`, giả header
để lách, hay sửa `sfboard.py` để bỏ cổng. Cần render video thì **báo user và chờ**.

## ⛔ LUẬT CỨNG — KHÔNG ĐỘNG VÀO BẢN ĐÃ DUYỆT

Ảnh SF `status: approved` và video `vstatus: approved` là **bản user đã chốt**.
Không xoá, không ghi đè, không crop, không "nâng cấp" lên bản nét hơn trong `versions/`.
Nghi bản đã duyệt bị sai thì **báo user**, để user quyết. Muốn thay phải bỏ duyệt trước.

Ảnh user tự dán vào là **bản chuẩn tuyệt đối**, kể cả khi độ phân giải thấp.

## ⛔ LUẬT CỨNG — TỐI ĐA 4 CHROME

Chỉ ≤4 cửa sổ Chrome debug (cổng 92xx) tại mọi thời điểm — nhiều hơn là máy cạn RAM
và sập hàng loạt với `Target crashed`. Render ảnh: 4 ChatGPT. Render video: 3 ChatGPT
+ 1 Grok. Chrome cá nhân của user không tính.

AI **không đăng nhập tài khoản, không nhập mật khẩu/2FA**. Tài khoản đăng xuất thì
báo user tự làm.

## Bố cục

```
sfboard/sfboard.py          # SF Board — app một trang, mọi thao tác duyệt đi qua đây
grokpipe/                   # executor: image_chatgpt.py (vẽ ảnh), video_grok.py (dựng video)
PIPELINE-<TÊN>.project/     # mỗi phim một thư mục
  ├── sf-board.json         #   NGUỒN CHUẨN DUY NHẤT: scenes → sfs → shots
  ├── assets/               #   ảnh SF đang dùng (1 file / SF)
  ├── versions/             #   mọi bản đã render, để so và chọn
  ├── videos/               #   video đang dùng · videos/versions/ là các bản
  └── CLAUDE.md             #   luật riêng của phim đó (nếu có)
.claude/skills/             # quy trình chi tiết — xem bên dưới
```

## Chạy board

```bash
python3 sfboard/sfboard.py PIPELINE-RUTHS-HOUSE.project --port 8779
```

Cổng cố định theo phim: RUTHS-HOUSE **8779**, 8DOLLARS **8778**.
Chạy nền trên macOS phải bọc subshell + `disown` (`setsid` KHÔNG có trên macOS):

```bash
( nohup python3 -u sfboard/sfboard.py <PROJECT> --port <PORT> > /tmp/sfboard.log 2>&1 < /dev/null & disown )
```

**Kiểm `/api/jobs` trước khi khởi động lại board** — restart giữa chừng làm mất
hàng đợi và job video đang chạy dở sẽ không kịp lưu thành bản chính.

**Đếm thừa cửa sổ Chrome thì HỎI, đừng tự đóng.** Board rotate nhiều tài khoản, và cửa sổ
đang có job chạy dở trông y hệt cửa sổ bỏ không — đóng nhầm cửa sổ Grok là giết cả hàng đợi video
đang chạy. Trước khi đóng bất kỳ cửa sổ nào: **đọc `/api/jobs` xem có job nào `running` không** và
xem `/api/accounts` cửa sổ đó thuộc `kind` gì. Vượt trần thì báo user chọn port, đừng tự quyết.

**Tắt tài khoản phải qua `/api/acct?op=toggle&port=<port>`, không phải `kill` tiến trình Chrome.**
Kill tay thì board vẫn giữ tài khoản trong pool và tiếp tục định tuyến việc sang đó — job video rơi
sang tài khoản ChatGPT rồi báo "Không nối được Grok". Toggle mới vừa đóng cửa sổ vừa gỡ khỏi pool.

**Chrome debug "sống nửa vời" — HTTP trả lời nhưng WebSocket treo.** Chạy vài chục ảnh liên tục
thì `connect_over_cdp` bắt đầu timeout 180s ở bước `<ws connecting>`, trong khi
`curl http://127.0.0.1:92xx/json/version` vẫn trả lời bình thường. Đừng tin phép thử HTTP: nó
KHÔNG chứng minh CDP còn dùng được. Cách chữa là làm sạch cả hai đầu — **dừng board, đóng hết
Chrome debug, mở lại board rồi mở lại Chrome**; khởi động lại riêng Chrome hay riêng board đều
không đủ, vì đầu còn lại vẫn giữ kết nối cũ.

## Quy tắc dựng phim

Chi tiết nằm trong skill `skills-film` (tự kích hoạt khi làm SF/prompt). Bốn điều
hay sai nhất, nhắc ở đây:

- **Một clip = một shot liền.** Không chuyển cảnh trong một clip. Đổi không gian → clip khác.
- **Không tụt pha không gian.** Đã vào trong nhà thì shot sau không được dùng SF ngoài sân.
- **Thời lượng ≈ số từ ÷ 3.** Quá dài thì tách clip, đừng nhồi.
- **Người ở tiền cảnh, kể cả quay lưng hay mờ, vẫn phải đính ảnh ref.**

## Dữ liệu `sf-board.json` — luật kỹ thuật

Skill `skills-film` chỉ chứa nghề làm phim. Mọi thứ về **dữ liệu và công cụ** ghi ở đây.

- **`shots[].dur` là SỐ NGUYÊN giây** (`10`, `6`) — KHÔNG phải chuỗi `"10s"`. Board đọc bằng
  `float(dur)` nên hậu tố chữ làm hỏng việc tạo video.
- **Trước khi ghi bất kỳ trường nào, đọc xem trường đó đang lưu ở KIỂU gì và ghi đúng kiểu đó.**
  Dữ liệu cũ và dữ liệu mới không cùng kiểu là bug đang chờ, không phải chuyện thẩm mỹ.
- **Kiểm bằng đúng biểu thức mà bên tiêu thụ dùng.** Phép kiểm tự viết dễ dùng luôn định dạng
  sai của chính mình nên PASS hết — muốn chắc thì gọi `float(...)` y như board gọi.
- **`shots[].sf` trỏ vào SF id đã chết sẽ hỏng khi render.** Xoá hay đổi tên SF xong phải quét
  shot mồ côi; quét lần cuối ngay trước khi render hàng loạt. Kiểm luôn media mồ côi trong
  `assets/` và `videos/`.
- **Trường phụ cho continuity:** mỗi SF có `pose` (`zone · who · dist · hands`); shot mang chuyển
  động khai `chuyen: true`, shot hồi tưởng hoặc cắt sang dòng thời gian khác khai `hoituong: true`.
  Board bỏ qua các trường lạ, không ảnh hưởng gì.

**Công cụ kiểm:**

```bash
python3 sfboard/chay-anh.py <PROJECT> --port <PORT>      # render hàng loạt ảnh SF (master trước, SF con sau)
python3 sfboard/liet-ke-dao-cu.py <PROJECT>              # liệt kê đạo cụ chủ chốt (bước 2)
python3 sfboard/kiem-noi-shot.py <PROJECT> [S1 S2 ...]   # bắt nhân vật "nhảy" giữa hai shot
```

## ⛔ LUẬT CỨNG — GIT: REPO NÀY CÔNG KHAI

`github.com/xuanminhcvp/grokpipe` là repo **PUBLIC**. Ai cũng đọc được. Vì vậy:

**KHÔNG BAO GIỜ đẩy lên git** (đã chặn sẵn trong `.gitignore`, đừng gỡ ra):

| Không đẩy | Vì sao |
|---|---|
| `.claude/skills/` | bí quyết làm phim — chỉ nằm trên máy user |
| `*.project/` | `sf-board.json` là **296 prompt mẫu đã làm xong**; công khai nó thì giấu skill cũng vô nghĩa |
| `sfboard/kiem-luat.py`, `kiem-noi-shot.py` | mã hoá sẵn ngưỡng của skill (3 shot/SF · mật độ ×4 · cận+trung 75-80% · giây ≈ từ ÷ 3) |

**Được đẩy:** `sfboard/sfboard.py` · `sfboard/chay-anh.py` · `liet-ke-dao-cu.py` · `grokpipe/` · `CLAUDE.md` · `.gitignore` — tức **code công cụ, không phải nội dung phim**.

**Quy trình mỗi lần commit + push:**

```bash
git add -A
git diff --cached --name-only | grep -E "^\.claude/skills/|\.project/|kiem-luat|kiem-noi-shot"
# ↑ PHẢI KHÔNG RA GÌ (trừ dòng có tiền tố D = đang gỡ khỏi git). Ra thứ khác là DỪNG.
git diff --cached -- . ':!CLAUDE.md' | grep "^+" | grep -v "^+++" | grep -ci "KHÓA TỪ ẢNH NEO\|TRẠNG THÁI KHÔNG GIAN\|cận+trung"
# ↑ PHẢI = 0. Phải loại CLAUDE.md ra vì chính dòng lệnh này nằm trong đó nên nó tự bắt chính mình.
```

Push xong **kiểm lại trên GitHub, đừng tin diff**:

```bash
gh api repos/xuanminhcvp/grokpipe/contents/.claude/skills/skills-film/SKILL.md >/dev/null 2>&1 && echo "✗ LỘ" || echo "✓ sạch"
```

**Ba điều đã biết, đừng báo lại như phát hiện mới:**
- **Lịch sử vẫn công khai.** Skill và `sf-board.json` nằm trong 19 commit cũ đã push (từ `61fd739`). User đã quyết **không viết lại lịch sử** (2026-08-04). Muốn xoá hẳn thì phải rewrite + force-push, hoặc chuyển repo sang private.
- **Dữ liệu phim KHÔNG còn backup trên git.** `sf-board.json` chỉ nằm trên máy — hỏng ổ là mất sạch. Backup là việc của user, nhắc một lần rồi thôi.
- `CLAUDE.md` vẫn nhắc tới `.claude/skills/` dù thư mục đó không lên git. Cố ý, không phải lỗi.

**Commit message: chỉ ghi `update`.** User không muốn mô tả chi tiết trên repo công khai — nội dung thay đổi đọc từ diff là đủ. Đừng tự ý viết dài.

## Skill

| Skill | Dùng khi |
|---|---|
| `skills-film` | viết/sửa prompt ảnh nhân vật, SF, prompt video, prompt nhạc |
| `viet-kich-ban` | viết kịch bản drama từ title hoặc ý tưởng |

Mỗi lần user sửa một lỗi, chưng cất thành **nguyên lý** rồi ghi vào
`.claude/skills/<skill>/references/bai-hoc.md` — viết ở tầng dùng lại được cho mọi
phim, không nhắc tên nhân vật cụ thể.

## Ngôn ngữ

Trả lời user bằng **tiếng Việt**. Thoại trong phim viết bằng **tiếng Anh giọng Mỹ**.
