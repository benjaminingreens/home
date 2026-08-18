import re

from core.text import split_title

RECORD = re.compile(
    r"^(note|todo|evnt):\s*(.*?)\s*(?:({.*?})\s*)?\[(.*?)\]$"
)


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
