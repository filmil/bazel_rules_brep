# SPDX-License-Identifier: Apache-2.0
"""A 40 x 30 mm plate, 3 mm thick, with a rib on top: cad_check_test's part.

The rib's thickness is a parameter (default 1.6 mm), so one script gives a
part that passes and one whose rib is too thin.
"""

from build123d import Align, Box, Pos


def build(params):
    rib = float(params.get("rib", 1.6))
    plate = Box(40, 30, 3, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return plate + Pos(0, 0, 3) * Box(40, rib, 8, align=(Align.CENTER, Align.CENTER, Align.MIN))
