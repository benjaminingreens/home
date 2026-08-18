from markupsafe import Markup, escape


def _hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def _rgb_to_hex(rgb):
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in rgb)


def mix(hex_a, hex_b, t):
    """Linear-interpolate between two hex colors - t=0 is hex_a, t=1 is
    hex_b."""

    a, b = _hex_to_rgb(hex_a), _hex_to_rgb(hex_b)
    return _rgb_to_hex(a[i] + (b[i] - a[i]) * t for i in range(3))


def contrasting_text_color(hex_color):
    """Simple perceived-brightness threshold, not full WCAG contrast math -
    good enough to guarantee readability for an arbitrary user-picked
    background without adding a color-math dependency."""

    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    return "#000000" if luminance > 0.6 else "#ffffff"


def theme_colors(bg_hex):
    """Every text tier the CSS needs, all derived from the user's chosen
    background rather than fixed grays - fixed grays only look right
    against the one background they were originally tuned for (black);
    mixing toward whatever background is actually in use keeps secondary/
    faint text readable (and borders visible) regardless of what the user
    picks."""

    fg = contrasting_text_color(bg_hex)

    return {
        "fg": fg,
        "fg_muted": mix(fg, bg_hex, 0.35),
        "fg_faint": mix(fg, bg_hex, 0.65),
        "border": mix(fg, bg_hex, 0.85),
    }


TAG_PALETTE = (
    "#7fa8e2", "#7fe28a", "#f2d94e", "#ff8f8f",
    "#d98fff", "#ff8fd9", "#8fffe2", "#ffb347",
)


def tag_color(text):
    """Deterministic color per string - same text always lands on the
    same palette entry, so tags/metadata/usernames stay visually stable
    across reloads while still being distinguishable from each other."""

    return TAG_PALETTE[sum(ord(c) for c in text) % len(TAG_PALETTE)]


META_COLOR = "#f2d94e"


def colorize_meta(text):
    """Split a semicolon-separated {meta} blob and color just the actual
    metadata items - not the {}/; punctuation around them - one single
    consistent color, not a different color per item. Used everywhere a
    {meta} block is shown: result cards and the file editor's inline
    view of the raw record text."""

    if not text:
        return Markup("")

    parts = [p.strip() for p in text.strip("{}").split(";") if p.strip()]

    if not parts:
        return escape(text)

    spans = [
        Markup('<span style="color: {}">').format(META_COLOR) + escape(p) + Markup("</span>")
        for p in parts
    ]

    return Markup("{") + Markup("; ").join(spans) + Markup("}")
