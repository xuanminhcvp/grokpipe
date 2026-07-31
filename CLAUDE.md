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

## Quy tắc dựng phim

Chi tiết nằm trong skill `skills-film` (tự kích hoạt khi làm SF/prompt). Bốn điều
hay sai nhất, nhắc ở đây:

- **Một clip = một shot liền.** Không chuyển cảnh trong một clip. Đổi không gian → clip khác.
- **Không tụt pha không gian.** Đã vào trong nhà thì shot sau không được dùng SF ngoài sân.
- **Thời lượng ≈ số từ ÷ 3.** Quá dài thì tách clip, đừng nhồi.
- **Người ở tiền cảnh, kể cả quay lưng hay mờ, vẫn phải đính ảnh ref.**

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
