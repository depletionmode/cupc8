"""Placement geometry in a top-view board frame, y up for supplier coordinates.

Bottom footprints reflect their local y coordinate before board rotation.
This is geometric consistency evidence; supplier preview and human CPL review
remain required. All callers must supply the actual physical assembly side.
"""
import math

def bottom(side):
    if side not in ('Top', 'Bottom'):
        raise ValueError('assembly side must be Top or Bottom')
    return side == 'Bottom'

def finite(*values):
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError('nonfinite assembly coordinate or angle')

def rotation(board_angle, correction, side):
    finite(board_angle, correction)
    return (board_angle - correction if bottom(side) else board_angle + correction) % 360

def midpoint(x, y_down, board_angle, offset, side):
    ox, oy_up = offset or (0.0, 0.0)
    finite(x, y_down, board_angle, ox, oy_up)
    if bottom(side):
        oy_up = -oy_up
    angle = math.radians(board_angle)
    return (x + ox*math.cos(angle) - oy_up*math.sin(angle),
            -y_down + ox*math.sin(angle) + oy_up*math.cos(angle))

def supplier_world(pads, angle, mid_x, mid_y_up, side):
    finite(angle, mid_x, mid_y_up)
    reflected = bottom(side)
    a = math.radians(angle)
    out = []
    for number, x, y in pads:
        finite(x, y)
        if reflected:
            y = -y
        out.append((str(number), mid_x + x*math.cos(a) - y*math.sin(a),
                    mid_y_up + x*math.sin(a) + y*math.cos(a)))
    return out
