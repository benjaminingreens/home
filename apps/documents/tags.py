import re

from apps.ark.runner import run

TAG_RE = re.compile(r"#(\S+)")


def _tags_from_meta(meta):
    return sorted(set(TAG_RE.findall(meta)))


def _as_note(record, workspace):
    return {
        "content": record["text"],
        "tags": _tags_from_meta(record["meta"]),
        "path": record["path"],
        "workspace_id": workspace["id"],
        "workspace_label": workspace["label"],
    }


def scan_notes(workspaces):
    notes = []

    for ws in workspaces:
        records, _, _ = run(ws["path"], "note")
        notes.extend(_as_note(r, ws) for r in records)

    return notes


def list_tags(workspaces):
    tags = set()

    for note in scan_notes(workspaces):
        tags.update(note["tags"])

    return sorted(tags)


def notes_by_tags(workspaces, tags):
    if not tags:
        return scan_notes(workspaces)

    query = "note, " + ", ".join(f"-#{t}" for t in tags)
    notes = []

    for ws in workspaces:
        records, _, _ = run(ws["path"], query)
        notes.extend(_as_note(r, ws) for r in records)

    return notes
