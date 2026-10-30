# SPDX-License-Identifier: Apache-2.0
"""The CAD runner: builds a part script with build123d and OCCT.

Usage:

    runner --part PART.py [--params JSON] [--summary OUT]

PART.py defines `build(params: dict)`, which returns a build123d shape.
The runner imports it, calls it with the parameters, and checks that the
shape is valid and has a volume: a solid, or a compound of solids. With
--summary it writes the volume and the bounding box size, in millimeters,
three decimals.

Every failure exits with a message that names the part script; an error
raised in the script also prints its traceback.

This is the only Python in rules_brep: build123d and OCCT are Python
libraries. Every checker is Go.
"""

import argparse
import importlib.util
import json
import os
import sys
import traceback


class PartError(Exception):
    """A part script that cannot be built; the message names it."""


def load_part(path):
    """Imports the part script at path as the module `part`.

    The module is in sys.modules while it runs, as an imported module is,
    so that dataclasses and pickling find it. The script's directory is on
    sys.path, so it can import its neighbors.
    """
    spec = importlib.util.spec_from_file_location("part", path)
    if spec is None or spec.loader is None:
        raise PartError("%s: cannot load it as a Python file" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["part"] = module
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        traceback.print_exc()
        raise PartError("%s: importing it failed: %s: %s" % (path, type(e).__name__, e))
    return module


def build(path, params):
    """Returns the shape that the part script at path builds."""
    module = load_part(path)
    fn = getattr(module, "build", None)
    if not callable(fn):
        raise PartError("%s defines no build(params) function" % path)
    try:
        shape = fn(params)
    except Exception as e:
        traceback.print_exc()
        raise PartError("%s: build() failed: %s: %s" % (path, type(e).__name__, e))
    if shape is None or not hasattr(shape, "volume") or not hasattr(shape, "is_valid"):
        raise PartError("%s: build() returned %r, not a build123d shape" % (path, shape))
    # is_valid is a property of build123d shapes (BRepCheck_Analyzer).
    if not shape.is_valid:
        raise PartError("%s: the shape is not valid" % path)
    if shape.volume <= 0:
        raise PartError("%s: the shape has no volume (a %s); a part is a solid" % (path, type(shape).__name__))
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
    try:
        params = json.loads(a.params)
    except json.JSONDecodeError as e:
        raise PartError("%s: --params is not JSON: %s" % (a.part, e))
    if not isinstance(params, dict):
        raise PartError("%s: --params must be a JSON object, not %s" % (a.part, type(params).__name__))
    shape = build(a.part, params)
    if a.summary:
        with open(a.summary, "w", encoding="utf-8") as f:
            f.write(summary(shape))


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except PartError as e:
        sys.exit("runner: %s" % e)
