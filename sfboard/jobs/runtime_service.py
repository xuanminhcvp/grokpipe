"""No-throw facade between production code and the runtime bug journal.

Production only ever calls `report_runtime_bug`, `runtime_bug_diagnostics`,
`start_runtime_bug_service` and `stop_runtime_bug_service`. None of them raise,
none of them block on `bd`, and none of them change job outcome. The `bd` CLI is
touched only by the bridge thread, and only when the local config explicitly
opts into `auto-create`.
"""

from __future__ import annotations

import logging
import os
import threading
import traceback
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from .beads_bridge import MODE_AUTO_CREATE, MODE_JOURNAL_ONLY, BeadsBridge
from .bugtool import build_config, diagnostics_snapshot, resolve_mode
from .runtime_classifier import classify_signal
from .runtime_fingerprint import fingerprint_event
from .runtime_journal import RuntimeBugJournal, default_journal_path
from .runtime_redaction import redact_event
from .runtime_sentry import SentryReporter


BRIDGE_THREAD_NAME = "runtime-bug-bridge"
REPEAT_MEMORY_LIMIT = 512
BRIDGE_POLL_SECONDS = 5.0
BRIDGE_BACKOFF_CAP = 300.0
STOP_JOIN_SECONDS = 2.0
STACKTRACE_LIMIT = 20_000

_LOCK = threading.Lock()
_SERVICE: "RuntimeBugService | None" = None


