"""
One layout for every team email (never customers). Team members only need the data and what
to do with it, so each one reads the same short way:

  1. Optional greeting.
  2. One plain sentence with the customer and what happened.
  3. The facts, one labeled line each (phone numbers formatted).
  4. Optional list of items (a table with headers in HTML, one small block each in plain text).
  5. "What to do" (or "nothing unless" for FYI emails), then any extra paragraphs.
  6. Links last, each with a label: in plain text the label on one line and the address on the next.
"""
import html as h
import re
from urllib.parse import urlparse

from backend.emails import markup
from backend.emails.compose import ComposedEmail, _wrap_html

CELL = "padding:6px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top;font-size:14px;line-height:20px;"
LABEL = CELL + "color:#6b7280;white-space:nowrap;width:1%;"
LINK = "color:#003C58;font-weight:bold;text-decoration:underline;"

_LINK_LABELS = {"JobNimbus": "Open the job in JobNimbus", "Scheduler": "Open the Scheduler"}


def format_phone(value: str) -> str:
    """3174406606 or +1 317-440-6606 -> (317) 440-6606. Anything else is left alone."""
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}" if len(digits) == 10 else value


def person(name: str) -> str:
    """JobNimbus often has "Mcclellan"; staff emails read better as "McClellan"."""
    return re.sub(r"\bMc([a-z]{2,})\b", lambda m: "Mc" + m.group(1).capitalize(), name or "")


def _is_link(value: str) -> bool:
    return str(value).startswith(("http://", "https://"))


def _link_label(label: str, url: str) -> str:
    if label in _LINK_LABELS:
        return _LINK_LABELS[label]
    host = urlparse(url).netloc
    host = host[4:] if host.startswith("www.") else host
    return f"{label}: {host}" if label.startswith("Source") and host else (host or "Open link")


def team_email(template: str, subject: str, lead: str, action: str,
               details: list[tuple[str, str]], greeting: str | None = None,
               extra: list[str] | None = None,
               items: tuple[list[str], list[list[str]]] | None = None) -> ComposedEmail:
    """lead, action and extra use the tiny markup (**bold**, "- " / "1. " lists); details are (label, value).

    Order: greeting, one sentence on what happened, the facts (one per line), an optional list of items
    (columns, rows), then what to do. Links are labeled, never a bare address in a sentence."""
    rows = [(k, v) for k, v in details if v not in (None, "")]
    rows = [(k, format_phone(str(v)) if "phone" in k.lower() else str(v)) for k, v in rows]
    facts = [(k, v) for k, v in rows if not _is_link(v)]
    links = [(_link_label(k, v), v) for k, v in rows if _is_link(v)]
    parts_html, parts_text = [], []

    def para(text):
        if text:
            parts_html.append(markup.to_html(text))
            parts_text.append(markup.to_text(text))

    para(greeting)
    para(lead)
    if facts:
        trs = "".join(f'<tr><td style="{LABEL}">{h.escape(k)}</td><td style="{CELL}">{h.escape(v)}</td></tr>'
                      for k, v in facts)
        parts_html.append('<table role="presentation" cellpadding="0" cellspacing="0" '
                          f'style="width:100%;border-collapse:collapse;margin:0 0 16px 0;">{trs}</table>')
        parts_text.append("\n".join(f"{k}: {v}" for k, v in facts))
    if items and items[1]:
        parts_html.append(markup.table_html(*items))
        parts_text.append(markup.blocks_text(*items))
    para(action)
    for para_ in extra or []:
        para(para_)
    for label, url in links:
        parts_html.append(f'<p style="margin:0 0 16px 0;"><a href="{h.escape(url)}" style="{LINK}">{h.escape(label)}</a></p>')
        parts_text.append(f"{label}\n{url}")
    return ComposedEmail(template, subject, _wrap_html("".join(parts_html), None, []),
                         "\n\n".join(parts_text), is_customer=False)
