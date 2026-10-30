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

    def pairs(self, kids):
        report = runner.interference(runner.assemble({"name": "s", "children": kids}))
        out = {}
        for line in report.splitlines():
            f = line.split("\t")
            self.assertEqual("pair", f[0])
            out[(f[1], f[2])] = float(f[3])
        return out

    def test_interference(self):
        # good.py is a 1 x 2 x 3 box about the origin (volume 6).
        a = self.part_step("a")
        got = self.pairs([
            {"name": "base", "step": a, "pos": [0, 0, 0], "rot": [0, 0, 0]},
            {"name": "half in", "step": a, "pos": [0.5, 0, 0], "rot": [0, 0, 0]},
            {"name": "touching", "step": a, "pos": [-1, 0, 0], "rot": [0, 0, 0]},
            {"name": "far", "step": a, "pos": [50, 0, 0], "rot": [0, 0, 0]},
        ])
        self.assertEqual(6, len(got))
        self.assertAlmostEqual(3.0, got[("base", "half in")], places=6)  # half of 6
        self.assertEqual(0.0, got[("base", "touching")])  # a shared face
        self.assertEqual(0.0, got[("base", "far")])

    def test_contact_and_rotation(self):
        # Unit cubes: touching along an edge and at a corner share nothing;
        # one turned 45 degrees about Z, centered on another, shares the
        # octagon prism they have in common, 2 * (sqrt(2) - 1) = 0.828...
        out = os.path.join(self.tmp.name, "u.step")
        runner.main(["--part", part("unit_cube.py"), "--name", "u", "--step", out])
        got = self.pairs([
            {"name": "c", "step": out, "pos": [0, 0, 0], "rot": [0, 0, 0]},
            {"name": "edge", "step": out, "pos": [1, 1, 0], "rot": [0, 0, 0]},
            {"name": "corner", "step": out, "pos": [1, 1, 1], "rot": [0, 0, 0]},
            {"name": "turned", "step": out, "pos": [0, 0, 0], "rot": [0, 0, 45]},
        ])
        self.assertEqual(0.0, got[("c", "edge")])
        self.assertEqual(0.0, got[("c", "corner")])
        self.assertAlmostEqual(2 * (2 ** 0.5 - 1), got[("c", "turned")], places=6)

    def test_part_of_two_solids(self):
        # A part of two cubes 3 mm apart; a unit cube placed on the second
        # overlaps it alone, by half.
        two = os.path.join(self.tmp.name, "two.step")
        runner.main(["--part", part("two_cubes.py"), "--name", "two", "--step", two])
        one = os.path.join(self.tmp.name, "one.step")
        runner.main(["--part", part("unit_cube.py"), "--name", "one", "--step", one])
        got = self.pairs([
            {"name": "two", "step": two, "pos": [0, 0, 0], "rot": [0, 0, 0]},
            {"name": "one", "step": one, "pos": [3.5, 0, 0], "rot": [0, 0, 0]},
        ])
        self.assertAlmostEqual(0.5, got[("two", "one")], places=6)

    def test_interference_cli(self):
        a = self.part_step("a")
        spec = os.path.join(self.tmp.name, "spec.json")
        with open(spec, "w", encoding="utf-8") as f:
            json.dump({"name": "s", "children": [
                {"name": "x", "step": a, "pos": [0, 0, 0], "rot": [0, 0, 0]},
                {"name": "y", "step": a, "pos": [0.5, 0, 0], "rot": [0, 0, 0]}]}, f)
        out = os.path.join(self.tmp.name, "r.txt")
        runner.main(["--interference", spec, "--report", out])
        with open(out, encoding="utf-8") as f:
            line = f.read()
        self.assertTrue(line.startswith("pair\tx\ty\t3.0"), line)
        for extra in (["--step", "o"], ["--name", "n"], ["--params", "{}x"], []):
            argv = ["--interference", spec] + (["--report", out] if extra else []) + extra
            with self.assertRaises(SystemExit):
                runner.main(argv)
        with self.assertRaises(SystemExit):
            runner.main(["--assemble", spec, "--step", "o", "--report", out])

    def step(self, script, params):
        out = os.path.join(self.tmp.name, "%s-%d.step" % (script, abs(hash(json.dumps(params, sort_keys=True)))))
        runner.main(["--part", part(script), "--params", json.dumps(params), "--name", "x", "--step", out])
        return out

    def fit(self, board=None, tray=None, z=4.0, rot=(0, 0, 0), cli=False):
        spec = {"board": self.step("board.py", board or {}), "enclosure": self.step("tray.py", tray or {}), "pos": [0, 0, z], "rot": list(rot)}
        if cli:
            path = os.path.join(self.tmp.name, "fit.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(spec, f)
            out = os.path.join(self.tmp.name, "fit.txt")
            runner.main(["--fit", path, "--report", out])
            with open(out, encoding="utf-8") as f:
                report = f.read()
        else:
            report = runner.fit(spec)
        got = {"hole": [], "mount": []}
        for line in report.splitlines():
            f = line.split("\t")
            if f[0] == "hole":
                got["hole"].append(tuple(round(float(v), 6) for v in f[1:]))
            elif f[0] == "mount":
                got["mount"].append(tuple(round(float(v), 6) for v in f[1:4]) + (f[4],))
            else:
                got[f[0]] = float(f[1])
        got["hole"].sort()
        got["mount"].sort()
        return got

    HOLES = [(-20, -10, 1.6), (-20, 10, 1.6), (20, -10, 1.6), (20, 10, 1.6)]

    def test_fit(self):
        got = self.fit(cli=True)
        self.assertEqual(0.0, got["overlap"])  # it rests on the bosses
        self.assertAlmostEqual(5.0, got["clearance"], places=6)  # 5 mm to each wall
        self.assertEqual(self.HOLES, got["hole"])
        # Each boss: its hole for the screw, and its outside (too wide to count).
        for x, y, _ in self.HOLES:
            self.assertIn((x, y, 1.25, "hole"), got["mount"])
            self.assertIn((x, y, 2.5, "hole"), got["mount"])
        self.assertEqual(8, len(got["mount"]))

    def test_turned_half_way(self):
        got = self.fit(rot=(0, 0, 180))
        self.assertEqual(0.0, got["overlap"])
        self.assertAlmostEqual(5.0, got["clearance"], places=6)
        self.assertEqual(self.HOLES, got["hole"])

    def test_moved_hole(self):
        got = self.fit(board={"shift": 1})
        self.assertIn((-19, -10, 1.6), got["hole"])
        self.assertNotIn((-19, -10), {m[:2] for m in got["mount"]})

    def test_board_in_the_floor(self):
        got = self.fit(z=-0.5)  # sunk 0.5 mm into the floor and the bosses
        self.assertGreater(got["overlap"], 0.0)

    def test_notch_is_no_hole(self):
        # A half-round notch in the edge is part of the outline, not a hole:
        # it comes 2 mm closer to the wall.
        got = self.fit(board={"notch": True})
        self.assertEqual(self.HOLES, got["hole"])
        self.assertAlmostEqual(5.0, got["clearance"], places=6)

    def test_parts_on_the_board(self):
        # A board with parts, as a kicad_step: the holes and the outline come
        # from the board alone, and the tall can, 10 mm up, does not pull the
        # walls into the clearance.
        got = self.fit(board={"parts": True})
        self.assertEqual(0.0, got["overlap"])
        self.assertAlmostEqual(5.0, got["clearance"], places=6)
        self.assertEqual(self.HOLES, got["hole"])

    def test_pins(self):
        # Pins up through the holes are mounts, not walls: the clearance is
        # still to the walls. The solid bosses under them are supports.
        got = self.fit(tray={"pins": True})
        self.assertEqual(0.0, got["overlap"])
        self.assertAlmostEqual(5.0, got["clearance"], places=6)
        self.assertEqual(sorted((x, y, 1.5, "pin") for x, y, _ in self.HOLES), got["mount"])

    def test_no_walls(self):
        got = self.fit(tray={"floor": True})
        self.assertEqual(float("inf"), got["clearance"])
        self.assertEqual(8, len(got["mount"]))

    def test_far_mounts(self):
        # Lifted 1 mm off the bosses, the board has no mounts.
        got = self.fit(z=5.0)
        self.assertEqual([], got["mount"])

    def test_bad_spec(self):
        for spec, msg in [
            ([], "must be a JSON object"),
            ({"enclosure": "e", "pos": [0, 0, 0], "rot": [0, 0, 0]}, "board must be a file name"),
            ({"board": "b", "enclosure": "e", "pos": [0, 0], "rot": [0, 0, 0]}, "pos must be 3 numbers"),
            ({"board": "b", "enclosure": "e", "pos": [0, 0, 0], "rot": [0, "x", 0]}, "rot must be 3 numbers"),
        ]:
            with self.assertRaises(runner.PartError) as cm:
                runner.fit(spec)
            self.assertIn(msg, str(cm.exception))

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
