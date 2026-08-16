import threading
import unittest

from sfboard.jobs.compat import (
    LegacyAction,
    LegacyEnqueueAdapter,
    LegacyPlan,
)
from sfboard.jobs.models import AssetId, Job, JobId, JobKind, JobOrigin
from sfboard.jobs.producer import ProducerResult


def make_producer_result(key, count=1):
    jobs = tuple(
        Job(JobId.new(), AssetId(f"A-{index}"), JobKind.IMAGE, JobOrigin.MANUAL)
        for index in range(count)
    )
    return ProducerResult(jobs, None, key, False, True)


def make_two_job_result(key):
    return make_producer_result(key, count=2)


def make_two_action_plan(result):
    return LegacyPlan(tuple(
        LegacyAction(
            action_id=f"member-{index}",
            legacy_keys=(str(job.asset_id),),
            job_ids=(job.job_id,),
            queue_kind="img",
            queue_ident="LO:" + str(job.asset_id),
            manual=True,
            state={"state": "queued", "msg": "chờ"},
        )
        for index, job in enumerate(result.jobs)
    ))


def make_legacy_plan():
    return LegacyPlan((
        LegacyAction(
            action_id="legacy-0", legacy_keys=("A",), job_ids=(),
            queue_kind="img", queue_ident="LO:A", manual=True,
            state={"state": "queued", "msg": "chờ"},
        ),
    ))


