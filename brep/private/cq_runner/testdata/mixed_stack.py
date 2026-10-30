# SPDX-License-Identifier: Apache-2.0
"""A Workplane that holds a solid and a vector."""

import cadquery as cq


def build(params):
    return cq.Workplane("XY").box(1, 1, 1).add(cq.Vector(1, 2, 3))