class RuntimeBugService:
    """Owns the journal, the optional logging adapter and the optional bridge."""

    def __init__(
        self,
        repo_root: str | Path,
        mode: str | None = None,
        run_bd=None,
        attach_logging: bool = False,
        poll_interval: float = BRIDGE_POLL_SECONDS,
        jitter=lambda: 0.0,
        sentry=None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.mode = mode or resolve_mode(self.repo_root)
        self.journal = RuntimeBugJournal(default_journal_path(self.repo_root), self.repo_root)
        # Không có DSN thì reporter tự tắt: không import mạng, không gửi gì.
        self.sentry = sentry if sentry is not None else SentryReporter(self.repo_root)
        self.bridge = BeadsBridge(build_config(self.repo_root, self.mode), run_bd=run_bd)
        self.bridge_thread: threading.Thread | None = None
        self._poll_interval = poll_interval
        self._jitter = jitter
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._synced = threading.Condition()
        self._sync_count = 0
        self._log_handler: logging.Handler | None = None
        # Đếm số lần TỪNG fingerprint xuất hiện, để chỗ gọi nói được "chỉ ghi khi
        # lặp lại N lần". Nhiều luồng thợ cùng gọi nên phải có khoá.
        self._repeats: "OrderedDict[str, int]" = OrderedDict()
        self._repeat_lock = threading.Lock()

        if self.mode == MODE_AUTO_CREATE:
            self.bridge_thread = threading.Thread(
                target=self._bridge_loop, name=BRIDGE_THREAD_NAME, daemon=True
            )
            self.bridge_thread.start()
        if attach_logging:
            self._log_handler = RuntimeBugLogHandler(self)
            logging.getLogger().addHandler(self._log_handler)

    # -- reporting ----------------------------------------------------------

    def report(self, signal: object) -> bool:
        """Classify, journal and (optionally) wake the bridge. Never raises."""
        try:
            if not isinstance(signal, Mapping):
                return False
            exception = _exception_info(signal)
            classification = classify_signal({**signal, "exception": exception})
            if not classification.reportable:
                return False
            event = _build_event(signal, classification, exception)
            if self._bo_qua_vi_chua_du_lap(event, _min_repeats(signal)):
                return False
            written = self.journal.record(event)
            if written:
                # Sentry hỏng KHÔNG được làm hỏng kết quả ghi sổ: sổ cục bộ mới
                # là nguồn chuẩn, cảnh báo từ xa chỉ là phần thêm.
                try:
                    self.sentry.capture(event)
                except Exception:  # noqa: BLE001
                    pass
                if self.bridge_thread is not None:
                    self._wake.set()
            return written
        except Exception:  # noqa: BLE001 - reporting must never break a job
            return False

    def _bo_qua_vi_chua_du_lap(self, event: dict[str, object], min_repeats: int) -> bool:
        """Lỗi lặp mới đáng ghi: `min_repeats=3` nghĩa là ghi ở lần 3, 6, 9…

        Xoay tài khoản là chuyện BÌNH THƯỜNG của board — ghi mọi lần xoay thì sổ
        thành rác và Bead thành chuông báo cháy kêu suốt ngày. `min_repeats=1`
        (mặc định) giữ nguyên hành vi cũ: ghi ngay lần đầu."""
        if min_repeats <= 1:
            return False
        fingerprint = fingerprint_event(redact_event(event, self.repo_root))
        with self._repeat_lock:
            count = self._repeats.get(fingerprint, 0) + 1
            self._repeats[fingerprint] = count
            self._repeats.move_to_end(fingerprint)
            while len(self._repeats) > REPEAT_MEMORY_LIMIT:
                self._repeats.popitem(last=False)
        if count % min_repeats:
            return True
        runtime = event.get("runtime")
        if isinstance(runtime, dict):
            runtime["repeats"] = count
        return False

    def diagnostics(self) -> dict[str, object]:
        return diagnostics_snapshot(self.repo_root)

    # -- bridge lifecycle ---------------------------------------------------

    def sync_now(self, timeout: float = 10.0) -> bool:
        """Ask the bridge thread for one pass; run inline when there is no thread."""
        if self.bridge_thread is None or not self.bridge_thread.is_alive():
            self.bridge.sync_once()
            return True
        with self._synced:
            target = self._sync_count + 1
            self._wake.set()
            return self._synced.wait_for(lambda: self._sync_count >= target, timeout=timeout)

    def _bridge_loop(self) -> None:
        backoff = 0.0
        while not self._stopping.is_set():
            self._wake.wait(timeout=backoff or self._poll_interval)
            if self._stopping.is_set():
                return
            self._wake.clear()
            try:
                health = self.bridge.sync_once()
                healthy = health.ok
            except Exception:  # noqa: BLE001 - the daemon must never die
                healthy = False
            backoff = 0.0 if healthy else min(max(backoff * 2, 5.0), BRIDGE_BACKOFF_CAP)
            if backoff:
                backoff = min(backoff + max(self._jitter(), 0.0), BRIDGE_BACKOFF_CAP)
            with self._synced:
                self._sync_count += 1
                self._synced.notify_all()

    def stop(self) -> None:
        """Detach the adapter, stop the daemon and close the journal. Never raises."""
        self._stopping.set()
        self._wake.set()
        thread, self.bridge_thread = self.bridge_thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=STOP_JOIN_SECONDS)
        handler, self._log_handler = self._log_handler, None
        if handler is not None:
            try:
                logging.getLogger().removeHandler(handler)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.sentry.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.journal.close()
        except Exception:  # noqa: BLE001
            pass


class RuntimeBugLogHandler(logging.Handler):
    """Forward only typed ERROR/CRITICAL records; everything else is ignored."""

    def __init__(self, service: RuntimeBugService) -> None:
        super().__init__(level=logging.ERROR)
        self._service = service

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < logging.ERROR:
                return
            if record.name.startswith("sfboard.runtime-bug"):
                return
            reason_code = getattr(record, "runtime_reason_code", None)
            if not isinstance(reason_code, str) or not reason_code.strip():
                return
            exc = record.exc_info[1] if record.exc_info else None
            source_file = getattr(record, "runtime_source_file", None)
            if exc is None and not source_file:
                return
            signal: dict[str, object] = {
                "reason_code": reason_code,
                "category": getattr(
                    record, "runtime_category", "unhandled_exception" if exc else "runtime"
                ),
                "severity": "CRITICAL" if record.levelno >= logging.CRITICAL else "ERROR",
                "job": getattr(record, "runtime_job", {}) or {},
                "runtime": {"logger": record.name},
            }
            if exc is not None:
                signal["exc"] = exc
            else:
                signal["exception"] = {
                    "type": getattr(record, "runtime_exception_type", "LoggedError"),
                    "message": record.getMessage(),
                    "source_file": source_file,
                    "source_function": getattr(record, "runtime_source_function", record.funcName),
                    "source_line": getattr(record, "runtime_source_line", record.lineno),
                }
            self._service.report(signal)
        except Exception:  # noqa: BLE001 - a logging adapter must stay silent
            pass


