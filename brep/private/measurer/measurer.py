# SPDX-License-Identifier: Apache-2.0
"""The CAD measurer: the size and shape of a STEP model, as text.

Usage:

    measurer --step IN.step --out OUT.txt [--min-wall GRID]

It writes one quantity per line, "key value...", numbers in millimeters
(mm, mm², mm³) with 6 decimals. The format is stable: geometry_equal_test
reads it, and cad_check_test will (issue #12).

    volume V
    area A
    center X Y Z
    min X Y Z
    max X Y Z
    solids N
    faces N
    edges N
    vertices N

With --min-wall GRID it adds a last line, "min_wall T": the thinnest
wall found, in mm. From a GRID x GRID grid of points on each face (those
inside it), a ray goes inward along the normal, and T is the shortest
distance to where it leaves the solid. It is sampled: a wall thinner than
the grid's spacing in a small spot can be missed; a larger GRID looks
closer. The order and the points are fixed, so T repeats.

center is the center of mass at uniform density; min and max are the
corners of the tightest box around the shape, from its geometry rather than
its tolerances or a mesh. The counts are of distinct subshapes.

geometry_equal_test compares two of these with tolerances (spec D3): OCCT's
results can differ in the last digits from one CPU to another. Area and
center catch what volume and box miss, such as a hole that moved.
"""

import argparse
import sys


class MeasureError(Exception):
    """A model that cannot be measured; the message names it."""


def load_step(path):
    """Returns the OCP shape in the STEP file at path."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise MeasureError("%s: cannot read it as STEP" % path)
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape is None or shape.IsNull():
        raise MeasureError("%s: the file holds no shape" % path)
    return shape


def count(shape, kind):
    """The number of distinct subshapes of shape of kind (a TopAbs value)."""
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    from OCP.TopExp import TopExp

    # TopTools_IndexedMapOfShape, under its name in this OCP.
    m = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, kind, m)
    return m.Extent()


def measure(shape):
    """The measurements of shape, as an ordered list of (name, values)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SOLID, TopAbs_VERTEX

    vprops = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vprops)
    sprops = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, sprops)
    box = Bnd_Box()
    # From the geometry: no mesh, and not widened by the shape's tolerances.
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        raise MeasureError("the shape is empty")
    c, lo, hi = vprops.CentreOfMass(), box.CornerMin(), box.CornerMax()
    return [
        ("volume", [vprops.Mass()]),
        ("area", [sprops.Mass()]),
        ("center", [c.X(), c.Y(), c.Z()]),
        ("min", [lo.X(), lo.Y(), lo.Z()]),
        ("max", [hi.X(), hi.Y(), hi.Z()]),
        ("solids", [count(shape, TopAbs_SOLID)]),
        ("faces", [count(shape, TopAbs_FACE)]),
        ("edges", [count(shape, TopAbs_EDGE)]),
        ("vertices", [count(shape, TopAbs_VERTEX)]),
    ]


def min_wall(shape, grid):
    """The thinnest wall of shape, sampled on a grid x grid per face (mm).

    Returns None when no inward ray meets the solid again (a shape with no
    solid, or only open faces).
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepTools import BRepTools
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt2d
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from OCP.TopAbs import TopAbs_FACE, TopAbs_IN, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    inter = IntCurvesFace_ShapeIntersector()
    inter.Load(shape, 1e-7)
    best = None
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = TopoDS.Face(exp.Current())
        exp.Next()
        umin, umax, vmin, vmax = BRepTools.UVBounds_s(face)
        surf = BRepAdaptor_Surface(face)
        for i in range(grid):
            for j in range(grid):
                u = umin + (i + 0.5) / grid * (umax - umin)
                v = vmin + (j + 0.5) / grid * (vmax - vmin)
                if BRepClass_FaceClassifier(face, gp_Pnt2d(u, v), 1e-7).State() != TopAbs_IN:
                    continue
                props = BRepLProp_SLProps(surf, u, v, 1, 1e-7)
                if not props.IsNormalDefined():
                    continue
                n = props.Normal()
                # The normal of the surface points out of the solid unless
                # the face is reversed.
                inward = n if face.Orientation() == TopAbs_REVERSED else n.Reversed()
                inter.PerformNearest(gp_Lin(props.Value(), gp_Dir(inward.XYZ())), 1e-6, 1e100)
                if inter.IsDone() and inter.NbPnt() > 0:
                    t = inter.WParameter(1)
                    if best is None or t < best:
                        best = t
    return best


def text(measurements):
    """The measurements as the lines the measurer writes."""

    def fmt(v):
        if isinstance(v, int):
            return str(v)
        # Rounded first, and -0.0 made 0.0, so a value near zero is "0.000000".
        return "%.6f" % (round(v, 6) + 0.0)

    return "".join("%s %s\n" % (name, " ".join(fmt(v) for v in values)) for name, values in measurements)


def main(argv):
    p = argparse.ArgumentParser(prog="measurer")
    p.add_argument("--step", required=True, help="the model, as STEP")
    p.add_argument("--out", required=True, help="write the measurements here")
    p.add_argument("--min-wall", type=int, default=0, help="also measure the thinnest wall, on a GRID x GRID grid per face")
    a = p.parse_args(argv)
    if a.min_wall < 0 or a.min_wall > 100:
        p.error("--min-wall must be 1 to 100 (0: not measured)")
    try:
        shape = load_step(a.step)
        m = measure(shape)
        if a.min_wall:
            w = min_wall(shape, a.min_wall)
            if w is None:
                raise MeasureError("no wall found: no inward ray meets the solid again")
            m.append(("min_wall", [w]))
        out = text(m)
    except MeasureError as e:
        if str(e).startswith(a.step):
            raise
        raise MeasureError("%s: %s" % (a.step, e)) from None
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(out)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except MeasureError as e:
        sys.exit("measurer: %s" % e)
