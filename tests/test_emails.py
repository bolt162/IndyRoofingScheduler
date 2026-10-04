"""Acceptance tests for build queue emails (handoff Part 4.7). Run: python -m pytest tests"""
import re
from dataclasses import replace
from datetime import datetime, date, timedelta
from types import SimpleNamespace

import pytest

from backend.emails import compose as K
from backend.emails import selector as S
from backend.emails.compose import compose, EmailContext
from backend.emails.preview import REPAIR_SEQUENCE, SAMPLES, SEQUENCE
from backend.emails.products import lookup_shingle

NOW = datetime(2026, 10, 8, 10, 0)  # a Thursday


def job(**kw):
    base = dict(bucket="to_schedule", jn_status="Schedule Job", date_scheduled=None, rescheduled_count=0)
    base.update(kw)
    return SimpleNamespace(**base)


def welcomed_state(**kw):
    st = S.new_state(1)
    st.welcome_sent = True
    st.last_jobs_ahead = 20
    st.last_counted_email_at = NOW - timedelta(days=7)
    for k, v in kw.items():
        setattr(st, k, v)
    return st


# --- Every template renders for every track, with no dashes or leftover placeholders ---

ALL_PAIRS = [(s, k) for s, c in SAMPLES.items()
             for k in (REPAIR_SEQUENCE if K.is_repair(c.track) else SEQUENCE)]


@pytest.mark.parametrize("sample,key", ALL_PAIRS)
def test_every_template_renders_clean(sample, key):
    email = compose(key, SAMPLES[sample])
    for part in (email.subject, email.text, email.html):
        assert "—" not in part and "–" not in part, "em/en dash in copy"
        assert " - " not in part.replace("\n- ", "\n"), "dashed aside in copy"
        assert not re.search(r"\{[a-z_]+\}", part), "unfilled placeholder"


def test_customer_emails_have_top_line_and_footer():
    email = compose("week_1", SAMPLES["roof_vista"])
    assert email.text.startswith("This is an automated update from a no reply address")
    assert "Replies to this email are not received or read" in email.text
    assert "5240 Elmwood Ave" in email.text


def test_internal_alert_has_no_customer_wrapper():
    email = compose(K.INTERNAL_SECOND_RESCHEDULE, SAMPLES["roof_vista"])
    assert not email.is_customer
    assert "no reply address" not in email.text
    assert email.subject == "Second reschedule: Jane Smith, 123 Main St, Indianapolis, IN 46203"


# --- Position block ---

def ctx(**kw):
    return replace(SAMPLES["roof_vista"], **kw)


def test_position_dropped():
    assert K.position_block(ctx(jobs_ahead=18, jobs_ahead_last_week=23, builds_completed_week=11)) == (
        "There are 18 builds ahead of you now, 5 fewer than last week. Our crews finished 11 roofs this week.")


def test_position_dropped_siding_says_projects():
    text = K.position_block(replace(SAMPLES["siding"], jobs_ahead=10, jobs_ahead_last_week=12))
    assert "11 projects this week" in text


def test_position_same():
    assert K.position_block(ctx(jobs_ahead=12, jobs_ahead_last_week=12)).startswith(
        "You're holding strong with 12 builds ahead of you.")


def test_position_went_up_shows_no_number():
    text = K.position_block(ctx(jobs_ahead=15, jobs_ahead_last_week=12))
    assert not re.search(r"\d", text)
    assert text.startswith("Your spot is locked in")


def test_three_or_fewer_sends_getting_close():
    d = S.weekly_decision(ctx(jobs_ahead=3), welcomed_state(), job(), NOW)
    assert d.template == K.GETTING_CLOSE


def test_getting_close_never_after_reschedule():
    d = S.weekly_decision(ctx(jobs_ahead=2, rescheduled_count=1), welcomed_state(), job(), NOW)
    assert d.template != K.GETTING_CLOSE


# --- Week 2 product lookup ---

def test_week2_vista_is_version_a():
    assert "Class 4 impact rating" in compose("week_2", ctx(shingle_line="Malarkey Vista")).text


def test_week2_highlander_is_version_b():
    assert "Class 3 impact rating" in compose("week_2", ctx(shingle_line="Malarkey Highlander")).text


def test_week2_duration_flex_beats_duration():
    assert lookup_shingle("OC Duration FLEX").impact_class == 4
    assert lookup_shingle("Owens Corning Duration").impact_class == 3


