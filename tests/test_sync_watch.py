"""SCH-05: Aaron gets one email when the JobNimbus sync stops, and one more only after it recovers and stops again."""
import time

import pytest

import backend.main as main


@pytest.fixture
def sent(monkeypatch):
    calls = []
    from backend.emails import runner
    monkeypatch.setattr(runner, "alert_owner", lambda db, subject, lead, action, details=None, **kw: calls.append(
        {"subject": subject, "lead": lead, "action": action, "details": details}) or True)
    monkeypatch.setitem(main._health, "sync_minutes", 30)
    monkeypatch.setitem(main._health, "started", time.time() - 10 * 3600)
    monkeypatch.setitem(main._sync_watch, "alerted", False)
    return calls


def _ago(minutes):
    return time.time() - minutes * 60


def test_quiet_while_the_sync_is_recent(sent, monkeypatch):
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(20))
    main._jn_sync_watch()
    assert sent == []


def test_quiet_right_after_a_restart(sent, monkeypatch):
    monkeypatch.setitem(main._health, "started", time.time() - 60)
    monkeypatch.setitem(main._health, "jn_sync_ok", None)
    main._jn_sync_watch()
    assert sent == []


def test_one_email_when_the_sync_has_stopped(sent, monkeypatch):
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(150))
    main._jn_sync_watch()
    assert len(sent) == 1
    email = sent[0]
    assert "JobNimbus" in email["subject"]
    assert "2 hours" in email["lead"] or "150 minutes" in email["lead"]
    # rule 11: plain words, no raw errors, ids or markup
    for text in [email["subject"], email["lead"], email["action"]]:
        assert "<" not in text and "{" not in text and "http" not in text


def test_no_repeat_email_while_it_stays_stopped(sent, monkeypatch):
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(150))
    main._jn_sync_watch()
    main._jn_sync_watch()
    main._jn_sync_watch()
    assert len(sent) == 1


def test_emails_again_after_it_recovers_and_stops_again(sent, monkeypatch):
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(150))
    main._jn_sync_watch()
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(5))
    main._jn_sync_watch()
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(200))
    main._jn_sync_watch()
    assert len(sent) == 2


def test_never_raises_if_the_alert_fails(monkeypatch):
    from backend.emails import runner

    def boom(*a, **k):
        raise RuntimeError("smtp down")
    monkeypatch.setattr(runner, "alert_owner", boom)
    monkeypatch.setitem(main._health, "jn_sync_ok", _ago(500))
    monkeypatch.setitem(main._sync_watch, "alerted", False)
    main._jn_sync_watch()  # no exception


def test_sync_job_counts_as_ok_only_when_it_worked(monkeypatch):
    """A sync that reports errors for every status it read is not a good sync."""
    from backend.services import jobnimbus
    monkeypatch.setitem(main._health, "jn_sync_ok", None)
    monkeypatch.setattr(jobnimbus, "sync_jobs_from_jn",
                        lambda db: {"created": 0, "updated": 0, "errors": ["x"], "fetched": 0})
    main._jn_sync_job()
    assert main._health["jn_sync_ok"] is None
