# SPDX-License-Identifier: Apache-2.0
"""Tests of the CAD renderer: the views, the PNG it writes, its errors."""

import ctypes
import os
import struct
import tempfile
import unittest
import zlib


def preload_gl_libs():
    """Loads the GL and X11 libraries OCP needs, dependencies first.

    The renderer gets them through LD_LIBRARY_PATH (the CAD toolchain); a
    test cannot set that for itself, as the loader reads it at start.
    """
    order = ["libexpat.so.1", "libmd.so.0", "libbsd.so.0", "libXau.so.6", "libXdmcp.so.6", "libxcb.so.1",
             "libX11.so.6", "libGLdispatch.so.0", "libGLX.so.0", "libGL.so.1"]
    paths = {os.path.basename(p): p for p in os.environ["BREP_GL_LIBS"].split()}
    for name in order:
        ctypes.CDLL(os.path.abspath(paths[name]), mode=ctypes.RTLD_GLOBAL)


preload_gl_libs()

import renderer  # noqa: E402 (after the libraries OCP needs)


def box_step(dx, dy, dz):
    """A box as a STEP file; returns its path."""
    from build123d import Box, export_step

    path = os.path.join(tempfile.mkdtemp(), "box.step")
    export_step(Box(dx, dy, dz), path)
    return path


def chunks(data):
    """The chunk types of a PNG, in order."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    kinds, i = [], 8
    while i < len(data):
        (n,) = struct.unpack(">I", data[i:i + 4])
        kinds.append(data[i + 4:i + 8].decode("ascii"))
        i += 12 + n
    return kinds


def pixels(data):
    """A PNG this renderer wrote, as (width, height, rows of RGB bytes)."""
    w, h = struct.unpack(">II", data[16:24])
    (n,) = struct.unpack(">I", data[33:37])
    raw = zlib.decompress(data[41:41 + n])
    stride = 1 + 3 * w
    return w, h, [raw[r * stride + 1:(r + 1) * stride] for r in range(h)]


class RendererTest(unittest.TestCase):
    def render(self, step, views, size=64):
        d = tempfile.mkdtemp()
        out = {v: os.path.join(d, v + ".png") for v in views}
        renderer.main(["--step", step, "--size", str(size)] + ["--out=%s=%s" % kv for kv in out.items()])
        result = {}
        for v, p in out.items():
            with open(p, "rb") as f:
                result[v] = f.read()
        return result

    def test_six_views_png_without_metadata(self):
        got = self.render(box_step(10, 20, 30), list(renderer.VIEWS))
        self.assertEqual(sorted(renderer.VIEWS), sorted(got))
        for view, data in got.items():
            self.assertEqual(["IHDR", "IDAT", "IEND"], chunks(data), view)
            w, h, rows = pixels(data)
            self.assertEqual((64, 64), (w, h), view)
            # The corner is background; the center is the model, shaded.
            self.assertEqual(b"\xff\xff\xff", rows[0][:3], view)
            self.assertNotEqual(b"\xff\xff\xff", rows[32][96:99], view)

    def test_same_bytes_twice(self):
        step = box_step(10, 20, 30)
        self.assertEqual(self.render(step, ["front", "top"]), self.render(step, ["front", "top"]))

    def test_views_differ(self):
        # A box of 10 x 20 x 30: from the front it is 10 wide and 30 high,
        # from the left 20 wide and 30 high, from the top 10 wide, 20 high.
        got = self.render(box_step(10, 20, 30), ["front", "left", "top"], size=128)

        def width(data):
            _, _, rows = pixels(data)
            row = rows[64]
            return sum(1 for i in range(0, len(row), 3) if row[i:i + 3] != b"\xff\xff\xff")

        front, left, top = width(got["front"]), width(got["left"]), width(got["top"])
        self.assertLess(front, left)
        self.assertLess(top, left)

    def test_axes_not_mirrored(self):
        # right x up points back at the camera in every view, and each
        # view's right is the axis a drawing would put there.
        import numpy as np

        want_right = {"front": (1, 0, 0), "back": (-1, 0, 0), "left": (0, -1, 0),
                      "right": (0, 1, 0), "top": (1, 0, 0), "bottom": (1, 0, 0)}
        for view in renderer.VIEWS:
            d, up, right = renderer.axes(view)
            np.testing.assert_array_equal(-d, np.cross(right, up), view)
            np.testing.assert_array_equal(want_right[view], right, view)

    def test_orientation_and_depth(self):
        # A tall column at -X on a low slab: from the front the column is at
        # the left, from the back at the right; from the top the column's
        # top, nearer the camera, is lighter than the slab's.
        from build123d import Box, Pos, export_step

        path = os.path.join(tempfile.mkdtemp(), "step.step")
        export_step(Pos(15, 0, 2) * Box(30, 10, 4) + Pos(2, 0, 10) * Box(4, 10, 20), path)
        got = self.render(path, ["front", "back", "top"], size=128)

        def top_row(data, x0, x1):
            _, _, rows = pixels(data)
            for y, row in enumerate(rows):
                if any(row[3 * x:3 * x + 3] != b"\xff\xff\xff" for x in range(x0, x1)):
                    return y
            return len(rows)

        # The column reaches higher (a smaller row) on its side.
        self.assertLess(top_row(got["front"], 0, 32), top_row(got["front"], 96, 128))
        self.assertLess(top_row(got["back"], 96, 128), top_row(got["back"], 0, 32))
        _, _, rows = pixels(got["top"])
        column, slab = rows[64][3 * 16:3 * 16 + 3], rows[64][3 * 96:3 * 96 + 3]
        self.assertGreater(sum(column), sum(slab))

    def test_odd_size(self):
        # 115 / 100 * 100 is less than 115 in floating point.
        for size in [115, 231]:
            w, h, _ = pixels(self.render(box_step(1, 2, 3), ["top"], size=size)["top"])
            self.assertEqual((size, size), (w, h))

    def test_nothing_faces_the_camera(self):
        import numpy as np

        # One triangle in the XY plane, facing +Z: the bottom view sees its back.
        tri = np.array([[(0, 0, 0), (1, 0, 0), (0, 1, 0)]], dtype=np.float64)
        renderer.project(tri, "top")
        with self.assertRaises(renderer.RenderError) as cm:
            renderer.project(tri, "bottom")
        self.assertIn("nothing faces the camera in the bottom view", str(cm.exception))

    def fonts_probe(self, guarded):
        """Imports matplotlib in a new Python and lists what reached the host.

        A fresh interpreter and an empty MPLCONFIGDIR make matplotlib list
        fonts as it does in an action. The spies sit below the guard: a
        process start goes through Popen, and os.walk lists through scandir.
        """
        import json
        import subprocess
        import sys

        code = """
