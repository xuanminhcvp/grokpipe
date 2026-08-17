"""One-attempt runners cho worker live.

Module này không biết Board, queue, Chrome hay retry. Provider và thao tác file
được inject; đầu ra duy nhất là fact mapping cho `LegacyExecutorAdapter`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Tuple

try:
    from .jobs.executor_adapter import ExecutorAttemptResult, PhaseEmitter
    from .jobs.models import AttemptPhase, CreditConsumption, JobId
except ImportError:  # sfboard.py chạy trực tiếp, thư mục sfboard nằm trên sys.path
    from jobs.executor_adapter import ExecutorAttemptResult, PhaseEmitter
    from jobs.models import AttemptPhase, CreditConsumption, JobId


class LiveAttemptError(RuntimeError):
    pass


class LiveValidationError(LiveAttemptError):
    pass


class LivePreSubmitError(LiveAttemptError):
    pass


@dataclass(frozen=True)
class ImageAttemptItem:
    job_id: JobId
    asset_id: str
    prompt: str

    def __post_init__(self) -> None:
        if not self.asset_id.strip() or not self.prompt.strip():
            raise LiveValidationError("ảnh live thiếu asset id hoặc prompt")


@dataclass(frozen=True)
class ImageAttemptRequest:
    items: Tuple[ImageAttemptItem, ...]
    attachments: Tuple[str, ...] = ()
    common_rules: str = ""
    stamp_codes: bool = True
    master_id: str = ""

    def __post_init__(self) -> None:
        if not self.items:
            raise LiveValidationError("image attempt không có member")
        if len({item.job_id for item in self.items}) != len(self.items):
            raise LiveValidationError("image attempt trùng JobId")


@dataclass(frozen=True)
class ImageProviderResponse:
    sources: Tuple[str, ...]
    chat_url: str = ""
    notes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoAttemptRequest:
    job_id: JobId
    shot_id: str
    prompt: str
    start_frame: str
    duration_s: float
    output_path: str

    def __post_init__(self) -> None:
        if not self.shot_id.strip() or not self.prompt.strip():
            raise LiveValidationError("video live thiếu shot id hoặc prompt")
        if not self.start_frame.strip() or not self.output_path.strip():
            raise LiveValidationError("video live thiếu start frame/output path")


ImageProvider = Callable[..., ImageProviderResponse]
ImageDownloader = Callable[[ImageProviderResponse], Tuple[str, ...]]
ImageSaver = Callable[[ImageAttemptItem, str], str]
VideoProvider = Callable[..., Tuple[str, ...]]


def _credit_phase(emit_phase: PhaseEmitter, phase: AttemptPhase) -> object:
    return emit_phase(phase, consumes_credit=CreditConsumption.TRUE)


def run_image_attempt(
    request: ImageAttemptRequest,
    emit_phase: PhaseEmitter,
    *,
    provider: ImageProvider,
    downloader: ImageDownloader,
    saver: ImageSaver,
) -> ExecutorAttemptResult:
    """Một tin ChatGPT; lệch số giữ turn nhưng tuyệt đối không đoán mapping."""
    emit_phase(AttemptPhase.ATTACHING)
    response = provider(
        request,
        on_submitted=lambda: _credit_phase(
            emit_phase, AttemptPhase.SUBMITTED),
        on_waiting_provider=lambda: _credit_phase(
            emit_phase, AttemptPhase.WAITING_PROVIDER),
    )
    if not bool(response.notes.get("da_gui", True)):
        diagnostic = str(response.notes.get("chan_doan") or "").strip()
        raise LivePreSubmitError(
            diagnostic or "ChatGPT chưa nhận được cú submit")
    if bool(response.notes.get("user_dung", False)):
        return ExecutorAttemptResult({})

    downloaded: Tuple[str, ...] = ()
    if response.sources:
        _credit_phase(emit_phase, AttemptPhase.DOWNLOADING)
        downloaded = tuple(downloader(response))
    has_text = bool(str(response.notes.get("loi_text") or "").strip())
    if len(downloaded) != len(request.items) or has_text:
        return ExecutorAttemptResult({})

    _credit_phase(emit_phase, AttemptPhase.SAVING)
    outputs = {}
    for item, source_path in zip(request.items, downloaded):
        saved = str(saver(item, source_path) or "").strip()
        if not saved:
            raise LiveAttemptError(
                f"không lưu được output cho {item.asset_id}")
        outputs[item.job_id] = (saved,)
    return ExecutorAttemptResult(outputs)


def run_video_attempt(
    request: VideoAttemptRequest,
    emit_phase: PhaseEmitter,
    *,
    provider: VideoProvider,
    reserve_submit: Callable[[], object],
) -> ExecutorAttemptResult:
    """Một submit Grok; budget reservation nằm ngay trước click qua callback."""
    emit_phase(AttemptPhase.ATTACHING)
    outputs = tuple(provider(
        request,
        before_submit=reserve_submit,
        on_submitted=lambda: _credit_phase(
            emit_phase, AttemptPhase.SUBMITTED),
        on_waiting_provider=lambda: _credit_phase(
            emit_phase, AttemptPhase.WAITING_PROVIDER),
        on_downloading=lambda: _credit_phase(
            emit_phase, AttemptPhase.DOWNLOADING),
        on_saving=lambda: _credit_phase(
            emit_phase, AttemptPhase.SAVING),
    ))
    outputs = tuple(path for path in outputs if str(path).strip())
    if not outputs:
        raise LiveAttemptError("Grok attempt không có output")
    return ExecutorAttemptResult({request.job_id: outputs})