def test_week2_unknown_is_c_with_office_flag():
    email = compose("week_2", ctx(shingle_line="Some New Shingle"))
    assert "impact rating" not in email.text
    assert email.flags and "Unknown shingle product" in email.flags[0]


def test_week2_low_slope_always_c_no_flag():
    email = compose("week_2", replace(SAMPLES["low_slope"], shingle_line="Malarkey Vista"))
    assert "impact rating" not in email.text and not email.flags


# --- Week 6 credential lines ---

def test_week6_owens_corning():
    assert "Owens Corning Preferred Contractor" in compose("week_6", SAMPLES["roof_duration"]).text


def test_week6_malarkey():
    assert "certified Malarkey contractor" in compose("week_6", SAMPLES["roof_vista"]).text


def test_week6_siding_has_brand_no_credential():
    text = compose("week_6", SAMPLES["siding"]).text
    assert "manufacturer warranty from James Hardie" in text
    assert "Preferred Contractor" not in text and "certified" not in text


def test_week6_gutters_workmanship():
    text = compose("week_6", SAMPLES["gutters"]).text
    assert "backed by our workmanship" in text and "manufacturer warranty" not in text


# --- Sequence / weekly rules ---

def test_sequence_advances_week_by_week():
    st = welcomed_state()
    c = ctx(jobs_ahead=20)
    seen = []
    t = NOW
    for _ in range(10):
        d = S.weekly_decision(c, st, job(), t)
        seen.append(d.template)
        S.apply_sent(st, d, c, t)
        t += timedelta(days=7)
    assert seen == [f"week_{n}" for n in range(1, 9)] + [K.ROTATION, K.ROTATION]
    assert st.rotation_index == 2


def test_rotation_never_repeats_pairing_back_to_back():
    for track in ("roof", "siding", "gutters"):
        pairs = [(i % len(K.C.ROTATION), K.tip_for(track, i)) for i in range(20)]
        assert all(pairs[i] != pairs[i + 1] for i in range(19))


def test_unwelcomed_job_gets_welcome_first():
    d = S.weekly_decision(ctx(), S.new_state(1), job(), NOW)
    assert d.template == K.WELCOME


def test_one_email_per_week():
    st = welcomed_state(last_counted_email_at=NOW - timedelta(days=1))
    assert S.weekly_decision(ctx(), st, job(), NOW).template is None


def test_weather_slowdown_replaces_weekly():
    assert S.weekly_decision(ctx(), welcomed_state(), job(), NOW, weather_on=True).template == K.WEATHER


def test_scheduled_job_gets_nothing():
    j = job(bucket="scheduled", jn_status="Pending Start Date", date_scheduled=date(2026, 10, 20))
    assert S.weekly_decision(ctx(), welcomed_state(), j, NOW).template is None


def test_commercial_never_receives_anything():
    c = ctx(is_commercial=True, rescheduled_count=2)
    st = welcomed_state(reschedule_pending_since=NOW, reschedule_track=True)
    assert S.weekly_decision(c, st, job(), NOW).template is None
    assert S.welcome_decision(c, S.new_state(1), job(), NOW).template is None
    assert S.reschedule_decision(c, st, job(rescheduled_count=2), NOW).template is None


def test_unknown_commercial_flag_blocks_sending():
    assert S.weekly_decision(ctx(is_commercial=None), welcomed_state(), job(), NOW).template is None


def test_tracks_by_primary_trade():
    assert S.track_for("roofing") == "roof"
    assert S.track_for("roofing_repair") == "roof_repair"
    assert S.track_for("siding_repair") == "siding_repair"
    assert S.track_for("windows") is None and S.track_for("paint") is None


def repair_ctx(**kw):
    return replace(SAMPLES["roof_repair"], **kw)


def test_repair_track_is_welcome_then_weekly_checkins():
    st = S.new_state(1)
    c = repair_ctx(jobs_ahead=2)  # 3 or fewer ahead never triggers Getting close on repairs
    seen, t = [], NOW
    for _ in range(4):
        d = S.weekly_decision(c, st, job(), t)
        seen.append(d.template)
        S.apply_sent(st, d, c, t)
        t += timedelta(days=7)
    assert seen == [K.WELCOME, K.ROTATION, K.ROTATION, K.ROTATION]


