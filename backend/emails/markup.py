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
