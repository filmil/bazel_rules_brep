# SPDX-License-Identifier: Apache-2.0
"""The CAD runner: builds a part script with build123d and OCCT.

Usage:

    runner --part PART.py [--params JSON] [--summary OUT]
           [--name NAME] [--step OUT.step] [--stl OUT.stl]
           [--stl-tolerance MM] [--stl-angular-tolerance RAD] [--path DIR]...
    runner --assemble SPEC.json --step OUT.step
    runner --interference SPEC.json --report OUT.txt
    runner --fit SPEC.json --report OUT.txt

PART.py defines `build(params: dict)`, which returns a build123d shape.
The runner imports it, calls it with the parameters, and checks that the
shape is valid and has a volume: a solid, or a compound of solids. With
--summary it writes the volume and the bounding box size, in millimeters,
three decimals.

--step writes the shape as STEP, named NAME, with the header time set to
SOURCE_DATE_EPOCH (seconds since 1970, UTC; 0 if unset). --stl writes it
as binary STL, meshed one face at a time (parallel meshing off), so the
bytes repeat. Neither file holds a path of the build.

--assemble reads a JSON spec: {"name": ..., "children": [{"name": ...,
"step": PATH, "pos": [x, y, z], "rot": [rx, ry, rz]}, ...]}. It loads each
child's STEP, moves it (millimeters; degrees, intrinsic X then Y then Z),
names it, and writes one STEP of all of them, named NAME, the same way as
--step.

--interference reads the same spec, places the children, and writes one
line per pair of them, in the order of the spec, fields separated by tabs:
"pair", A, B, and the volume (mm^3, full precision) that A and B share:
the solids of their common part, summed over every pair of their solids.
Parts that only touch, at a face, an edge or a point, share none.

--fit reads {"board": STEP, "enclosure": STEP, "pos": [...], "rot": [...]},
places the board in the enclosure, and writes, tab-separated:

    overlap V        the volume the board and the enclosure share (mm^3)
    clearance D      the least distance from the board's outline (its side
                     faces, not its holes) to the enclosure beside it: the
                     enclosure's material between the board's bottom and
                     top, so supports that touch the board from below or
                     above do not count (mm); "inf" when none is beside it
    hole X Y R       each mounting hole of the board: a hole along Z
    mount X Y R      each feature along Z in the enclosure that a hole can
                     sit on: a boss's hole or a pin

A cylinder along Z is a hole when its axis runs outside the solid's
material.

Every failure exits with a message that names the part script (or the
assembly); an error raised in the script also prints its traceback.

Loading a part script, the epoch and the STL writer live in export.py,
shared with the CadQuery runner (issue #15). Every checker is Go.
"""

import argparse
import io
import json
import math
import os
import sys

# Shared with the CadQuery runner (issue #15).
from export import PartError, call_build, epoch_timestamp, load_part, write_stl  # noqa: F401


def build(path, params):
    """Returns the shape that the part script at path builds."""
    shape = call_build(path, params)
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


def write_step(shape, name, path, timestamp):
    """Writes shape as STEP, named name, at timestamp.

    It writes to memory first, so that no file path of the build reaches the
    header. The shape's label is the name only while it is written.
    """
    from build123d import export_step

    old = shape.label
    shape.label = name
    try:
        buf = io.BytesIO()
        export_step(shape, buf, timestamp=timestamp)
    finally:
        shape.label = old
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def assemble(spec):
    """The compound of the spec's children, each moved and named."""
    from build123d import Compound, Location, import_step

    children = []
    loaded = {}
    for c in spec.get("children", []):
        try:
            name, step, pos, rot = c["name"], c["step"], c["pos"], c["rot"]
        except (KeyError, TypeError) as e:
            raise PartError("a child lacks %s: %r" % (e, c))
        if step not in loaded:
            # Each part's file once, however often it is placed.
            try:
                loaded[step] = import_step(step)
            except Exception as e:
                raise PartError("child %s: reading %s failed: %s" % (name, step, e))
        # moved() returns a new shape, placed in the part's own frame.
        moved = loaded[step].moved(Location(tuple(pos), tuple(rot)))
        moved.label = name
        children.append(moved)
    if not children:
        raise PartError("the assembly has no children")
    return Compound(children=children)


