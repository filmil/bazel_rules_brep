# SPDX-License-Identifier: Apache-2.0
"""cad_part: a part script built into STEP and STL (issue #8)."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load(":run_tool.bzl", "RUN_TOOL_TOOLCHAINS", "run_tool")

_CAD = Label("//brep:toolchain_type")

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
        if decoded == None and v != "null":
            fail("%s: params[%r] = %r is not a JSON value; write a string as %r" % (ctx.label, k, v, json.encode(v)))
        parts.append("%s: %s" % (json.encode(k), json.encode(decoded)))
    return "{" + ", ".join(parts) + "}"

def _cad_part_impl(ctx):
    epoch = ctx.attr._epoch[BuildSettingInfo].value
    if epoch < 0:
        fail("--@rules_brep//brep:source_date_epoch=%d: want 0 or more" % epoch)
    for t in [ctx.attr.stl_tolerance, ctx.attr.stl_angular_tolerance]:
        if float(t) <= 0:
            fail("%s: STL tolerances must be positive, got %s" % (ctx.label, t))
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
        ],
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

The script defines `build(params: dict)`, which returns a build123d solid.
It runs with build123d and OCCT on the CAD toolchain.

* `<name>.step` names the shape `<name>`, and its header time is
  `--@rules_brep//brep:source_date_epoch` (default 1970-01-01).
* `<name>.stl` is binary, meshed with parallel meshing off, so the same
  part gives the same bytes on the same platform. Across platforms the
  geometry may differ in the last digits; `geometry_equal_test` compares
  by tolerance (spec D3).
""",
    attrs = {
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
            doc = "Python files the script imports, from its own directory.",
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
