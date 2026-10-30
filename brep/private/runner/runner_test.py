# SPDX-License-Identifier: Apache-2.0
"""Tests of the CAD runner's checks and messages."""

import ctypes
import json
import os
import subprocess
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


class AssemblyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["SOURCE_DATE_EPOCH"] = "0"
        self.addCleanup(os.environ.pop, "SOURCE_DATE_EPOCH", None)

    def part_step(self, name):
        out = os.path.join(self.tmp.name, name + ".step")
        runner.main(["--part", part("good.py"), "--name", name, "--step", out])
        return out

    def assemble(self, children):
        spec = os.path.join(self.tmp.name, "spec.json")
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({"name": "stack", "children": children}, f)
        out = os.path.join(self.tmp.name, "stack.step")
        runner.main(["--assemble", spec, "--step", out])
        with open(out, "rb") as f:
            return f.read().decode("latin-1")

    def test_named_children(self):
        a = self.part_step("a")
        text = self.assemble([
            {"name": "lower", "step": a, "pos": [0, 0, 0], "rot": [0, 0, 0]},
            {"name": "upper", "step": a, "pos": [0, 0, 10], "rot": [0, 0, 90]},
        ])
        self.assertIn("FILE_NAME('stack','1970-01-01T00:00:00'", text)
        for name in ["'lower'", "'upper'"]:
            self.assertIn(name, text)
        self.assertNotIn(self.tmp.name, text)

    def test_same_bytes_in_two_processes(self):
        # OCCT numbers assembly links with a counter that lives as long as
        # the process; Bazel runs each action as a process of its own, so
        # that is the comparison that matters.
        a = self.part_step("a")
        spec = os.path.join(self.tmp.name, "spec.json")
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({"name": "stack", "children": [
                {"name": "one", "step": a, "pos": [1, 2, 3], "rot": [10, 20, 30]}]}, f)
        libdirs = sorted({os.path.dirname(os.path.abspath(p)) for p in os.environ["BREP_GL_LIBS"].split()})
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path), LD_LIBRARY_PATH=os.pathsep.join(libdirs))
        outs = []
        for i in range(2):
            out = os.path.join(self.tmp.name, "stack%d.step" % i)
            subprocess.run([sys.executable, runner.__file__, "--assemble", spec, "--step", out], env=env, check=True)
            with open(out, "rb") as f:
                outs.append(f.read())
        self.assertEqual(outs[0], outs[1])

    def test_placement(self):
        # good.py is a 1 x 2 x 3 box about the origin. rot is intrinsic X-Y-Z:
        # [90, 90, 0] turns its X edge to world Y, Y to Z, and Z to X, so
        # the bounding box is 3 x 1 x 2. Extrinsic X-Y-Z would give 2 x 3 x 1.
        a = self.part_step("a")
        asm = runner.assemble({"name": "s", "children": [
            {"name": "still", "step": a, "pos": [0, 0, 0], "rot": [0, 0, 0]},
            {"name": "turned", "step": a, "pos": [100, 0, 0], "rot": [90, 90, 0]},
        ]})
        sizes = {}
        for child in asm.children:
            bb = child.bounding_box()
            sizes[child.label] = (bb.center(), [round(v, 6) for v in (bb.size.X, bb.size.Y, bb.size.Z)])
        self.assertEqual([1, 2, 3], sizes["still"][1])
        self.assertEqual([3, 1, 2], sizes["turned"][1])
        self.assertAlmostEqual(100, sizes["turned"][0].X, places=6)

    def test_failures(self):
        with self.assertRaises(runner.PartError) as cm:
            self.assemble([])
        self.assertIn("no children", str(cm.exception))
        with self.assertRaises(runner.PartError) as cm:
            self.assemble([{"name": "x", "step": "/nonexistent.step", "pos": [0, 0, 0], "rot": [0, 0, 0]}])
        self.assertIn("child x", str(cm.exception))
        with self.assertRaises(runner.PartError) as cm:
            self.assemble([{"name": "x", "pos": [0, 0, 0]}])
        self.assertIn("a child lacks", str(cm.exception))
        bad = os.path.join(self.tmp.name, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{nope")
        with self.assertRaises(runner.PartError) as cm:
            runner.main(["--assemble", bad, "--step", os.path.join(self.tmp.name, "o.step")])
        self.assertIn("bad.json: reading the spec failed", str(cm.exception))
        with self.assertRaises(SystemExit):
            runner.main(["--assemble", bad, "--step", "o.step", "--stl", "o.stl"])


if __name__ == "__main__":
    unittest.main()