def test_repair_emails_never_show_a_count():
    """Ops request: repairs get fit in around builds, so never show how many are ahead."""
    c = repair_ctx(jobs_ahead=5, jobs_ahead_last_week=7, builds_completed_week=11)
    emails = [compose(K.WELCOME, c)] + [compose(K.ROTATION, c, rotation_index=i) for i in range(5)]
    emails.append(compose(K.FRONT_OF_LINE, c))
    for e in emails:
        # Message body only: drop the footer (office address) and phone numbers
        body = e.text.split("Replies to this email are not received")[0]
        body = re.sub(r"\(\d{3}\) \d{3}-\d{4}", "", body)  # phone numbers are fine
        assert not re.search(r"\d", body), f"number in {e.template}: {e.subject}"
        assert "ahead of you" not in body
        assert "build" not in body.lower() and "new roof" not in body.lower()
    assert emails[0].subject == "Your repair is on our schedule, Jane"
    assert "roof repair is officially on our schedule" in emails[0].text
    assert "working its way up the list" in emails[1].text


def test_repair_emails_thank_them_and_cover_leaks():
    c = repair_ctx()
    for key in (K.WELCOME, K.ROTATION):
        text = compose(key, c).text
        assert "while we work through our customer list" in text
        assert "please call Mike Johnson, the rep who signed you up, at (317) 555-0199" in text
        assert "tarp" in text
    no_rep = compose(K.ROTATION, repair_ctx(rep_phone="")).text
    assert "If a leak starts while you wait:** please call us at (317) 886-7436".replace("**", "") in no_rep
    siding = compose(K.ROTATION, replace(SAMPLES["siding_repair"])).text
    assert "while we work through our customer list" in siding and "tarp" not in siding


def test_repair_reschedule_says_repair_not_build():
    c = repair_ctx(original_date=date(2026, 10, 14))
    for key in (K.RESCHEDULE, K.FRONT_OF_LINE, K.SECOND_RESCHEDULE):
        e = compose(key, c)
        assert "build" not in (e.subject + e.text).lower()
    assert compose(K.RESCHEDULE, c).subject == "A quick update on your repair date"
    assert "Your repair that was set for Wednesday, October 14" in compose(K.RESCHEDULE, c).text


def test_repair_tips_rotate_without_back_to_back_repeats():
    for track in ("roof_repair", "siding_repair"):
        pairs = [(i % len(K.C.REPAIR_ROTATION), K.tip_for(track, i)) for i in range(20)]
        assert all(pairs[i] != pairs[i + 1] for i in range(19))


def test_repair_cannot_get_build_day_emails():
    with pytest.raises(ValueError):
        compose("week_3", repair_ctx())
    with pytest.raises(ValueError):
        compose(K.GETTING_CLOSE, repair_ctx())


def test_commercial_repair_gets_nothing():
    d = S.weekly_decision(repair_ctx(is_commercial=True), S.new_state(1), job(), NOW)
    assert d.template is None


# --- Reschedules ---

def scheduled_job(count, when=date(2026, 10, 7)):
    return job(bucket="scheduled", jn_status="Pending Start Date", date_scheduled=when,
               rescheduled_count=count)


def test_first_reschedule_no_new_date():
    st = welcomed_state()
    j = scheduled_job(0)
    j.rescheduled_count = 1          # marked Not Built
    assert S.note_reschedule(st, j, NOW)
    assert st.original_date == date(2026, 10, 7)
    d = S.reschedule_decision(ctx(rescheduled_count=1), st, j, NOW)
    assert d.template == K.RESCHEDULE and not d.internal_alert
    S.apply_sent(st, d, ctx(), NOW)
    assert st.reschedule_track
    email = compose(K.RESCHEDULE, ctx(original_date=st.original_date))
    assert "set for Wednesday, October 7 had to be rescheduled" in email.text


def test_still_no_date_by_thursday_gets_front_of_line_without_number():
    st = welcomed_state(reschedule_track=True, original_date=date(2026, 10, 7))
    # JN may still show the old status; a past date is not a new date
    d = S.weekly_decision(ctx(rescheduled_count=1), st, scheduled_job(1), NOW)
    assert d.template == K.FRONT_OF_LINE
    text = compose(K.FRONT_OF_LINE, ctx()).text
    assert "builds ahead" not in text


def test_new_date_set_same_day_sends_nothing_and_leaves_track():
    st = welcomed_state(reschedule_track=True, original_date=date(2026, 10, 7),
                        reschedule_pending_since=NOW)
    j = scheduled_job(1, when=date(2026, 10, 15))
    assert S.reschedule_decision(ctx(rescheduled_count=1), st, j, NOW).template is None
    S.clear_reschedule_if_dated(st, j, NOW.date())
    assert not st.reschedule_track
    assert S.weekly_decision(ctx(rescheduled_count=1), st, j, NOW).template is None


