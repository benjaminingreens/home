import re

from apps.ark.runner import run
from core.text import split_title

TAG_RE = re.compile(r"#([^\s;]+)")

# One raw Ark record, as it's actually written to disk - "type: content
# {meta};;" on its own line. Matches both an untidied inbox.txt (mixed
# note/todo/evnt lines) and a compacted TYPE/yyyy/mm/ file (many records
# of the same type merged into one file).
RECORD_LINE = re.compile(r"^(note|todo|evnt):\s*(.*?)\s*(\{[^{}]*\})?\s*;;\s*$")


def _tags_from_meta(meta):
    return sorted(set(TAG_RE.findall(meta)))


def _normalize_path(path):
    """Ark's own query output always prefixes paths with "./"
    (e.g. "./note/2026/07/x.txt"); Path.relative_to() never does. Without
    normalizing, the seen_paths dedup silently never matched, so a file
    Ark's real "note" query had already parsed correctly got reprocessed
    by the raw-file fallback below too - which doesn't understand a
    tidied multi-line note's on-disk shape and mangled its title."""

    return path[2:] if path.startswith("./") else path


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


def _plain_txt_notes(ws, seen_paths):
    """Any .txt file anywhere in the workspace (inbox.txt at the root, a
    stray file in todo/evnt, a nested folder someone made up) that isn't
    already one of Ark's own note/ records. Surfaced so nothing written
    to the workspace is invisible in Documents just because it hasn't
    been tidied or doesn't live under note/.

    A file like this can hold several distinct records on their own
    lines (an untidied inbox.txt, or a compacted TYPE/yyyy/mm/ file) -
    those get pulled out individually. Only if the file has no
    note:/todo:/evnt: records at all is it treated as one freeform note,
    first line as title - otherwise one record's line could end up
    shown as the "title" for a completely unrelated record that just
    happened to share the same file."""

    if not ws["path"].is_dir():
        return []

    notes = []

    for f in sorted(ws["path"].rglob("*.txt")):
        if not f.is_file():
            continue

        relpath = str(f.relative_to(ws["path"]))

        if relpath in seen_paths:
            continue

        content = f.read_text(encoding="utf-8", errors="replace")
        matches = [RECORD_LINE.match(line.strip()) for line in content.splitlines()]
        matches = [m for m in matches if m]

        if not matches:
            title, preview = split_title(content)

            notes.append(_as_note(
                {"title": title, "preview": preview, "meta": content, "display_meta": "", "path": relpath},
                ws,
            ))
            continue

        for m in matches:
            if m.group(1) != "note":
                continue

            notes.append(_as_note(
                {"title": None, "preview": m.group(2), "meta": m.group(3) or "", "path": relpath},
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
        notes.extend(_plain_txt_notes(ws, {_normalize_path(r["path"]) for r in records}))

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

        all_records, _, _ = run(ws["path"], "note")
        records, _, _ = run(ws["path"], query)
        notes.extend(_as_note(r, ws) for r in records)

        for note in _plain_txt_notes(ws, {_normalize_path(r["path"]) for r in all_records}):
            if all(t in note["tags"] for t in tags):
                notes.append(note)

    return notes
