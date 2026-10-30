# SPDX-License-Identifier: Apache-2.0
"""An L-bracket, as a user of rules_brep would write a part."""

from build123d import Box, Pos


def build(params):
    t = float(params.get("thickness", 3))
    return Pos(15, 0, t / 2) * Box(30, 20, t) + Pos(t / 2, 0, 15) * Box(t, 20, 30)
