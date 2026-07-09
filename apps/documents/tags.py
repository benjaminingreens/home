import re

from apps.ark.runner import run

TAG_RE = re.compile(r"#(\S+)")


def _tags_from_meta(meta):
    return sorted(set(TAG_RE.findall(meta)))


def _as_note(record):
    return {
        "content": record["text"],
        "tags": _tags_from_meta(record["meta"]),
        "path": record["path"],
    }


def scan_notes(workspace):
    records, _, _ = run(workspace, "note")
    return [_as_note(r) for r in records]


def list_tags(workspace):
    tags = set()

    for note in scan_notes(workspace):
        tags.update(note["tags"])

    return sorted(tags)


def notes_by_tags(workspace, tags):
    if not tags:
        return scan_notes(workspace)

    query = "note, " + ", ".join(f"-#{t}" for t in tags)
    records, _, _ = run(workspace, query)

    return [_as_note(r) for r in records]
