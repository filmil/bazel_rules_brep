# SPDX-License-Identifier: Apache-2.0
"""Two unit cubes, apart: a Workplane that holds two solids."""

import cadquery as cq


def build(params):
    return cq.Workplane("XY").pushPoints([(0, 0), (5, 0)]).box(1, 1, 1)
