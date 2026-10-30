# SPDX-License-Identifier: Apache-2.0
"""A 10 mm cube with a corner at the origin: interference_test's test part."""

from build123d import Align, Box


def build(params):
    return Box(10, 10, 10, align=(Align.MIN, Align.MIN, Align.MIN))
