# SPDX-License-Identifier: Apache-2.0
"""Tests of the CAD measurer: what it measures, what it writes, its errors."""

import ctypes
import math
import os
import tempfile
import unittest


def preload_gl_libs():
    """Loads the GL and X11 libraries OCP needs, dependencies first.

    The measurer gets them through LD_LIBRARY_PATH (the CAD toolchain); a
    test cannot set that for itself, as the loader reads it at start.
    """
    order = ["libexpat.so.1", "libmd.so.0", "libbsd.so.0", "libXau.so.6", "libXdmcp.so.6", "libxcb.so.1",
             "libX11.so.6", "libGLdispatch.so.0", "libGLX.so.0", "libGL.so.1"]
    paths = {os.path.basename(p): p for p in os.environ["BREP_GL_LIBS"].split()}
    for name in order:
        ctypes.CDLL(os.path.abspath(paths[name]), mode=ctypes.RTLD_GLOBAL)


preload_gl_libs()

import measurer  # noqa: E402 (after the libraries OCP needs)


def step_of(shape):
    """shape as a STEP file; returns its path."""
    from build123d import export_step

    path = os.path.join(tempfile.mkdtemp(), "shape.step")
    export_step(shape, path)
    return path


def run(path):
    out = os.path.join(tempfile.mkdtemp(), "m.txt")
    measurer.main(["--step", path, "--out", out])
    with open(out, encoding="utf-8") as f:
        return f.read()


def parse(text):
    return {line.split()[0]: [float(v) for v in line.split()[1:]] for line in text.splitlines()}


class MeasurerTest(unittest.TestCase):
    def test_box(self):
        from build123d import Box, Pos

        got = parse(run(step_of(Pos(1, 2, 3) * Box(10, 20, 30))))
        want = {
            "volume": [6000], "area": [2200], "center": [1, 2, 3],
            "min": [-4, -8, -12], "max": [6, 12, 18],
            "solids": [1], "faces": [6], "edges": [12], "vertices": [8],
        }
        self.assertEqual(list(want), list(got))
        for k, vs in want.items():
            for w, g in zip(vs, got[k]):
                self.assertAlmostEqual(w, g, places=6, msg=k)

    def test_cylinder(self):
        from build123d import Cylinder

        got = parse(run(step_of(Cylinder(5, 10))))
        self.assertAlmostEqual(math.pi * 25 * 10, got["volume"][0], places=6)
        # The box is from the geometry, not widened by tolerances or a mesh.
        for w, g in zip([-5, -5, -5, 5, 5, 5], got["min"] + got["max"]):
            self.assertAlmostEqual(w, g, places=6)
        self.assertEqual([3], got["faces"])

    def test_two_solids(self):
        from build123d import Box, Compound, Pos

        got = parse(run(step_of(Compound([Box(1, 1, 1), Pos(5, 0, 0) * Box(1, 1, 1)]))))
        self.assertEqual([2], got["solids"])
        self.assertEqual([12], got["faces"])
        self.assertAlmostEqual(2, got["volume"][0], places=6)

    def test_text(self):
        self.assertEqual("volume 1.500000\ncenter 0.000000 0.100000 -2.000000\nfaces 6\n",
                         measurer.text([("volume", [1.5]), ("center", [-1e-9, 0.1, -2.0]), ("faces", [6])]))

    def test_same_text_twice(self):
        from build123d import Box

        path = step_of(Box(3, 4, 5))
        self.assertEqual(run(path), run(path))

    def test_no_shape(self):
        # A valid STEP file with an empty DATA section. The message names the
        # file, as every message of the measurer does.
        d = tempfile.mkdtemp()
        empty = os.path.join(d, "empty.step")
        with open(empty, "w") as f:
            f.write("ISO-10303-21;\nHEADER;\nFILE_DESCRIPTION((''),'2;1');\n"
                    "FILE_NAME('','',(''),(''),'','','');\nFILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
                    "ENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")
        with self.assertRaises(measurer.MeasureError) as cm:
            measurer.main(["--step", empty, "--out", os.path.join(d, "m.txt")])
        self.assertTrue(str(cm.exception).startswith(empty + ": "), str(cm.exception))
        self.assertIn("the file holds no shape", str(cm.exception))
        self.assertFalse(os.path.exists(os.path.join(d, "m.txt")))

    def test_not_step(self):
        d = tempfile.mkdtemp()
        bad = os.path.join(d, "bad.step")
        with open(bad, "w") as f:
            f.write("not a step file\n")
        with self.assertRaises(measurer.MeasureError) as cm:
            measurer.main(["--step", bad, "--out", os.path.join(d, "m.txt")])
        self.assertIn(bad, str(cm.exception))
        self.assertIn("cannot read it as STEP", str(cm.exception))


class MinWallTest(unittest.TestCase):
    def wall(self, shape, grid="5"):
        out = os.path.join(tempfile.mkdtemp(), "m.txt")
        measurer.main(["--step", step_of(shape), "--out", out, "--min-wall", grid])
        with open(out, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertTrue(lines[-1].startswith("min_wall "), lines[-1])
        self.assertEqual("vertices", lines[-2].split()[0])  # the agreed order, then min_wall
        return float(lines[-1].split()[1])

    def test_solid_box(self):
        from build123d import Box

        self.assertAlmostEqual(10, self.wall(Box(10, 20, 30)), places=6)

    def test_plate(self):
        from build123d import Box

        self.assertAlmostEqual(2, self.wall(Box(40, 30, 2)), places=6)

    def test_hollow_box(self):
        # A 20 mm cube with a 18 mm cube taken out of it: 1 mm walls.
        from build123d import Box

        self.assertAlmostEqual(1, self.wall(Box(20, 20, 20) - Box(18, 18, 18)), places=6)

    def test_thin_rib(self):
        # A 5 mm thick base with a 0.8 mm rib on top: the rib is thinnest.
        from build123d import Box, Pos

        shape = Box(30, 30, 5) + Pos(0, 0, 7.5) * Box(30, 0.8, 10)
        self.assertAlmostEqual(0.8, self.wall(shape), places=6)

    def test_cylinder_wall(self):
        # A tube, outer radius 5, inner 4: a 1 mm wall around the curve.
        from build123d import Cylinder

        self.assertAlmostEqual(1, self.wall(Cylinder(5, 20) - Cylinder(4, 20)), places=3)

    def test_same_twice_and_off_by_default(self):
        from build123d import Box

        s = Box(4, 5, 6)
        self.assertEqual(self.wall(s), self.wall(s))
        self.assertNotIn("min_wall", run(step_of(s)))  # only with --min-wall

    def test_bad_grid(self):
        for g in ["-1", "101"]:
            with self.assertRaises(SystemExit):
                measurer.main(["--step", "x", "--out", "y", "--min-wall", g])

    def test_no_wall(self):
        # A lone face: no ray leaves a solid, so there is no wall.
        from build123d import Rectangle

        with self.assertRaises(measurer.MeasureError) as cm:
            self.wall(Rectangle(10, 10))
        self.assertIn("no wall found", str(cm.exception))

    def test_two_touching_solids(self):
        # Two cubes sharing a face: the shared face is measured once, and
        # each cube's own thickness, 10 mm, is the wall.
        from build123d import Box, Compound, Pos

        self.assertAlmostEqual(10, self.wall(Compound([Box(10, 10, 10), Pos(10, 0, 0) * Box(10, 10, 10)])), places=6)


if __name__ == "__main__":
    unittest.main()
