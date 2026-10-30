# SPDX-License-Identifier: Apache-2.0
"""A tray for the test board: 5 mm of room around it, and a boss under each
mounting hole, its top at z = 4.
"""

from build123d import Align, Box, Cylinder, Pos

HOLES = [(-20, -10), (20, -10), (-20, 10), (20, 10)]


def build(params):
    # A tray 60 x 40 inside, 2 mm walls and floor (floor top at z = 0), and a
    # 5 mm boss with a 2.5 mm hole under each mounting hole; boss tops at 4.
    a = (Align.CENTER, Align.CENTER, Align.MIN)
    tray = Pos(0, 0, -2) * Box(64, 44, 12, align=a) - Pos(0, 0, 0) * Box(60, 40, 12, align=a)
    for x, y in HOLES:
        tray += Pos(x, y, 0) * Cylinder(2.5, 4, align=a)
        tray -= Pos(x, y, 0) * Cylinder(1.25, 4, align=a)
    return tray
