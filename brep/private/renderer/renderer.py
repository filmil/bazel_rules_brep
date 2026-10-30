# SPDX-License-Identifier: Apache-2.0
"""The CAD renderer: six views of a STEP model as PNG, without OpenGL.

Usage:

    renderer --step IN.step --out VIEW=OUT.png [--out VIEW=OUT.png]...
             [--size PIXELS]

VIEW is one of front, back, left, right, top, bottom; PIXELS is 64 to
4096 (default 512). The model is meshed with OCP (one face at a time,
parallel meshing off), projected orthographically, and drawn flat shaded
with matplotlib's Agg backend: back faces are culled, and the rest are
painted from far to near, by the depth of each triangle's center. Where a
large triangle and a small one overlap in a view, that order can be wrong
for part of them; the views are pictures for review, not measurements.

The PNG is written here, not by matplotlib: RGB, 8 bits, and no chunks
but IHDR, IDAT and IEND, so it holds no time, software name or path.

VTK and pyrender need libOSMesa or libEGL from the host; Agg draws on the
CPU alone. The views draw no text, so no font is used. matplotlib still
lists fonts when it is imported; the renderer lets it list only the ones in
its own wheel (see `import_matplotlib`).
"""

import argparse
import contextlib
import math
import os
import struct
import subprocess
import sys
import zlib


class RenderError(Exception):
    """A model that cannot be rendered; the message names it."""


# Each view: the direction the camera looks in, and the direction that is
# up in the picture. Z is up, and the front view looks along +Y. The
# picture's right is look x up, so no view is mirrored (see `axes`).
VIEWS = {
    "front": ((0, 1, 0), (0, 0, 1)),
    "back": ((0, -1, 0), (0, 0, 1)),
    "left": ((1, 0, 0), (0, 0, 1)),
    "right": ((-1, 0, 0), (0, 0, 1)),
    "top": ((0, 0, -1), (0, 1, 0)),
    "bottom": ((0, 0, 1), (0, -1, 0)),
}

# The model's color, the background, and how much light is not directional.
COLOR = (0.55, 0.65, 0.80)
BACKGROUND = (1.0, 1.0, 1.0)
AMBIENT = 0.35

# How much darker the farthest face is than the nearest.
DEPTH_CUE = 0.3

# The width of each triangle's edge, which closes the seams between them.
EDGE_PIXELS = 0.7

# The mesh's linear deflection, as a fraction of the bounding box diagonal,
# and its angular deflection in radians: fine enough for a picture, coarse
# enough to draw quickly.
DEFLECTION = 0.002
ANGULAR_DEFLECTION = 0.3


@contextlib.contextmanager
def guard_host_fonts(data):
    """While active, no `fc-list` runs and only directories under data are walked.

    When matplotlib has no font cache, it lists the fonts it can find: its
    own, those that `fc-list` knows, and those in the host's font
    directories. The renderer draws no text, but it must not run a host
    tool or read host directories, so it lists fonts under this guard, with
    data the directory of matplotlib's own wheel.
    """
    data = os.path.abspath(data)
    real_walk = os.walk
    real_check_output = subprocess.check_output

    def walk(top, *args, **kwargs):
        top = os.path.abspath(os.fspath(top))
        if top != data and not top.startswith(data + os.sep):
            return iter(())
        return real_walk(top, *args, **kwargs)

    def check_output(cmd, *args, **kwargs):
        raise FileNotFoundError("the renderer runs no host tool: %r" % (cmd,))

    os.walk = walk
    subprocess.check_output = check_output
    try:
        yield
    finally:
        os.walk = real_walk
        subprocess.check_output = real_check_output


def import_matplotlib():
    """Imports matplotlib's Agg backend, with no fonts from the host.

    The font list matplotlib makes on import is made under
    `guard_host_fonts`; the cache it writes goes to MPLCONFIGDIR, in the
    action's private home.
    """
    import matplotlib

    with guard_host_fonts(matplotlib.get_data_path()):
        matplotlib.use("Agg")
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.collections import PolyCollection
        from matplotlib.figure import Figure
    return FigureCanvasAgg, PolyCollection, Figure


