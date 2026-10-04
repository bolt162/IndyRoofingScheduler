"""
Assemble a finished email (subject, HTML, text) from a template key and a job's EmailContext.
"""
import re
from dataclasses import dataclass, field, replace
from datetime import date

from backend.emails import copy as C
from backend.emails import markup
from backend.emails.config import COMPANY_NAME, OFFICE_ADDRESS
from backend.emails.products import ProductInfo, lookup_shingle, manufacturer_from_text, credential_line


INSTALL_TRACKS = ("roof", "siding", "gutters")
REPAIR_TRACKS = ("roof_repair", "siding_repair")
TRACKS = INSTALL_TRACKS + REPAIR_TRACKS

# Template keys
WELCOME = "welcome"
WEEKS = {f"week_{n}" for n in range(1, 9)}
ROTATION = "rotation"
GETTING_CLOSE = "getting_close"
WEATHER = "weather_slowdown"
RESCHEDULE = "reschedule"
FRONT_OF_LINE = "front_of_line"
SECOND_RESCHEDULE = "second_reschedule"
INTERNAL_SECOND_RESCHEDULE = "internal_second_reschedule"
OFFICE_FLAG = "office_flag"
SCHEDULED = "scheduled"


@dataclass
class EmailContext:
    """Everything an email might need about one job. Missing values are None/blank."""
    job_id: int
    track: str                       # roof / siding / gutters / roof_repair / siding_repair
    first_name: str = ""
    customer_name: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    job_address: str = ""
    is_low_slope: bool = False
    is_commercial: bool | None = None
    shingle_line: str = ""           # raw product text from JN, e.g. "Malarkey Vista"
    product: ProductInfo | None = None  # office-approved researched product, if any
    shingle_color: str = ""
    siding_product: str = ""
    siding_color: str = ""
    gutter_color: str = ""
    rep_name: str = ""
    rep_phone: str = ""
    rep_email: str = ""
    pm_name: str = ""
    pm_email: str = ""
    original_date: date | None = None
    job_link: str = ""
    jobs_ahead: int = 0
    jobs_ahead_last_week: int | None = None
    builds_completed_week: int = 0
    rescheduled_count: int = 0
    scheduled_date: date | None = None        # JobNimbus start date, for the scheduled email
    jn_schedule_email_sent: bool = True       # did JobNimbus's official email go out?


@dataclass
class ComposedEmail:
    template: str
    subject: str
    html: str
    text: str
    is_customer: bool = True
    flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _clean(value) -> str:
    """Values from JN go into copy; strip anything that would break the markup."""
    if value is None:
        return ""
    return re.sub(r"[*{}\r\n]+", " ", str(value)).strip()


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def project_word(track: str) -> str:
    return {"roof": "roof", "siding": "siding", "gutters": "gutters",
            "roof_repair": "roof repair", "siding_repair": "siding repair"}[track]


def is_repair(track: str) -> bool:
    return track in REPAIR_TRACKS


def _noun(track: str) -> tuple[str, str]:
    """What's in line ahead of the customer: builds for installs, repairs for repairs."""
    return ("repair", "repairs") if is_repair(track) else ("build", "builds")


def _ahead_count(n: int, track: str = "roof") -> str:
    one, many = _noun(track)
    return f"no {many} ahead of you" if n <= 0 else f"{_plural(n, one, many)} ahead of you"


def _ahead_now(n: int, track: str = "roof") -> str:
    one, many = _noun(track)
    if n <= 0:
        return f"There are no {many} ahead of you now"
    if n == 1:
        return f"There is 1 {one} ahead of you now"
    return f"There are {n} {many} ahead of you now"


def _ahead_bold(n: int, track: str = "roof") -> str:
    one, many = _noun(track)
    if n <= 0:
        return f"there are **no {many} ahead of you.**"
    if n == 1:
        return f"there is **1 {one} ahead of you.**"
    return f"there are **{n} {many} ahead of you.**"


# Stop counting down below these numbers (Aaron, 2026-10-03): near the front, the count
# moves unpredictably, so show "moving toward the front" instead of a number.
COUNT_FLOOR = {"roof": 10, "siding": 7, "gutters": 7}


def shows_count(ctx: EmailContext) -> bool:
    floor = COUNT_FLOOR.get(ctx.track)
    return floor is not None and ctx.jobs_ahead >= floor


