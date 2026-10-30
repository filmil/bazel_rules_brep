# SPDX-License-Identifier: Apache-2.0
"""A block with a hole, in build123d: cq_block.py's twin."""

from build123d import Box, Cylinder


def build(params):
    h = float(params.get("height", 6))
    return Box(10, 20, h) - Cylinder(2, h)
