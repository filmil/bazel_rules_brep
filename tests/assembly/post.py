# SPDX-License-Identifier: Apache-2.0
"""A post that stands on the plate: cad_assembly's test part."""

from build123d import Cylinder, Pos


def build(params):
    return Pos(0, 0, 10) * Cylinder(3, 20)
