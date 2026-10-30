# SPDX-License-Identifier: Apache-2.0
"""A 1 x 2 x 3 box, as a Workplane."""

import cadquery as cq


def build(params):
    return cq.Workplane("XY").box(1, 2, 3)
