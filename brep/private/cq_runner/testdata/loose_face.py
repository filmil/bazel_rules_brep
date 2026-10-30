# SPDX-License-Identifier: Apache-2.0
"""A compound of a solid and a face that is not part of it."""

import cadquery as cq


def build(params):
    box = cq.Solid.makeBox(1, 1, 1)
    face = cq.Face.makePlane(1, 1, basePnt=(5, 0, 0))
    return cq.Compound.makeCompound([box, face])
