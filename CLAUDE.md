# grokpipe — quy trình làm phim AI

Repo này sản xuất phim drama ngắn bằng pipeline hai chặng:
**ChatGPT vẽ ảnh Start Frame → Grok biến ảnh thành video**, duyệt qua SF Board.

Đừng ask question, suy nghĩ hướng nào tốt nhất rồi làm theo thôi, user bận không có thời gian trả lời question đâu

## Lifecycle job ảnh/video

Khi task liên quan `JOBS`, queue, state, retry, cancel/stop, account assignment,
auto/worker/watchdog hoặc job API/UI, bắt buộc đọc
[`docs/JOB-LIFECYCLE-README.md`](docs/JOB-LIFECYCLE-README.md) trước.

Làm theo chuỗi: README → tài liệu được route → symbol/writer bằng Serena nếu khả
dụng → regression test → fix đúng owner → full verification gate. Không tạo thêm
writer, retry hoặc re-enqueue authority.

## ⛔ LUẬT CỨNG

Không tự ý sửa skill, chỉ sửa khi user bảo sửa. 
## ⛔ LUẬT CỨNG — KHÔNG TỰ Ý ĐỘNG VÀO ẢNH/VIDEO ĐANG DÙNG

`approved` chỉ là **dấu để user nhìn cho dễ quản lý**, không phải khoá kỹ thuật
(user chốt 2026-08-14). User chủ động bấm tạo lại thì ảnh mới **đè lên bản đang
dùng, kể cả thẻ đã duyệt** — bản cũ vẫn nằm nguyên trong `versions/` nên không
mất gì.

Cái bị cấm là **AI tự ý**: không xoá, không crop, không "nâng cấp" lên bản nét
hơn trong `versions/` khi user không bảo. Nghi bản đang dùng bị sai thì **báo
user**, để user quyết.

Ảnh user tự dán vào là **bản chuẩn tuyệt đối**, kể cả khi độ phân giải thấp.

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
  └── KICH-BAN.md           #   kịch bản đầy đủ + ghi chú riêng của phim
.claude/skills/             # quy trình chi tiết — xem bên dưới
```

**KHÔNG tạo `CLAUDE.md` riêng cho từng phim.**

## Chạy board

⛔ **Luôn gọi `./.venv/bin/python3`, KHÔNG gọi `python3` trần** — cho MỌI script trong
`sfboard/` và `grokpipe/`. `playwright` chỉ cài trong `.venv`; `python3` trần là bản 3.9 của
macOS, board vẫn lên nhưng mọi job chết với `No module named 'playwright'`.

```bash
./.venv/bin/python3 sfboard/sfboard.py PIPELINE-RUTHS-HOUSE.project --port 8779
```

Cổng cố định theo phim: RUTHS-HOUSE **8779**, 8DOLLARS **8778**, PORCH-LIGHT **8780**,
TAXI-DRIVER **8781**, LOOKING-POOR **8782**.
Chạy nền trên macOS phải bọc subshell + `disown` (`setsid` KHÔNG có trên macOS):

```bash
( nohup ./.venv/bin/python3 -u sfboard/sfboard.py <PROJECT> --port <PORT> > /tmp/sfboard.log 2>&1 < /dev/null & disown )
```

Gọn nhất là `./chay-board.command <PROJECT>` — script đã chọn sẵn đúng python và cổng.

**Kiểm `/api/jobs` trước khi khởi động lại board** — restart giữa chừng làm mất
hàng đợi và job video đang chạy dở sẽ không kịp lưu thành bản chính.


**Tắt tài khoản phải qua `/api/acct?op=toggle&port=<port>`, không phải `kill` tiến trình Chrome.**
Kill tay thì board vẫn giữ tài khoản trong pool và tiếp tục định tuyến việc sang đó — job video rơi
sang tài khoản ChatGPT rồi báo "Không nối được Grok". Toggle mới vừa đóng cửa sổ vừa gỡ khỏi pool.

**Chrome debug "sống nửa vời" — HTTP trả lời nhưng WebSocket treo.** Chạy vài chục ảnh liên tục
thì `connect_over_cdp` bắt đầu timeout 180s ở bước `<ws connecting>`, trong khi
`curl http://127.0.0.1:92xx/json/version` vẫn trả lời bình thường. Đừng tin phép thử HTTP: nó
KHÔNG chứng minh CDP còn dùng được. Cách chữa là làm sạch cả hai đầu — **dừng board, đóng hết
Chrome debug, mở lại board rồi mở lại Chrome**; khởi động lại riêng Chrome hay riêng board đều
không đủ, vì đầu còn lại vẫn giữ kết nối cũ.

