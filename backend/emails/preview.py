"""
Render every email for a set of sample jobs into HTML files for review.

    python -m backend.emails.preview [output_dir]

Writes one .html file per email plus index.html. Sends nothing.
"""
import html
import sys
from datetime import date
from pathlib import Path

from backend.emails import compose as K
from backend.emails.compose import EmailContext, compose

_COMMON = dict(
    first_name="Jane", customer_name="Jane Smith", customer_email="jane@example.com",
    customer_phone="(317) 555-0142", job_address="123 Main St, Indianapolis, IN 46203",
    is_commercial=False, rep_name="Mike Johnson", rep_phone="(317) 555-0199",
    rep_email="mike@example.com", pm_name="Chris Lee", pm_email="chris@example.com",
    original_date=date(2026, 10, 14), scheduled_date=date(2026, 10, 21), job_link="https://app.jobnimbus.com/job/sample",
    jobs_ahead=18, jobs_ahead_last_week=23, builds_completed_week=11,
)

SAMPLES = {
    "roof_vista": EmailContext(job_id=1, track="roof", shingle_line="Malarkey Vista",
                               shingle_color="Weathered Wood", **_COMMON),
    "roof_highlander": EmailContext(job_id=2, track="roof", shingle_line="Malarkey Highlander",
                                    shingle_color="Midnight Black", **_COMMON),
    "roof_duration": EmailContext(job_id=3, track="roof", shingle_line="Owens Corning Duration",
                                  shingle_color="Driftwood", **_COMMON),
    "roof_oakridge": EmailContext(job_id=8, track="roof", shingle_line="Owens Corning Oakridge",
                                  shingle_color="Driftwood", **_COMMON),
    "roof_unknown_product": EmailContext(job_id=4, track="roof", shingle_line="GAF Timberline HDZ",
                                         shingle_color="Charcoal", **_COMMON),
    "low_slope": EmailContext(job_id=5, track="roof", is_low_slope=True, **_COMMON),
    "siding": EmailContext(job_id=6, track="siding", siding_product="James Hardie",
                           siding_color="Arctic White", **_COMMON),
    "gutters": EmailContext(job_id=7, track="gutters", gutter_color="Musket Brown", **_COMMON),
    "roof_repair": EmailContext(job_id=9, track="roof_repair", **_COMMON),
    "siding_repair": EmailContext(job_id=10, track="siding_repair", **_COMMON),
}

REPAIR_SEQUENCE = [K.WELCOME, K.ROTATION, K.WEATHER, K.RESCHEDULE, K.FRONT_OF_LINE, K.SECOND_RESCHEDULE, K.SCHEDULED]

SEQUENCE = [K.WELCOME] + [f"week_{n}" for n in range(1, 9)] + [
    K.ROTATION, K.GETTING_CLOSE, K.WEATHER, K.RESCHEDULE, K.FRONT_OF_LINE,
    K.SECOND_RESCHEDULE, K.INTERNAL_SECOND_RESCHEDULE, K.SCHEDULED,
]

# Templates that look the same for every sample; render them once from the roof sample
SHARED_ONCE = {K.WELCOME, "week_7", "week_8", K.WEATHER, K.RESCHEDULE,
               K.SECOND_RESCHEDULE, K.INTERNAL_SECOND_RESCHEDULE}

LABELS = {
    K.WELCOME: "Day 0 Welcome", "week_1": "Week 1 Behind the scenes", "week_2": "Week 2 Save money",
    "week_3": "Week 3 Prep", "week_4": "Week 4 Install day", "week_5": "Week 5 Weather",
    "week_6": "Week 6 Warranty", "week_7": "Week 7 Referral", "week_8": "Week 8 Note from Aaron",
    K.ROTATION: "Week 9+ Rotation (repairs: weekly check-in)", K.GETTING_CLOSE: "Getting close", K.WEATHER: "Weather slowdown",
    K.RESCHEDULE: "Reschedule", K.FRONT_OF_LINE: "Front of the line",
    K.SECOND_RESCHEDULE: "Second reschedule", K.INTERNAL_SECOND_RESCHEDULE: "Internal alert (PM + rep)",
    K.SCHEDULED: "You're scheduled (fun one)",
}


def render_all(out_dir: Path) -> list[tuple[str, str, str, str]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for sample, ctx in SAMPLES.items():
        repair = K.is_repair(ctx.track)
        for key in (REPAIR_SEQUENCE if repair else SEQUENCE):
            shared = key in SHARED_ONCE and not (repair and key in (K.WELCOME,))
            if shared and sample not in ("roof_vista",) and not (repair and key == K.WELCOME):
                continue
            email = compose(key, ctx)
            name = f"{sample}__{key}.html"
            (out_dir / name).write_text(email.html, encoding="utf-8")
            rows.append((sample, LABELS[key], email.subject, name))
    return rows


def write_index(out_dir: Path, rows) -> Path:
    body = []
    current = None
    for sample, label, subject, name in rows:
        if sample != current:
            if current is not None:
                body.append("</ul>")
            body.append(f"<h2>{html.escape(sample.replace('_', ' ').title())}</h2><ul>")
            current = sample
        body.append(f'<li><a href="{name}" target="view">{html.escape(label)}</a>'
                    f' <span>{html.escape(subject)}</span></li>')
    body.append("</ul>")
    page = (
        "<!doctype html><meta charset='utf-8'><title>Build Queue Email Previews</title>"
        "<style>body{margin:0;display:flex;font-family:Arial,sans-serif}"
        "nav{width:380px;height:100vh;overflow:auto;padding:12px 16px;border-right:1px solid #ddd;box-sizing:border-box}"
        "h2{font-size:15px;margin:18px 0 6px}ul{margin:0;padding-left:18px}li{margin:4px 0;font-size:14px}"
        "span{display:block;color:#666;font-size:12px}iframe{flex:1;height:100vh;border:0}</style>"
        f"<nav><h1 style='font-size:18px'>Build Queue Emails</h1>{''.join(body)}</nav>"
        f"<iframe name='view' src='{rows[0][3]}'></iframe>"
    )
    path = out_dir / "index.html"
    path.write_text(page, encoding="utf-8")
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "email-previews")
    rows = render_all(out)
    print(f"Wrote {len(rows)} emails. Open {write_index(out, rows)}")
