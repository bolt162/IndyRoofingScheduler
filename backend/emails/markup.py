"""
Tiny markup used by copy.py, rendered to HTML and plain text.

Blocks are separated by a blank line.
  - A block whose lines all start with "- " is a bullet list.
  - A block whose lines all start with "1. ", "2. " ... is a numbered list.
  - Anything else is a paragraph.
**bold** works inside any block.
"""
import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_NUMBERED = re.compile(r"^\d+\.\s")


def _blocks(text: str) -> list[str]:
    return [b.strip() for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]


def _inline_html(text: str) -> str:
    return _BOLD.sub(r"<strong>\1</strong>", html.escape(text, quote=False))


def _inline_text(text: str) -> str:
    return _BOLD.sub(r"\1", text)


def _kind(lines: list[str]) -> str:
    if all(l.startswith("- ") for l in lines):
        return "ul"
    if all(_NUMBERED.match(l) for l in lines):
        return "ol"
    return "p"


P_STYLE = "margin:0 0 16px 0;"
LIST_STYLE = "margin:0 0 16px 0;padding-left:24px;"
LI_STYLE = "margin:0 0 8px 0;"


def to_html(text: str) -> str:
    out = []
    for block in _blocks(text):
        lines = [l.strip() for l in block.splitlines()]
        kind = _kind(lines)
        if kind == "p":
            out.append(f'<p style="{P_STYLE}">{_inline_html(" ".join(lines))}</p>')
        else:
            strip = (lambda l: l[2:]) if kind == "ul" else (lambda l: _NUMBERED.sub("", l, count=1))
            items = "".join(f'<li style="{LI_STYLE}">{_inline_html(strip(l))}</li>' for l in lines)
            out.append(f'<{kind} style="{LIST_STYLE}">{items}</{kind}>')
    return "\n".join(out)


def to_text(text: str) -> str:
    out = []
    for block in _blocks(text):
        lines = [l.strip() for l in block.splitlines()]
        kind = _kind(lines)
        if kind == "p":
            out.append(_inline_text(" ".join(lines)))
        else:
            out.append("\n".join(_inline_text(l) for l in lines))
    return "\n\n".join(out)


# --- Lists of items (customers, jobs): a real table in HTML, one small block each in plain text ---

_CELL = "padding:8px 10px;border-bottom:1px solid #e5e7eb;vertical-align:top;font-size:14px;line-height:20px;"
_HEAD = _CELL + "text-align:left;background:#f3f4f6;color:#003C58;font-weight:bold;"


def table_html(cols: list[str], rows: list[list[str]]) -> str:
    ths = "".join(f'<th style="{_HEAD}">{html.escape(c)}</th>' for c in cols)
    trs = "".join("<tr>" + "".join(f'<td style="{_CELL}">{html.escape(v or "")}</td>' for v in r) + "</tr>"
                  for r in rows)
    return ('<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="width:100%;border-collapse:collapse;margin:0 0 16px 0;"><tr>{ths}</tr>{trs}</table>')


def blocks_text(cols: list[str], rows: list[list[str]]) -> str:
    """First column on its own line, then the other columns as indented "Label: value" lines."""
    out = []
    for r in rows:
        lines = [r[0]] + [f"   {c}: {v}" for c, v in zip(cols[1:], r[1:]) if v]
        out.append("\n".join(lines))
    return "\n\n".join(out)
