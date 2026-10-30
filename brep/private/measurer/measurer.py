# SPDX-License-Identifier: Apache-2.0
"""The CAD measurer: the size and shape of a STEP model, as text.

Usage:

    measurer --step IN.step --out OUT.txt

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
    a = p.parse_args(argv)
    try:
        out = text(measure(load_step(a.step)))
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
