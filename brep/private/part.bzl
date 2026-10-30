# SPDX-License-Identifier: Apache-2.0
"""cad_part: a part script built into STEP and STL (issue #8)."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load(":numbers.bzl", "parse_number")
load(":run_tool.bzl", "RUN_TOOL_TOOLCHAINS", "run_tool")

_CAD = Label("//brep:toolchain_type")

# The CAD library a part is built with (issue #15): the CAD toolchain of
# that library is the one toolchain resolution picks for the part.
_LIBRARY = str(Label("//brep/toolchains:cad_library"))

CAD_LIBRARIES = ["build123d", "cadquery"]

def _library_impl(_settings, attr):
    return {_LIBRARY: attr.library}

_library_transition = transition(
    implementation = _library_impl,
    inputs = [],
    outputs = [_LIBRARY],
)

CadPartInfo = provider(
    doc = "A built part.",
    fields = {
        "step": "File: the part as STEP.",
        "stl": "File: the part as binary STL.",
        "src": "File: the part script.",
    },
)

def _params_json(ctx):
    """The params as one JSON object; each value must be JSON itself."""
    parts = []
    for k in sorted(ctx.attr.params.keys()):
        v = ctx.attr.params[k]
        decoded = json.decode(v, default = None)
        if decoded == None and v.strip() != "null":
            fail("%s: params[%r] = %r is not a JSON value; write a string as %r" % (ctx.label, k, v, json.encode(v)))
        parts.append("%s: %s" % (json.encode(k), json.encode(decoded)))
    return "{" + ", ".join(parts) + "}"

def _positive(ctx, attr, v):
    """v as a positive, finite number, or a failure that names attr."""
    x = parse_number(v)
    if x == None:
        fail("%s: %s = %r is not a number" % (ctx.label, attr, v))
    if not (x > 0) or x == float("inf"):
        fail("%s: %s = %r: STL tolerances must be positive and finite" % (ctx.label, attr, v))
    return x

def _cad_part_impl(ctx):
    epoch = ctx.attr._epoch[BuildSettingInfo].value
    if epoch < 0:
        fail("--@rules_brep//brep:source_date_epoch=%d: want 0 or more" % epoch)
    _positive(ctx, "stl_tolerance", ctx.attr.stl_tolerance)
    _positive(ctx, "stl_angular_tolerance", ctx.attr.stl_angular_tolerance)

    # Each dependency's directory, so the script imports it wherever it is
    # (a generated file is under bazel-out, a source file is not).
    dirs = {}
    for f in [ctx.file.src] + ctx.files.deps:
        dirs[f.dirname] = True
    path_args = []
    for d in sorted(dirs.keys()):
        path_args += ["--path", d]
    step = ctx.actions.declare_file(ctx.label.name + ".step")
    stl = ctx.actions.declare_file(ctx.label.name + ".stl")
    run_tool(
        ctx,
        _CAD,
        "runner",
        arguments = [
            "--part",
            ctx.file.src.path,
            "--params",
            _params_json(ctx),
            "--name",
            ctx.label.name,
            "--step",
            step.path,
            "--stl",
            stl.path,
            "--stl-tolerance",
            ctx.attr.stl_tolerance,
            "--stl-angular-tolerance",
            ctx.attr.stl_angular_tolerance,
        ] + path_args,
        inputs = [ctx.file.src] + ctx.files.deps,
        outputs = [step, stl],
        env = {"SOURCE_DATE_EPOCH": str(epoch)},
        mnemonic = "BrepPart",
        progress_message = "Building the part %{label}",
    )
    return [
        DefaultInfo(files = depset([step, stl])),
        CadPartInfo(step = step, stl = stl, src = ctx.file.src),
    ]

cad_part = rule(
    implementation = _cad_part_impl,
    doc = """A part script, built into `<name>.step` and `<name>.stl`.

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

With `library = "cadquery"`, the script is a CadQuery script instead: its
`build(params)` returns a CadQuery `Workplane` or `Shape`, and it runs on
the CadQuery toolchain, with CadQuery 2.8 and its own OCCT. Its wheels (467
MB, VTK among them) are fetched only for a build that has such a part.

* `<name>.step` names the shape `<name>`, and its header time is
  `--@rules_brep//brep:source_date_epoch` (default 1970-01-01).
* `<name>.stl` is binary, meshed with parallel meshing off, so the same
  part gives the same bytes on the same platform. Across platforms the
  geometry may differ in the last digits; `geometry_equal_test` compares
  by tolerance (spec D3).
""",
    cfg = _library_transition,
    attrs = {
        "library": attr.string(
            doc = "The CAD library of the script: `\"build123d\"` or `\"cadquery\"`.",
            default = "build123d",
            values = CAD_LIBRARIES,
        ),
        "src": attr.label(
            doc = "The part script.",
            mandatory = True,
            allow_single_file = [".py"],
        ),
        "params": attr.string_dict(
            doc = "Parameters for `build(params)`. Each value is JSON: `\"3\"` is the number 3, " +
                  "`'\"steel\"'` the string steel, `\"true\"` a boolean.",
        ),
        "deps": attr.label_list(
            doc = "Python files the script imports; each one's directory is on the import path.",
            allow_files = [".py"],
        ),
        "stl_tolerance": attr.string(
            doc = "The STL mesh's linear deflection, in mm.",
            default = "0.001",
        ),
        "stl_angular_tolerance": attr.string(
            doc = "The STL mesh's angular deflection, in radians.",
            default = "0.1",
        ),
        "_epoch": attr.label(default = "//brep:source_date_epoch"),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
