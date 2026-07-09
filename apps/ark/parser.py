import re

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

        records.append({

            "type": m.group(1),

            "text": m.group(2),

            "meta": strip_id(m.group(3) or ""),

            "path": m.group(4),

        })

    return records
