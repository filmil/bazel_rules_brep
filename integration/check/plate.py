# SPDX-License-Identifier: Apache-2.0
"""A 30 x 20 x 4 mm plate, as a user of hdlf_rules_brep would write a part."""

from build123d import Box


def build(params):
    return Box(30, 20, 4)
