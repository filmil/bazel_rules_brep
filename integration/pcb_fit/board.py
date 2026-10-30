# SPDX-License-Identifier: Apache-2.0
"""A 50 x 30 x 1.6 mm test board with four mounting holes: pcb_fit_test's board.

It stands in for a board STEP from kicad_step.
"""

from build123d import Axis, Box, Cylinder, Pos, fillet

HOLES = [(-20, -10), (20, -10), (-20, 10), (20, 10)]


def build(params):
    # A 50 x 30 x 1.6 mm board, bottom at z = 0, rounded corners, four
    # 3.2 mm mounting holes.
    board = Pos(0, 0, 0.8) * Box(50, 30, 1.6)
    board = fillet(board.edges().filter_by(Axis.Z), 2)
    for x, y in HOLES:
        board -= Pos(x, y, 0.8) * Cylinder(1.6, 4)
    return board
