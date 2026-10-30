# SPDX-License-Identifier: Apache-2.0
"""build() returns a Workplane with nothing on it."""

import cadquery as cq


def build(params):
    return cq.Workplane("XY")