def load_step(path):
    """Returns the OCP shape in the STEP file at path."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader

    reader = STEPControl_Reader()
    if reader.ReadFile(path) != IFSelect_RetDone:
        raise RenderError("%s: cannot read it as STEP" % path)
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape is None or shape.IsNull():
        raise RenderError("%s: the file holds no shape" % path)
    return shape


def triangles(shape):
    """Meshes shape and returns its triangles as an (n, 3, 3) array.

    The triangles of each face are turned so that their normals point out
    of the solid. Faces come in the order the shape lists them.
    """
    import numpy as np
    from OCP.Bnd import Bnd_Box
    from OCP.BRep import BRep_Tool
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    if box.IsVoid():
        raise RenderError("the shape is empty")
    diagonal = box.CornerMin().Distance(box.CornerMax())
    if not diagonal > 0:
        raise RenderError("the shape has no extent")

    BRepTools.Clean_s(shape)
    mesh = BRepMesh_IncrementalMesh(shape, DEFLECTION * diagonal, False, ANGULAR_DEFLECTION, False)
    if not mesh.IsDone():
        raise RenderError("meshing failed")

    out = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        explorer.Next()
        location = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, location)
        if tri is None:
            raise RenderError("a face could not be meshed")
        trsf = location.Transformation()
        nodes = []
        for i in range(1, tri.NbNodes() + 1):
            p = tri.Node(i).Transformed(trsf)
            nodes.append((p.X(), p.Y(), p.Z()))
        reversed_face = face.Orientation() == TopAbs_REVERSED
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if reversed_face:
                b, c = c, b
            out.append((nodes[a - 1], nodes[b - 1], nodes[c - 1]))
    if not out:
        raise RenderError("the shape has no faces to draw")
    return np.array(out, dtype=np.float64)


def axes(view):
    """The view's look, up and right directions, as numpy vectors.

    right is look x up: with right and up on the screen, look points into
    it, as a camera sees, so no view is a mirror image.
    """
    import numpy as np

    d, up = (np.array(v, dtype=np.float64) for v in VIEWS[view])
    return d, up, np.cross(d, up)


def project(tris, view):
    """The visible triangles of tris in view, far to near.

    Returns the triangles' 2D points (n, 3, 2), their shades (n,), and the
    2D bounds of the whole model in this view (xmin, xmax, ymin, ymax).
    """
    import numpy as np

    d, up, right = axes(view)
    # The light comes from behind the camera, a little from above and the left.
    light = -d + 0.5 * up - 0.3 * right
    light /= np.linalg.norm(light)

    normals = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    keep = lengths > 0
    normals[keep] /= lengths[keep, None]
    # A face whose normal points away from the camera is at the back.
    keep &= normals @ d < 0

    x = tris @ right
    y = tris @ up
    bounds = (x.min(), x.max(), y.min(), y.max())
    depth = (tris @ d).mean(axis=1)

    idx = np.nonzero(keep)[0]
    if not len(idx):
        raise RenderError("nothing faces the camera in the %s view" % view)
    # Far first; equal depths keep their mesh order, so the order is total.
    order = idx[np.lexsort((idx, -depth[idx]))]
    shade = AMBIENT + (1 - AMBIENT) * np.clip(normals[order] @ light, 0, 1)
    # Farther faces are darker, so that parallel faces at different depths
    # (the steps of a part seen from above) do not look the same.
    near, far = depth.min(), depth.max()
    if far > near:
        shade *= 1 - DEPTH_CUE * (depth[order] - near) / (far - near)
    points = np.stack([x[order], y[order]], axis=-1)
    return points, shade, bounds


def draw(tris, view, size, modules):
    """Draws view of tris and returns its pixels as (size, size, 3) uint8."""
    import numpy as np

    FigureCanvasAgg, PolyCollection, Figure = modules
    points, shade, (xmin, xmax, ymin, ymax) = project(tris, view)

    # One inch at size dots per inch: exactly size pixels, which size / 100
    # inches at 100 dpi is not for every size (115 / 100 * 100 < 115).
    fig = Figure(figsize=(1, 1), dpi=size, facecolor=BACKGROUND)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.set_facecolor(BACKGROUND)
    # The same scale on both axes, with a margin of 5% of the larger side.
    half = max(xmax - xmin, ymax - ymin) * 0.55
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    colors = shade[:, None] * np.array(COLOR)[None, :]
    # Not antialiased, and each triangle's edge in its own color, so that no
    # seam shows between the triangles of a face. Line widths are in points,
    # 1/72 inch, and the figure is one inch: this is EDGE_PIXELS pixels.
    ax.add_collection(PolyCollection(points, facecolors=colors, edgecolors=colors,
                                     linewidths=EDGE_PIXELS * 72 / size, antialiased=False))
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba())
    if rgba.shape[:2] != (size, size):
        raise RenderError("matplotlib drew %dx%d pixels, not %dx%d" % (rgba.shape[1], rgba.shape[0], size, size))
    return np.ascontiguousarray(rgba[:, :, :3])


def png(pixels):
    """pixels (h, w, 3) uint8 as a PNG: IHDR, IDAT and IEND only."""
    h, w, _ = pixels.shape

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    # Filter type 0 (none) on every row.
    raw = b"".join(b"\x00" + pixels[row].tobytes() for row in range(h))
    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) +
            chunk(b"IEND", b""))


def parse_out(values):
    """The --out values as an ordered {view: path}."""
    out = {}
    for v in values:
        view, sep, path = v.partition("=")
        if not sep or not path:
            raise RenderError("--out %r: want VIEW=PATH" % v)
        if view not in VIEWS:
            raise RenderError("--out %r: the view must be one of %s" % (v, ", ".join(VIEWS)))
        if view in out:
            raise RenderError("--out %r: the view %s is given twice" % (v, view))
        out[view] = path
    if not out:
        raise RenderError("no --out given")
    return out


def main(argv):
    p = argparse.ArgumentParser(prog="renderer")
    p.add_argument("--step", required=True, help="the model, as STEP")
    p.add_argument("--out", action="append", default=[], help="VIEW=PATH: write this view as PNG here")
    p.add_argument("--size", type=int, default=512, help="the width and height of each view, in pixels")
    a = p.parse_args(argv)
    try:
        if not 64 <= a.size <= 4096:
            raise RenderError("--size %d: want 64 to 4096 pixels" % a.size)
        out = parse_out(a.out)
        tris = triangles(load_step(a.step))
        modules = import_matplotlib()
        for view, path in out.items():
            with open(path, "wb") as f:
                f.write(png(draw(tris, view, a.size, modules)))
    except RenderError as e:
        if str(e).startswith(a.step):
            raise
        raise RenderError("%s: %s" % (a.step, e)) from None


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except RenderError as e:
        sys.exit("renderer: %s" % e)
