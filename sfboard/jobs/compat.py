"""Dependency-injected bridge from producer intents to legacy queue actions."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Callable, Mapping, Optional, Tuple
from uuid import uuid4

from .models import JobId
from .producer import ProducerResult


@dataclass(frozen=True)
class LegacyAction:
    action_id: str
    legacy_keys: Tuple[str, ...]
    job_ids: Tuple[JobId, ...]
    queue_kind: str
    queue_ident: str
    manual: bool
    state: Optional[Mapping[str, object]] = None
    forced_account_id: Optional[str] = None


@dataclass(frozen=True)
class LegacyPlan:
    actions: Tuple[LegacyAction, ...]


@dataclass(frozen=True)
class LegacyDeliveryResult:
    delivered: bool
    replayed: bool
    completed_action_ids: Tuple[str, ...]


class LegacyEnqueueAdapter:
    """Deliver typed producer actions through callbacks owned by the legacy runtime."""

    def __init__(
        self,
        set_job_state: Callable[[str, Mapping[str, object], str], None],
        enqueue_image: Callable[[str, bool, str], None],
        enqueue_video: Callable[[str, bool, str], None],
        enqueue_private_image: Callable[[str, str, bool, str], None],
        bind_projection: Callable[[str, Tuple[JobId, ...]], None],
        mark_delivered: Callable[[str], None],
    ) -> None:
        self._set_job_state = set_job_state
        self._enqueue_image = enqueue_image
        self._enqueue_video = enqueue_video
        self._enqueue_private_image = enqueue_private_image
        self._bind_projection = bind_projection
        self._mark_delivered = mark_delivered
        self._locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._delivered: set[str] = set()
        self._completed_steps: dict[str, set[str]] = {}

    def deliver(
        self, result: ProducerResult, plan: LegacyPlan
    ) -> LegacyDeliveryResult:
        self._validate_plan(plan, result)
        key = result.idempotency_key
        lock = self._lock_for(key)
        with lock:
            if not result.delivery_required:
                return LegacyDeliveryResult(False, result.replayed, ())
            if key in self._delivered:
                return LegacyDeliveryResult(
                    False,
                    True,
                    tuple(action.action_id for action in plan.actions),
                )
            self._bind_plan(key, plan)
            for action in plan.actions:
                self._run_action(key, action)
            self._mark_delivered(key)
            self._delivered.add(key)
            return LegacyDeliveryResult(
                True,
                result.replayed,
                tuple(action.action_id for action in plan.actions),
            )

    def deliver_legacy(self, plan: LegacyPlan) -> LegacyDeliveryResult:
        self._validate_plan(plan, None)
        key = "legacy:" + uuid4().hex
        lock = self._lock_for(key)
        try:
            with lock:
                self._bind_plan(key, plan)
                for action in plan.actions:
                    self._run_action(key, action)
                return LegacyDeliveryResult(
                    True,
                    False,
                    tuple(action.action_id for action in plan.actions),
                )
        finally:
            with self._locks_guard:
                self._locks.pop(key, None)
                self._completed_steps.pop(key, None)

    def _lock_for(self, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(key, threading.Lock())

    def _bind_plan(self, delivery_key: str, plan: LegacyPlan) -> None:
        for action in plan.actions:
            self._bind_action(delivery_key, action)

    def _bind_action(self, delivery_key: str, action: LegacyAction) -> None:
        for legacy_key in action.legacy_keys:
            self._run_step(
                delivery_key,
                f"{action.action_id}:bind:{legacy_key}",
                lambda legacy_key=legacy_key: self._bind_projection(
                    legacy_key, action.job_ids
                ),
            )

    def _run_action(self, delivery_key: str, action: LegacyAction) -> None:
        state = action.state
        if state is not None:
            self._run_step(
                delivery_key,
                f"{action.action_id}:state",
                lambda: self._set_job_state(
                    action.queue_ident,
                    state,
                    f"{delivery_key}:{action.action_id}:state",
                ),
            )
        forced_account_id = action.forced_account_id
        if action.queue_kind == "img" and forced_account_id is not None:
            enqueue = lambda: self._enqueue_private_image(
                forced_account_id,
                action.queue_ident,
                action.manual,
                f"{delivery_key}:{action.action_id}:enqueue",
            )
        elif action.queue_kind == "img":
            enqueue = lambda: self._enqueue_image(
                action.queue_ident,
                action.manual,
                f"{delivery_key}:{action.action_id}:enqueue",
            )
        else:
            enqueue = lambda: self._enqueue_video(
                action.queue_ident,
                action.manual,
                f"{delivery_key}:{action.action_id}:enqueue",
            )
        self._run_step(delivery_key, f"{action.action_id}:enqueue", enqueue)

    def _run_step(
        self, delivery_key: str, step_id: str, callback: Callable[[], None]
    ) -> None:
        completed = self._completed_steps.setdefault(delivery_key, set())
        if step_id in completed:
            return
        callback()
        completed.add(step_id)

    @staticmethod
    def _validate_plan(plan: LegacyPlan, result: Optional[ProducerResult]) -> None:
        if not isinstance(plan, LegacyPlan) or not plan.actions:
            raise ValueError("legacy plan phải có action")
        action_ids = set()
        result_job_ids = (
            {job.job_id for job in result.jobs} if result is not None else set()
        )
        for action in plan.actions:
            if not isinstance(action, LegacyAction):
                raise ValueError("legacy plan chỉ chứa LegacyAction")
            if not isinstance(action.action_id, str) or not action.action_id.strip():
                raise ValueError("action_id không được rỗng")
            if action.action_id in action_ids:
                raise ValueError("action_id không được trùng")
            action_ids.add(action.action_id)
            if action.queue_kind not in {"img", "vid"}:
                raise ValueError("queue_kind phải là img hoặc vid")
            if not isinstance(action.queue_ident, str) or not action.queue_ident.strip():
                raise ValueError("queue_ident không được rỗng")
            if not action.legacy_keys or any(
                not isinstance(key, str) or not key.strip()
                for key in action.legacy_keys
            ):
                raise ValueError("legacy key không được rỗng")
            if action.queue_kind == "vid" and action.forced_account_id is not None:
                raise ValueError("video không hỗ trợ forced account")
            if result is not None:
                if not action.job_ids:
                    raise ValueError("shadow delivery cần job_ids")
                if not set(action.job_ids).issubset(result_job_ids):
                    raise ValueError("member JobId không thuộc ProducerResult")
