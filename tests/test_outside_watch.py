"""The outside watcher flags a stale timer, a dead page and a missing field; stays quiet when all is fresh."""
import json
from datetime import datetime, timedelta, timezone

from tools import outside_watch as w

NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)
T = {"name": "x", "url": "u", "checks": [{"field": "worker.alive", "equals": True},
                                         {"field": "worker.secs", "max": 900},
                                         {"field": "last_ok", "max_age_s": 6000}]}


def run(body, status=200, target=T):
    return w.check_target(target, lambda url: (status, json.dumps(body) if not isinstance(body, str) else body), NOW)


def good():
    return {"ok": True, "worker": {"alive": True, "secs": 54}, "last_ok": (NOW - timedelta(minutes=10)).isoformat()}


def test_fresh_app_has_no_problems():
    assert run(good()) == []


def test_stale_number_timestamp_and_dead_worker_are_each_named():
    b = good()
    b["worker"] = {"alive": False, "secs": 5000}
    b["last_ok"] = (NOW - timedelta(hours=5)).isoformat()
    p = run(b)
    assert len(p) == 3 and any("300 minutes" in x for x in p)


def test_http_503_unreachable_and_non_json_are_problems():
    assert "503" in run({}, 503)[0]
    assert "nothing" in run("", 0)[0]
    assert "not JSON" in run("<html>")[0]


def test_app_saying_not_ok_and_missing_field():
    assert any("not healthy" in x for x in run({**good(), "ok": False}))
    assert any("missing" in x for x in run({"ok": True}))


def test_exit_code_follows_the_worst_app(tmp_path):
    f = tmp_path / "t.json"
    f.write_text(json.dumps([{"name": "a", "url": "u"}]))
    assert w.main(str(f), lambda url: (200, '{"ok": true}')) == 0
    assert w.main(str(f), lambda url: (503, "{}")) == 1