import json, os, subprocess, sys
import matplotlib
data = os.path.abspath(matplotlib.get_data_path())
ran, listed = [], []
real_popen, real_scandir = subprocess.Popen, os.scandir
class Popen(real_popen):
    def __init__(self, args, *a, **k):
        ran.append(str(args))
        super().__init__(args, *a, **k)
def scandir(path="."):
    p = os.path.abspath(os.fspath(path))
    if p != data and not p.startswith(data + os.sep):
        listed.append(p)
    return real_scandir(path)
subprocess.Popen, os.scandir = Popen, scandir
if sys.argv[1] == "guarded":
    import renderer
    renderer.import_matplotlib()
else:
    import matplotlib.font_manager
print(json.dumps({"ran": ran, "listed": listed}))
"""
        env = dict(os.environ, MPLCONFIGDIR=tempfile.mkdtemp(), PYTHONPATH=os.pathsep.join(sys.path))
        out = subprocess.run([sys.executable, "-c", code, "guarded" if guarded else "bare"],
                             env=env, check=True, capture_output=True, text=True).stdout
        return json.loads(out.splitlines()[-1])

    def test_no_host_fonts(self):
        # Without the guard, matplotlib reaches for fc-list or the host's
        # font directories (each attempt counts, found or not).
        bare = self.fonts_probe(guarded=False)
        self.assertTrue(bare["ran"] or bare["listed"], bare)
        # With it, nothing is run and nothing outside its wheel is listed.
        self.assertEqual({"ran": [], "listed": []}, self.fonts_probe(guarded=True))

    def failure(self, args):
        with self.assertRaises(renderer.RenderError) as cm:
            renderer.main(args)
        return str(cm.exception)

    def test_bad_view(self):
        self.assertIn("the view must be one of", self.failure(["--step", "x.step", "--out", "side=a.png"]))

    def test_view_twice(self):
        self.assertIn("is given twice", self.failure(["--step", "x.step", "--out", "top=a.png", "--out", "top=b.png"]))

    def test_no_out(self):
        self.assertIn("no --out given", self.failure(["--step", "x.step"]))

    def test_bad_size(self):
        for size in ["8", "63", "4097"]:
            self.assertIn("want 64 to 4096", self.failure(["--step", "x.step", "--out", "top=a.png", "--size", size]))

    def test_not_step(self):
        d = tempfile.mkdtemp()
        bad = os.path.join(d, "bad.step")
        with open(bad, "w") as f:
            f.write("not a step file\n")
        msg = self.failure(["--step", bad, "--out", "top=" + os.path.join(d, "a.png")])
        self.assertIn(bad, msg)
        self.assertIn("cannot read it as STEP", msg)


if __name__ == "__main__":
    unittest.main()
