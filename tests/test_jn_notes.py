"""JobNimbus notes lookup feeding the AI note scanner. No network: _jn_get is faked."""
import json

from backend.services import jobnimbus as jn


def fake_activities(monkeypatch, items):
    calls = []

    def fake_get(endpoint, params=None):
        calls.append((endpoint, params))
        return {"count": len(items), "activity": items}
    monkeypatch.setattr(jn, "_jn_get", fake_get)
    return calls


def act(kind, note, ts):
    return {"record_type_name": kind, "note": note, "date_created": ts}


def test_filters_by_related_job_not_parent_jnid(monkeypatch):
    calls = fake_activities(monkeypatch, [])
    jn.fetch_notes_for_job("abc123")
    endpoint, params = calls[0]
    assert endpoint == "activities" and "parent_jnid" not in params
    assert json.loads(params["filter"]) == {"must": [{"term": {"related.id": "abc123"}}]}


def test_reads_activity_key_and_keeps_only_human_notes(monkeypatch):
    fake_activities(monkeypatch, [
        act("Note", "Permit is ready, picked up today", 300),
        act("Phone Call", "Customer asked about steep pitch", 200),
        act("Status Changed", "Job Updated Status: A => B", 400),
        act("Automation", "Project Update from Indy Roof", 500),
        act("Email", "Re: invoice", 600),
        act("Note", "[SCHEDULER SYSTEM -- Oct 1] Job selected for scheduling", 700),
        act("Note", "   ", 800),
    ])
    notes = jn.fetch_notes_for_job("abc123")
    assert [n["note"] for n in notes] == ["Permit is ready, picked up today", "Customer asked about steep pitch"]


def test_newest_first_and_capped(monkeypatch):
    fake_activities(monkeypatch, [act("Note", f"note {i}", i) for i in range(80)])
    notes = jn.fetch_notes_for_job("abc123")
    assert len(notes) == jn.MAX_NOTES and notes[0]["note"] == "note 79"


def test_build_notes_raw_includes_description_and_caps_length():
    notes = [{"note": "x" * 5000}, {"note": "y" * 5000}, {"note": "z" * 5000}]
    raw = jn.build_notes_raw("Steep 12/12, two layers", notes)
    assert raw.startswith("[Job Description] Steep 12/12, two layers")
    assert raw.count("[Note]") == 2 and "z" not in raw


def test_build_notes_raw_strips_html():
    raw = jn.build_notes_raw("", [{"note": "<b>Permit</b> ready&nbsp;today<br>call &amp; confirm"}])
    assert raw == "[Note] Permit ready\xa0today\ncall & confirm"


def test_old_bug_is_gone(monkeypatch):
    """Before the fix the lookup returned the whole dict, so notes were silently dropped."""
    fake_activities(monkeypatch, [act("Note", "Needs specialty crew", 1)])
    assert jn.build_notes_raw("", jn.fetch_notes_for_job("j")) == "[Note] Needs specialty crew"
