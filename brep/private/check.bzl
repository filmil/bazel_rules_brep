# SPDX-License-Identifier: Apache-2.0
"""cad_check_test: a part's volume, size and thinnest wall within limits (issue #12)."""

load(":numbers.bzl", "parse_number")
load(":run_tool.bzl", "HELPERS_TOOLCHAIN_TYPE", "RUN_TOOL_TOOLCHAINS", "run_tool")
load(":step_file.bzl", "step_file")

_CAD = Label("//brep:toolchain_type")

def _limit(ctx, attr, value):
    """value checked as a finite number, 0 or more; "" stays "" (not checked)."""
    if value == "":
        return ""
    x = parse_number(value)
    if x == None or x < 0:
        fail("%s: %s = %r: want a number, 0 or more" % (ctx.label, attr, value))
    return value

def _rlocation(ctx, f):
    if f.short_path.startswith("../"):
        return f.short_path[3:]
    return ctx.workspace_name + "/" + f.short_path

def _cad_check_test_impl(ctx):
    a = ctx.attr
    min_volume = _limit(ctx, "min_volume", a.min_volume)
    max_volume = _limit(ctx, "max_volume", a.max_volume)
    min_wall = _limit(ctx, "min_wall", a.min_wall)
    if a.max_size and len(a.max_size) != 3:
        fail("%s: max_size must be 3 numbers (X, Y, Z in mm), got %r" % (ctx.label, a.max_size))
    max_size = [_limit(ctx, "max_size[%s]" % axis, v) for axis, v in zip(["X", "Y", "Z"], a.max_size)]
    if "" in max_size:
        fail("%s: max_size has an empty value" % ctx.label)
    if not (min_volume or max_volume or min_wall or max_size):
        fail("%s: no limit given; set min_volume, max_volume, max_size or min_wall" % ctx.label)
    if min_volume and max_volume and float(min_volume) > float(max_volume):
        fail("%s: min_volume %s is above max_volume %s" % (ctx.label, min_volume, max_volume))
    names = ["min_volume", "max_volume", "max_size", "min_wall"]
    for n in a.expect_failing:
        if n not in names:
            fail("%s: expect_failing has %r; the limits are %s" % (ctx.label, n, names))
    if a.expect_failing and a.expect != "fail":
        fail("%s: expect_failing goes with expect = \"fail\"" % ctx.label)
    if a.wall_grid < 1 or a.wall_grid > 100:
        fail("%s: wall_grid = %d: want 1 to 100" % (ctx.label, a.wall_grid))

    step = step_file(ctx, a.part, "part")
    measured = ctx.actions.declare_file(ctx.label.name + ".measurements.txt")
    args = ["--step", step.path, "--out", measured.path]
    if min_wall:
        args += ["--min-wall", str(a.wall_grid)]
    run_tool(
        ctx,
        _CAD,
        "measurer",
        arguments = args,
        inputs = [step],
        outputs = [measured],
        mnemonic = "BrepMeasure",
        progress_message = "Measuring the part of %{label}",
    )
    check = ctx.toolchains[HELPERS_TOOLCHAIN_TYPE].helpers.partcheck
    exe = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = exe, target_file = check.files_to_run.executable, is_executable = True)
    return [
        DefaultInfo(
            executable = exe,
            runfiles = ctx.runfiles(files = [measured]).merge(check.default_runfiles),
        ),
        RunEnvironmentInfo(environment = {
            "CHECK_EXPECT": a.expect,
            "CHECK_EXPECT_FAILING": ",".join(a.expect_failing),
            "CHECK_MAX_SIZE": " ".join(max_size),
            "CHECK_MAX_VOLUME": max_volume,
            "CHECK_MEASURE": _rlocation(ctx, measured),
            "CHECK_MIN_VOLUME": min_volume,
            "CHECK_MIN_WALL": min_wall,
        }),
    ]

cad_check_test = rule(
    implementation = _cad_check_test_impl,
    test = True,
    doc = """Checks a part against limits: volume, size, thinnest wall.

```starlark
cad_check_test(
    name = "bracket_check_test",
    part = ":bracket",
    max_size = ["40", "30", "35"],
    max_volume = "5000",
    min_wall = "1.5",
)
```

The part is measured with OCP on the CAD toolchain (the measurer of
`geometry_equal_test`), and the limits are checked in Go. Each limit is
checked only when set; the test fails listing every limit that does not
hold, with the value found. A value at a limit holds.

* `min_volume`, `max_volume`: mm^3.
* `max_size`: the largest bounding box, `[X, Y, Z]` in mm.
* `min_wall`: the thinnest wall, in mm. It is sampled: from a
  `wall_grid` x `wall_grid` grid of points on each face, a ray goes
  inward, and the shortest way through the solid counts. A wall thinner
  than the grid's spacing in a small spot can be missed; raise
  `wall_grid` to look closer. Measured only when `min_wall` is set.

Raising a limit so that a part passes needs a person (AGENTS.md rule 7).
`expect = "fail"` is for a known-bad part (spec T3): the test then passes
when a limit does not hold; `expect_failing` names which, so the part
fails for the reason it was made for.
""",
    attrs = {
        "part": attr.label(
            doc = "The part: a `cad_part`, or a target that names one STEP file.",
            mandatory = True,
            allow_files = True,
        ),
        "min_volume": attr.string(doc = "The least volume, mm^3."),
        "max_volume": attr.string(doc = "The most volume, mm^3."),
        "max_size": attr.string_list(doc = "The largest bounding box: X, Y, Z in mm."),
        "min_wall": attr.string(doc = "The thinnest wall allowed, mm."),
        "wall_grid": attr.int(
            doc = "Points per side of the grid on each face for min_wall.",
            default = 8,
        ),
        "expect_failing": attr.string_list(
            doc = "With expect = \"fail\": the limits that must fail, and only they " +
                  "(min_volume, max_volume, max_size, min_wall).",
        ),
        "expect": attr.string(
            doc = "\"pass\", or \"fail\" for a known-bad part.",
            default = "pass",
            values = ["pass", "fail"],
        ),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
