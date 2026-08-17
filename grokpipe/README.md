# grokpipe CLI

`grokpipe/` là CLI pipeline độc lập để parse, chạy tiếp và kiểm tra pipeline
text. Đây là công cụ cấp thấp/secondary; production làm phim hằng ngày dùng SF
Board và lifecycle authoritative ở thư mục `sfboard/`.

## Cài đặt

Từ root repo:

```bash
python3 -m venv .venv
./.venv/bin/python3 -m pip install -r grokpipe/requirements.txt
./.venv/bin/python3 -m playwright install chromium
```

`ffmpeg` cần cho khâu video. Lần đầu dùng browser automation, người dùng tự đăng
nhập trong Chrome; không đưa credential/cookie vào command hoặc Git.

## Lệnh

```bash
# kiểm tra parser
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe parse PIPELINE.txt

# chỉ in kế hoạch
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe run PIPELINE.txt --dry-run

# chạy/resume state của CLI
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe run PIPELINE.txt

# xem trạng thái
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe status PIPELINE.txt

# reset có chủ đích một task
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe reset PIPELINE.txt --task TASK_ID
```

`PYTHONPATH` cần vì package CLI hiện chưa có metadata để `pip install -e`.
Phương án tương đương là `cd grokpipe`, rồi dùng Python ở `../.venv/bin/`.

Các cờ hữu ích của `run`:

- `--from TASK_ID`: bắt đầu từ task đã chọn.
- `--only A,B`: chỉ chạy một tập task.
- `--max-retry N`: giới hạn retry của CLI.
- `--manual-image`, `--manual-video`: ép cổng duyệt/chạy tay.
- `--auto`: bỏ cổng duyệt tay.
- `--chrome-cdp http://localhost:9222`: nối Chrome debug đang mở.
- `--stop-on-fail`: dừng pipeline CLI khi task lỗi.

Xem contract đầy đủ bằng:

```bash
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe --help
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe run --help
```

## Chrome CDP

CLI có thể mở profile riêng:

```bash
PYTHONPATH=./grokpipe ./.venv/bin/python3 -m grokpipe chrome --port 9222 \
  --profile ~/.grokpipe-chrome
```

Người dùng đăng nhập trong cửa sổ đó, sau đó chạy pipeline với `--chrome-cdp`.
Không chạy nhiều tiến trình cùng điều khiển một profile/cổng.

## Dữ liệu và resume

Mặc định CLI dùng thư mục `<pipeline>.project`; có thể đổi bằng
`--project-dir`. State của CLI chỉ phục vụ runner này, không phải SQLite
lifecycle authority của SF Board. Không trộn reset/retry của CLI với một board
đang xử lý cùng asset.

## Khi nào dùng SF Board

Dùng root repo:

```bash
./chay-board.command PIPELINE-AISLE-SEVEN.project
```

SF Board có queue bền vững, idempotency, execution/attempt, account lease,
cancel/stop, retry theo phase, live image/video executor và diagnostics. Xem
[tài liệu lifecycle](../docs/JOB-LIFECYCLE-README.md) trước khi sửa phần này.

## An toàn

- Live image/video có thể tiêu credit; chỉ chạy khi người dùng cho phép.
- Không xoá asset/version hoặc reset toàn bộ state để chữa một lỗi đơn lẻ.
- Không commit project phim, media, Chrome profile, account config hoặc runtime
  database vào repo public.