# -- module facade ----------------------------------------------------------


def start_runtime_bug_service(
    repo_root: str | Path,
    mode: str | None = None,
    run_bd=None,
    attach_logging: bool = False,
    sentry=None,
) -> RuntimeBugService | None:
    """Start (or restart) the singleton service. Returns None when start fails."""
    global _SERVICE
    with _LOCK:
        if _SERVICE is not None:
            _SERVICE.stop()
            _SERVICE = None
        try:
            _SERVICE = RuntimeBugService(
                repo_root,
                mode=mode,
                run_bd=run_bd,
                attach_logging=attach_logging,
                sentry=sentry,
            )
        except Exception:  # noqa: BLE001 - the board must start without the journal
            _SERVICE = None
        return _SERVICE


def report_runtime_bug(signal: object) -> bool:
    """Journal one runtime signal. Returns False when the service is not running."""
    service = _SERVICE
    if service is None:
        return False
    return service.report(signal)


def runtime_bug_diagnostics() -> dict[str, object]:
    """Projection for `/api/chan-doan`; defaults when the service is not running."""
    service = _SERVICE
    if service is None:
        return {
            "bug_bridge": {
                "mode": MODE_JOURNAL_ONLY,
                "pending": 0,
                "last_sync_at": None,
                "last_error": "",
                "created": 0,
                "updated": 0,
            }
        }
    return service.diagnostics()


def stop_runtime_bug_service() -> None:
    global _SERVICE
    with _LOCK:
        service, _SERVICE = _SERVICE, None
    if service is not None:
        service.stop()


# -- event shaping ----------------------------------------------------------


def _build_event(
    signal: Mapping[str, object],
    classification,
    exception: Mapping[str, object],
) -> dict[str, object]:
    runtime = dict(signal.get("runtime") or {}) if isinstance(signal.get("runtime"), Mapping) else {}
    runtime.setdefault("pid", os.getpid())
    runtime.setdefault("thread", threading.current_thread().name)
    severity = classification.severity if classification.severity in {"ERROR", "CRITICAL"} else "ERROR"
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "occurred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "severity": severity,
        "category": classification.category,
        "reason_code": classification.reason_code,
        "fingerprint": "pending",
        "job": dict(signal.get("job") or {}) if isinstance(signal.get("job"), Mapping) else {},
        "runtime": runtime,
        "exception": dict(exception),
    }


def _min_repeats(signal: Mapping[str, object]) -> int:
    value = signal.get("min_repeats")
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return 1
    return value


def _exception_info(signal: Mapping[str, object]) -> dict[str, object]:
    declared = signal.get("exception")
    info: dict[str, object] = dict(declared) if isinstance(declared, Mapping) else {}
    exc = signal.get("exc")
    if isinstance(exc, BaseException):
        frame = _last_frame(exc)
        info.setdefault("type", type(exc).__name__)
        info.setdefault("message", str(exc))
        if frame is not None:
            info.setdefault("source_file", frame[0])
            info.setdefault("source_function", frame[1])
            info.setdefault("source_line", frame[2])
        info.setdefault(
            "stacktrace",
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[
                :STACKTRACE_LIMIT
            ],
        )
    return info


def _last_frame(exc: BaseException) -> tuple[str, str, int] | None:
    tb = exc.__traceback__
    last = None
    while tb is not None:
        last = tb
        tb = tb.tb_next
    if last is None:
        return None
    code = last.tb_frame.f_code
    return code.co_filename, code.co_name, last.tb_lineno
