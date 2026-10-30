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


if __name__ == "__main__":
    unittest.main()
