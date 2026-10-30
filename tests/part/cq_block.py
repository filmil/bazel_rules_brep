# SPDX-License-Identifier: Apache-2.0
"""A block with a hole, in CadQuery: cad_part's CadQuery test part.

block.py is the same block in build123d; geometry_equal_test compares them.
"""

import cadquery as cq


def build(params):
    h = float(params.get("height", 6))
    return cq.Workplane("XY").box(10, 20, h).faces(">Z").workplane().hole(4)
