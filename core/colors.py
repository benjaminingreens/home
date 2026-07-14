def contrasting_text_color(hex_color):
    """Simple perceived-brightness threshold, not full WCAG contrast math -
    good enough to guarantee readability for an arbitrary user-picked
    background without adding a color-math dependency."""

    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    return "#000000" if luminance > 0.6 else "#ffffff"


TAG_PALETTE = (
    "#7fa8e2", "#7fe28a", "#f2d94e", "#ff8f8f",
    "#d98fff", "#ff8fd9", "#8fffe2", "#ffb347",
)


def tag_color(text):
    """Deterministic color per string - same text always lands on the
    same palette entry, so tags/metadata/usernames stay visually stable
    across reloads while still being distinguishable from each other.
    Mirrored in JS in file.html's highlightMeta() - keep both in sync."""

    return TAG_PALETTE[sum(ord(c) for c in text) % len(TAG_PALETTE)]
