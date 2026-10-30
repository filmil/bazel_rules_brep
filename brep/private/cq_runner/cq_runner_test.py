# SPDX-License-Identifier: Apache-2.0
"""Tests of the CadQuery runner: shapes, files, messages."""

import ctypes
import os
import subprocess
import sys
import tempfile
import unittest


def preload_gl_libs():
    """Loads the GL and X11 libraries OCP needs, dependencies first.

    The runner gets them through LD_LIBRARY_PATH (the CAD toolchain); a test
    cannot set that for itself, as the loader reads it at start.
    """
    order = ["libexpat.so.1", "libmd.so.0", "libbsd.so.0", "libXau.so.6", "libXdmcp.so.6", "libxcb.so.1",
             "libX11.so.6", "libGLdispatch.so.0", "libGLX.so.0", "libGL.so.1"]
    paths = {os.path.basename(p): p for p in os.environ["BREP_GL_LIBS"].split()}
    for name in order:
        ctypes.CDLL(os.path.abspath(paths[name]), mode=ctypes.RTLD_GLOBAL)


preload_gl_libs()

import cq_runner  # noqa: E402 (after the libraries OCP needs)

cq_runner.preload_vtk()

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "testdata")


def part(name):
    return os.path.join(D, name)


class CqRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.epoch = os.environ.get("SOURCE_DATE_EPOCH")
        os.environ["SOURCE_DATE_EPOCH"] = "0"
        self.path = list(sys.path)

    def tearDown(self):
        self.tmp.cleanup()
        if self.epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = self.epoch
        sys.path[:] = self.path

    def out(self, name):
        return os.path.join(self.tmp.name, name)

    def summary(self, name, params="{}"):
        cq_runner.main(["--part", part(name), "--params", params, "--summary", self.out("s.txt")])
        with open(self.out("s.txt"), encoding="utf-8") as f:
            return f.read()

    def test_workplane(self):
        self.assertEqual("volume 6.000\nsize 1.000 2.000 3.000\n", self.summary("good.py"))

    def test_two_solids(self):
        self.assertEqual("volume 2.000\nsize 6.000 1.000 1.000\n", self.summary("two_solids.py"))

    def test_shape_and_params(self):
        self.assertIn("size 4.000 4.000 2.000", self.summary("shape.py", '{"r": 2}'))

    def failure(self, name, *extra):
        with self.assertRaises(cq_runner.PartError) as cm:
            cq_runner.main(["--part", part(name), "--summary", self.out("s.txt")] + list(extra))
        msg = str(cm.exception)
        self.assertIn(name, msg)
        return msg

    def test_no_build(self):
        self.assertIn("defines no build(params) function", self.failure("no_build.py"))

    def test_raises(self):
        self.assertIn("build() failed: ValueError: no such size", self.failure("raises.py"))

    def test_params(self):
        self.assertIn("--params is not JSON", self.failure("good.py", "--params", "{"))
        self.assertIn("--params must be a JSON object, not list", self.failure("good.py", "--params", "[]"))

    def test_bad_tolerances_before_the_script(self):
        # Checked first, with or without --stl: raises.py would fail otherwise.
        for flag, v in [("--stl-tolerance", "nan"), ("--stl-tolerance", "0"), ("--stl-angular-tolerance", "inf")]:
            self.assertIn("the STL tolerances must be positive and finite", self.failure("raises.py", flag, v))

    def test_bad_epoch_before_the_script(self):
        os.environ["SOURCE_DATE_EPOCH"] = "soon"
        self.assertIn("SOURCE_DATE_EPOCH='soon' is not a number", self.failure("raises.py"))

    def test_dependency_from_another_directory(self):
        cq_runner.main(["--part", part("uses_helper.py"), "--path", os.path.join(D, "lib"),
                        "--summary", self.out("s.txt")])
        with open(self.out("s.txt"), encoding="utf-8") as f:
            self.assertEqual("volume 8.000\nsize 2.000 2.000 2.000\n", f.read())

    def test_mixed_stack(self):
        self.assertIn("a Workplane that holds a Vector, not only shapes", self.failure("mixed_stack.py"))

    def test_loose_face(self):
        self.assertIn("the shape holds 1 face outside its solids", self.failure("loose_face.py"))

    def test_vtk_libs(self):
        # The libraries come from OCP's own list, so a new VTK or Python
        # changes nothing here.
        import importlib.util

        vtkdir = list(importlib.util.find_spec("vtkmodules").submodule_search_locations)[0]
        libs = cq_runner.vtk_libs(cq_runner.ocp_libraries(), vtkdir)
        self.assertIn("libvtkCommonCore.so", libs)
        self.assertIn("libvtkInteractionStyle.so", libs)  # needed by a bundled OCCT library
        self.assertTrue(any(n.startswith("libvtkWrappingPythonCore") for n in libs), libs)

    def test_not_a_shape(self):
        self.assertIn("returned 42, not a CadQuery Workplane or Shape", self.failure("not_shape.py"))

    def test_no_volume(self):
        self.assertIn("the shape has no volume (a Face)", self.failure("no_volume.py"))

    def test_empty_workplane(self):
        self.assertIn("a Workplane that holds no shape", self.failure("empty.py"))

    def test_step_and_stl(self):
        cq_runner.main(["--part", part("good.py"), "--name", "block", "--step", self.out("b.step"),
                        "--stl", self.out("b.stl")])
        with open(self.out("b.step"), encoding="latin-1") as f:
            text = f.read()
        self.assertTrue(text.startswith("ISO-10303-21;"))
        self.assertIn("FILE_NAME('block','1970-01-01T00:00:00'", text)
        self.assertIn("'cadquery'", text)
        self.assertNotIn(self.tmp.name, text)  # no path of the build
        with open(self.out("b.stl"), "rb") as f:
            stl = f.read()
        n = int.from_bytes(stl[80:84], "little")
        self.assertGreaterEqual(n, 12)
        self.assertEqual(84 + 50 * n, len(stl))

    def test_same_bytes_in_two_processes(self):
        # Bazel runs each action as a process of its own: that is the
        # comparison that matters.
        libdirs = sorted({os.path.dirname(os.path.abspath(p)) for p in os.environ["BREP_GL_LIBS"].split()})
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path), LD_LIBRARY_PATH=os.pathsep.join(libdirs),
                   HOME=self.tmp.name, XDG_CACHE_HOME=self.tmp.name)
        outs = []
        for i in range(2):
            step, stl = self.out("p%d.step" % i), self.out("p%d.stl" % i)
            subprocess.run([sys.executable, cq_runner.__file__, "--part", part("shape.py"), "--name", "c",
                            "--step", step, "--stl", stl], env=env, check=True)
            with open(step, "rb") as f, open(stl, "rb") as g:
                outs.append((f.read(), g.read()))
        self.assertEqual(outs[0], outs[1])


if __name__ == "__main__":
    unittest.main()