## Khi khâu render hỏng

Selector chết · không thấy nút Submit / mode Video / chip thời lượng · CDP không nối · tab crash ·
cả lô SF chết mà log vẫn sạch → **nạp skill `grokpipe-ops` và làm theo. Đừng đoán, đừng vá mò.**

Nhiều job lỗi cùng lúc thì **nghi hạ tầng trước** (RAM, Chrome crash, tab treo), đừng sửa prompt —
sửa prompt khi gốc là hạ tầng thì vừa mất công vừa làm hỏng prompt đang đúng.

## Quy tắc dựng phim

Chi tiết nằm trong skill `skills-film` (tự kích hoạt khi làm SF/prompt).

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
- **CẤM sửa/đọc trực tiếp file 917KB `sf-board.json` bằng text-editor hoặc lệnh bash thay thế.**
  - **Để ĐỌC một scene:** Bắt buộc dùng `./.venv/bin/python3 sfboard/sua-board.py xem <PROJECT> <SCENE_ID>`.
  - **Để GHI/THÊM/SỬA:** Tạo một file JSON trung gian cực nhỏ (ví dụ `patch.json` chứa riêng các thẻ cần sửa) rồi dùng lệnh `./.venv/bin/python3 sfboard/sua-board.py patch <PROJECT> <SCENE_ID> <patch.json>`. Công cụ này sẽ tự lọc rác (như `note`, `usedBy`), ép kiểu (`dur`), và giữ nguyên cấu trúc file gốc.

- **`luatchung` — khối LUẬT CHUNG của địa điểm. THẺ NÀO MANG NÓ LÀ THẺ ĐỊA ĐIỂM.** Đó cũng là
  dấu hiệu `sfboard.py` và `kiem-luat.py` dùng để nhận ra chỗ dừng khi leo `refs.bg` — một địa
  điểm = một đoạn chat. Board truyền nó vào `image_chatgpt.generate_lo(luat_chung=…)`, gửi **một
  lần lúc mở chat mới**; các lô sau quay lại đúng `chat_url` nên không gửi lại. Vì vậy phần lặp
  (nội thất · bảng màu · ánh sáng · trang phục · trục · luật chữ) viết vào đây, KHÔNG viết vào
  `prompt`. Trường này **tên cũ là `hienphap`, đã đổi 2026-08-06**; gặp dữ liệu cũ thì đổi key.
- **Tên SF đặt theo SỐ SHOT nó phục vụ, KHÔNG có ngoại lệ** (luật 1:1 từ 2026-08-06): shot
  `V-S1-07` dùng SF `SF-S1-07`. **Thẻ địa điểm cũng theo luật này** — nó là SF của shot mở cảnh,
  thường là `SF-S<n>-01`, và mang thêm `luatchung` + `chat`. Địa điểm dùng cho nhiều scene thì các
  scene sau trỏ `refs.bg` về thẻ của scene đầu tiên.
  **Tiền tố cũ `SF-M-<ĐỊA ĐIỂM>` đã bỏ 2026-08-07** — code vẫn nhận để dự án cũ chạy được, nhưng
  đừng tạo mới. Dự án cũ có master trỏ master (`BATH → FOYER → MANSION-EXT`) nên **đừng đổi phép
  nhận diện thành "leo tới gốc"**: làm thế cả toà nhà gộp thành một chat, và `luatchung` của phòng
  đầu tiên khoá look cho mọi phòng còn lại — bếp thừa hưởng bảng màu của phòng ngủ, im lặng.
- **`goc` — mô tả góc máy MỘT DÒNG trên mỗi SF** (`cỡ cảnh · ai NÉT · ai vai-gáy/mờ · ai quay
  lưng`). Bước 5 viết khối "Trong khung" của prompt video bằng đúng dòng này, không phải mở cả
  prompt SF ra đọc — và viết sai ai-nét/ai-vai-gáy là model bịa mặt mới.
- **Trường phụ cho continuity:** mỗi SF có `pose` (`zone · who · dist · hands`); shot mang chuyển
  động khai `chuyen: true`, shot hồi tưởng hoặc cắt sang dòng thời gian khác khai `hoituong: true`.
  Board bỏ qua các trường lạ, không ảnh hưởng gì.

**Công cụ kiểm:**

```bash
./.venv/bin/python3 sfboard/chay-anh.py <PROJECT> --port <PORT>      # render hàng loạt ảnh SF (master trước, SF con sau)
./.venv/bin/python3 sfboard/liet-ke-dao-cu.py <PROJECT>              # liệt kê đạo cụ chủ chốt (bước 2)
./.venv/bin/python3 sfboard/kiem-noi-shot.py <PROJECT> [S1 S2 ...]   # bắt nhân vật "nhảy" giữa hai shot
```

