import json

from sfboard.jobs.runtime_sentry import SentryReporter, resolve_dsn


CANARY = "Bearer shhh9x7q cookie=sessionid=shhh9x7q"


class FakeSdk:
    def __init__(self, fail_init=False, fail_capture=False):
        self.init_kwargs = None
        self.events = []
        self.flushed = False
        self._fail_init = fail_init
        self._fail_capture = fail_capture

    def init(self, **kwargs):
        if self._fail_init:
            raise RuntimeError("dsn hỏng")
        self.init_kwargs = kwargs

    def capture_event(self, event):
        if self._fail_capture:
            raise RuntimeError("mạng chết")
        self.events.append(event)

    def flush(self, timeout=None):
        self.flushed = True


def event(**overrides):
    base = {
        "schema_version": 1,
        "event_id": "00000000-0000-4000-8000-000000000000",
        "occurred_at": "2026-08-14T01:02:03Z",
        "severity": "ERROR",
        "category": "provider",
        "reason_code": "PROVIDER_TRANSIENT",
        "fingerprint": "f" * 64,
        "job": {"job_id": "V-S1-07", "kind": "vid", "phase": "submitting"},
        "runtime": {"endpoint": "127.0.0.1:9222"},
        "exception": {
            "type": "TimeoutError",
            "message": f"không nối được Grok — {CANARY}",
            "source_file": "grokpipe/video_grok.py",
            "source_function": "submit",
            "source_line": 88,
        },
    }
    base.update(overrides)
    return base


def test_without_dsn_everything_is_a_silent_no_op(tmp_path):
    sdk = FakeSdk()

    reporter = SentryReporter(tmp_path, sdk=sdk, env={})

    assert reporter.enabled is False
    assert reporter.capture(event()) is False
    assert sdk.init_kwargs is None
    assert sdk.events == []


def test_missing_sentry_package_disables_reporting(tmp_path):
    reporter = SentryReporter(tmp_path, dsn="https://k@example.test/1", sdk=None, env={})
    reporter._sdk = None
    reporter.enabled = False

    assert reporter.capture(event()) is False


def test_dsn_enables_privacy_safe_initialisation(tmp_path):
    sdk = FakeSdk()

    reporter = SentryReporter(tmp_path, sdk=sdk, env={"SENTRY_DSN": "https://k@example.test/1"})

    assert reporter.enabled is True
    assert sdk.init_kwargs["dsn"] == "https://k@example.test/1"
    assert sdk.init_kwargs["send_default_pii"] is False
    assert sdk.init_kwargs["traces_sample_rate"] == 0.0
    assert sdk.init_kwargs["environment"] == "grokpipe"


def test_captured_payload_is_redacted_and_grouped_by_fingerprint(tmp_path):
    sdk = FakeSdk()
    reporter = SentryReporter(tmp_path, dsn="https://k@example.test/1", sdk=sdk, env={})

    assert reporter.capture(event()) is True

    payload = sdk.events[0]
    assert payload["fingerprint"] == ["f" * 64]
    assert payload["level"] == "error"
    assert payload["tags"]["reason_code"] == "PROVIDER_TRANSIENT"
    assert "shhh9x7q" not in json.dumps(payload)


def test_critical_severity_maps_to_fatal(tmp_path):
    sdk = FakeSdk()
    reporter = SentryReporter(tmp_path, dsn="https://k@example.test/1", sdk=sdk, env={})

    reporter.capture(event(severity="CRITICAL"))

    assert sdk.events[0]["level"] == "fatal"


def test_broken_transport_never_raises(tmp_path):
    reporter = SentryReporter(
        tmp_path, dsn="https://k@example.test/1", sdk=FakeSdk(fail_capture=True), env={}
    )

    assert reporter.capture(event()) is False
    assert reporter.last_error


def test_broken_init_leaves_reporting_disabled(tmp_path):
    reporter = SentryReporter(
        tmp_path, dsn="https://k@example.test/1", sdk=FakeSdk(fail_init=True), env={}
    )

    assert reporter.enabled is False
    assert reporter.last_error


def test_close_flushes_once_and_disables(tmp_path):
    sdk = FakeSdk()
    reporter = SentryReporter(tmp_path, dsn="https://k@example.test/1", sdk=sdk, env={})

    reporter.close()

    assert sdk.flushed is True
    assert reporter.enabled is False


def test_resolve_dsn_prefers_the_project_specific_variable():
    assert resolve_dsn({"GROKPIPE_SENTRY_DSN": "a", "SENTRY_DSN": "b"}) == "a"
    assert resolve_dsn({"SENTRY_DSN": "b"}) == "b"
    assert resolve_dsn({"SENTRY_DSN": "  "}) == ""
    assert resolve_dsn({}) == ""
