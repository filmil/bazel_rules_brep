<!-- Generated with Stardoc: http://skydoc.bazel.build -->

Public API of rules_brep.

Load every rule from this file:

```starlark
load("@rules_brep//brep:defs.bzl", "determinism_test", "swap_test", "tool_toolchain")
```

The rules arrive in milestone M4 (see the issues of
https://github.com/filmil/bazel_rules_brep). This file is the only public
entry point; everything under `//brep/private` may change without notice.

<a id="cad_part"></a>

## cad_part

<pre>
load("@rules_brep//brep:defs.bzl", "cad_part")

cad_part(<a href="#cad_part-name">name</a>, <a href="#cad_part-deps">deps</a>, <a href="#cad_part-src">src</a>, <a href="#cad_part-params">params</a>, <a href="#cad_part-stl_angular_tolerance">stl_angular_tolerance</a>, <a href="#cad_part-stl_tolerance">stl_tolerance</a>)
</pre>

A part script, built into `<name>.step` and `<name>.stl`.

```starlark
cad_part(
    name = "bracket",
    src = "bracket.py",
    params = {"thickness": "3"},
)
```

The script defines `build(params: dict)`, which returns a build123d solid
(or a compound of solids).
It runs with build123d and OCCT on the CAD toolchain.

* `<name>.step` names the shape `<name>`, and its header time is
  `--@rules_brep//brep:source_date_epoch` (default 1970-01-01).
* `<name>.stl` is binary, meshed with parallel meshing off, so the same
  part gives the same bytes on the same platform. Across platforms the
  geometry may differ in the last digits; `geometry_equal_test` compares
  by tolerance (spec D3).

**ATTRIBUTES**


| Name  | Description | Type | Mandatory | Default |
| :------------- | :------------- | :------------- | :------------- | :------------- |
| <a id="cad_part-name"></a>name |  A unique name for this target.   | <a href="https://bazel.build/concepts/labels#target-names">Name</a> | required |  |
| <a id="cad_part-deps"></a>deps |  Python files the script imports; each one's directory is on the import path.   | <a href="https://bazel.build/concepts/labels">List of labels</a> | optional |  `[]`  |
| <a id="cad_part-src"></a>src |  The part script.   | <a href="https://bazel.build/concepts/labels">Label</a> | required |  |
| <a id="cad_part-params"></a>params |  Parameters for `build(params)`. Each value is JSON: `"3"` is the number 3, `'"steel"'` the string steel, `"true"` a boolean.   | <a href="https://bazel.build/rules/lib/core/dict">Dictionary: String -> String</a> | optional |  `{}`  |
| <a id="cad_part-stl_angular_tolerance"></a>stl_angular_tolerance |  The STL mesh's angular deflection, in radians.   | String | optional |  `"0.1"`  |
| <a id="cad_part-stl_tolerance"></a>stl_tolerance |  The STL mesh's linear deflection, in mm.   | String | optional |  `"0.001"`  |


<a id="cad_render"></a>

## cad_render

<pre>
load("@rules_brep//brep:defs.bzl", "cad_render")

cad_render(<a href="#cad_render-name">name</a>, <a href="#cad_render-src">src</a>, <a href="#cad_render-size">size</a>, <a href="#cad_render-views">views</a>)
</pre>

Views of a model as PNG: `<name>_<view>.png`.

```starlark
cad_render(
    name = "bracket_views",
    src = ":bracket",
)
```

`src` is a `cad_part`, or a target that names one STEP file. The model is
meshed with OCP and drawn flat shaded with matplotlib's Agg backend: no
OpenGL, so it runs anywhere the CAD toolchain does. Each view is an
orthographic projection, with Z up and the front view looking along +Y,
scaled so the model fills it with a margin. Triangles are painted far to
near by the depth of their centers, which can be wrong where a large one
and a small one overlap; the views are for review, not for measuring.

The PNG files hold no time, path or software name, so the same model gives
the same bytes on the same platform. A change to geometry attaches these
PNGs to its pull request (AGENTS.md, rule 5).

**ATTRIBUTES**


| Name  | Description | Type | Mandatory | Default |
| :------------- | :------------- | :------------- | :------------- | :------------- |
| <a id="cad_render-name"></a>name |  A unique name for this target.   | <a href="https://bazel.build/concepts/labels#target-names">Name</a> | required |  |
| <a id="cad_render-src"></a>src |  The model: a `cad_part`, or a target that names one STEP file.   | <a href="https://bazel.build/concepts/labels">Label</a> | required |  |
| <a id="cad_render-size"></a>size |  The width and height of each view, in pixels: 64 to 4096.   | Integer | optional |  `512`  |
| <a id="cad_render-views"></a>views |  The views to draw, each one of front, back, left, right, top, bottom.   | List of strings | optional |  `["front", "back", "left", "right", "top", "bottom"]`  |


<a id="cad_toolchain"></a>

## cad_toolchain

<pre>
load("@rules_brep//brep:defs.bzl", "cad_toolchain")

cad_toolchain(<a href="#cad_toolchain-name">name</a>, <a href="#cad_toolchain-libs">libs</a>, <a href="#cad_toolchain-python_version">python_version</a>, <a href="#cad_toolchain-renderer">renderer</a>, <a href="#cad_toolchain-runner">runner</a>)
</pre>

The CAD toolchain, for `@rules_brep//brep:toolchain_type`.

Its tool, `runner --part PART.py [--params JSON] [--summary OUT]`, imports
a part script, calls its `build(params)` function, and checks that the
result is a valid build123d shape. Its tool `renderer --step IN.step
--out VIEW=OUT.png [--out VIEW=OUT.png]... [--size PIXELS]` draws views of a
model as PNG, with no OpenGL.
rules_brep registers one on the
hermetic Python of rules_python, with build123d and OCP locked by hash,
and the GL and X11 libraries OCP loads, from pinned Debian 11 packages.

**ATTRIBUTES**


| Name  | Description | Type | Mandatory | Default |
| :------------- | :------------- | :------------- | :------------- | :------------- |
| <a id="cad_toolchain-name"></a>name |  A unique name for this target.   | <a href="https://bazel.build/concepts/labels#target-names">Name</a> | required |  |
| <a id="cad_toolchain-libs"></a>libs |  Shared libraries the runner and the renderer (through OCP) load from the host otherwise, all in one directory; it goes on their LD_LIBRARY_PATH.   | <a href="https://bazel.build/concepts/labels">Label</a> | optional |  `None`  |
| <a id="cad_toolchain-python_version"></a>python_version |  The Python version of the runner and the renderer.   | String | required |  |
| <a id="cad_toolchain-renderer"></a>renderer |  The CAD renderer.   | <a href="https://bazel.build/concepts/labels">Label</a> | required |  |
| <a id="cad_toolchain-runner"></a>runner |  The CAD runner.   | <a href="https://bazel.build/concepts/labels">Label</a> | required |  |


<a id="tool_toolchain"></a>

## tool_toolchain

<pre>
load("@rules_brep//brep:defs.bzl", "tool_toolchain")

tool_toolchain(<a href="#tool_toolchain-name">name</a>, <a href="#tool_toolchain-tools">tools</a>)
</pre>

A toolchain that offers tools by name, for `run_tool`.

Example, a toolchain for another build of the CAD runner (the toolchain
type arrives with this module's toolchain issue):

```starlark
tool_toolchain(
    name = "my_cad_runner_impl",
    tools = {"//third_party/cad_runner:cad_runner": "cad_runner"},
)

toolchain(
    name = "my_cad_runner",
    toolchain = ":my_cad_runner_impl",
    toolchain_type = "@rules_brep//brep:toolchain_type",
)
```

**ATTRIBUTES**


| Name  | Description | Type | Mandatory | Default |
| :------------- | :------------- | :------------- | :------------- | :------------- |
| <a id="tool_toolchain-name"></a>name |  A unique name for this target.   | <a href="https://bazel.build/concepts/labels#target-names">Name</a> | required |  |
| <a id="tool_toolchain-tools"></a>tools |  Executable targets, each mapped to the name rules use for it.   | <a href="https://bazel.build/rules/lib/core/dict">Dictionary: Label -> String</a> | required |  |


<a id="CadPartInfo"></a>

## CadPartInfo

<pre>
load("@rules_brep//brep:defs.bzl", "CadPartInfo")

CadPartInfo(<a href="#CadPartInfo-step">step</a>, <a href="#CadPartInfo-stl">stl</a>, <a href="#CadPartInfo-src">src</a>)
</pre>

A built part.

**FIELDS**

| Name  | Description |
| :------------- | :------------- |
| <a id="CadPartInfo-step"></a>step |  File: the part as STEP.    |
| <a id="CadPartInfo-stl"></a>stl |  File: the part as binary STL.    |
| <a id="CadPartInfo-src"></a>src |  File: the part script.    |


<a id="CadToolchainInfo"></a>

## CadToolchainInfo

<pre>
load("@rules_brep//brep:defs.bzl", "CadToolchainInfo")

CadToolchainInfo(<a href="#CadToolchainInfo-python_version">python_version</a>)
</pre>

What the CAD toolchain offers beyond its `runner` and `renderer` tools.

**FIELDS**

| Name  | Description |
| :------------- | :------------- |
| <a id="CadToolchainInfo-python_version"></a>python_version |  string: the Python version of the runner and the renderer, such as "3.12".    |


<a id="determinism_test"></a>

## determinism_test

<pre>
load("@rules_brep//brep:defs.bzl", "determinism_test")

determinism_test(<a href="#determinism_test-name">name</a>, <a href="#determinism_test-target">target</a>, <a href="#determinism_test-kwargs">**kwargs</a>)
</pre>

Checks that two builds of `target` give byte-identical outputs.

The target is built twice in one build, under two configurations that
differ only in a setting no rule reads, so every action runs twice.
The test compares the SHA-256 of every output file, directories walked,
and fails on any difference (spec D1).

Two runs in the same second can hide a time stamp with a one-second
resolution, so pair this with a header scan where a format has one. CI
also builds every determinism_test target in two fresh output bases and
compares the results.

Example:

```starlark
determinism_test(
    name = "bracket_determinism_test",
    target = ":bracket",
)
```


**PARAMETERS**


| Name  | Description | Default Value |
| :------------- | :------------- | :------------- |
| <a id="determinism_test-name"></a>name |  the test's name.   |  none |
| <a id="determinism_test-target"></a>target |  the target whose outputs must not change between builds.   |  none |
| <a id="determinism_test-kwargs"></a>kwargs |  common test attributes, such as `size` and `tags`.   |  none |


<a id="swap_test"></a>

## swap_test

<pre>
load("@rules_brep//brep:defs.bzl", "swap_test")

swap_test(<a href="#swap_test-name">name</a>, <a href="#swap_test-targets">targets</a>, <a href="#swap_test-kwargs">**kwargs</a>)
</pre>

Builds targets with every tool swapped for a stub, and checks them.

The targets are built with `--@rules_brep//brep/toolchains:use_stub`,
so each tool toolchain that honors the flag resolves to the stub tool.
The stub writes a record into every output, files and directories
alike. The test fails if any output file of the targets lacks the
record: some action made it without a toolchain tool.

Example:

```starlark
swap_test(
    name = "swap_test",
    targets = [":gerbers", ":bom"],
)
```


**PARAMETERS**


| Name  | Description | Default Value |
| :------------- | :------------- | :------------- |
| <a id="swap_test-name"></a>name |  the test's name.   |  none |
| <a id="swap_test-targets"></a>targets |  targets whose outputs must all come from the stub.   |  none |
| <a id="swap_test-kwargs"></a>kwargs |  common test attributes, such as `size` and `tags`.   |  none |


