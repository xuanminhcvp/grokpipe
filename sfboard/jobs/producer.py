"""Typed producer commands for the shadow job lifecycle.

This module deliberately creates only durable domain intents.  Legacy queue
delivery remains outside this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Optional, Tuple
from uuid import uuid4

from .models import (
    AssetId,
    Batch,
    BatchId,
    BatchMode,
    EventActor,
    Job,
    JobEvent,
    JobId,
    JobKind,
    JobOrigin,
)
from .store import IdempotencyRecord, JobNotFound, JobStore, StaleScopeParent


@dataclass(frozen=True)
class CreateJobRequest:
    asset_id: AssetId
    kind: JobKind
    origin: JobOrigin
    request_scope: str
    manual: bool = False
    replace_current: bool = False
    forced_account_id: Optional[str] = None
    allow_account_fallback: bool = False


@dataclass(frozen=True)
class CreateBatchRequest:
    members: Tuple[CreateJobRequest, ...]
    mode: BatchMode


@dataclass(frozen=True)
class ProducerResult:
    jobs: Tuple[Job, ...]
    batch: Optional[Batch]
    idempotency_key: str
    replayed: bool
    delivery_required: bool


def _canonical(requests: Tuple[CreateJobRequest, ...], mode: Optional[BatchMode]):
    return {
        "assets": [str(request.asset_id) for request in requests],
        "kinds": [request.kind.value for request in requests],
        "origins": [request.origin.value for request in requests],
        "scopes": [request.request_scope for request in requests],
        "mode": mode.value if mode else None,
        "manual": [request.manual for request in requests],
        "replace": [request.replace_current for request in requests],
        "forced_accounts": [request.forced_account_id for request in requests],
        "fallback": [request.allow_account_fallback for request in requests],
    }


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_key(key: str) -> str:
    if not isinstance(key, str) or not key.strip():
        raise ValueError("idempotency_key không được rỗng")
    return key.strip()


class ProducerService:
    """Build idempotent shadow jobs without delivering them to a runtime."""

    def __init__(self, store: JobStore) -> None:
        self.store = store

    def create_job(
        self, request: CreateJobRequest, idempotency_key: Optional[str] = None
    ) -> ProducerResult:
        return self._create((request,), None, idempotency_key)

    def create_batch(
        self, request: CreateBatchRequest, idempotency_key: Optional[str] = None
    ) -> ProducerResult:
        if not isinstance(request, CreateBatchRequest):
            raise TypeError("request phải là CreateBatchRequest")
        return self._create(request.members, request.mode, idempotency_key)

    def rerun_job(
        self,
        old_job_id: JobId,
        request: CreateJobRequest,
        idempotency_key: str,
    ) -> ProducerResult:
        key = _validate_key(idempotency_key)
        old = self.store.get(old_job_id)
        if old is None:
            raise JobNotFound(str(old_job_id))
        if not old.state.is_terminal:
            raise ValueError("chỉ được rerun job terminal")
        if request.asset_id != old.asset_id or request.kind is not old.kind:
            raise ValueError("rerun phải giữ asset_id và kind của job cũ")
        return self._create((request,), None, key, rerun_of=(old.job_id,))

    def mark_delivered(self, idempotency_key: str) -> None:
        self.store.mark_intent_delivered(_validate_key(idempotency_key))

    def _create(
        self,
        requests: Tuple[CreateJobRequest, ...],
        mode: Optional[BatchMode],
        idempotency_key: Optional[str],
        *,
        rerun_of: Optional[Tuple[JobId, ...]] = None,
    ) -> ProducerResult:
        self._validate_requests(requests, mode)
        fingerprint = _digest(_canonical(requests, mode))
        scope_fingerprint = _digest(
            {
                "assets": [str(request.asset_id) for request in requests],
                "kinds": [request.kind.value for request in requests],
                "scopes": [request.request_scope for request in requests],
                "mode": mode.value if mode else None,
                "copies": len(requests),
            }
        )
        # Auto cũng cần dựng lại parent: lứa trước terminal mà thẻ vẫn thiếu ảnh
        # thì vòng quét sau là một Ý ĐỊNH MỚI, không phải replay của lứa đã chết.
        rebuild_parent = rerun_of is None and (
            all(request.manual for request in requests)
            or all(request.origin is JobOrigin.AUTO for request in requests)
        )
        while True:
            parent_job_ids = (
                self._terminal_scope_job_ids(scope_fingerprint, len(requests))
                if rebuild_parent
                else rerun_of
            )
            key = self._resolve_key(
                requests, scope_fingerprint, idempotency_key,
                parent_job_ids=parent_job_ids,
            )
            batch_id = BatchId.new() if mode is not None else None
            jobs = tuple(
                self._make_job(
                    request,
                    batch_id=batch_id,
                    rerun_of=parent_job_ids[index] if parent_job_ids else None,
                    copy_index=index if mode is BatchMode.MULTI_COPY else None,
                )
                for index, request in enumerate(requests)
            )
            batch = (
                Batch(batch_id, jobs[0].kind, mode, tuple(job.job_id for job in jobs))
                if batch_id is not None
                else None
            )
            record = IdempotencyRecord(
                key=key,
                fingerprint=fingerprint,
                scope_fingerprint=scope_fingerprint,
                job_ids=tuple(job.job_id for job in jobs),
                batch_id=batch_id,
                delivered=False,
            )
            try:
                write = self.store.create_intent(
                    record,
                    batch,
                    tuple((job, self._make_event(job)) for job in jobs),
                    expected_scope_job_ids=parent_job_ids,
                    check_scope_parent=rebuild_parent,
                )
            except StaleScopeParent:
                if not rebuild_parent:
                    raise
                continue
            break
        return ProducerResult(
            jobs=write.jobs,
            batch=write.batch,
            idempotency_key=key,
            replayed=write.replayed,
            delivery_required=not write.record.delivered,
        )

    @staticmethod
    def _make_job(
        request: CreateJobRequest,
        *,
        batch_id: Optional[BatchId],
        rerun_of: Optional[JobId],
        copy_index: Optional[int],
    ) -> Job:
        return Job(
            job_id=JobId.new(),
            asset_id=request.asset_id,
            kind=request.kind,
            origin=request.origin,
            batch_id=batch_id,
            rerun_of=rerun_of,
            copy_index=copy_index,
            replace_current=request.replace_current,
            forced_account_id=request.forced_account_id,
            allow_account_fallback=request.allow_account_fallback,
        )

    @staticmethod
    def _make_event(job: Job) -> JobEvent:
        return JobEvent(
            uuid4(),
            job.job_id,
            EventActor.MANAGER,
            "producer.created",
            "producer.accepted",
        )

    @staticmethod
    def _resolve_key(
        requests: Tuple[CreateJobRequest, ...],
        scope_fingerprint: str,
        idempotency_key: Optional[str],
        *,
        parent_job_ids: Optional[Tuple[JobId, ...]] = None,
    ) -> str:
        if idempotency_key:
            return _validate_key(idempotency_key)
        if all(request.origin is JobOrigin.AUTO for request in requests):
            # Cố định TRONG MỘT LỨA — hai vòng quét liên tiếp phải ra cùng khoá,
            # nếu không auto xếp hai lượt cho một thẻ. Nhưng phải ĐỔI khi lứa
            # trước đã terminal, nếu không khoá cũ giam auto lại vĩnh viễn.
            if parent_job_ids:
                return "auto:" + scope_fingerprint + ":" + _digest(
                    [str(job_id) for job_id in parent_job_ids])
            return "auto:" + scope_fingerprint
        return "request:" + uuid4().hex

    def _terminal_scope_job_ids(
        self, scope_fingerprint: str, count: int
    ) -> Optional[Tuple[JobId, ...]]:
        latest = self.store.latest_for_scope(scope_fingerprint)
        if latest is None or len(latest.job_ids) != count:
            return None
        jobs = tuple(self.store.get(job_id) for job_id in latest.job_ids)
        if any(job is None or not job.state.is_terminal for job in jobs):
            return None
        return latest.job_ids

    @staticmethod
    def _validate_requests(
        requests: Tuple[CreateJobRequest, ...], mode: Optional[BatchMode]
    ) -> None:
        if not requests:
            raise ValueError("cần ít nhất một request")
        if mode is not None and not isinstance(mode, BatchMode):
            raise TypeError("mode phải là BatchMode")
        for request in requests:
            if not isinstance(request, CreateJobRequest):
                raise TypeError("member phải là CreateJobRequest")
            if not isinstance(request.asset_id, AssetId) or not isinstance(
                request.kind, JobKind
            ) or not isinstance(request.origin, JobOrigin):
                raise TypeError("request phải dùng typed identity và enum chuẩn")
            if not isinstance(request.request_scope, str) or not request.request_scope.strip():
                raise ValueError("request_scope không được rỗng")
            if not isinstance(request.manual, bool) or request.manual != (
                request.origin is JobOrigin.MANUAL
            ):
                raise ValueError("manual phải khớp origin")
            if not isinstance(request.replace_current, bool) or not isinstance(
                request.allow_account_fallback, bool
            ):
                raise TypeError("replace_current/fallback phải là bool")
            if request.forced_account_id is not None and (
                not isinstance(request.forced_account_id, str)
                or not request.forced_account_id.strip()
            ):
                raise ValueError("forced_account_id không được rỗng")
            if request.allow_account_fallback and not request.forced_account_id:
                raise ValueError("fallback chỉ hợp lệ khi ép account")

        if mode is None:
            if len(requests) != 1:
                raise ValueError("nhiều member cần batch mode")
            return
        if len({request.kind for request in requests}) != 1:
            raise ValueError("mọi member batch phải cùng kind")
        if mode in {BatchMode.IMAGE_GROUP, BatchMode.MULTI_COPY} and (
            requests[0].kind is not JobKind.IMAGE
        ):
            raise ValueError("image batch phải có kind=image")
        if mode is BatchMode.BULK_VIDEO and requests[0].kind is not JobKind.VIDEO:
            raise ValueError("bulk_video phải có kind=video")
        asset_ids = tuple(request.asset_id for request in requests)
        if mode is BatchMode.IMAGE_GROUP and len(set(asset_ids)) != len(asset_ids):
            raise ValueError("image_group không được có asset trùng")
        if mode is BatchMode.MULTI_COPY and len(set(asset_ids)) != 1:
            raise ValueError("multi_copy phải dùng cùng một asset")
