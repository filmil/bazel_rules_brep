# SPDX-License-Identifier: Apache-2.0
"""A plate with a hole: geometry_equal_test's test part.

Moving the hole keeps the volume, the area and the box, and moves the
center of mass.
"""

from build123d import Box, Cylinder, Pos


def build(params):
    x = float(params.get("hole_x", 10))
    return Box(40, 20, 4) - Pos(x, 0, 0) * Cylinder(3, 8)
