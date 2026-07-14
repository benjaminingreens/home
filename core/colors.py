def contrasting_text_color(hex_color):
    """Simple perceived-brightness threshold, not full WCAG contrast math -
    good enough to guarantee readability for an arbitrary user-picked
    background without adding a color-math dependency."""

    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255

    return "#000000" if luminance > 0.6 else "#ffffff"
