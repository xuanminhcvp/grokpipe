"""Cảnh báo từ xa TÙY CHỌN qua Sentry.

Luật: KHÔNG có DSN thì mọi thứ chạy y như cũ — không import, không mạng, không
lỗi. Có DSN mới gửi, và chỉ gửi bản ĐÃ LỌC BÍ MẬT giống hệt bản ghi xuống JSONL.
Sổ JSONL cục bộ vẫn là nguồn AI đọc; Sentry chỉ để user biết có chuyện khi đang
không ngồi trước máy.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from .runtime_redaction import redact_event


DSN_ENV_VARS = ("GROKPIPE_SENTRY_DSN", "SENTRY_DSN")
ENVIRONMENT_ENV_VAR = "GROKPIPE_SENTRY_ENV"
STACKTRACE_LIMIT = 8_000


def resolve_dsn(env: Mapping[str, str] | None = None) -> str:
    """DSN lấy từ môi trường; rỗng nghĩa là tắt hẳn."""
    source = env if env is not None else os.environ
    for name in DSN_ENV_VARS:
        value = (source.get(name) or "").strip()
        if value:
            return value
    return ""


class SentryReporter:
    """Bọc `sentry_sdk` sao cho thiếu gói hay thiếu DSN đều là no-op yên lặng."""

    def __init__(
        self,
        repo_root: str | Path = ".",
        dsn: str | None = None,
        environment: str | None = None,
        sdk: object | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self._dsn = dsn if dsn is not None else resolve_dsn(env)
        self._sdk = sdk if sdk is not None else _import_sdk()
        self.enabled = False
        self.last_error = ""
        if not self._dsn or self._sdk is None:
            return
        try:
            self._sdk.init(
                dsn=self._dsn,
                environment=environment
                or (env or os.environ).get(ENVIRONMENT_ENV_VAR)
                or "grokpipe",
                send_default_pii=False,
                traces_sample_rate=0.0,
                max_breadcrumbs=0,
                attach_stacktrace=False,
                # KHÔNG BẬT INTEGRATION MẶC ĐỊNH NÀO.
                #
                # `init()` trần bật sẵn logging · threading · excepthook · stdlib
                # …, và hai cái đầu gửi BẢN THÔ vòng qua toàn bộ phép lọc:
                # LoggingIntegration bắt mọi `logging.error` trong tiến trình và
                # gửi nguyên văn thân log; ThreadingIntegration bắt lỗi chưa xử
                # lý của luồng thợ KÈM BIẾN CỤC BỘ — mà `_worker_entry` cố ý
                # `raise` lại sau khi ghi sổ, nên mỗi lần thợ chết là prompt,
                # `chat_url`, cookie, token bay đi nguyên vẹn, nằm ngay cạnh bản
                # đã lọc. `send_default_pii=False` không chạm tới hai thứ đó.
                default_integrations=False,
                auto_enabling_integrations=False,
                include_local_variables=False,
                # Lớp chắn thứ hai, ở cửa ra: `init()` là TOÀN CỤC, nên mã khác
                # trong tiến trình gọi thẳng `sentry_sdk.capture_*` vẫn đi qua
                # client này mà không qua `capture()` của lớp đây.
                before_send=_chi_nhan_su_kien_cua_so_runtime,
            )
            self.enabled = True
        except Exception as exc:  # noqa: BLE001 - cảnh báo hỏng không được làm chết board
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]

    def capture(self, event: Mapping[str, object]) -> bool:
        """Gửi MỘT sự kiện đã lọc. Không bao giờ ném lỗi ra ngoài."""
        if not self.enabled:
            return False
        try:
            self._sdk.capture_event(self._payload(redact_event(event, self.repo_root)))
            return True
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"[:200]
            return False

    def close(self) -> None:
        self.enabled = False
        flush = getattr(self._sdk, "flush", None)
        if flush is None:
            return
        try:
            flush(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass

    def _payload(self, event: Mapping[str, object]) -> dict[str, object]:
        job = _mapping(event.get("job"))
        exception = _mapping(event.get("exception"))
        severity = str(event.get("severity") or "ERROR")
        title = (
            f"[{event.get('reason_code')}] {exception.get('type') or 'Error'} "
            f"@ {job.get('kind') or '?'}/{job.get('phase') or '?'}"
        )
        return {
            "level": "fatal" if severity == "CRITICAL" else "error",
            "logger": "grokpipe.runtime-bug",
            "message": {"formatted": title},
            "fingerprint": [str(event.get("fingerprint") or title)],
            "tags": {
                "reason_code": str(event.get("reason_code") or ""),
                "category": str(event.get("category") or ""),
                "job_kind": str(job.get("kind") or ""),
                "job_phase": str(job.get("phase") or ""),
            },
            "extra": {
                "event_id": event.get("event_id"),
                "occurred_at": event.get("occurred_at"),
                "job_id": job.get("job_id"),
                "exception_message": exception.get("message"),
                "source": (
                    f"{exception.get('source_file')}:{exception.get('source_line')}"
                    f" in {exception.get('source_function')}"
                ),
                "stacktrace": str(exception.get("stacktrace") or "")[:STACKTRACE_LIMIT],
            },
        }


SO_RUNTIME_LOGGER = "grokpipe.runtime-bug"


def _chi_nhan_su_kien_cua_so_runtime(event, hint):
    """Chỉ cho qua sự kiện do `_payload()` dựng; mọi thứ khác vứt im lặng.

    Nhận diện bằng trường `logger` vì đó là thứ `_payload()` luôn đóng vào và
    không có đường nào khác đặt được — không dùng `extra`/`tags` vì bản thô của
    integration cũng có thể mang chúng.
    """
    try:
        if isinstance(event, Mapping) and event.get("logger") == SO_RUNTIME_LOGGER:
            return event
    except Exception:  # noqa: BLE001 - lọc hỏng thì thà không gửi còn hơn gửi bừa
        pass
    return None


def _import_sdk():
    try:
        import sentry_sdk  # noqa: PLC0415 - nhập trễ để thiếu gói vẫn chạy được
    except Exception:  # noqa: BLE001
        return None
    return sentry_sdk


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}
