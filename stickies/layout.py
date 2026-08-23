"""Pack sticky notes into rows across the screen. Pure geometry, no GTK."""


def arrange_grid(boxes, area, gap=16, by_size=False):
    """Lay ``boxes`` - (key, width, height) - into left-to-right rows inside
    ``area`` (x, y, width, height), ``gap`` pixels apart. Returns {key: (x, y)}.

    Rows wrap when the next box would overflow the area's right edge; a row is
    as tall as its tallest box, so equal-sized notes form a true grid and mixed
    sizes still line up along the top of each row. With ``by_size`` the boxes
    are sorted tallest-first so rows waste less space. Anything that does not
    fit vertically is clamped to the bottom edge rather than pushed off-screen.
    """
    ax, ay, aw, ah = area
    ordered = sorted(boxes, key=lambda b: (-b[2], -b[1])) if by_size else list(boxes)
    placed = {}
    x, y, row_h = ax, ay, 0
    for key, w, h in ordered:
        if x > ax and x + w > ax + aw:           # wrap; never wrap the first in a row
            x, y, row_h = ax, y + row_h + gap, 0
        placed[key] = (x, y)
        x += w + gap
        row_h = max(row_h, h)
    bottom = ay + ah
    for key, (px, py) in placed.items():
        h = next(b[2] for b in ordered if b[0] == key)
        placed[key] = (max(ax, min(px, ax + aw - 1)), max(ay, min(py, bottom - h)))
    return placed
