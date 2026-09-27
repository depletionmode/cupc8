#!/usr/bin/env python3
"""DC sheet-resistance sensitivity of the saved main-board In1 GND fill.

This finite-difference mesh solves the current spreading from a routed GND
via to the USB-C connector's GND pads. Only In1 copper is represented. It
omits barrel/contact resistance, pad thermal spokes, and the F/B GND pours;
the result is a sensitivity estimate, not a sign-off value. Two grid pitches
expose discretization error. Other GND layers would add parallel paths.
"""

from collections import deque
import math
import sys

import numpy as np
import pcbnew

from main_ground_raster import J1_GND


CASES = (
    ("buck U3 return", (38.3, 160.0), (5.0, 45.0, 150.0, 188.0)),
    ("far slot J11 return", (23.0, 29.0), (0.0, 45.0, 20.0, 188.0)),
)


def resistance(board, source, region, pitch):
    zones = board.Zones()
    ground = [zones[i] for i in range(len(zones))
              if zones[i].GetNetname() == "/GND" and zones[i].GetLayer() == pcbnew.In1_Cu]
    if len(ground) != 1 or not ground[0].IsFilled():
        raise ValueError("one saved, filled In1 GND zone is required")
    tracks = board.Tracks()
    if not any(tracks[i].GetClass() == "PCB_VIA" and tracks[i].GetNetname() == "/GND" and
               math.dist(tuple(pcbnew.ToMM(v) for v in
                               (tracks[i].GetPosition().x, tracks[i].GetPosition().y)), source) < 0.01
               for i in range(len(tracks))):
        raise ValueError("expected GND via absent at %s" % (source,))
    xmin, xmax, ymin, ymax = region
    cols = round((xmax - xmin) / pitch) + 1
    rows = round((ymax - ymin) / pitch) + 1
    filled = np.zeros((rows, cols), dtype=bool)
    for y in range(rows):
        for x in range(cols):
            at = pcbnew.VECTOR2I(pcbnew.FromMM(xmin + x * pitch),
                                 pcbnew.FromMM(ymin + y * pitch))
            filled[y, x] = ground[0].HitTestFilledArea(pcbnew.In1_Cu, at)

    def cells(center, radius):
        selected = np.zeros_like(filled)
        x, y = center
        for row in range(max(0, int((y - radius - ymin) / pitch)),
                         min(rows, int((y + radius - ymin) / pitch) + 2)):
            for col in range(max(0, int((x - radius - xmin) / pitch)),
                             min(cols, int((x + radius - xmin) / pitch) + 2)):
                if filled[row, col] and math.hypot(xmin + col * pitch - x,
                                                   ymin + row * pitch - y) < radius:
                    selected[row, col] = True
        return selected

    injection = cells(source, 0.6)
    sink = np.zeros_like(filled)
    for pad in J1_GND:
        sink |= cells(pad, 0.9)
    if not injection.any() or not sink.any():
        raise ValueError("GND source or connector pad has no represented copper")

    # Keep only the connected component of the source. Otherwise the sparse
    # Laplacian has singular floating islands.
    component = np.zeros_like(filled)
    pending = deque(zip(*np.where(injection)))
    component[injection] = True
    while pending:
        row, col = pending.popleft()
        for nr, nc in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
            if (0 <= nr < rows and 0 <= nc < cols and filled[nr, nc] and
                    not component[nr, nc]):
                component[nr, nc] = True
                pending.append((nr, nc))
    if not (component & sink).any():
        raise ValueError("In1 fill does not connect GND source to J1")
    active = component & ~sink
    right = component[:, :-1] & component[:, 1:]
    down = component[:-1, :] & component[1:, :]
    degree = np.zeros((rows, cols), dtype=float)
    degree[:, :-1] += right
    degree[:, 1:] += right
    degree[:-1, :] += down
    degree[1:, :] += down

    def product(voltage):
        result = degree * voltage
        result[:, :-1] -= right * voltage[:, 1:]
        result[:, 1:] -= right * voltage[:, :-1]
        result[:-1, :] -= down * voltage[1:, :]
        result[1:, :] -= down * voltage[:-1, :]
        result[~active] = 0
        return result

    rhs = np.zeros_like(degree)
    rhs[injection] = 1 / injection.sum()  # total of one ampere
    voltage = np.zeros_like(rhs)
    residual = rhs.copy()
    direction = residual / np.maximum(degree, 1)
    direction[~active] = 0
    rz = np.sum(residual * direction)
    for iteration in range(10000):
        ad = product(direction)
        denominator = np.sum(direction * ad)
        if denominator <= 0:
            raise ValueError("nonpositive GND mesh")
        alpha = rz / denominator
        voltage += alpha * direction
        residual -= alpha * ad
        if np.linalg.norm(residual) < 1e-9:
            break
        preconditioned = residual / np.maximum(degree, 1)
        preconditioned[~active] = 0
        next_rz = np.sum(residual * preconditioned)
        direction = preconditioned + next_rz / rz * direction
        rz = next_rz
    else:
        raise ValueError("GND mesh solve did not converge")
    rho_100 = 17e-6 * (1 + 0.00393 * 80)
    thickness = 0.0174 * 0.9
    return 1000 * voltage[injection].mean() * rho_100 / thickness, iteration + 1


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "build/hw/main/main.kicad_pcb"
    board = pcbnew.LoadBoard(path)
    for name, source, region in CASES:
        coarse, coarse_iterations = resistance(board, source, region, 0.5)
        fine, fine_iterations = resistance(board, source, region, 0.25)
        error = abs(fine - coarse) / max(fine, coarse)
        print("%s: In1 100 C/90%%-thickness mesh %.3f/%.3f mOhm "
              "(0.5/0.25 mm; %.1f%% disagreement; %d/%d iterations)" %
              (name, coarse, fine, 100 * error, coarse_iterations, fine_iterations))
        if error > 0.1:
            raise SystemExit("FAIL GND mesh pitch disagreement >10%")
    print("SENSITIVITY ONLY: pad/via contacts, other layers and temperature coupling open")


if __name__ == "__main__":
    main()