def _solids(shape):
    """The OCCT solids in shape, each with its bounding box."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    out = []
    exp = TopExp_Explorer(shape.wrapped, TopAbs_SOLID)
    while exp.More():
        box = Bnd_Box()
        BRepBndLib.Add_s(exp.Current(), box)
        out.append((exp.Current(), box))
        exp.Next()
    return out


def _common_volume(a, b):
    """The volume of the solids that OCCT's boolean common of a and b gives.

    Only solids count: where a and b touch at a face, an edge or a point,
    the common part has no solid, and so no volume.
    """
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    op = BRepAlgoAPI_Common(a, b)
    if not op.IsDone():
        raise PartError("OCCT could not intersect two solids")
    total = 0.0
    exp = TopExp_Explorer(op.Shape(), TopAbs_SOLID)
    while exp.More():
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(exp.Current(), props)
        total += abs(props.Mass())
        exp.Next()
    return total


def _z_cylinders(shape):
    """Each cylinder along Z in shape: (x, y, radius, axis in material?).

    A cylinder split into several faces counts once.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.GeomAbs import GeomAbs_Cylinder
    from OCP.gp import gp_Pnt
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.TopAbs import TopAbs_FACE, TopAbs_IN
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    found = {}
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face(exp.Current())
        exp.Next()
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() != GeomAbs_Cylinder:
            continue
        cyl = surf.Cylinder()
        d = cyl.Axis().Direction()
        if abs(d.Z()) < 0.999999:
            continue
        loc, r = cyl.Location(), cyl.Radius()
        key = (round(loc.X(), 6), round(loc.Y(), 6), round(r, 6))
        if key in found:
            continue
        # The face's middle height: is the axis there inside the material?
        box = Bnd_Box()
        BRepBndLib.Add_s(face, box)
        zmid = (box.CornerMin().Z() + box.CornerMax().Z()) / 2
        cls = BRepClass3d_SolidClassifier(shape, gp_Pnt(loc.X(), loc.Y(), zmid), 1e-7)
        found[key] = cls.State() == TopAbs_IN
    return sorted((x, y, r, inside) for (x, y, r), inside in found.items())


def _outline(shape):
    """The board's outline: its faces that are not flat along XY, nor holes."""
    from OCP.BRep import BRep_Builder
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS, TopoDS_Compound

    holes = {(round(x, 6), round(y, 6), round(r, 6)) for x, y, r, inside in _z_cylinders(shape) if not inside}
    comp = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(comp)
    n = 0
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face(exp.Current())
        exp.Next()
        surf = BRepAdaptor_Surface(face)
        t = surf.GetType()
        if t == GeomAbs_Plane and abs(surf.Plane().Axis().Direction().Z()) > 0.999999:
            continue  # the top or the bottom
        if t == GeomAbs_Cylinder:
            c = surf.Cylinder()
            loc = c.Location()
            if (round(loc.X(), 6), round(loc.Y(), 6), round(c.Radius(), 6)) in holes:
                continue
        builder.Add(comp, face)
        n += 1
    if n == 0:
        raise PartError("the board has no outline faces")
    return comp


def _slab(enclosure, board):
    """The enclosure's material at the board's height, or None.

    The slab runs from just above the board's bottom to just below its top,
    so a boss under the board or a lid over it is left out.
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(board, box, False, False)
    lo, hi = box.CornerMin(), box.CornerMax()
    eps = min(1e-4, (hi.Z() - lo.Z()) / 4)
    big = 1e5
    slab = BRepPrimAPI_MakeBox(gp_Pnt(lo.X() - big, lo.Y() - big, lo.Z() + eps), gp_Pnt(hi.X() + big, hi.Y() + big, hi.Z() - eps)).Shape()
    op = BRepAlgoAPI_Common(enclosure, slab)
    if not op.IsDone():
        raise PartError("OCCT could not cut the enclosure at the board's height")
    if not TopExp_Explorer(op.Shape(), TopAbs_SOLID).More():
        return None
    return op.Shape()


def fit(spec):
    """The --fit report of the spec's board, placed in its enclosure."""
    from build123d import Location, import_step
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    try:
        board_file, enclosure_file, pos, rot = spec["board"], spec["enclosure"], spec["pos"], spec["rot"]
    except (KeyError, TypeError) as e:
        raise PartError("the spec lacks %s" % e)
    try:
        board = import_step(board_file).moved(Location(tuple(pos), tuple(rot)))
        enclosure = import_step(enclosure_file)
    except Exception as e:
        raise PartError("reading the models failed: %s" % e)
    overlap = 0.0
    for sa, ba in _solids(board):
        for sb, bb in _solids(enclosure):
            if not ba.IsOut(bb):
                overlap += _common_volume(sa, sb)
    beside = _slab(enclosure.wrapped, board.wrapped)
    if beside is None:
        clearance = float("inf")
    else:
        dist = BRepExtrema_DistShapeShape(_outline(board.wrapped), beside)
        if not dist.IsDone():
            raise PartError("OCCT could not measure the clearance")
        clearance = dist.Value()
    lines = ["overlap\t%r\n" % overlap, "clearance\t%r\n" % clearance]
    for x, y, r, inside in _z_cylinders(board.wrapped):
        if not inside:
            lines.append("hole\t%r\t%r\t%r\n" % (x, y, r))
    for x, y, r, inside in _z_cylinders(enclosure.wrapped):
        lines.append("mount\t%r\t%r\t%r\n" % (x, y, r))
    return "".join(lines)


