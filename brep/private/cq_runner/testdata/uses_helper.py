# SPDX-License-Identifier: Apache-2.0
"""Imports sizes.py, which --path puts on the import path."""

import cadquery as cq
import sizes


def build(params):
    return cq.Workplane("XY").box(sizes.EDGE, sizes.EDGE, sizes.EDGE)
