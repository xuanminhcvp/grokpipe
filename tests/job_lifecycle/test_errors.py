import dataclasses
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sfboard.jobs.errors import ErrorClass, ErrorFact
from sfboard.jobs.models import (
    AccountLease,
    AttemptId,
    AttemptPhase,
    EventActor,
    JobEvent,
    JobId,
    JobState,
)


class ErrorFactTest(unittest.TestCase):
    def test_all_approved_error_classes_exist(self):
        self.assertEqual(
            {error_class.value for error_class in ErrorClass},
            {
                "validation",
                "cancelled",
                "session_transient",
                "provider_transient",
                "quota_rate_limit",
                "permanent",
                "unknown_outcome",
                "account_lost",
            },
        )

    def test_unknown_outcome_requires_submitted_boundary(self):
        with self.assertRaises(ValueError):
            ErrorFact(
                ErrorClass.UNKNOWN_OUTCOME,
                "mất kết nối",
                AttemptPhase.ATTACHING,
            )

    def test_error_fact_is_immutable(self):
        fact = ErrorFact(
            ErrorClass.SESSION_TRANSIENT,
            "tab đóng",
            AttemptPhase.PREPARING,
        )
        with self.assertRaises(dataclasses.FrozenInstanceError):
            fact.message = "khác"


class LifecycleFactTest(unittest.TestCase):
    def test_transition_event_requires_both_states(self):
        with self.assertRaises(ValueError):
            JobEvent(
                uuid4(),
                JobId.new(),
                EventActor.MANAGER,
                "transition",
                "test",
                from_state=JobState.CREATED,
            )

    def test_account_lease_expiry_must_follow_acquisition(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValueError):
            AccountLease("lease-1", "acct-1", AttemptId.new(), 0, now, now)
        valid = AccountLease(
            "lease-2",
            "acct-1",
            AttemptId.new(),
            1,
            now,
            now + timedelta(minutes=1),
        )
        self.assertEqual(valid.slot, 1)
