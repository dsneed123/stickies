"""Size-aware grid: notes span one or more cells of a base unit. Pure geometry."""

import math

DEFAULT_UNIT = (236, 248)      # a fresh note's window size = one cell
MIN_UNIT_H = 150               # header + a couple of lines + footer


class SpanGrid:
    """A grid of ``cols`` columns of unit cells inside ``area``; rows grow as
    needed. Each note takes a whole number of cells in each direction so the
    layout lines up, yet big notes stay big and small ones stay small."""

    def __init__(self, area, gap=16, unit=DEFAULT_UNIT):
        self.ax, self.ay, self.aw, self.ah = area
        self.gap = gap
        self.cols = max(1, (self.aw + gap) // (unit[0] + gap))
        self.unit_w = (self.aw - (self.cols - 1) * gap) // self.cols   # stretch to fill
        self.unit_h = unit[1]
        self.hint_h = unit[1]

    def span(self, w, h):
        """(cols, rows) a window of this size should occupy."""
        sw = round((w + self.gap) / (self.unit_w + self.gap))
        sh = round((h + self.gap) / (self.hint_h + self.gap))
        return max(1, min(self.cols, sw)), max(1, sh)

    def cell_at(self, point, span):
        """Nearest (col, row) for a window of ``span`` whose top-left is at ``point``."""
        px, py = point
        col = round((px - self.ax) / (self.unit_w + self.gap))
        row = round((py - self.ay) / (self.unit_h + self.gap))
        return max(0, min(self.cols - span[0], col)), max(0, row)

    def pack(self, items, pinned=None):
        """Place ``items`` - (key, w, h) in order - first-fit into the grid.
        ``pinned`` maps a key to the (col, row) it must take. Returns
        {key: (x, y, w, h)}; if the rows overflow the area, rows are squeezed
        (every note shrinks in height) so the whole block fits."""
        pinned = pinned or {}
        taken = set()
        cells = {}

        def free(col, row, sw, sh):
            return all((c, r) not in taken for c in range(col, col + sw) for r in range(row, row + sh))

        def take(key, col, row, sw, sh):
            taken.update((c, r) for c in range(col, col + sw) for r in range(row, row + sh))
            cells[key] = (col, row, sw, sh)

        def fill(spans):
            taken.clear()
            cells.clear()
            for key, (col, row) in pinned.items():
                if key in spans:
                    take(key, col, row, *spans[key])
            for key, _w, _h in items:
                if key in cells:
                    continue
                sw, sh = spans[key]
                row = 0
                while key not in cells:
                    for col in range(0, self.cols - sw + 1):
                        if free(col, row, sw, sh):
                            take(key, col, row, sw, sh)
                            break
                    row += 1
            return max((r + sh for _c, r, _sw, sh in cells.values()), default=1)

        def height_for(rows):
            return rows * (self.unit_h + self.gap) - self.gap

        def squeezed(rows):
            return (self.ah - (rows - 1) * self.gap) // rows

        spans = {key: self.span(w, h) for key, w, h in items}
        rows = fill(spans)
        comfy = MIN_UNIT_H
        if squeezed(rows) < comfy and any(sh > 1 for _sw, sh in spans.values()):
            # rows would get cramped: flatten every note to one row first
            rows = fill({k: (sw, 1) for k, (sw, _sh) in spans.items()})
        unit_h = self.unit_h
        if height_for(rows) > self.ah:
            unit_h = max(MIN_UNIT_H, squeezed(rows))
        placed = {}
        for key, (col, row, sw, sh) in cells.items():
            placed[key] = (
                self.ax + col * (self.unit_w + self.gap),
                self.ay + row * (unit_h + self.gap),
                sw * self.unit_w + (sw - 1) * self.gap,
                sh * unit_h + (sh - 1) * self.gap,
            )
        return placed

    @staticmethod
    def reading_order(placed):
        return sorted(placed, key=lambda k: (placed[k][1], placed[k][0]))
