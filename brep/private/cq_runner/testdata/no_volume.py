# SPDX-License-Identifier: Apache-2.0
"""build() returns a face: valid, but no volume."""

import cadquery as cq


def build(params):
    return cq.Workplane("XY").rect(1, 1).extrude(1).faces(">Z").val()