def position_block(ctx: EmailContext) -> str:
    """{position_block} per the rules table. Never shows a number when the count went up,
    or once it drops below the track's floor."""
    n, last = ctx.jobs_ahead, ctx.jobs_ahead_last_week
    if not shows_count(ctx):
        text = C.POSITION_NEAR_FRONT
        if last is not None and n < last and ctx.builds_completed_week > 0:
            unit = ("roof", "roofs") if ctx.track == "roof" else ("project", "projects")
            text += " " + C.POSITION_DROPPED_BUILDS.format(
                builds_completed=_plural(ctx.builds_completed_week, *unit))
        return text
    if last is None:
        return C.POSITION_FIRST.format(ahead_count=_ahead_count(n, ctx.track))
    if n > last:
        return C.POSITION_UP
    if n == last:
        return C.POSITION_SAME.format(ahead_count=_ahead_count(n, ctx.track))
    text = C.POSITION_DROPPED.format(ahead_now=_ahead_now(n, ctx.track), delta=last - n)
    if ctx.builds_completed_week > 0:
        unit = {"roof": ("roof", "roofs")}.get(
            ctx.track, ("repair", "repairs") if is_repair(ctx.track) else ("project", "projects"))
        text += " " + C.POSITION_DROPPED_BUILDS.format(
            builds_completed=_plural(ctx.builds_completed_week, *unit)
        )
    return text


def tip_for(track: str, index: int) -> str:
    bank = {"roof": C.ROOF_TIPS, "siding": C.SIDING_TIPS, "gutters": C.GUTTER_TIPS,
            "roof_repair": C.REPAIR_ROOF_TIPS, "siding_repair": C.REPAIR_SIDING_TIPS}[track]
    return bank[index % len(bank)]


def product_for(ctx: EmailContext) -> ProductInfo | None:
    """Built-in table first, then an office-approved researched product."""
    return lookup_shingle(ctx.shingle_line) or ctx.product


def week2_version(ctx: EmailContext) -> tuple[str, bool]:
    """Return (version, office_flag). Low slope is always C. Unknown product is C plus a flag."""
    if ctx.is_low_slope:
        return "C", False
    info = product_for(ctx)
    if info is None:
        return "C", True
    return info.week2_version, False


# ---------------------------------------------------------------------------
# Template bodies
# ---------------------------------------------------------------------------

def _roof_materials(ctx: EmailContext) -> str:
    info = product_for(ctx)
    line = info.display_name if info else _clean(ctx.shingle_line)
    color = _clean(ctx.shingle_color)
    if line and color:
        return f"your {line} shingles in {color}"
    if line:
        return f"your {line} shingles"
    if color:
        return f"your shingles in {color}"
    return "your shingles"


