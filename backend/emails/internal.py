"""
One layout for every team email (never customers). Team members only need the data and what
to do with it, so each one reads the same short way:

  1. Optional greeting.
  2. One plain sentence with the customer and what happened.
  3. "What to do" in bold (or "nothing unless" for FYI emails).
  4. A details table, one fact per row; links show as short clickable text.
  5. Optional extra paragraphs.
"""
import html as h
from urllib.parse import urlparse

from backend.emails import markup
from backend.emails.compose import ComposedEmail, _wrap_html

CELL = "padding:6px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top;font-size:14px;line-height:20px;"
LABEL = CELL + "color:#6b7280;white-space:nowrap;width:1%;"


def _link_text(label: str, url: str) -> str:
    if label == "JobNimbus":
        return "Open the job in JobNimbus"
    host = urlparse(url).netloc
    return host[4:] if host.startswith("www.") else host or "Open link"


def _value_html(label: str, value: str) -> str:
    if value.startswith(("http://", "https://")):
        return f'<a href="{h.escape(value)}" style="color:#1e3a5f;">{h.escape(_link_text(label, value))}</a>'
    return h.escape(value)


def team_email(template: str, subject: str, lead: str, action: str,
               details: list[tuple[str, str]], greeting: str | None = None,
               extra: list[str] | None = None) -> ComposedEmail:
    """lead, action and extra use the tiny markup (**bold**, "- " / "1. " lists); details are (label, value)."""
    rows = [(k, v) for k, v in details if v not in (None, "")]
    parts_html, parts_text = [], []
    for para in [greeting, lead, action]:
        if para:
            parts_html.append(markup.to_html(para))
            parts_text.append(markup.to_text(para))
    if rows:
        trs = "".join(f'<tr><td style="{LABEL}">{h.escape(k)}</td><td style="{CELL}">{_value_html(k, str(v))}</td></tr>'
                      for k, v in rows)
        parts_html.append('<table role="presentation" cellpadding="0" cellspacing="0" '
                          f'style="width:100%;border-collapse:collapse;margin:0 0 16px 0;">{trs}</table>')
        parts_text.append("\n".join(f"{k}: {v}" for k, v in rows))
    for para in extra or []:
        parts_html.append(markup.to_html(para))
        parts_text.append(markup.to_text(para))
    return ComposedEmail(template, subject, _wrap_html("".join(parts_html), None, []),
                         "\n\n".join(parts_text), is_customer=False)