## ⛔ LUẬT CỨNG — GIT: REPO NÀY CÔNG KHAI

Chỉ đẩy lên khi user bảo đẩy lên Github.
Không commit các dự án phim lên. Project là private nhé.

`github.com/xuanminhcvp/grokpipe` là repo **PUBLIC**. Ai cũng đọc được. Vì vậy:

**KHÔNG BAO GIỜ đẩy lên git** (đã chặn sẵn trong `.gitignore`, đừng gỡ ra):

| Không đẩy | Vì sao |
|---|---|
| `.claude/skills/` | bí quyết làm phim — chỉ nằm trên máy user |
| `*.project/` | `sf-board.json` là **296 prompt mẫu đã làm xong**; công khai nó thì giấu skill cũng vô nghĩa |
| `sfboard/kiem-luat.py`, `kiem-noi-shot.py` | mã hoá sẵn ngưỡng của skill (3 shot/SF · mật độ ×4 · cận+trung 75-80% · giây ≈ từ ÷ 3) |

**Được đẩy:** `sfboard/sfboard.py` · `sfboard/chay-anh.py` · `liet-ke-dao-cu.py` · `grokpipe/` · `CLAUDE.md` · `.gitignore` — tức **code công cụ, không phải nội dung phim**.

⛔ **TRƯỚC MỖI LẦN PUSH: mở [`.claude/git-release.md`](.claude/git-release.md) và làm đúng theo.**
Ở đó có phép kiểm trước push, cách kiểm lại trên GitHub sau push, cơ chế hai kho, và ba điều đã
biết rồi (lịch sử cũ đã lộ · media không có backup) — **đừng báo lại như phát hiện mới**.

**Sửa gì trong code hay skill thì đẩy CẢ HAI**: `git push` cho public, `./day-rieng.sh day` cho
private. Private là nơi duy nhất có backup của skill và dữ liệu prompt.

**Commit message: chỉ ghi `update`.** User không muốn mô tả chi tiết trên repo công khai — nội dung thay đổi đọc từ diff là đủ. Đừng tự ý viết dài.

## Skill

| Skill | Dùng khi |
|---|---|
| `skills-film` | viết/sửa prompt ảnh nhân vật, SF, prompt video, prompt nhạc |

### ⛔ LUẬT CỨNG — SỬA SKILL

Trước khi thêm/sửa/xoá bất cứ thứ gì trong `.claude/skills/` — kể cả file trong
`references/` — **nạp skill `chuan-skill` và làm theo**. Không đọc thì không sửa.

Riêng grokpipe, thêm một điều ngoài chuẩn chung:

- Sửa xong đẩy **cả hai** repo: `git push` cho public, `./day-rieng.sh day` cho private.
  `.gitignore` loại `.claude/skills/` khỏi repo công khai → **private là bản backup duy nhất.**

## Ngôn ngữ

Trả lời user bằng **tiếng Việt**. Thoại trong phim viết bằng **tiếng Anh giọng Mỹ**.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:46cd31e7 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/core-concepts/sync-concepts.md for details and anti-patterns.

## Agent Context Profiles

The managed Beads block is task-tracking guidance, not permission to override repository, user, or orchestrator instructions.

- **Conservative (default)**: Use `bd` for task tracking. Do not run git commits, git pushes, or Dolt remote sync unless explicitly asked. At handoff, report changed files, validation, and suggested next commands.
- **Minimal**: Keep tool instruction files as pointers to `bd prime`; use the same conservative git policy unless active instructions say otherwise.
- **Team-maintainer**: Only when the repository explicitly opts in, agents may close beads, run quality gates, commit, and push as part of session close. A current "do not commit" or "do not push" instruction still wins.

## Session Completion

This protocol applies when ending a Beads implementation workflow. It is subordinate to explicit user, repository, and orchestrator instructions.

1. **File issues for remaining work** - Create beads for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **Handle git/sync by active profile**:
   ```bash
   # Conservative/minimal/default: report status and proposed commands; wait for approval.
   git status

   # Team-maintainer opt-in only, unless current instructions forbid it:
   git pull --rebase
   bd dolt push
   git push
   git status
   ```
5. **Hand off** - Summarize changes, validation, issue status, and any blocked sync/commit/push step

**Critical rules:**
- Explicit user or orchestrator instructions override this Beads block.
- Do not commit or push without clear authority from the active profile or the current user request.
- If a required sync or push is blocked, stop and report the exact command and error.
<!-- END BEADS INTEGRATION -->
