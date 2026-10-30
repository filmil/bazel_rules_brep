# SPDX-License-Identifier: Apache-2.0
"""Tests of the CAD runner's checks and messages."""

import os
import sys
import tempfile
import unittest

import runner

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


if __name__ == "__main__":
    unittest.main()
