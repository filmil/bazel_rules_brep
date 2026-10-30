# SPDX-License-Identifier: Apache-2.0
"""The CadQuery runner: builds a CadQuery part script (issue #15).

Usage, the same as the build123d runner's for a part:

    cq_runner --part PART.py [--params JSON] [--summary OUT]
              [--name NAME] [--step OUT.step] [--stl OUT.stl]
              [--stl-tolerance MM] [--stl-angular-tolerance RAD] [--path DIR]...

PART.py defines `build(params: dict)`, which returns a CadQuery Workplane
or Shape. The runner imports it, calls it with the parameters, and checks
that the shape is valid and has a volume: a solid, or a compound of
solids. With --summary it writes the volume and the bounding box size, in
millimeters, three decimals.

--step writes the shape as STEP, named NAME, with the header time set to
SOURCE_DATE_EPOCH (seconds since 1970, UTC; 0 if unset) and CadQuery as
the originating system. --stl writes it as binary STL, meshed one face at a
time (parallel meshing off), so the bytes repeat. Neither file holds a path
of the build.

It runs on its own hub of wheels, @brep_pip_cadquery: CadQuery pins an
older OCCT than build123d, built with VTK, whose libraries the runner
loads first (see preload_vtk). Loading, the epoch and the writers are shared
with the build123d runner, in brep/private/runner/export.py.
"""

import argparse
import ctypes
import importlib.util
import json
import math
import os
import re
import sys

from export import PartError, call_build, epoch_timestamp, write_step, write_stl

def ocp_libraries():
    """The shared libraries of the OCP wheel: its extension module, and the
    OCCT libraries it bundles in cadquery_ocp.libs, beside the package."""
    spec = importlib.util.find_spec("OCP")
    if spec is None or not spec.submodule_search_locations:
        raise PartError("the cadquery-ocp wheel is not on the import path")
    pkg = list(spec.submodule_search_locations)[0]
    out = []
    for d in [pkg, os.path.join(os.path.dirname(pkg), "cadquery_ocp.libs")]:
        if os.path.isdir(d):
            out += [os.path.join(d, n) for n in sorted(os.listdir(d)) if ".so" in n]
    if not out:
        raise PartError("no shared library in the OCP wheel at %s" % pkg)
    return out


def vtk_libs(libraries, vtkdir):
    """The VTK libraries in vtkdir that the given libraries link to.

    The names a library links to are NUL-ended strings in its dynamic string
    table; every libvtk*.so string in them that is a file in vtkdir is one.
    """
    found = set()
    for lib in libraries:
        with open(lib, "rb") as f:
            data = f.read()
        for m in re.finditer(rb"libvtk[A-Za-z0-9_.]*\.so(?:\.[0-9.]+)?\x00", data):
            name = m.group(0)[:-1].decode("ascii")
            if os.path.exists(os.path.join(vtkdir, name)):
                found.add(name)
    return sorted(found)


def preload_vtk():
    """Loads the VTK libraries OCP links to, before OCP is imported.

    OCP finds them through its RUNPATH, $ORIGIN/../vtkmodules: beside it in
    one site-packages, as pip installs it. rules_python puts each wheel in a
    directory of its own, so that path leads nowhere. A library already
    loaded under its soname satisfies the link. The VTK libraries carry no
    RUNPATH themselves, so each is loaded after the ones it needs: a pass
    loads what it can, and the next pass retries the rest.
    """
    spec = importlib.util.find_spec("vtkmodules")
    if spec is None or not spec.submodule_search_locations:
        raise PartError("the vtk wheel is not on the import path")
    d = list(spec.submodule_search_locations)[0]
    pending = vtk_libs(ocp_libraries(), d)
    if not pending:
        raise PartError("OCP names no VTK library in %s" % d)
    while pending:
        left, errors = [], []
        for name in pending:
            try:
                ctypes.CDLL(os.path.join(d, name), mode=ctypes.RTLD_GLOBAL)
            except OSError as e:
                left.append(name)
                errors.append(str(e))
        if len(left) == len(pending):
            raise PartError("cannot load the VTK libraries from %s: %s" % (d, "; ".join(errors)))
        pending = left


