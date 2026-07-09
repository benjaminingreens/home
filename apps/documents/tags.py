import re

RECORD_RE = re.compile(r"(?:^|\n)\s*note\s*:\s*(.*?);;", re.S)
META_RE = re.compile(r"\{([^{}]*)\}", re.S)


def _parse_notes(path, text):
    notes = []

    for m in RECORD_RE.finditer(text):
        body = m.group(1)

        meta_raw = ""
        content = body

        meta_match = META_RE.search(body)
        if meta_match:
            meta_raw = meta_match.group(1)
            content = body[:meta_match.start()] + body[meta_match.end():]

        tags = sorted({
            tok.strip()[1:]
            for tok in meta_raw.split(";")
            if tok.strip().startswith("#")
        })

        notes.append({
            "content": content.strip(),
            "tags": tags,
            "path": str(path),
        })

    return notes


def scan_notes(workspace):
    notes = []

    note_dir = workspace / "note"
    if not note_dir.is_dir():
        return notes

    for path in sorted(note_dir.rglob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        notes.extend(_parse_notes(path.relative_to(workspace), text))

    return notes


def list_tags(workspace):
    tags = set()

    for note in scan_notes(workspace):
        tags.update(note["tags"])

    return sorted(tags)


def notes_by_tags(workspace, tags):
    tags = set(tags)
    notes = scan_notes(workspace)

    if not tags:
        return notes

    return [n for n in notes if tags.issubset(set(n["tags"]))]
