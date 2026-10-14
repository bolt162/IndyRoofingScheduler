"""
One layout for every team email (never customers), so each one reads the same way:

  1. Gray "what this is" line: which automatic email this is and why you got it.
  2. Optional greeting.
  3. "What to do" in bold (or "Nothing to do" for FYI emails).
  4. A details table, one fact per row; links are clickable.
  5. Optional extra paragraphs.
"""
import html as h

from backend.emails import markup
from backend.emails.compose import ComposedEmail, _wrap_html

CELL = "padding:6px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top;font-size:14px;line-height:20px;"
LABEL = CELL + "color:#6b7280;white-space:nowrap;width:1%;"
WHAT_THIS_IS = ("background:#f3f4f6;border-left:4px solid #1e3a5f;padding:10px 12px;margin:0 0 20px 0;"
                "font-size:14px;line-height:20px;color:#374151;")


def _value_html(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return f'<a href="{h.escape(value)}" style="color:#1e3a5f;">{h.escape(value)}</a>'
    return h.escape(value)


def team_email(template: str, subject: str, what_this_is: str, action: str,
               details: list[tuple[str, str]], greeting: str | None = None,
               extra: list[str] | None = None) -> ComposedEmail:
    """action and extra use the tiny markup (**bold**, "- " bullets); details are (label, value)."""
    rows = [(k, v) for k, v in details if v not in (None, "")]
    parts_html = [f'<div style="{WHAT_THIS_IS}">{markup._inline_html(what_this_is)}</div>']
    parts_text = [markup._inline_text(what_this_is)]
    if greeting:
        parts_html.append(markup.to_html(greeting))
        parts_text.append(greeting)
    parts_html.append(markup.to_html(action))
    parts_text.append(markup.to_text(action))
    if rows:
        trs = "".join(f'<tr><td style="{LABEL}">{h.escape(k)}</td><td style="{CELL}">{_value_html(str(v))}</td></tr>'
                      for k, v in rows)
        parts_html.append('<table role="presentation" cellpadding="0" cellspacing="0" '
                          f'style="width:100%;border-collapse:collapse;margin:0 0 16px 0;">{trs}</table>')
        parts_text.append("\n".join(f"{k}: {v}" for k, v in rows))
    for para in extra or []:
        parts_html.append(markup.to_html(para))
        parts_text.append(markup.to_text(para))
    return ComposedEmail(template, subject, _wrap_html("".join(parts_html), None, []),
                         "\n\n".join(parts_text), is_customer=False)