def shape_of(path, result):
    """The cadquery.Shape that build() returned, from a Workplane or a Shape."""
    import cadquery as cq

    if isinstance(result, cq.Workplane):
        vals = result.vals()
        if not vals:
            raise PartError("%s: build() returned a Workplane that holds no shape" % path)
        others = sorted({type(v).__name__ for v in vals if not isinstance(v, cq.Shape)})
        if others:
            raise PartError("%s: build() returned a Workplane that holds a %s, not only shapes" % (path, ", ".join(others)))
        return vals[0] if len(vals) == 1 else cq.Compound.makeCompound(vals)
    if isinstance(result, cq.Shape):
        return result
    raise PartError("%s: build() returned %r, not a CadQuery Workplane or Shape" % (path, result))


def build(path, params):
    """Returns the cadquery.Shape that the part script at path builds."""
    shape = shape_of(path, call_build(path, params))
    if not shape.isValid():
        raise PartError("%s: the shape is not valid" % path)
    # A face or a shell has a "volume" in OCCT's sense (the signed volume it
    # bounds with the origin), so the test is for solids first.
    if not shape.Solids() or shape.Volume() <= 0:
        raise PartError("%s: the shape has no volume (a %s); a part is a solid" % (path, type(shape).__name__))
    loose = loose_parts(shape.wrapped)
    if loose:
        raise PartError("%s: the shape holds %s outside its solids; a part is solids only" % (path, loose))
    return shape


def loose_parts(shape):
    """What shape holds outside its solids, as "2 faces, 1 edge", or ""."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer

    out = []
    # Each kind, not inside the kind that would hold it in a solid.
    for kind, avoid, word in [(TopAbs_SHELL, TopAbs_SOLID, "shell"), (TopAbs_FACE, TopAbs_SHELL, "face"),
                              (TopAbs_WIRE, TopAbs_FACE, "wire"), (TopAbs_EDGE, TopAbs_WIRE, "edge"),
                              (TopAbs_VERTEX, TopAbs_EDGE, "vertex")]:
        n = 0
        e = TopExp_Explorer(shape, kind, avoid)
        while e.More():
            n += 1
            e.Next()
        if n:
            out.append("%d %s%s" % (n, word, "" if n == 1 else ("es" if word == "vertex" else "s")))
    return ", ".join(out)


def summary(shape):
    """The volume and the bounding box size, one per line."""
    box = shape.BoundingBox()
    return "volume %.3f\nsize %.3f %.3f %.3f\n" % (shape.Volume(), box.xlen, box.ylen, box.zlen)


def main(argv):
    p = argparse.ArgumentParser(prog="cq_runner")
    p.add_argument("--part", required=True, help="the part script")
    p.add_argument("--params", default="{}", help="the parameters, as a JSON object")
    p.add_argument("--summary", help="write the volume and size here")
    p.add_argument("--name", default="part", help="the shape's name in the STEP file")
    p.add_argument("--step", help="write the shape as STEP here")
    p.add_argument("--stl", help="write the shape as binary STL here")
    p.add_argument("--stl-tolerance", type=float, default=0.001, help="the STL mesh's linear deflection, mm")
    p.add_argument("--stl-angular-tolerance", type=float, default=0.1, help="the STL mesh's angular deflection, radians")
    p.add_argument("--path", action="append", default=[], help="a directory to import the part's dependencies from")
    a = p.parse_args(argv)
    try:
        preload_vtk()
        run(a)
    except PartError as e:
        # Every message names the part script.
        if str(e).startswith(a.part):
            raise
        raise PartError("%s: %s" % (a.part, e)) from None


def run(a):
    """Builds the part and writes what the arguments ask for."""
    for d in reversed(a.path):
        sys.path.insert(0, os.path.abspath(d))
    try:
        params = json.loads(a.params)
    except json.JSONDecodeError as e:
        raise PartError("%s: --params is not JSON: %s" % (a.part, e))
    if not isinstance(params, dict):
        raise PartError("%s: --params must be a JSON object, not %s" % (a.part, type(params).__name__))
    # The arguments are checked before the script runs, whether or not the
    # file they are for is asked for.
    for t in [a.stl_tolerance, a.stl_angular_tolerance]:
        if not math.isfinite(t) or t <= 0:
            raise PartError("%s: the STL tolerances must be positive and finite" % a.part)
    timestamp = epoch_timestamp()
    shape = build(a.part, params)
    if a.summary:
        with open(a.summary, "w", encoding="utf-8") as f:
            f.write(summary(shape))
    if a.step:
        write_step(shape.wrapped, a.name, a.step, timestamp, "cadquery")
    if a.stl:
        write_stl(shape.wrapped, a.stl, a.stl_tolerance, a.stl_angular_tolerance)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except PartError as e:
        sys.exit("cq_runner: %s" % e)