def _body_and_subject(key: str, ctx: EmailContext, v: dict, flags: list[str]) -> tuple[str, str]:
    t = ctx.track

    if is_repair(t):
        if t == "roof_repair":
            v["leak_note"] = (
                C.REPAIR_LEAK_WITH_REP.format(rep_name=v["rep_name"], rep_phone=v["rep_phone"])
                if v["rep_name"] and v["rep_phone"] else C.REPAIR_LEAK_NO_REP
            )
        else:
            v["leak_note"] = ""
        if key in (RESCHEDULE, FRONT_OF_LINE, SECOND_RESCHEDULE):
            # Same approved reschedule copy, with "repair" in place of "build"
            subject, body = _body_and_subject(key, replace(ctx, track="roof"), v, flags)
            v["tip"] = tip_for(t, v.get("rotation_index", 0))
            return subject.replace("build", "repair"), body.replace("build", "repair")
        if key == WELCOME:
            return C.REPAIR_WELCOME_SUBJECT, C.REPAIR_WELCOME_BODY
        if key == ROTATION:
            idx = v.get("rotation_index", 0)
            subject, opener = C.REPAIR_ROTATION[idx % len(C.REPAIR_ROTATION)]
            v["opener"] = opener
            v["tip"] = tip_for(t, idx)
            return subject, C.REPAIR_WEEKLY_BODY
        if key in WEEKS or key == GETTING_CLOSE:
            raise ValueError(f"'{key}' is not part of the repair track")
        if key == SCHEDULED:
            pass  # handled below, with repair wording

    if key == WELCOME:
        return C.WELCOME_SUBJECT, C.WELCOME_BODY

    if key == "week_1":
        if t == "roof":
            if ctx.is_low_slope:
                v["roof_materials_bullet"] = C.ROOF_W1_MATERIALS_LOW_SLOPE
                v["color_tip"] = ""
            else:
                v["roof_materials_bullet"] = C.ROOF_W1_MATERIALS.format(roof_materials=_roof_materials(ctx))
                v["color_tip"] = C.ROOF_W1_COLOR_TIP
            return C.ROOF_W1_SUBJECT, C.ROOF_W1_BODY
        if t == "siding":
            product, color = _clean(ctx.siding_product), _clean(ctx.siding_color)
            v["siding_desc"] = (
                f"your {product} in {color}" if product and color
                else f"your {product}" if product
                else f"your siding in {color}" if color
                else "your siding"
            )
            return C.SIDING_W1_SUBJECT, C.SIDING_W1_BODY
        color = _clean(ctx.gutter_color)
        v["gutter_color_desc"] = f"your {color} color" if color else "your gutter color"
        return C.GUTTER_W1_SUBJECT, C.GUTTER_W1_BODY

    if key == "week_2":
        if t == "roof":
            version, flag = week2_version(ctx)
            if flag:
                flags.append(
                    f"Unknown shingle product '{_clean(ctx.shingle_line) or '(blank)'}'. "
                    "Sent the insurance tip without an impact rating (Version C). "
                    "Add the product to the lookup table if it has a rating."
                )
            info = product_for(ctx)
            v["shingle_line"] = info.display_name if info else ""
            body = {"A": C.ROOF_W2_A_BODY, "B": C.ROOF_W2_B_BODY, "C": C.ROOF_W2_C_BODY}[version]
            return C.INSURANCE_SUBJECT, body
        if t == "siding":
            return C.SIDING_W2_SUBJECT, C.SIDING_W2_BODY
        return C.GUTTER_W2_SUBJECT, C.GUTTER_W2_BODY

    if key == "week_3":
        return {
            "roof": (C.ROOF_W3_SUBJECT, C.ROOF_W3_BODY),
            "siding": (C.SIDING_W3_SUBJECT, C.SIDING_W3_BODY),
            "gutters": (C.GUTTER_W3_SUBJECT, C.GUTTER_W3_BODY),
        }[t]

    if key == "week_4":
        if t == "roof":
            if ctx.is_low_slope:
                v["roof_install_bullet"] = C.ROOF_W4_INSTALL_LOW_SLOPE
            else:
                color = _clean(ctx.shingle_color)
                v["roof_install_bullet"] = C.ROOF_W4_INSTALL.format(
                    new_shingles=f"your new {color} shingles" if color else "your new shingles"
                )
            return C.ROOF_W4_SUBJECT, C.ROOF_W4_BODY
        if t == "siding":
            color = _clean(ctx.siding_color)
            v["new_siding"] = f"your new {color} siding" if color else "your new siding"
            return C.SIDING_W4_SUBJECT, C.SIDING_W4_BODY
        return C.GUTTER_W4_SUBJECT, C.GUTTER_W4_BODY

    if key == "week_5":
        if t == "roof":
            sentence = C.W5_LOW_SLOPE_SENTENCE if ctx.is_low_slope else C.W5_SHINGLE_SENTENCE
            v["w5_opener"] = C.W5_OPENER_ROOF
            v["w5_conditions"] = C.W5_CONDITIONS_ROOF.format(w5_material_sentence=sentence)
            v["w5_tip"] = C.W5_TIP_ROOF
            return C.W5_SUBJECT_ROOF, C.W5_BODY
        v["w5_opener"] = C.W5_OPENER_PROJECT
        v["w5_conditions"] = C.W5_CONDITIONS_SIDING if t == "siding" else C.W5_CONDITIONS_GUTTERS
        v["w5_tip"] = ""
        return C.W5_SUBJECT_PROJECT, C.W5_BODY

    if key == "week_6":
        if t == "gutters":
            v["warranty_sentence"] = C.W6_WARRANTY_GUTTERS
        else:
            source = ctx.siding_product if t == "siding" else ctx.shingle_line
            info = product_for(ctx) if t == "roof" else None
            mfr = info.manufacturer if info else manufacturer_from_text(source)
            if mfr:
                sentence = C.W6_WARRANTY_WITH_MFR.format(project_word=v["project_word"], manufacturer=mfr)
                cred = credential_line(mfr) if t == "roof" else ""
                v["warranty_sentence"] = f"{sentence} {cred}".strip()
            else:
                v["warranty_sentence"] = C.W6_WARRANTY_NO_MFR.format(project_word=v["project_word"])
        return C.W6_SUBJECT, C.W6_BODY

    if key == "week_7":
        if _clean(ctx.rep_name) and _clean(ctx.rep_phone):
            v["referral_steps"] = C.W7_STEPS_WITH_REP.format(rep_name=v["rep_name"], rep_phone=v["rep_phone"])
        else:
            v["referral_steps"] = C.W7_STEPS_NO_REP
        return C.W7_SUBJECT, C.W7_BODY

    if key == "week_8":
        return C.W8_SUBJECT, C.W8_BODY

    if key == ROTATION:
        idx = v.get("rotation_index", 0)
        subject, opener = C.ROTATION[idx % len(C.ROTATION)]
        v["opener"] = opener
        v["tip"] = tip_for(t, idx)
        return subject, C.ROTATION_BODY

    if key == GETTING_CLOSE:
        checklist = {
            "roof": C.GETTING_CLOSE_CHECKLIST_ROOF,
            "siding": C.GETTING_CLOSE_CHECKLIST_SIDING,
            "gutters": C.GETTING_CLOSE_CHECKLIST_GUTTERS,
        }[t]
        if t == "roof":
            color = _clean(ctx.shingle_color)
            almost = (
                C.ALMOST_HERE_ROOF_COLOR.format(shingle_color=color)
                if color and not ctx.is_low_slope else C.ALMOST_HERE_ROOF
            )
        else:
            almost = C.ALMOST_HERE_SIDING if t == "siding" else C.ALMOST_HERE_GUTTERS
        v["checklist"] = checklist
        v["almost_here"] = almost
        return C.GETTING_CLOSE_SUBJECT, C.GETTING_CLOSE_BODY

    if key == SCHEDULED:
        word = "new " + v["project_word"] if not is_repair(t) else v["project_word"]
        v["official_email_line"] = C.SCHEDULED_OFFICIAL_LINE if ctx.jn_schedule_email_sent else ""
        v["date_line"] = (
            C.SCHEDULED_DATE_LINE.format(project_word=word, scheduled_date=_format_date(ctx.scheduled_date))
            if ctx.scheduled_date else C.SCHEDULED_NO_DATE_LINE.format(project_word=word)
        )
        v["finish_line"] = (C.SCHEDULED_FINISH_REPAIR if is_repair(t)
                            else C.SCHEDULED_FINISH_INSTALL.format(project_word=v["project_word"]))
        return C.SCHEDULED_SUBJECT, C.SCHEDULED_BODY

    if key == WEATHER:
        return C.WEATHER_SUBJECT, C.WEATHER_BODY

    if key == RESCHEDULE:
        return C.RESCHEDULE_SUBJECT, C.RESCHEDULE_BODY

    if key == FRONT_OF_LINE:
        v["tip"] = tip_for(t, v.get("rotation_index", 0))
        return C.FRONT_OF_LINE_SUBJECT, C.FRONT_OF_LINE_BODY

    if key == SECOND_RESCHEDULE:
        return C.SECOND_RESCHEDULE_SUBJECT, C.SECOND_RESCHEDULE_BODY

    raise ValueError(f"Unknown template '{key}'")