def interference(compound):
    """One line per pair of children: the volume the two share."""
    kids = list(compound.children)
    solids = [_solids(k) for k in kids]
    lines = []
    for i in range(len(kids)):
        for j in range(i + 1, len(kids)):
            vol = 0.0
            for sa, ba in solids[i]:
                for sb, bb in solids[j]:
                    # Solids whose boxes do not meet share nothing; skip the
                    # boolean.
                    if not ba.IsOut(bb):
                        vol += _common_volume(sa, sb)
            lines.append("pair\t%s\t%s\t%r\n" % (kids[i].label, kids[j].label, vol))
    return "".join(lines)


def main(argv):
    p = argparse.ArgumentParser(prog="runner")
    p.add_argument("--part", help="the part script")
    p.add_argument("--assemble", help="an assembly spec (JSON), instead of --part")
    p.add_argument("--interference", help="an assembly spec (JSON): report the volume each pair shares")
    p.add_argument("--fit", help="a board-in-enclosure spec (JSON): report how the board fits")
    p.add_argument("--report", help="where --interference or --fit writes its report")
    p.add_argument("--params", default="{}", help="the parameters, as a JSON object")
    p.add_argument("--summary", help="write the volume and size here")
    p.add_argument("--name", default="part", help="the shape's name in the STEP file")
    p.add_argument("--step", help="write the shape as STEP here")
    p.add_argument("--stl", help="write the shape as binary STL here")
    p.add_argument("--stl-tolerance", type=float, default=0.001, help="the STL mesh's linear deflection, mm")
    p.add_argument("--stl-angular-tolerance", type=float, default=0.1, help="the STL mesh's angular deflection, radians")
    p.add_argument("--path", action="append", default=[], help="a directory to import the part's dependencies from")
    a = p.parse_args(argv)
    if sum(bool(x) for x in [a.part, a.assemble, a.interference, a.fit]) != 1:
        p.error("give one of --part, --assemble, --interference and --fit")
    if a.interference or a.fit:
        extra = [f for f, v in [("--step", a.step), ("--stl", a.stl), ("--summary", a.summary), ("--path", a.path)] if v]
        if a.name != "part":
            extra.append("--name")
        if a.params != "{}":
            extra.append("--params")
        if extra or not a.report:
            p.error("--interference and --fit take only --report; got %s" % (extra or "no --report"))
    if a.report and not (a.interference or a.fit):
        p.error("--report goes with --interference or --fit")
    if a.assemble:
        extra = [f for f, v in [("--summary", a.summary), ("--stl", a.stl), ("--path", a.path)] if v]
        if extra or a.name != "part":
            p.error("--assemble takes only --step (the name is the spec's); got %s" % (extra + (["--name"] if a.name != "part" else [])))
    what = a.part or a.assemble or a.interference or a.fit
    try:
        if a.fit:
            try:
                with open(a.fit, encoding="utf-8") as f:
                    spec = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                raise PartError("reading the spec failed: %s" % e)
            report = fit(spec)
            with open(a.report, "w", encoding="utf-8") as f:
                f.write(report)
        elif a.interference:
            spec = read_spec(a.interference)
            report = interference(assemble(spec))
            with open(a.report, "w", encoding="utf-8") as f:
                f.write(report)
        elif a.assemble:
            run_assembly(a)
        else:
            run(a)
    except PartError as e:
        # Every message names the part script, or the assembly spec.
        if str(e).startswith(what):
            raise
        raise PartError("%s: %s" % (what, e)) from None


def read_spec(path):
    """The assembly spec at path."""
    try:
        with open(path, encoding="utf-8") as f:
            spec = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise PartError("reading the spec failed: %s" % e)
    if not isinstance(spec, dict) or not isinstance(spec.get("name"), str):
        raise PartError("the spec must be an object with a name")
    return spec


def run_assembly(a):
    """Writes the assembly that the spec describes as STEP."""
    spec = read_spec(a.assemble)
    if not a.step:
        raise PartError("--assemble needs --step")
    write_step(assemble(spec), spec["name"], a.step, epoch_timestamp())


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
    shape = build(a.part, params)
    if a.summary:
        with open(a.summary, "w", encoding="utf-8") as f:
            f.write(summary(shape))
    if a.step:
        write_step(shape, a.name, a.step, epoch_timestamp())
    if a.stl:
        for t in [a.stl_tolerance, a.stl_angular_tolerance]:
            if not math.isfinite(t) or t <= 0:
                raise PartError("%s: the STL tolerances must be positive and finite" % a.part)
        write_stl(shape.wrapped, a.stl, a.stl_tolerance, a.stl_angular_tolerance)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except PartError as e:
        sys.exit("runner: %s" % e)
