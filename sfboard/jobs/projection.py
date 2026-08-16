from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Callable, Optional, Tuple
from uuid import uuid4

from .manager import IllegalTransition, JobManager, TransitionCommand
from .models import (
    AssetId,
    EventActor,
    Job,
    JobId,
    JobKind,
    JobOrigin,
    JobState,
)
from .store import VersionConflict


LEGACY_STATE_MAP = {
    "queued": JobState.QUEUED,
    "running": JobState.RUNNING,
    "done": JobState.COMPLETED,
}
ACTIVE_STATES = {
    JobState.CREATED,
    JobState.QUEUED,
    JobState.RUNNING,
    JobState.RETRY_WAIT,
}
CANCEL_WORDS = (
    "đã huỷ",
    "đã hủy",
    "đã dừng",
    "huỷ riêng",
    "hủy riêng",
    "chưa chạy",
)


@dataclass(frozen=True)
class ShadowMismatch:
    legacy_key: str
    current_state: JobState
    target_state: JobState
    reason_code: str


def _target(value) -> Optional[JobState]:
    if not isinstance(value, dict):
        return None
    state = str(value.get("state") or "")
    if state != "error":
        return LEGACY_STATE_MAP.get(state)
    message = str(value.get("msg") or "").lower()
    if any(word in message for word in CANCEL_WORDS):
        return JobState.CANCELLED
    return JobState.FAILED


def _reason(value, target: JobState) -> str:
    state = str(value.get("state") or "") if isinstance(value, dict) else "unknown"
    return f"legacy.{state}.{target.value}"


class LegacyShadowProjection:
    def __init__(
        self,
        manager: JobManager,
        kind_resolver: Callable[[str], JobKind],
        mismatch_sink: Optional[Callable[[ShadowMismatch], None]] = None,
    ) -> None:
        self._manager = manager
        self._kind_resolver = kind_resolver
        self._mismatch_sink = mismatch_sink
        self._lock = RLock()
        self._job_ids: dict[str, Tuple[JobId, ...]] = {}
        self._compatibility_keys: set[str] = set()
        self._observed_writes = 0
        self._mismatch_count = 0
        self._mismatches: deque[ShadowMismatch] = deque(maxlen=20)

    def job_for(self, legacy_key: str) -> Job:
        with self._lock:
            return self._manager.get(self._job_ids[legacy_key][0])

    def jobs_for(self, legacy_key: str) -> Tuple[Job, ...]:
        with self._lock:
            return tuple(
                self._manager.get(job_id) for job_id in self._job_ids[legacy_key]
            )

    def bind(self, legacy_key: str, job_ids: Tuple[JobId, ...]) -> None:
        if not legacy_key or not job_ids or len(set(job_ids)) != len(job_ids):
            raise ValueError("projection binding không hợp lệ")
        with self._lock:
            jobs = tuple(self._manager.get(job_id) for job_id in job_ids)
            current_ids = self._job_ids.get(legacy_key)
            if current_ids is not None and current_ids != job_ids:
                current = tuple(self._manager.get(job_id) for job_id in current_ids)
                if any(not job.state.is_terminal for job in current):
                    self._record_mismatch(
                        ShadowMismatch(
                            legacy_key,
                            current[0].state,
                            jobs[0].state,
                            "projection.bind_active_collision",
                        )
                    )
                    return
            self._job_ids[legacy_key] = tuple(job_ids)
            self._compatibility_keys.discard(legacy_key)

    def _start_job(
        self,
        key: str,
        previous: Optional[Job],
        reason: str,
    ) -> Job:
        job = Job(
            JobId.new(),
            AssetId(key),
            self._kind_resolver(key),
            JobOrigin.COMPATIBILITY,
            rerun_of=previous.job_id if previous else None,
        )
        self._manager.create_job(
            job,
            uuid4(),
            EventActor.MANAGER,
            reason,
        )
        self._job_ids[key] = (job.job_id,)
        self._compatibility_keys.add(key)
        return job

    def _record_mismatch(self, mismatch: ShadowMismatch) -> None:
        self._mismatch_count += 1
        self._mismatches.append(mismatch)
        if self._mismatch_sink is not None:
            self._mismatch_sink(mismatch)

    def observe(self, key: str, old_value, new_value) -> None:
        target = _target(new_value)
        if target is None:
            return
        with self._lock:
            self._observed_writes += 1
            reason = _reason(new_value, target)
            current_jobs = (
                self.jobs_for(key) if key in self._job_ids else tuple()
            )
            if not current_jobs:
                current_jobs = (self._start_job(key, None, reason),)
            elif (
                key in self._compatibility_keys
                and all(job.state.is_terminal for job in current_jobs)
                and target in ACTIVE_STATES
            ):
                current_jobs = (
                    self._start_job(key, current_jobs[0], reason),
                )

            for current in current_jobs:
                if current.state is target:
                    self._manager.record_progress(
                        current.job_id,
                        uuid4(),
                        EventActor.MANAGER,
                        "legacy.progress",
                        reason,
                    )
                    continue
                command = TransitionCommand(
                    current.job_id,
                    current.version,
                    target,
                    EventActor.MANAGER,
                    "legacy.transition",
                    reason,
                    uuid4(),
                )
                try:
                    self._manager.transition(command)
                except (IllegalTransition, VersionConflict):
                    self._record_mismatch(
                        ShadowMismatch(
                            key,
                            current.state,
                            target,
                            reason,
                        )
                    )

    def diagnostics(self) -> dict:
        with self._lock:
            return {
                "mode": "shadow",
                "observed_writes": self._observed_writes,
                "tracked_jobs": len(self._job_ids),
                "mismatches": self._mismatch_count,
                "recent_mismatches": [
                    {
                        "legacy_key": item.legacy_key,
                        "from": item.current_state.value,
                        "to": item.target_state.value,
                        "reason_code": item.reason_code,
                    }
                    for item in self._mismatches
                ],
            }