def _format_date(d: date | None) -> str:
    if not d:
        return "your scheduled date"
    return f"{d.strftime('%A, %B')} {d.day}"


def _subject(template: str, v: dict) -> str:
    if not v["first_name"]:
        template = re.sub(r",?\s*\{first_name\}", "", template)
    return template.format_map(v).strip()


def _wrap_html(inner: str, top_line: str | None, footer: list[str]) -> str:
    gray = "color:#6b7280;font-size:12px;line-height:18px;"
    top = f'<p style="{gray}margin:0 0 20px 0;">{top_line}</p>' if top_line else ""
    foot = "".join(f'<p style="{gray}margin:0 0 8px 0;">{line}</p>' for line in footer)
    foot_block = (
        f'<div style="border-top:1px solid #e5e7eb;margin-top:24px;padding-top:16px;">{foot}</div>'
        if footer else ""
    )
    return (
        '<!doctype html><html><body style="margin:0;padding:0;background:#ffffff;">'
        '<div style="max-width:600px;margin:0 auto;padding:24px 16px;font-family:Arial,Helvetica,sans-serif;'
        'font-size:16px;line-height:24px;color:#111827;">'
        f"{top}{inner}{foot_block}</div></body></html>"
    )


def _base_values(ctx: EmailContext) -> dict:
    return {
        "first_name": _clean(ctx.first_name),
        "customer_name": _clean(ctx.customer_name),
        "customer_phone": _clean(ctx.customer_phone) or "(not on file)",
        "job_address": _clean(ctx.job_address),
        "rep_name": _clean(ctx.rep_name),
        "rep_phone": _clean(ctx.rep_phone),
        "pm_name": _clean(ctx.pm_name) or "Team",
        "job_link": _clean(ctx.job_link),
        "project_word": project_word(ctx.track),
        "shingle_color": _clean(ctx.shingle_color),
        "original_date": _format_date(ctx.original_date),
        "jobs_ahead": ctx.jobs_ahead,
        "ahead_bold": _ahead_bold(ctx.jobs_ahead, ctx.track) if shows_count(ctx) else C.WELCOME_NEAR_FRONT,
        "repair_word": project_word(ctx.track),
    }


