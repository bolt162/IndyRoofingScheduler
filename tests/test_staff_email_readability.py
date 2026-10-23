"""Every email a staff member gets: labeled lines, no pipes, no bare links in sentences, no error text.
All names, phones and links here are made up."""
import re
from datetime import datetime, date, timedelta

from backend.emails import compose as K
from backend.emails import runner as R
from backend.emails.internal import format_phone, person, team_email
from backend.emails.preview import SAMPLES
from tests.test_email_runner import THU, add_job, db, jn, outbox, resched_setup, sched_job  # noqa: F401


def assert_readable(email) -> None:
    for part in (email["subject"] if isinstance(email, dict) else email.subject,
                 email["text"] if isinstance(email, dict) else email.text):
        assert "|" not in part, part
        assert "Traceback" not in part and "Exception" not in part and "Error" not in part, part
        assert not re.search(r"\{[a-z_]+\}", part), part
        assert "**" not in part and "<" not in part, part
    text = email["text"] if isinstance(email, dict) else email.text
    for line in text.splitlines():
        # a link is alone on its own line, never inside a sentence
        if "http" in line:
            assert line.startswith("http"), line


def test_phone_and_name_helpers():
    assert format_phone("3174406606") == "(317) 440-6606"
    assert format_phone("+1 317-440-6606") == "(317) 440-6606"
    assert format_phone("(not on file)") == "(not on file)"
    assert person("Anna Mcclellan") == "Anna McClellan" and person("Mcdonald Roofing") == "McDonald Roofing"
    assert person("Mc Neil") == "Mc Neil"


def test_team_email_layout_puts_links_last_with_labels():
    e = team_email("internal", "s", "Pat Doe's date moved.", "**What to do:** call Pat.",
                   [("Customer", "Pat Doe"), ("Customer phone", "3175550123"), ("JobNimbus", "https://example.com/j/1")])
    assert e.text == ("Pat Doe's date moved.\n\nCustomer: Pat Doe\nCustomer phone: (317) 555-0123\n\n"
                      "What to do: call Pat.\n\nOpen the job in JobNimbus\nhttps://example.com/j/1")
    assert '<a href="https://example.com/j/1"' in e.html and ">Open the job in JobNimbus</a>" in e.html


def test_jobnimbus_email_missing_alert_reads_clearly(db, jn, outbox):
    job = sched_job(db, jn)
    job.customer_name = "Anna Mcclellan"
    jn["details"][job.jn_job_id].customer_phone = "3174406606"
    db.commit()
    jn["jn_email"] = False
    R.run_scheduled_emails(db, THU + timedelta(hours=2), mode="live")
    mail = outbox[1]
    assert mail["subject"] == "No scheduling email from JobNimbus: Anna McClellan"
    assert mail["text"].startswith("Anna McClellan hasn't gotten JobNimbus's Project Update email with their build date (")
    assert "Customer phone: (317) 440-6606" in mail["text"] and "3174406606" not in mail["text"]
    assert "Build date: " in mail["text"]
    assert "1. Check the work order's start date and save.\n2. Move the work order off Pending Start" in mail["text"]
    assert "Open the job in JobNimbus\nhttps://app.jobnimbus.com/job/" in mail["text"]
    assert "Automatic check" not in mail["text"] and "fun" not in mail["text"]
    assert_readable(mail)


def test_second_reschedule_alert_reads_clearly(db, jn, outbox):
    resched_setup(db, jn, 2)
    R.run_reschedule_checks(db, THU + timedelta(hours=8), mode="live")
    assert_readable(outbox[1])
    assert "Customer phone: (317) 555-0100" in outbox[1]["text"]


def test_long_wait_alerts_read_clearly(db, jn, outbox):
    add_job(db, jn, "Jane Smith", entered=THU - timedelta(weeks=10))
    R.run_long_wait_alerts(db, THU, mode="live")
    assert len(outbox) == 2
    for mail in outbox:
        assert_readable(mail)
        assert "Open the job in JobNimbus\nhttps://" in mail["text"]


