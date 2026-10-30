# SPDX-License-Identifier: Apache-2.0
"""A cube, size from the parameters: the CAD toolchain's smoke test."""

from build123d import Box


def build(params):
    s = float(params.get("size", 10))
    return Box(s, s, s)
