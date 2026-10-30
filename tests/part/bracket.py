# SPDX-License-Identifier: Apache-2.0
"""An L-bracket with a hole in each leg: cad_part's test part."""

from build123d import Box, Cylinder, Pos, Rot

import dims


def build(params):
    t = float(params.get("thickness", 3))
    base = Pos(dims.LEG / 2, 0, t / 2) * Box(dims.LEG, dims.WIDTH, t)
    wall = Pos(t / 2, 0, dims.LEG / 2) * Box(t, dims.WIDTH, dims.LEG)
    hole_base = Pos(dims.LEG * 0.66, 0, t / 2) * Cylinder(dims.HOLE / 2, t * 2)
    hole_wall = Pos(t / 2, 0, dims.LEG * 0.66) * Rot(0, 90, 0) * Cylinder(dims.HOLE / 2, t * 2)
    return base + wall - hole_base - hole_wall
