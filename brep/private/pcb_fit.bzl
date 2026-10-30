# SPDX-License-Identifier: Apache-2.0
"""pcb_fit_test: a board fits its enclosure (issue #14)."""

load(":numbers.bzl", "parse_number")
load(":run_tool.bzl", "HELPERS_TOOLCHAIN_TYPE", "RUN_TOOL_TOOLCHAINS", "run_tool")
load(":step_file.bzl", "step_file")

_CAD = Label("//brep:toolchain_type")

def _setting(ctx, attr):
    v = getattr(ctx.attr, attr)
    x = parse_number(v)
    if x == None or x < 0:
        fail("%s: %s = %r: want a number, 0 or more" % (ctx.label, attr, v))
    return v

def _vec3(ctx, where, v):
    if type(v) != "list" or len(v) != 3:
        fail("%s: %s must be 3 numbers, got %r" % (ctx.label, where, v))
    for x in v:
        if type(x) not in ["int", "float"] or x != x or x in [float("inf"), float("-inf")]:
            fail("%s: %s must be 3 finite numbers, got %r" % (ctx.label, where, v))
    return [float(x) for x in v]

def _placement(ctx):
    text = ctx.attr.board_placement
    p = json.decode(text, default = None)
    if type(p) != "dict":
        fail("%s: board_placement = %r: want a JSON object like {\"pos\": [0, 0, 4], \"rot\": [0, 0, 0]}" % (ctx.label, text))
    unknown = sorted([k for k in p.keys() if k not in ["pos", "rot"]])
    if unknown:
        fail("%s: board_placement has unknown keys %s; it takes pos and rot" % (ctx.label, unknown))
    pos = _vec3(ctx, "board_placement.pos", p.get("pos", [0, 0, 0]))
    rot = _vec3(ctx, "board_placement.rot", p.get("rot", [0, 0, 0]))
    for axis, a in zip(["X", "Y"], rot[:2]):
        if a % 180 != 0:
            fail("%s: board_placement turns the board %s degrees about %s; the board must lie flat (0 or 180 about X and Y)" % (ctx.label, a, axis))
    return pos, rot

def _rlocation(ctx, f):
    if f.short_path.startswith("../"):
        return f.short_path[3:]
    return ctx.workspace_name + "/" + f.short_path

def _pcb_fit_test_impl(ctx):
    min_clearance = _setting(ctx, "min_clearance_mm")
    tolerance = _setting(ctx, "hole_tolerance_mm")
    epsilon = _setting(ctx, "overlap_epsilon_mm3")
    pos, rot = _placement(ctx)
    board = step_file(ctx, ctx.attr.board, "board")
    enclosure = step_file(ctx, ctx.attr.enclosure, "enclosure")
    spec = ctx.actions.declare_file(ctx.label.name + ".fit.json")
    ctx.actions.write(spec, json.encode_indent({
        "board": board.path,
        "enclosure": enclosure.path,
        "pos": pos,
        "rot": rot,
    }))
    report = ctx.actions.declare_file(ctx.label.name + ".fit.txt")
    run_tool(
        ctx,
        _CAD,
        "runner",
        arguments = ["--fit", spec.path, "--report", report.path],
        inputs = [spec, board, enclosure],
        outputs = [report],
        mnemonic = "BrepPcbFit",
        progress_message = "Fitting the board of %{label}",
    )
    check = ctx.toolchains[HELPERS_TOOLCHAIN_TYPE].helpers.fitcheck
    exe = ctx.actions.declare_file(ctx.label.name)
    ctx.actions.symlink(output = exe, target_file = check.files_to_run.executable, is_executable = True)
    return [
        DefaultInfo(
            executable = exe,
            runfiles = ctx.runfiles(files = [report]).merge(check.default_runfiles),
        ),
        RunEnvironmentInfo(environment = {
            "FIT_EPSILON": epsilon,
            "FIT_EXPECT": ctx.attr.expect,
            "FIT_HOLE_TOLERANCE": tolerance,
            "FIT_MIN_CLEARANCE": min_clearance,
            "FIT_REPORT": _rlocation(ctx, report),
        }),
    ]

pcb_fit_test = rule(
    implementation = _pcb_fit_test_impl,
    test = True,
    doc = """Checks that a circuit board fits its enclosure.

```starlark
pcb_fit_test(
    name = "board_fit_test",
    board = "@my_board//:step",        # kicad_step of rules_kicad, or any STEP
    enclosure = ":enclosure",          # a cad_part
    board_placement = '{"pos": [0, 0, 4]}',
    min_clearance_mm = "0.5",
)
```

The board is placed in the enclosure (`board_placement`: `pos` in mm and
`rot` in degrees, intrinsic X-Y-Z, as in `cad_assembly`). It must lie flat:
about X and Y only 0 or 180 degrees, about Z any angle. The test checks
three things, listing each that fails:

* **Fit:** the board and the enclosure share no more than
  `overlap_epsilon_mm3` of volume. Resting on supports is touching, not
  overlapping.
* **Clearance:** the board's outline (its side faces, not its holes) is at
  least `min_clearance_mm` from the enclosure's material beside it, between
  the board's bottom and top. Supports under or over the board, and pins in
  its holes, do not count.
* **Holes:** the board has a mounting hole (a whole hole along Z; a notch or
  a fillet is not one), and each has a mount in the enclosure: a whole
  cylinder along Z that reaches the board (within 0.1 mm of its bottom or
  top), a boss's hole or a pin, no wider than the hole, whose center is
  within `hole_tolerance_mm`. A moved hole fails, and so does a solid boss
  with no hole in it.

The board may be a `kicad_step` with its parts on it. Its outline and holes
come from the board itself, the solid with the largest footprint; every
solid, parts included, counts for the overlap.

The geometry runs on the CAD toolchain; the checks are Go.
`expect = "fail"` is for a known-bad fit (spec T3).
""",
    attrs = {
        "board": attr.label(
            doc = "The board: a target that names one STEP file (such as rules_kicad's " +
                  "`kicad_step`), or a `cad_part`. Its holes run along Z.",
            mandatory = True,
            allow_files = True,
        ),
        "enclosure": attr.label(
            doc = "The enclosure: a `cad_part`, or a target that names one STEP file.",
            mandatory = True,
            allow_files = True,
        ),
        "board_placement": attr.string(
            doc = "Where the board sits in the enclosure, as JSON: {\"pos\": [x, y, z], \"rot\": [rx, ry, rz]}.",
            default = "{}",
        ),
        "min_clearance_mm": attr.string(
            doc = "The least distance from the board's outline to the enclosure, mm.",
            mandatory = True,
        ),
        "hole_tolerance_mm": attr.string(
            doc = "How far a mount's center may be from its hole's, mm.",
            default = "0.05",
        ),
        "overlap_epsilon_mm3": attr.string(
            doc = "The shared volume that still counts as none, mm^3.",
            default = "0.001",
        ),
        "expect": attr.string(
            doc = "\"pass\", or \"fail\" for a known-bad fit.",
            default = "pass",
            values = ["pass", "fail"],
        ),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
