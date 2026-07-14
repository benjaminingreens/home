import re

from markupsafe import escape

from core.text import split_title
from core.colors import colorize_meta

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


META_TITLE = re.compile(r"/([^;{}]+)")


def split_meta_title(meta):
    """Ark's own record syntax supports a `/title` metadata field (see
    `ark help`'s "Metadata symbols" section) - pull it out as the result
    card's title when present, and drop it from the meta shown
    underneath (it's already shown as the title, no need to repeat it)."""

    m = META_TITLE.search(meta)

    if not m:
        return None, meta

    title = m.group(1).strip()
    inner = meta[1:-1] if meta.startswith("{") and meta.endswith("}") else meta
    parts = [p.strip() for p in inner.split(";") if p.strip() and not p.strip().startswith("/")]
    remaining = "{" + "; ".join(parts) + "}" if parts else ""

    return title, remaining


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

        meta = strip_id(m.group(3) or "")
        meta_title, meta = split_meta_title(meta)

        if meta_title:
            title, preview = meta_title, m.group(2)
        else:
            title, preview = split_title(m.group(2))

        records.append({

            "type": m.group(1),

            "title": title,

            "preview": preview,

            "meta": meta,

            "path": m.group(4),

        })

    return records


def highlight_meta(line):
    """Ark stores records on disk as `type: text {meta};;` - reading a
    file shows that raw syntax verbatim, so wrap the trailing {meta}
    block's individual ;-separated items in their own colors (via
    colorize_meta - same per-item treatment as the result cards) instead
    of the whole block as one color. Falls back to a plain escaped line
    when there's no trailing {...} to highlight (e.g. plain text files,
    .arkrc)."""

    m = TRAILING_META.search(line)

    if not m:
        return escape(line)

    prefix = line[:m.start()]
    html = escape(prefix) + colorize_meta(m.group(1))

    if m.group(2):
        html += escape(m.group(2))

    return html