def test_second_reschedule_customer_email_and_internal_alert():
    st = welcomed_state(reschedule_track=True, reschedule_count_seen=1, original_date=date(2026, 10, 7))
    j = scheduled_job(2, when=date(2026, 10, 7))
    assert S.note_reschedule(st, j, NOW)
    d = S.reschedule_decision(ctx(rescheduled_count=2), st, j, NOW)
    assert d.template == K.SECOND_RESCHEDULE and d.internal_alert


def test_reschedule_email_does_not_use_up_the_weekly_email():
    st = welcomed_state(reschedule_pending_since=NOW - timedelta(days=2))
    d = S.Decision(K.RESCHEDULE)
    S.apply_sent(st, d, ctx(), NOW - timedelta(days=2))
    assert S.weekly_decision(ctx(rescheduled_count=1), st, scheduled_job(1), NOW).template == K.FRONT_OF_LINE


# --- Missing data never leaves a blank ---

def test_missing_first_name_and_color():
    c = ctx(first_name="", shingle_color="", shingle_line="", rep_phone="")
    for key in ("week_1", "week_4", K.GETTING_CLOSE, "week_7", K.FRONT_OF_LINE, K.WELCOME):
        email = compose(key, c)
        assert "Hi there," in email.text
        assert ",  " not in email.subject and not email.subject.endswith(",")
        assert "  " not in email.text
    assert compose(K.WELCOME, c).subject == "You're officially on the build schedule"


# --- Countdown floor: no number under 10 for roofing, under 7 for siding ---

@pytest.mark.parametrize("track_sample,floor", [("roof_vista", 10), ("low_slope", 10), ("siding", 7), ("gutters", 7)])
def test_countdown_stops_below_floor(track_sample, floor):
    base = SAMPLES[track_sample]
    at = replace(base, jobs_ahead=floor, jobs_ahead_last_week=floor + 4)
    assert f"There are {floor} builds ahead of you now" in K.position_block(at)
    below = replace(base, jobs_ahead=floor - 1, jobs_ahead_last_week=floor + 4)
    text = K.position_block(below)
    assert text.startswith("Your spot is locked in and you're moving toward the front.")
    assert "ahead of you" not in text
    assert f"{floor - 1}" not in text.replace("11 ", "")  # builds-finished stat may remain


def test_welcome_below_floor_has_no_number():
    e = compose(K.WELCOME, replace(SAMPLES["roof_vista"], jobs_ahead=6, jobs_ahead_last_week=None))
    assert "Right now your spot is locked in and you're moving toward the front." in e.text
    assert "builds ahead" not in e.text
    e = compose(K.WELCOME, replace(SAMPLES["roof_vista"], jobs_ahead=25, jobs_ahead_last_week=None))
    assert "Right now there are 25 builds ahead of you." in e.text


def test_getting_close_still_fires_at_three():
    d = S.weekly_decision(ctx(jobs_ahead=3), welcomed_state(), job(), NOW)
    assert d.template == K.GETTING_CLOSE



# --- You're scheduled (fun one) ---

def test_scheduled_email_has_date_and_weather_and_official_note():
    e = compose(K.SCHEDULED, ctx(scheduled_date=date(2026, 10, 21)))
    assert e.subject.startswith("It's official, Jane! You're on the calendar")
    assert "Your new roof is scheduled for Wednesday, October 21!" in e.text
    assert "pesky weather (boo, hiss)" in e.text
    assert "more official email from us" in e.text
    assert "brand new roof" in e.text


def test_scheduled_email_without_jn_email_or_date():
    e = compose(K.SCHEDULED, ctx(scheduled_date=None, jn_schedule_email_sent=False))
    assert "more official email" not in e.text
    assert "Your new roof is officially on the calendar!" in e.text


def test_scheduled_email_for_repairs_and_siding():
    rep = compose(K.SCHEDULED, repair_ctx(scheduled_date=date(2026, 10, 21)))
    assert "Your roof repair is scheduled for Wednesday, October 21!" in rep.text
    assert "one less thing on your list" in rep.text and "brand new" not in rep.text
    sid = compose(K.SCHEDULED, replace(SAMPLES["siding"], scheduled_date=date(2026, 10, 21)))
    assert "Your new siding is scheduled for" in sid.text and "brand new siding" in sid.text
