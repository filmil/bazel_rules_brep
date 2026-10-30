# SPDX-License-Identifier: Apache-2.0
"""A cylinder, as a Shape rather than a Workplane."""

import cadquery as cq


def build(params):
    return cq.Solid.makeCylinder(float(params.get("r", 1)), 2)
