# SPDX-License-Identifier: Apache-2.0
"""geometry_equal_test: two shapes are the same within tolerances (issue #11)."""

load(":numbers.bzl", "parse_number")
load(":run_tool.bzl", "HELPERS_TOOLCHAIN_TYPE", "RUN_TOOL_TOOLCHAINS", "run_tool")
load(":step_file.bzl", "step_file")

_CAD = Label("//brep:toolchain_type")

def _tolerance(ctx, attr):
    """The value of attr, checked to be a finite number, 0 or more."""
    v = getattr(ctx.attr, attr)
    x = parse_number(v)
    if x == None or x < 0:
        fail("%s: %s = %r: want a finite number, 0 or more, such as \"0.001\"" % (ctx.label, attr, v))
    return v

def _rlocation(ctx, f):
    """The runfiles path (rlocation path) of f, for the runfiles library."""
    if f.short_path.startswith("../"):
        return f.short_path[3:]
    return ctx.workspace_name + "/" + f.short_path

def _measure(ctx, target, attr):
    """Measures target's STEP file; returns the measurements' file."""
    step = step_file(ctx, target, attr)
    out = ctx.actions.declare_file("%s.%s.txt" % (ctx.label.name, attr))
    run_tool(
        ctx,
        _CAD,
        "measurer",
        arguments = ["--step", step.path, "--out", out.path],
        inputs = [step],
        outputs = [out],
        mnemonic = "BrepMeasure",
        progress_message = "Measuring %s for %%{label}" % attr,
    )
    return out

def _geometry_equal_test_impl(ctx):
    abs_tol = _tolerance(ctx, "abs_tolerance")
    rel_tol = _tolerance(ctx, "rel_tolerance")
    a = _measure(ctx, ctx.attr.a, "a")
    b = _measure(ctx, ctx.attr.b, "b")
    check = ctx.toolchains[HELPERS_TOOLCHAIN_TYPE].helpers.geqcheck
    exe = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(
        output = exe,
        target_file = check.files_to_run.executable,
        is_executable = True,
    )
    return [
        DefaultInfo(
            executable = exe,
            runfiles = ctx.runfiles(files = [a, b]).merge(check.default_runfiles),
        ),
        RunEnvironmentInfo(environment = {
            "GEQ_A": _rlocation(ctx, a),
            "GEQ_ABS": abs_tol,
            "GEQ_B": _rlocation(ctx, b),
            "GEQ_EXPECT": ctx.attr.expect,
            "GEQ_REL": rel_tol,
        }),
    ]

geometry_equal_test = rule(
    implementation = _geometry_equal_test_impl,
    test = True,
    doc = """Checks that two shapes are the same within tolerances (spec D3).

```starlark
geometry_equal_test(
    name = "bracket_geometry_test",
    a = ":bracket",
    b = "bracket_golden.step",
    abs_tolerance = "0.001",
)
```

`a` and `b` are each a `cad_part`, or a target that names one STEP file.
Each is measured with OCP on the CAD toolchain: volume, surface area,
center of mass, bounding box, and the numbers of solids, faces, edges and
vertices. The test fails when a count differs, or when two numbers differ
by more than `abs_tolerance + rel_tolerance * max(|a|, |b|)`, and says
which.

OCCT's results can differ in the last digits from one CPU to another, so a
golden STEP file compares by bytes only on the platform that wrote it; this
test compares by tolerance, on any platform. Area and center catch what
volume and box miss, such as a hole that moved.
""",
    attrs = {
        "a": attr.label(
            doc = "The first shape: a `cad_part`, or a target that names one STEP file.",
            mandatory = True,
            allow_files = [".step", ".stp"],
        ),
        "b": attr.label(
            doc = "The second shape, as `a`.",
            mandatory = True,
            allow_files = [".step", ".stp"],
        ),
        "abs_tolerance": attr.string(
            doc = "How far two numbers may be apart, in mm, mm² or mm³, on top of the relative " +
                  "part: a floor for values near 0, such as a coordinate at the origin. The " +
                  "measurements have 6 decimals, so less than 0.000001 tells nothing apart.",
            default = "0.00001",
        ),
        "rel_tolerance": attr.string(
            doc = "How far two numbers may be apart, as a fraction of the larger in size: the " +
                  "part of the tolerance that scales with each quantity's own unit and size.",
            default = "0.000001",
        ),
        "expect": attr.string(
            doc = "\"equal\", or \"different\" to check that two shapes are told apart.",
            default = "equal",
            values = ["equal", "different"],
        ),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
