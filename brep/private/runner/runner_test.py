# SPDX-License-Identifier: Apache-2.0
"""Tests of the CAD runner's checks and messages."""

import ctypes
import os
import sys
import tempfile
import unittest

import runner


def preload_gl_libs():
    """Loads the GL and X11 libraries OCP needs, dependencies first.

    The runner gets them through LD_LIBRARY_PATH (the CAD toolchain); a test
    cannot set that for itself, as the loader reads it at start. A library
    already loaded under its soname satisfies OCP's link to it.
    """
    order = ["libexpat.so.1", "libmd.so.0", "libbsd.so.0", "libXau.so.6", "libXdmcp.so.6", "libxcb.so.1",
             "libX11.so.6", "libGLdispatch.so.0", "libGLX.so.0", "libGL.so.1"]
    paths = {os.path.basename(p): p for p in os.environ["BREP_GL_LIBS"].split()}
    for name in order:
        ctypes.CDLL(os.path.abspath(paths[name]), mode=ctypes.RTLD_GLOBAL)


preload_gl_libs()

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")


def part(name):
    return os.path.join(D, name)


class RunnerTest(unittest.TestCase):
    def test_good(self):
        out = os.path.join(tempfile.mkdtemp(), "s.txt")
        runner.main(["--part", part("good.py"), "--summary", out])
        with open(out, encoding="utf-8") as f:
            self.assertEqual("volume 6.000\nsize 1.000 2.000 3.000\n", f.read())

    def test_dataclass_in_part(self):
        # The part module is in sys.modules while it runs.
        self.assertAlmostEqual(1.0, runner.build(part("dataclass_part.py"), {}).volume)

    def failure(self, name, params="{}"):
        with self.assertRaises(runner.PartError) as cm:
            runner.main(["--part", part(name), "--params", params])
        msg = str(cm.exception)
        self.assertIn(name, msg)
        return msg

    def test_no_build(self):
        self.assertIn("defines no build(params) function", self.failure("no_build.py"))

    def test_not_a_shape(self):
        self.assertIn("returned 42, not a build123d shape", self.failure("not_shape.py"))

    def test_no_volume(self):
        self.assertIn("has no volume", self.failure("flat.py"))

    def test_raises(self):
        self.assertIn("build() failed: ValueError: broken on purpose", self.failure("raises.py"))

    def test_bad_import(self):
        self.assertIn("importing it failed: ModuleNotFoundError", self.failure("bad_import.py"))

    def test_params_not_json(self):
        self.assertIn("--params is not JSON", self.failure("good.py", "{size"))

    def test_params_not_object(self):
        self.assertIn("must be a JSON object, not list", self.failure("good.py", "[1]"))


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        old = os.environ.get("SOURCE_DATE_EPOCH")

        def restore():
            if old is None:
                os.environ.pop("SOURCE_DATE_EPOCH", None)
            else:
                os.environ["SOURCE_DATE_EPOCH"] = old

        self.addCleanup(restore)

    def export(self, epoch="0", extra=(), part_name="good.py"):
        d = tempfile.mkdtemp(dir=self.tmp.name)
        step, stl = os.path.join(d, "x.step"), os.path.join(d, "x.stl")
        os.environ["SOURCE_DATE_EPOCH"] = epoch
        runner.main(["--part", part(part_name), "--name", "bracket", "--step", step, "--stl", stl] + list(extra))
        with open(step, "rb") as f:
            step_bytes = f.read()
        with open(stl, "rb") as f:
            stl_bytes = f.read()
        return d, step_bytes, stl_bytes

    def test_same_bytes_twice(self):
        _, step1, stl1 = self.export()
        _, step2, stl2 = self.export()
        self.assertEqual(step1, step2)
        self.assertEqual(stl1, stl2)

    def test_step_header(self):
        d, step, _ = self.export()
        text = step.decode("latin-1")
        self.assertTrue(text.startswith("ISO-10303-21;"))
        self.assertIn("FILE_NAME('bracket','1970-01-01T00:00:00'", text)
        self.assertIn("build123d", text)
        self.assertNotIn(d, text)  # no path of the build
        self.assertNotIn(self.tmp.name, text)

    def test_epoch(self):
        _, step, _ = self.export(epoch="86400")
        self.assertIn("'1970-01-02T00:00:00'", step.decode("latin-1"))
        for bad in ["soon", "-1"]:
            with self.assertRaises(runner.PartError) as cm:
                self.export(epoch=bad)
            self.assertIn("good.py", str(cm.exception))

    def test_stl(self):
        d, _, stl = self.export()
        # Binary STL: an 80-byte header, a triangle count, 50 bytes each.
        n = int.from_bytes(stl[80:84], "little")
        self.assertGreaterEqual(n, 12)  # a box has at least 12 triangles
        self.assertEqual(84 + 50 * n, len(stl))
        self.assertNotIn(self.tmp.name.encode(), stl[:80])  # no path in the header

    def test_bad_tolerances(self):
        for flag, v in [("--stl-tolerance", "nan"), ("--stl-angular-tolerance", "0"), ("--stl-angular-tolerance", "inf")]:
            with self.assertRaises(runner.PartError) as cm:
                self.export(extra=[flag, v])
            self.assertIn("positive and finite", str(cm.exception))

    def test_dependency_from_another_directory(self):
        # uses_helper.py imports helper, which is in testdata/lib, given by
        # --path. Without it first: once imported, helper stays in this
        # process (a build runs the runner afresh for each part).
        with self.assertRaises(runner.PartError):
            self.export(part_name="uses_helper.py")
        _, step, _ = self.export(extra=["--path", os.path.join(D, "lib")], part_name="uses_helper.py")
        self.assertTrue(step.startswith(b"ISO-10303-21;"))


if __name__ == "__main__":
    unittest.main()
