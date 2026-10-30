# SPDX-License-Identifier: Apache-2.0
"""interference_test: no two parts of an assembly overlap (issue #13)."""

load(":assembly.bzl", "CadAssemblyInfo")
load(":numbers.bzl", "parse_number")
load(":run_tool.bzl", "HELPERS_TOOLCHAIN_TYPE", "RUN_TOOL_TOOLCHAINS", "run_tool")

_CAD = Label("//brep:toolchain_type")

def _rlocation_path(ctx, f):
    """f's runfiles path: "<repo>/<path>", also for a file of another repository."""
    if f.short_path.startswith("../"):
        return f.short_path[3:]
    return ctx.workspace_name + "/" + f.short_path

def _interference_test_impl(ctx):
    eps = ctx.attr.epsilon_mm3
    x = parse_number(eps)
    if x == None or x < 0 or x == float("inf"):
        fail("%s: epsilon_mm3 = %r: want a number, 0 or more" % (ctx.label, eps))
    asm = ctx.attr.assembly[CadAssemblyInfo]
    spec = ctx.actions.declare_file(ctx.label.name + ".spec.json")
    ctx.actions.write(spec, json.encode_indent({
        "name": ctx.attr.assembly.label.name,
        "children": [
            {"name": c.name, "step": c.part.step.path, "pos": c.pos, "rot": c.rot}
            for c in asm.children
        ],
    }))
    report = ctx.actions.declare_file(ctx.label.name + ".report.txt")
    run_tool(
        ctx,
        _CAD,
        "runner",
        arguments = ["--interference", spec.path, "--report", report.path],
        inputs = depset([spec] + [c.part.step for c in asm.children]),
        outputs = [report],
        mnemonic = "BrepInterference",
        progress_message = "Measuring the overlaps in %{label}",
    )
    check = ctx.toolchains[HELPERS_TOOLCHAIN_TYPE].helpers.overlapcheck
    exe = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = exe, target_file = check.files_to_run.executable, is_executable = True)
    return [
        DefaultInfo(
            executable = exe,
            runfiles = ctx.runfiles(files = [report]).merge(check.default_runfiles),
        ),
        RunEnvironmentInfo(environment = {
            "OVERLAP_EPSILON": eps,
            "OVERLAP_EXPECT": ctx.attr.expect,
            "OVERLAP_REPORT": _rlocation_path(ctx, report),
        }),
    ]

interference_test = rule(
    implementation = _interference_test_impl,
    test = True,
    doc = """Fails when two parts of an assembly overlap.

```starlark
interference_test(
    name = "stand_interference_test",
    assembly = ":stand",
)
```

Every pair of the assembly's children is intersected, solid by solid; a
pair that shares more than `epsilon_mm3` of volume fails the test, and the
message names each such pair and the volume. A volume exactly at
`epsilon_mm3` passes. Parts that only touch, at a face, an edge or a
point, share none. The intersection runs on the CAD toolchain as a build
action, skipping solids whose bounding boxes do not meet; the check is Go.

`expect = "overlap"` is for a known-bad assembly (spec T3): the test then
passes when at least one pair overlaps, and fails when none does.
""",
    attrs = {
        "assembly": attr.label(
            doc = "The assembly (`cad_assembly`).",
            mandatory = True,
            providers = [CadAssemblyInfo],
        ),
        "epsilon_mm3": attr.string(
            doc = "The shared volume, in mm^3, that still counts as none: room for " +
                  "rounding at faces that touch.",
            default = "0.001",
        ),
        "expect": attr.string(
            doc = "\"none\", or \"overlap\" for a known-bad assembly.",
            default = "none",
            values = ["none", "overlap"],
        ),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
