def split_title(text):
    """First line as a bold title only when there's more than one
    non-blank line - true for multi-line file-backed notes, always
    False for Ark's own note:/todo:/evnt: records (one line per record
    by format, so this naturally falls through to "no title" for them)."""

    lines = [l for l in (text or "").splitlines() if l.strip()]

    if not lines:
        return None, None

    if len(lines) == 1:
        return None, lines[0]

    return lines[0], "\n".join(lines[1:]).strip()
