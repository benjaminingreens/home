import re

from apps.ark.runner import run

TAG_RE = re.compile(r"#([^\s;]+)")


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


def _root_txt_notes(ws):
    """.txt files sitting directly at the workspace root (siblings of
    note/todo/evnt - e.g. an untidied inbox.txt, or anything else someone
    drops there) aren't Ark records the query engine knows about. Surface
    them too rather than hiding anything that isn't already tidied."""

    if not ws["path"].is_dir():
        return []

    notes = []

    for f in sorted(ws["path"].glob("*.txt")):
        if not f.is_file():
            continue

        content = f.read_text(encoding="utf-8", errors="replace")
        preview = content.strip().splitlines()[0] if content.strip() else f.name

        notes.append(_as_note({"text": preview, "meta": content, "path": f.name}, ws))

    return notes


def scan_notes(workspaces):
    notes = []

    for ws in workspaces:
        records, _, _ = run(ws["path"], "note")
        notes.extend(_as_note(r, ws) for r in records)
        notes.extend(_root_txt_notes(ws))

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

        for note in _root_txt_notes(ws):
            if all(t in note["tags"] for t in tags):
                notes.append(note)

    return notes
