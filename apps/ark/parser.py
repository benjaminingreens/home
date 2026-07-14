import re

from markupsafe import Markup, escape

from core.text import split_title

RECORD = re.compile(
    r"^(note|todo|evnt):\s*(.*?)\s*(?:({.*?})\s*)?\[(.*?)\]$"
)

TRAILING_META = re.compile(r"(\{[^{}]*\})(;;)?\s*$")


def strip_id(meta):
    if not meta:
        return meta

    cleaned = re.sub(r"&[^;{}]*;?", "", meta)
    cleaned = re.sub(r";\s*;", ";", cleaned)
    cleaned = re.sub(r";\s*}", "}", cleaned)
    cleaned = re.sub(r"{\s*;\s*", "{", cleaned)

    return cleaned


def parse(stdout):

    records = []

    for line in stdout.splitlines():

        line = line.strip()

        if (
            not line
            or line.startswith("scanning")
        ):
            continue

        m = RECORD.match(line)

        if not m:
            continue

        title, preview = split_title(m.group(2))

        records.append({

            "type": m.group(1),

            "title": title,

            "preview": preview,

            "meta": strip_id(m.group(3) or ""),

            "path": m.group(4),

        })

    return records


def highlight_meta(line):
    """Ark stores records on disk as `type: text {meta};;` - reading a
    file shows that raw syntax verbatim, so wrap the trailing {meta}
    block in a styled span to visually separate the bookkeeping from the
    actual note content. Falls back to a plain escaped line when there's
    no trailing {...} to highlight (e.g. plain text files, .arkrc)."""

    m = TRAILING_META.search(line)

    if not m:
        return escape(line)

    prefix = line[:m.start()]
    html = escape(prefix)
    html += Markup('<span class="line-meta">') + escape(m.group(1)) + Markup("</span>")

    if m.group(2):
        html += escape(m.group(2))

    return html