def test_preview_emails_use_blocks_and_headed_tables(db, jn, outbox):
    add_job(db, jn, "Jane Smith", rep="Nick Smith", entered=THU - timedelta(days=30))
    add_job(db, jn, "Bob Jones", rep="Joe Venn", entered=THU - timedelta(days=40))
    add_job(db, jn, "Noemail Owner", rep="Nick Smith", email="", entered=THU - timedelta(days=40))
    add_job(db, jn, "Long Waiter", rep="Nick Smith", entered=THU - timedelta(weeks=11))
    R.send_preview(db, THU - timedelta(hours=20), mode="live")
    full = next(s for s in outbox if len(s["to"]) > 1)
    assert full["subject"] == "3 customers get their build queue email Thursday"
    assert_readable(full)
    assert "Jane Smith (Roof)\n   Rep: Nick Smith\n   Email they get: " in full["text"]
    assert "\n   Their spot: " in full["text"]
    for header in ("Customer", "Rep", "Email they get", "Their spot"):
        assert f"<th" in full["html"] and f">{header}</th>" in full["html"]
    assert "Not getting an email (1)" in full["text"] and "Please fix in JobNimbus" in full["text"]
    nick = next(s for s in outbox if s["to"] == ["nick.smith@indyroofandrestoration.com"])
    assert_readable(nick)
    assert nick["subject"] == "2 of your customers get their weekly email Thursday" and "Bob Jones" not in nick["text"]
    assert "Rep:" not in nick["text"]


def test_past_date_and_ready_digest_have_headed_tables(db, jn, outbox):
    from backend.emails.jn_data import BuildDates
    add_job(db, jn, "Jenn Golding", bucket="scheduled", jn_status="Pending Start Date")
    R.run_past_date_alerts(db, datetime(2026, 10, 19, 12, 0), mode="live",
                           fetch=lambda jnid: BuildDates("J-26426", date(2026, 10, 14), [("WO-1", "Roofing", date(2026, 10, 14))]))
    assert_readable(outbox[0])
    assert ">Start date that passed</th>" in outbox[0]["html"] and "<td" in outbox[0]["html"]


def test_product_research_email_reads_clearly():
    import json
    from backend.models.email import ProductClassification
    row = ProductClassification(raw_text="Acme Roofing Shield AR 30", display_name="Acme Shield", impact_class=4,
                                composition="polymer_modified", confidence="high", summary="Class 4 rated.",
                                status="approved", sources=json.dumps([{"url": "https://example.com/a"}]))
    from backend.emails import research
    e = research.review_email(row)
    assert e.text.startswith("We looked up a shingle that wasn't on our list: Acme Shield.")
    assert "Source 1: example.com\nhttps://example.com/a" in e.text
    assert_readable(e)
    row.status = "pending"
    assert research.review_email(row).text.startswith("A shingle that wasn't on our list needs your OK")


def test_office_flag_email_reads_clearly():
    e = K.compose_office_flag(SAMPLES["roof_vista"], "The shingle on the order isn't one we know yet.")
    assert e.text.startswith("The shingle on the order isn't one we know yet.\n\nCustomer: Jane Smith")
    assert "Open the job in JobNimbus\nhttps://app.jobnimbus.com/job/sample" in e.text
    assert_readable(e)


def test_job_data_problems_are_plain_english_in_the_preview(db, jn, outbox):
    job = add_job(db, jn, "Jane Smith", entered=THU - timedelta(days=30))
    jn["details"][job.jn_job_id].errors = ["job/contact: HTTPSConnectionPool(host='x'): Max retries"]
    preview = R.build_preview(db, THU, mode="test")
    assert preview["rows"][0]["notes"] == ["We couldn't read the customer's contact details from JobNimbus"]


def test_preview_long_wait_and_heads_up_sections_read_clearly():
    preview = {"rows": [{"customer": "Pat Doe", "rep": "Nick Smith", "trade": "roof", "template": None, "label": "",
                         "reason": "no customer email", "subject": "", "spot": "", "notes": ["Something odd."]}],
               "fix": [{"customer": "Pat Doe", "rep": "Nick Smith", "reason": "no customer email"}],
               "long_wait": [{"customer": "Lee Roe", "rep": "", "weeks": 12}], "sending": 0}
    text = R.preview_text(preview)
    assert "Waiting 10+ weeks\n\nLee Roe\n   Rep: No rep\n   Weeks waiting: 12" in text
    assert "Heads up\n\nPat Doe\n   Note: Something odd" in text
    assert "|" not in text and "; " not in text
