# SPDX-License-Identifier: Apache-2.0
"""A stepped block with a round hole: cad_render's test part.

It differs in every view: two steps from the front, a hole from the top.
"""

from build123d import Box, Cylinder, Pos


def build(params):
    low = Pos(15, 10, 5) * Box(30, 20, 10)
    high = Pos(5, 10, 15) * Box(10, 20, 10)
    hole = Pos(22, 10, 5) * Cylinder(4, 20)
    return low + high - hole
