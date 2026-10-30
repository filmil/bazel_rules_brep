<!-- SPDX-License-Identifier: Apache-2.0 -->
[![Test](https://github.com/filmil/bazel_rules_brep/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/filmil/bazel_rules_brep/actions/workflows/test.yml)
[![Tag and Release](https://github.com/filmil/bazel_rules_brep/actions/workflows/tag-and-release.yml/badge.svg)](https://github.com/filmil/bazel_rules_brep/releases)
[![Publish to my Bazel registry](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish.yml/badge.svg)](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish.yml)
[![Publish on Bazel Central Registry](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish-bcr.yml/badge.svg)](https://github.com/filmil/bazel_rules_brep/actions/workflows/publish-bcr.yml)

# rules_brep

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
bazel_dep(name = "rules_brep", version = "0.1.0")
```

`.bazelrc`, while the module is only in the filmil registry:

```
common --registry=https://raw.githubusercontent.com/filmil/bazel-registry/main
common --registry=https://bcr.bazel.build
```

The rules are documented in [docs/defs.md](docs/defs.md). A part:

```starlark
load("@rules_brep//brep:defs.bzl", "cad_part")

cad_part(
    name = "bracket",
    src = "bracket.py",  # defines build(params) -> a build123d solid
    params = {"thickness": "3"},
)
```

`bazel build :bracket` writes `bracket.step` and `bracket.stl`.

The CAD runner is Python (build123d and OCCT) on the hermetic interpreter
of rules_python; rules_brep registers it. Add this to `.bazelrc`, or
rules_python starts it through the host's `python3`:

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
Prebuilt tools and libraries that the build downloads are listed here, with
their versions, sources and licenses, as they are added.

* Python 3.12, the hermetic interpreter of rules_python
  (python-build-standalone): PSF License.
* build123d 0.13.0 (Apache 2.0) and OCP, OCCT's Python binding, as
  cadquery-ocp-novtk 8.0.1.1.0 wheels (LGPL 2.1 with the OCCT exception),
  with their dependencies, pinned by hash in `requirements_lock.txt`.
* The GL, X11 and expat libraries OCP loads, from Debian 11 packages pinned
  by sha256 (`brep/private/gl_libs.bzl`): libglvnd (MIT-style), libX11,
  libxcb, libXau, libXdmcp and expat (MIT), libbsd and libmd (BSD and
  public domain). Each package's `copyright` file has the details.
