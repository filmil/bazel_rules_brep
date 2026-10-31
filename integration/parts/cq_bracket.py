# SPDX-License-Identifier: Apache-2.0
"""An L-bracket in CadQuery, as a user of hdlf_rules_brep would write one."""

import cadquery as cq


def build(params):
    t = float(params.get("thickness", 3))
    base = cq.Workplane("XY").box(30, 20, t, centered=(False, True, False))
    wall = cq.Workplane("XY").box(t, 20, 30, centered=(False, True, False))
    return base.union(wall)