def compose(key: str, ctx: EmailContext, rotation_index: int = 0,
            unsubscribe_url: str | None = None) -> ComposedEmail:
    """Build a customer email (or the internal alert) for one job."""
    if ctx.track not in TRACKS:
        raise ValueError(f"Unknown track '{ctx.track}'")

    v = _base_values(ctx)
    v["rotation_index"] = rotation_index
    flags: list[str] = []

    if key == INTERNAL_SECOND_RESCHEDULE:
        if not v["rep_name"]:
            v["rep_name"] = "Sales Rep"
        subject = C.INTERNAL_SECOND_RESCHEDULE_SUBJECT.format_map(v)
        body = C.INTERNAL_SECOND_RESCHEDULE_BODY.format_map(v)
        html = _wrap_html(markup.to_html(body), None, [])
        return ComposedEmail(key, subject, html, markup.to_text(body), is_customer=False)

    subject_t, body_t = _body_and_subject(key, ctx, v, flags)
    v["position_block"] = position_block(ctx)

    greeting = f"Hi {v['first_name']}," if v["first_name"] else "Hi there,"
    body = greeting + "\n\n" + body_t.strip().format_map(v)
    # Drop blocks that came out empty (e.g. a tip that doesn't apply to this track)
    body = re.sub(r"\n\s*\n(\s*\n)+", "\n\n", body)
    subject = _subject(subject_t, v)

    if v["rep_name"] and v["rep_phone"]:
        footer_text = C.FOOTER_WITH_REP.format(rep_name=v["rep_name"], rep_phone=v["rep_phone"])
    else:
        footer_text = C.FOOTER_NO_REP
    address_line = f"{COMPANY_NAME}, {OFFICE_ADDRESS}"

    footer_html = [markup._inline_html(footer_text), markup._inline_html(address_line)]
    footer_txt = [footer_text, address_line]
    if unsubscribe_url:
        footer_html.append(
            f'<a href="{unsubscribe_url}" style="color:#6b7280;">Stop these weekly updates</a>'
        )
        footer_txt.append(f"Stop these weekly updates: {unsubscribe_url}")

    html = _wrap_html(markup.to_html(body), markup._inline_html(C.TOP_LINE), footer_html)
    text = C.TOP_LINE + "\n\n" + markup.to_text(body) + "\n\n" + "\n".join(footer_txt)
    return ComposedEmail(key, subject, html, text, is_customer=True, flags=flags)


def compose_office_flag(ctx: EmailContext, flag_text: str) -> ComposedEmail:
    v = _base_values(ctx)
    v["flag_text"] = _clean(flag_text)
    subject = C.OFFICE_FLAG_SUBJECT.format_map(v)
    body = C.OFFICE_FLAG_BODY.format_map(v)
    return ComposedEmail(OFFICE_FLAG, subject, _wrap_html(markup.to_html(body), None, []),
                         markup.to_text(body), is_customer=False)
