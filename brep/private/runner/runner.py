# SPDX-License-Identifier: Apache-2.0
"""The CAD runner: builds a part script with build123d and OCCT.

Usage:

    runner --part PART.py [--params JSON] [--summary OUT]

PART.py defines `build(params: dict)`, which returns a build123d shape.
The runner imports it, calls it with the parameters, checks that the
shape is a valid solid, and with --summary writes its volume and bounding
box, in millimeters, three decimals.

This is the only Python in rules_brep: build123d and OCCT are Python
libraries. Every checker is Go.
"""

import argparse
import importlib.util
import json
import sys


def load_part(path):
    """Imports the part script at path as a module."""
    spec = importlib.util.spec_from_file_location("part", path)
    if spec is None or spec.loader is None:
        raise SystemExit("runner: cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(path, params):
    """Returns the shape that the part script at path builds."""
    module = load_part(path)
    fn = getattr(module, "build", None)
    if not callable(fn):
        raise SystemExit("runner: %s defines no build(params) function" % path)
    shape = fn(params)
    if shape is None or not hasattr(shape, "volume"):
        raise SystemExit("runner: %s: build() returned %r, not a build123d shape" % (path, shape))
    if not shape.is_valid:
        raise SystemExit("runner: %s: the shape is not valid" % path)
    return shape


def summary(shape):
    """The volume and the bounding box size, one per line."""
    size = shape.bounding_box().size
    return "volume %.3f\nsize %.3f %.3f %.3f\n" % (shape.volume, size.X, size.Y, size.Z)


def main(argv):
    p = argparse.ArgumentParser(prog="runner")
    p.add_argument("--part", required=True, help="the part script")
    p.add_argument("--params", default="{}", help="the parameters, as a JSON object")
    p.add_argument("--summary", help="write the volume and size here")
    a = p.parse_args(argv)
    params = json.loads(a.params)
    if not isinstance(params, dict):
        raise SystemExit("runner: --params must be a JSON object")
    shape = build(a.part, params)
    if a.summary:
        with open(a.summary, "w") as f:
            f.write(summary(shape))


if __name__ == "__main__":
    main(sys.argv[1:])