class LegacyEnqueueAdapterTest(unittest.TestCase):
    def setUp(self):
        self.enqueued = []
        self.states = []
        self.bound = []
        self.marked = []
        self.counts = {}
        self.fail_once_on = None
        self.fail_next_enqueue = False
        self.events = []
        self.adapter = LegacyEnqueueAdapter(
            set_job_state=self._set_job_state,
            enqueue_image=self._enqueue_image,
            enqueue_video=self._enqueue_video,
            enqueue_private_image=self._enqueue_private_image,
            bind_projection=self._bind_projection,
            mark_delivered=self._mark_delivered,
        )

    def _record_enqueue(self, action_key, queue_ident):
        self.events.append("enqueue:" + queue_ident)
        self.counts[action_key] = self.counts.get(action_key, 0) + 1
        if self.fail_next_enqueue:
            self.fail_next_enqueue = False
            raise RuntimeError("queue unavailable")
        if action_key == self.fail_once_on and self.counts[action_key] == 1:
            raise RuntimeError("queue unavailable")
        self.enqueued.append((action_key, queue_ident))

    def _set_job_state(self, ident, state, action_key):
        self.events.append("state:" + ident)
        self.states.append((action_key, ident, dict(state)))

    def _enqueue_image(self, ident, manual, action_key):
        self._record_enqueue(action_key, ident)

    def _enqueue_video(self, ident, manual, action_key):
        self._record_enqueue(action_key, ident)

    def _enqueue_private_image(self, account_id, ident, manual, action_key):
        self._record_enqueue(action_key, ident)

    def _bind_projection(self, legacy_key, job_ids):
        self.events.append("bind:" + legacy_key)
        self.bound.append((legacy_key, job_ids))

    def _mark_delivered(self, key):
        self.marked.append(key)

    def test_two_threads_deliver_one_intent_once(self):
        result = make_producer_result("intent-1")
        plan = LegacyPlan((
            LegacyAction(
                action_id="member-0", legacy_keys=("A",), job_ids=(result.jobs[0].job_id,),
                queue_kind="img", queue_ident="LO:A", manual=True,
                state={"state": "queued", "msg": "chờ · 1 ảnh"},
            ),
        ))
        barrier = threading.Barrier(2)
        threads = [
            threading.Thread(
                target=lambda: (barrier.wait(), self.adapter.deliver(result, plan))
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(self.enqueued, [("intent-1:member-0:enqueue", "LO:A")])
        self.assertEqual(self.marked, ["intent-1"])

    def test_partial_failure_retries_only_unconfirmed_action(self):
        result = make_two_job_result("intent-2")
        plan = make_two_action_plan(result)
        self.fail_once_on = "intent-2:member-1:enqueue"
        with self.assertRaises(RuntimeError):
            self.adapter.deliver(result, plan)
        self.adapter.deliver(result, plan)
        self.assertEqual(self.counts["intent-2:member-0:enqueue"], 1)
        self.assertEqual(self.counts["intent-2:member-1:enqueue"], 2)
        self.assertEqual(self.marked, ["intent-2"])

    def test_delivery_replay_after_success_performs_no_callbacks(self):
        result = make_producer_result("intent-replay")
        plan = make_two_action_plan(result)
        first = self.adapter.deliver(result, plan)
        callbacks_after_first = (
            tuple(self.enqueued), tuple(self.states), tuple(self.bound), tuple(self.marked)
        )
        second = self.adapter.deliver(result, plan)
        self.assertTrue(first.delivered)
        self.assertFalse(first.replayed)
        self.assertFalse(second.delivered)
        self.assertTrue(second.replayed)
        self.assertEqual(
            callbacks_after_first,
            (tuple(self.enqueued), tuple(self.states), tuple(self.bound), tuple(self.marked)),
        )

    def test_delivery_not_required_performs_no_callbacks(self):
        original = make_producer_result("delivered-in-store")
        result = ProducerResult(
            original.jobs, None, "delivered-in-store", True, False
        )
        outcome = self.adapter.deliver(result, make_two_action_plan(original))
        self.assertFalse(outcome.delivered)
        self.assertTrue(outcome.replayed)
        self.assertEqual((self.enqueued, self.states, self.bound, self.marked), ([], [], [], []))

    def test_legacy_delivery_does_not_dedupe_distinct_calls(self):
        plan = make_legacy_plan()
        self.adapter.deliver_legacy(plan)
        self.adapter.deliver_legacy(plan)
        self.assertEqual(len(self.enqueued), 2)

    def test_binds_entire_plan_before_state_or_enqueue(self):
        result = make_two_job_result("intent-bind-order")
        self.adapter.deliver(result, make_two_action_plan(result))
        self.assertEqual(
            self.events,
            [
                "bind:A-0",
                "bind:A-1",
                "state:LO:A-0",
                "enqueue:LO:A-0",
                "state:LO:A-1",
                "enqueue:LO:A-1",
            ],
        )

    def test_legacy_delivery_cleans_nonce_caches_after_each_call(self):
        baseline = (len(self.adapter._locks), len(self.adapter._completed_steps))
        plan = make_legacy_plan()
        for _ in range(3):
            self.adapter.deliver_legacy(plan)
        self.assertEqual(len(self.enqueued), 3)
        self.assertEqual(
            (len(self.adapter._locks), len(self.adapter._completed_steps)), baseline
        )

    def test_failed_legacy_delivery_cleans_nonce_caches(self):
        baseline = (len(self.adapter._locks), len(self.adapter._completed_steps))
        self.fail_next_enqueue = True
        with self.assertRaises(RuntimeError):
            self.adapter.deliver_legacy(make_legacy_plan())
        self.assertEqual(sum(self.counts.values()), 1)
        self.assertEqual(
            (len(self.adapter._locks), len(self.adapter._completed_steps)), baseline
        )

    def test_invalid_shadow_plan_has_no_callbacks(self):
        result = make_producer_result("intent-invalid")
        invalid_plans = (
            LegacyPlan(()),
            LegacyPlan((
                LegacyAction("same", ("A",), (result.jobs[0].job_id,), "img", "LO:A", True),
                LegacyAction("same", ("B",), (result.jobs[0].job_id,), "img", "LO:B", True),
            )),
            LegacyPlan((
                LegacyAction("bad-kind", ("A",), (result.jobs[0].job_id,), "audio", "LO:A", True),
            )),
            LegacyPlan((
                LegacyAction("empty-ident", ("A",), (result.jobs[0].job_id,), "img", "", True),
            )),
            LegacyPlan((
                LegacyAction("empty-key", ("",), (result.jobs[0].job_id,), "img", "LO:A", True),
            )),
            LegacyPlan((
                LegacyAction("empty-members", ("A",), (), "img", "LO:A", True),
            )),
            LegacyPlan((
                LegacyAction("foreign-member", ("A",), (JobId.new(),), "img", "LO:A", True),
            )),
            LegacyPlan((
                LegacyAction("video-private", ("A",), (result.jobs[0].job_id,), "vid", "V:A", True, forced_account_id="7"),
            )),
        )
        for plan in invalid_plans:
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                self.adapter.deliver(result, plan)
            self.assertEqual((self.enqueued, self.states, self.bound, self.marked), ([], [], [], []))
