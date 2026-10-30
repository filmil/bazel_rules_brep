# SPDX-License-Identifier: Apache-2.0
"""A base plate: cad_assembly's test part."""

from build123d import Box, Pos


def build(params):
    return Pos(0, 0, 1) * Box(60, 30, 2)
