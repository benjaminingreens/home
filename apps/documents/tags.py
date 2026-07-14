import re

from apps.ark.runner import run
from core.text import split_title

TAG_RE = re.compile(r"#([^\s;]+)")


def _tags_from_meta(meta):
    return sorted(set(TAG_RE.findall(meta)))


def _as_note(record, workspace):
    """`record["meta"]` doubles as the tag-scan source (needs the full
    raw text, e.g. an entire file's contents for root .txt notes) and
    `display_meta` is what actually renders in the card - short bracket
    metadata for real Ark records, blank for plain files where there's no
    such thing."""

    return {
        "type": record.get("type", "note"),
        "title": record["title"],
        "preview": record["preview"],
        "tags": _tags_from_meta(record["meta"]),
        "path": record["path"],
        "meta": record.get("display_meta", record["meta"]),
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
        title, preview = split_title(content)

        notes.append(_as_note(
            {"title": title, "preview": preview, "meta": content, "display_meta": "", "path": f.name},
            ws,
        ))

    return notes


def scan_notes(workspaces):
    notes = []

    for ws in workspaces:
        if not ws["path"].is_dir():
            # A workspace can have a DB record (e.g. just switched into via
            # the group dropdown) before anyone has set it up through Ark,
            # so its directory may not exist on disk yet - nothing to scan.
            continue

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
        if not ws["path"].is_dir():
            continue

        records, _, _ = run(ws["path"], query)
        notes.extend(_as_note(r, ws) for r in records)

        for note in _root_txt_notes(ws):
            if all(t in note["tags"] for t in tags):
                notes.append(note)

    return notes
