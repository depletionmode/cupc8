#!/usr/bin/env python3
"""Sensitivity scan of the main board's saved In1 GND fill.

The scan samples KiCad's actual filled zone at two grid pitches, erodes the
binary mask by a fixed corridor radius, and seeks a cardinal route from the
U3 GND via to a J1 GND pad. A raster path is evidence of available copper,
not a certified resistance bound: cell corners, thermal spokes, connector
contact and the other GND layers are not resolved.
"""

from collections import deque
import math
import sys

import numpy as np
import pcbnew


REGION = (5.0, 45.0, 150.0, 188.0)
J1_GND = ((34.33, 181.71), (34.33, 185.89), (25.67, 185.89),
          (25.67, 181.71), (26.8, 180.95), (33.2, 180.95))
U3_GND_VIA = (38.3, 160.0)


def scan(board, pitch, corridor):
    zones = board.Zones()
    ground = [zones[i] for i in range(len(zones))
              if zones[i].GetNetname() == "/GND" and zones[i].GetLayer() == pcbnew.In1_Cu]
    if len(ground) != 1 or not ground[0].IsFilled():
        raise ValueError("one saved, filled In1 GND zone is required")
    zone = ground[0]
    xmin, xmax, ymin, ymax = REGION
    cols = round((xmax - xmin) / pitch) + 1
    rows = round((ymax - ymin) / pitch) + 1

    def xy(index):
        return xmin + index % cols * pitch, ymin + index // cols * pitch

    filled = np.zeros((rows, cols), dtype=bool)
    for y in range(rows):
        for x in range(cols):
            at = pcbnew.VECTOR2I(pcbnew.FromMM(xmin + x * pitch),
                                 pcbnew.FromMM(ymin + y * pitch))
            filled[y, x] = zone.HitTestFilledArea(pcbnew.In1_Cu, at)
    safe = filled.copy()
    radius = corridor / 2
    reach = math.ceil(radius / pitch)
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            if (dx == dy == 0 or math.hypot(dx * pitch, dy * pitch) > radius + 1e-9):
                continue
            shifted = np.zeros_like(filled)
            y0, y1 = max(0, dy), min(rows, rows + dy)
            x0, x1 = max(0, dx), min(cols, cols + dx)
            shifted[y0:y1, x0:x1] = filled[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
            safe &= shifted
    cells = safe.ravel()
    starts = [i for i in range(len(cells)) if cells[i] and
              math.dist(xy(i), U3_GND_VIA) < 0.9]
    targets = {i for i in range(len(cells)) if cells[i] and
               any(math.dist(xy(i), pad) < 0.9 for pad in J1_GND)}
    if not starts or not targets:
        return None
    todo = deque(starts)
    distance = {i: 0 for i in starts}
    while todo:
        i = todo.popleft()
        if i in targets:
            return distance[i] * pitch
        for j in (i - 1, i + 1, i - cols, i + cols):
            if (j < 0 or j >= len(cells) or
                    (j in (i - 1, i + 1) and j // cols != i // cols) or
                    not cells[j] or j in distance):
                continue
            distance[j] = distance[i] + 1
            todo.append(j)
    return None


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "build/hw/main/main.kicad_pcb"
    board = pcbnew.LoadBoard(path)
    rho_100 = 17e-6 * (1 + 0.00393 * 80)
    thickness = 0.0174 * 0.9
    for corridor in (0.5, 1.0, 2.0):
        lengths = [scan(board, pitch, corridor) for pitch in (0.5, 0.25)]
        if any(length is None for length in lengths):
            print("In1 GND %.1f mm corridor: no U3-to-J1 path at both pitches" % corridor)
            continue
        worst = max(lengths)
        milliohms = 1000 * rho_100 * worst / (corridor * thickness)
        print("In1 GND %.1f mm corridor: %.2f / %.2f mm at 0.5 / 0.25 mm pitch; "
              "%.2f mOhm 100 C strip sensitivity (via/contact excluded)" %
              (corridor, *lengths, milliohms))


if __name__ == "__main__":
    main()
