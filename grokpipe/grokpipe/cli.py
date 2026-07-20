"""CLI: run / status / reset / parse."""
from __future__ import annotations

import argparse
import os
import sys

from .models import Status
from .parser import parse_pipeline, ParseError
from .state import Store
from .logutil import setup_logger
from .runner import Runner, RunOptions


def _default_project_dir(pipeline_path: str) -> str:
    stem = os.path.splitext(os.path.basename(pipeline_path))[0]
    return os.path.join(os.path.dirname(os.path.abspath(pipeline_path)),
                        f"{stem}.project")


def _load(pipeline_path: str):
    try:
        return parse_pipeline(pipeline_path)
    except (ParseError, FileNotFoundError) as e:
        print(f"LỖI đọc pipeline: {e}", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------- run
def cmd_run(args) -> int:
    tasks = _load(args.pipeline)
    proj = args.project_dir or _default_project_dir(args.pipeline)
    store = Store(proj)
    logger = setup_logger(store.log_path)
    logger.info(f"Pipeline: {args.pipeline}  ({len(tasks)} task)")
    logger.info(f"Project : {store.dir}")

    only = set(x.strip() for x in args.only.split(",")) if args.only else None
    opts = RunOptions(
        max_retry=args.max_retry,
        manual_image=args.manual_image,
        manual_video=args.manual_video,
        auto=args.auto,
        gate_extract=args.gate_extract,
        from_id=args.from_task,
        only=only,
        dry_run=args.dry_run,
        headless=args.headless,
        chatgpt_url=args.chatgpt_url,
        chrome_cdp=args.chrome_cdp,
        stop_on_fail=args.stop_on_fail,
    )
    runner = Runner(tasks, store, logger, opts)
    failed = runner.run()
    if args.dry_run:
        return 0
    _print_summary(store, tasks)
    if failed:
        logger.warning(f"Hoàn tất với {failed} task FAILED. Xem `status` / sửa rồi chạy lại.")
        return 1
    logger.info("Tất cả task trong phạm vi đã DONE.")
    return 0


# ---------------------------------------------------------------- status
def cmd_status(args) -> int:
    tasks = _load(args.pipeline)
    proj = args.project_dir or _default_project_dir(args.pipeline)
    store = Store(proj)
    _print_summary(store, tasks, verbose=True)
    return 0


def _print_summary(store: Store, tasks, verbose: bool = False) -> None:
    counts = {s.value: 0 for s in Status}
    print("\n" + "=" * 70)
    print(f"{'TASK':6} {'LOẠI':7} {'OUTPUT':24} {'TRẠNG THÁI':10} GHI CHÚ")
    print("-" * 70)
    for t in tasks:
        st = store.get(t.id, t.output_id)
        status = st.status
        if status == Status.DONE.value and not store.asset_exists(t.output_id):
            status = "PENDING"  # file bị xóa
        counts[status] = counts.get(status, 0) + 1
        if verbose or status != Status.DONE.value:
            print(f"{t.id:6} {t.type.value:7} {t.output_id:24} "
                  f"{status:10} {st.note}")
    print("-" * 70)
    print("  ".join(f"{k}={v}" for k, v in counts.items()))
    print("=" * 70)


# ---------------------------------------------------------------- reset
def cmd_reset(args) -> int:
    tasks = _load(args.pipeline)
    proj = args.project_dir or _default_project_dir(args.pipeline)
    store = Store(proj)
    ids = set(x.strip() for x in args.task.split(",")) if args.task else None
    n = 0
    for t in tasks:
        if ids is not None and t.id not in ids and t.output_id not in ids:
            continue
        st = store.get(t.id, t.output_id)
        st.status = Status.PENDING.value
        st.note = "reset"
        n += 1
    store.save()
    print(f"Đã reset {n} task về PENDING (file asset giữ nguyên).")
    return 0


# ---------------------------------------------------------------- chrome
_CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def cmd_chrome(args) -> int:
    """Mở Chrome thật với remote-debugging để tool nối vào (bạn tự đăng nhập)."""
    import subprocess
    chrome = args.chrome_path
    if not chrome:
        chrome = next((c for c in _CHROME_CANDIDATES if os.path.exists(c)), None)
    if not chrome or not os.path.exists(chrome):
        print("Không tìm thấy Chrome. Chỉ đường bằng --chrome-path.", file=sys.stderr)
        return 2
    profile = os.path.abspath(os.path.expanduser(args.profile))
    os.makedirs(profile, exist_ok=True)
    cmd = [chrome, f"--remote-debugging-port={args.port}",
           f"--user-data-dir={profile}", "https://chatgpt.com/"]
    print("Mở Chrome (remote-debugging) với profile riêng:")
    print("   " + " ".join(f'"{c}"' if " " in c else c for c in cmd))
    subprocess.Popen(cmd)
    print(f"\n  1) Trong cửa sổ Chrome vừa mở: tự qua 'Verify you are human' (nếu có)")
    print(f"     và ĐĂNG NHẬP ChatGPT (kể cả 2FA). Lần sau không phải làm lại.")
    print(f"  2) Giữ Chrome này mở, rồi chạy:")
    print(f"\n     python3 -m grokpipe run <pipeline.txt> "
          f"--chrome-cdp http://localhost:{args.port}\n")
    return 0


# ---------------------------------------------------------------- parse (debug)
def cmd_parse(args) -> int:
    tasks = _load(args.pipeline)
    for t in tasks:
        deps = ", ".join(t.input_ids) or "-"
        print(f"{t.id} {t.type.value:7} -> {t.output_id:24} | {t.name}")
        print(f"       input: {deps}")
        if t.srt_range:
            print(f"       srt  : {t.srt_range}  ({t.duration_s:.0f}s)")
    print(f"\nTổng: {len(tasks)} task.")
    return 0


# ---------------------------------------------------------------- argparse
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="grokpipe",
        description="Chạy pipeline sản xuất video: ChatGPT tạo ảnh + Grok tạo video.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("pipeline", help="đường dẫn file pipeline .txt")
        sp.add_argument("--project-dir", default=None,
                        help="thư mục lưu asset/state (mặc định: <pipeline>.project)")

    r = sub.add_parser("run", help="chạy pipeline (resume tự động)")
    common(r)
    r.add_argument("--from", dest="from_task", default=None,
                   help="bắt đầu từ TASK_ID/OUTPUT_ID này")
    r.add_argument("--only", default=None,
                   help="chỉ chạy các TASK_ID/OUTPUT_ID (phân tách bằng dấu phẩy)")
    r.add_argument("--max-retry", type=int, default=3)
    r.add_argument("--manual-image", action="store_true",
                   help="ép tạo ảnh thủ công (không dùng Playwright)")
    r.add_argument("--manual-video", action="store_true",
                   help="ép tạo video Grok thủ công (không tự động qua CDP)")
    r.add_argument("--auto", action="store_true",
                   help="chạy thuần: bỏ mọi cổng duyệt tay (tự nhận mọi kết quả)")
    r.add_argument("--gate-extract", action="store_true",
                   help="duyệt lại frame sau khi cắt (mặc định đã chọn tay khi cắt)")
    r.add_argument("--headless", action="store_true",
                   help="chạy trình duyệt ẩn (không khuyến nghị lần đầu — cần đăng nhập)")
    r.add_argument("--chatgpt-url", default="https://chatgpt.com/")
    r.add_argument("--chrome-cdp", default=None, metavar="URL",
                   help="nối vào Chrome thật đang mở, vd http://localhost:9222 "
                        "(chạy `grokpipe chrome` trước để mở Chrome đúng cách)")
    r.add_argument("--stop-on-fail", action="store_true",
                   help="dừng hẳn khi gặp task FAILED")
    r.add_argument("--dry-run", action="store_true",
                   help="chỉ in kế hoạch, không chạy")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("status", help="xem trạng thái các task")
    common(s)
    s.set_defaults(func=cmd_status)

    rs = sub.add_parser("reset", help="đưa task về PENDING để chạy lại")
    common(rs)
    rs.add_argument("--task", default=None,
                    help="TASK_ID/OUTPUT_ID cần reset (bỏ trống = tất cả)")
    rs.set_defaults(func=cmd_reset)

    ps = sub.add_parser("parse", help="kiểm tra parse file pipeline")
    common(ps)
    ps.set_defaults(func=cmd_parse)

    ch = sub.add_parser("chrome",
                        help="mở Chrome thật (remote-debugging) để nối CDP")
    ch.add_argument("--port", type=int, default=9222)
    ch.add_argument("--profile", default="~/.grokpipe-chrome",
                    help="thư mục profile Chrome riêng (đăng nhập một lần)")
    ch.add_argument("--chrome-path", default=None,
                    help="đường dẫn Chrome nếu không tự tìm được")
    ch.set_defaults(func=cmd_chrome)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
