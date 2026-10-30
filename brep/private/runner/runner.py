# SPDX-License-Identifier: Apache-2.0
"""The CAD runner: builds a part script with build123d and OCCT.

Usage:

    runner --part PART.py [--params JSON] [--summary OUT]
           [--name NAME] [--step OUT.step] [--stl OUT.stl]
           [--stl-tolerance MM] [--stl-angular-tolerance RAD]

PART.py defines `build(params: dict)`, which returns a build123d shape.
The runner imports it, calls it with the parameters, and checks that the
shape is valid and has a volume: a solid, or a compound of solids. With
--summary it writes the volume and the bounding box size, in millimeters,
three decimals.

--step writes the shape as STEP, named NAME, with the header time set to
SOURCE_DATE_EPOCH (seconds since 1970, UTC; 0 if unset). --stl writes it
as binary STL, meshed one face at a time (parallel meshing off), so the
bytes repeat. Neither file holds a path of the build.

Every failure exits with a message that names the part script; an error
raised in the script also prints its traceback.

This is the only Python in rules_brep: build123d and OCCT are Python
libraries. Every checker is Go.
"""

import argparse
import datetime
import importlib.util
import io
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


def epoch_timestamp():
    """SOURCE_DATE_EPOCH as an ISO 8601 time in UTC, as STEP headers have it."""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "0")
    try:
        t = int(raw)
    except ValueError:
        raise PartError("SOURCE_DATE_EPOCH=%r is not a number of seconds" % raw)
    if t < 0:
        raise PartError("SOURCE_DATE_EPOCH=%d is before 1970" % t)
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def write_step(shape, name, path):
    """Writes shape as STEP, named name, at the SOURCE_DATE_EPOCH time.

    It writes to memory first, so that no file path of the build reaches the
    header.
    """
    from build123d import export_step

    shape.label = name
    buf = io.BytesIO()
    export_step(shape, buf, timestamp=epoch_timestamp())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def write_stl(shape, path, tolerance, angular_tolerance):
    """Writes shape as binary STL, meshed with parallel meshing off.

    build123d's export_stl meshes in parallel, which may order the
    triangles differently from run to run.
    """
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.StlAPI import StlAPI_Writer

    mesh = BRepMesh_IncrementalMesh(shape.wrapped, tolerance, False, angular_tolerance, False)
    mesh.Perform()
    if not mesh.IsDone():
        raise PartError("meshing for STL failed")
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(shape.wrapped, path):
        raise PartError("writing %s failed" % path)


def main(argv):
    p = argparse.ArgumentParser(prog="runner")
    p.add_argument("--part", required=True, help="the part script")
    p.add_argument("--params", default="{}", help="the parameters, as a JSON object")
    p.add_argument("--summary", help="write the volume and size here")
    p.add_argument("--name", default="part", help="the shape's name in the STEP file")
    p.add_argument("--step", help="write the shape as STEP here")
    p.add_argument("--stl", help="write the shape as binary STL here")
    p.add_argument("--stl-tolerance", type=float, default=0.001, help="the STL mesh's linear deflection, mm")
    p.add_argument("--stl-angular-tolerance", type=float, default=0.1, help="the STL mesh's angular deflection, radians")
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
    if a.step:
        write_step(shape, a.name, a.step)
    if a.stl:
        if a.stl_tolerance <= 0 or a.stl_angular_tolerance <= 0:
            raise PartError("%s: the STL tolerances must be positive" % a.part)
        write_stl(shape, a.stl, a.stl_tolerance, a.stl_angular_tolerance)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except PartError as e:
        sys.exit("runner: %s" % e)
