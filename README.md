<!-- SPDX-License-Identifier: Apache-2.0 -->
[![Test](https://github.com/filmil/bazel_rules_brep/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/filmil/bazel_rules_brep/actions/workflows/test.yml)
[![Tag and Release](https://github.com/filmil/bazel_rules_brep/actions/workflows/tag-and-release.yml/badge.svg)](https://github.com/filmil/bazel_rules_brep/releases)
[![Publish to my Bazel registry](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish.yml/badge.svg)](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish.yml)
[![Publish on Bazel Central Registry](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish-bcr.yml/badge.svg)](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish-bcr.yml)

# hdlf_rules_brep

Hermetic Bazel rules for mechanical parts written as build123d scripts.
The build turns each part script into STEP and STL files, combines parts
into assemblies, renders them to PNG, and checks them: size, volume, wall
thickness, overlaps between parts, and the fit of a circuit board in its
enclosure.
Every tool comes from a Bazel toolchain, so nothing needs to be installed
on the machine, and two builds give byte-identical outputs.

This repository is new. The rules arrive in milestones; see the
[issues](https://github.com/filmil/bazel_rules_brep/issues) and the
[milestones](https://github.com/filmil/bazel_rules_brep/milestones).
Only Linux x86_64 hosts are supported.

## Using it

```starlark
bazel_dep(name = "hdlf_rules_brep", version = "0.0.1")
```

`.bazelrc`, while the module is only in the filmil registry:

```
common --registry=https://raw.githubusercontent.com/filmil/bazel-registry/main
common --registry=https://bcr.bazel.build
```

The rules are documented in [docs/defs.md](docs/defs.md). A part:

```starlark
load("@hdlf_rules_brep//brep:defs.bzl", "cad_part", "cad_render", "geometry_equal_test")

cad_part(
    name = "bracket",
    src = "bracket.py",  # build(params) returns a solid, or a compound of solids
    params = {"thickness": "3"},
)
```

`bazel build :bracket` writes `bracket.step` and `bracket.stl`. Its views,
as PNG, with no OpenGL:

```starlark
cad_render(
    name = "bracket_views",
    src = ":bracket",
)
```

`bazel build :bracket_views` writes `bracket_views_front.png`, and the
back, left, right, top and bottom views. To check a part against a golden
STEP file from another platform, by measurement within tolerances:

```starlark
geometry_equal_test(
    name = "bracket_geometry_test",
    a = ":bracket",
    b = "bracket_golden.step",
)
```

A part checked against limits (volume, size, thinnest wall), an assembly
of parts with no two overlapping, and a board in its enclosure:

```starlark
load("@hdlf_rules_brep//brep:defs.bzl", "cad_assembly", "cad_check_test", "interference_test", "pcb_fit_test")

cad_check_test(
    name = "bracket_check_test",
    part = ":bracket",
    max_size = ["40", "30", "35"],  # mm, X Y Z
    max_volume = "5000",  # mm^3
    min_wall = "1.5",  # mm
)

# :base and :enclosure are cad_parts, as :bracket. pos is in mm; rot is
# in degrees, about X, then the turned Y, then the turned Z.
cad_assembly(
    name = "stand",
    parts = {
        ":base": '{"pos": [0, 0, 0]}',
        ":bracket": '[{"pos": [10, 0, 5]}, {"pos": [40, 0, 5], "rot": [0, 0, 180]}]',
    },
)

interference_test(
    name = "stand_interference_test",
    assembly = ":stand",
)

pcb_fit_test(
    name = "board_fit_test",
    board = "@my_board//:step",  # kicad_step of hdlf_rules_kicad, or any STEP
    enclosure = ":enclosure",  # a cad_part
    board_placement = '{"pos": [0, 0, 4]}',
    min_clearance_mm = "0.5",
)
```

A CadQuery script builds the same way, with `library = "cadquery"`:

```starlark
cad_part(
    name = "bracket_cq",
    src = "bracket_cq.py",  # build(params) returns a Workplane or a Shape
    library = "cadquery",
)
```

CadQuery 2.8 needs an older OCCT than build123d, so it has a toolchain and
a locked set of wheels of its own (`requirements_cadquery_lock.txt`):
467 MB, VTK, casadi and numba among them. Bazel fetches them only for a
build that has a CadQuery part.

The CAD runners are Python (build123d or CadQuery, and OCCT) on the
hermetic interpreter of rules_python; hdlf_rules_brep registers them.
Add this to `.bazelrc`, or rules_python starts it through the host's
`python3`:

```
common --@rules_python//python/config_settings:bootstrap_impl=script
```

and, so that the flag's label resolves, to `MODULE.bazel`:

```starlark
bazel_dep(name = "rules_python", version = "2.4.6")
```

Under Bazel 8, rules_python asks
for a C++ toolchain even though nothing is compiled, so a build that finds
none on the host needs one, such as hermetic_cc_toolchain (see
`integration/MODULE.bazel`). Bazel 9 does not ask.

## Building

```sh
bazel build //...
bazel test //...
cd integration && bazel test //...
```

After changing a `.bzl` file, regenerate the documentation with
`bazel run //docs:update_docs`.
Format with `bazel run //tools:buildifier`.

## Releasing

The operator runs the `Tag and Release` workflow
(`.github/workflows/tag-and-release.yml`, `workflow_dispatch`).
It picks the next version from the conventional commits since the last
tag, makes the tag, the release and its source archive, and opens one
pull request on the filmil registry and one on the Bazel Central Registry.
It needs the repository secret `BCR_PUBLISH_TOKEN`.

None of the modules published here are published with any sort of guarantee
whatsoever. Use at your own risk.

See the overall description at the [project page][pp].

[pp]: https://hdlfactory.com/post/2025/09/29/getting-ready-for-the-brave-new-bazel-modules-world/

## Licenses

This repository is under the Apache License 2.0 (`LICENSE`).
The prebuilt tools and libraries that the build downloads, with their
versions, sources and licenses:

* Python 3.12, the hermetic interpreter of rules_python 2.4.6
  (python-build-standalone, https://github.com/astral-sh/python-build-standalone):
  PSF License.
* build123d 0.13.0 (Apache 2.0) and OCP, OCCT's Python binding, as
  cadquery-ocp-novtk 8.0.1.1.0 wheels (LGPL 2.1 with the OCCT exception),
  with their dependencies, pinned by hash in `requirements_lock.txt`.
* CadQuery 2.8.0 (Apache 2.0) and its OCP, as cadquery-ocp 7.9.3.1.1
  wheels (LGPL 2.1 with the OCCT exception), with VTK 9.6.2 (BSD 3-clause)
  and their other dependencies, pinned by hash in
  `requirements_cadquery_lock.txt`. Fetched only for CadQuery parts.
* The GL, X11 and expat libraries OCP loads, from Debian 11 packages pinned
  by sha256 (`brep/private/gl_libs.bzl`): libglvnd (MIT-style), libX11,
  libxcb, libXau, libXdmcp and expat (MIT), libbsd and libmd (BSD and
  public domain). Each package's `copyright` file has the details.
* The Go SDK (go1.26.7 with rules_go 0.64.2, https://go.dev):
  BSD-3-Clause. rules_go downloads it to build this module's checkers
  from source.
