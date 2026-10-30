# SPDX-License-Identifier: Apache-2.0
"""cad_assembly: parts placed together, written as one STEP (issue #9)."""

load("@bazel_skylib//rules:common_settings.bzl", "BuildSettingInfo")
load(":part.bzl", "CadPartInfo")
load(":run_tool.bzl", "RUN_TOOL_TOOLCHAINS", "run_tool")

_CAD = Label("//brep:toolchain_type")

CadAssemblyInfo = provider(
    doc = "A built assembly.",
    fields = {
        "step": "File: the assembly as STEP, one named child per placement.",
        "children": "list of struct(name, part, pos, rot): each placement, in order; " +
                    "`part` is the part's CadPartInfo.",
    },
)

def _vec3(ctx, where, v):
    if type(v) != "list" or len(v) != 3:
        fail("%s: %s must be a list of 3 numbers, got %r" % (ctx.label, where, v))
    for x in v:
        if type(x) not in ["int", "float"] or x != x or x in [float("inf"), float("-inf")]:
            fail("%s: %s must be 3 finite numbers, got %r" % (ctx.label, where, v))
    return [float(x) for x in v]

def _placements(ctx, label, text):
    """The placements a part's value gives: one object, or a list of them."""
    where = "parts[%s]" % label
    value = json.decode(text, default = None)
    if value == None:
        fail("%s: %s = %r is not JSON" % (ctx.label, where, text))
    items = value if type(value) == "list" else [value]
    if not items:
        fail("%s: %s places the part nowhere" % (ctx.label, where))
    out = []
    for i, p in enumerate(items):
        w = where if len(items) == 1 else "%s[%d]" % (where, i)
        if type(p) != "dict":
            fail("%s: %s must be an object like {\"pos\": [0, 0, 0], \"rot\": [0, 0, 0]}, got %r" % (ctx.label, w, p))
        unknown = sorted([k for k in p.keys() if k not in ["pos", "rot"]])
        if unknown:
            fail("%s: %s has unknown keys %s; it takes pos and rot" % (ctx.label, w, unknown))
        out.append(struct(
            pos = _vec3(ctx, w + ".pos", p.get("pos", [0, 0, 0])),
            rot = _vec3(ctx, w + ".rot", p.get("rot", [0, 0, 0])),
        ))
    return out

def _cad_assembly_impl(ctx):
    epoch = ctx.attr._epoch[BuildSettingInfo].value
    if epoch < 0:
        fail("--@rules_brep//brep:source_date_epoch=%d: want 0 or more" % epoch)
    if not ctx.attr.parts:
        fail("%s: parts is empty" % ctx.label)
    children = []
    names = {}
    for target, text in ctx.attr.parts.items():
        part = target[CadPartInfo]
        places = _placements(ctx, target.label, text)
        for i, p in enumerate(places):
            name = target.label.name if len(places) == 1 else "%s_%d" % (target.label.name, i + 1)
            if name in names:
                fail("%s: two children are named %r (%s and %s); rename a part" % (ctx.label, name, names[name], target.label))
            names[name] = target.label
            children.append(struct(name = name, part = part, pos = p.pos, rot = p.rot))
    spec = ctx.actions.declare_file(ctx.label.name + ".assembly.json")
    ctx.actions.write(spec, json.encode_indent({
        "name": ctx.label.name,
        "children": [
            {"name": c.name, "step": c.part.step.path, "pos": c.pos, "rot": c.rot}
            for c in children
        ],
    }))
    step = ctx.actions.declare_file(ctx.label.name + ".step")
    run_tool(
        ctx,
        _CAD,
        "runner",
        arguments = ["--assemble", spec.path, "--step", step.path],
        inputs = [spec] + [c.part.step for c in children],
        outputs = [step],
        env = {"SOURCE_DATE_EPOCH": str(epoch)},
        mnemonic = "BrepAssembly",
        progress_message = "Assembling %{label}",
    )
    return [
        DefaultInfo(files = depset([step])),
        CadAssemblyInfo(step = step, children = children),
    ]

cad_assembly = rule(
    implementation = _cad_assembly_impl,
    doc = """Parts placed together, written as `<name>.step` with a named child each.

```starlark
cad_assembly(
    name = "stand",
    parts = {
        ":base": '{"pos": [0, 0, 0]}',
        ":bracket": '[{"pos": [10, 0, 5]}, {"pos": [40, 0, 5], "rot": [0, 0, 180]}]',
    },
)
```

Each value places its part: a JSON object with `pos` (x, y, z in mm) and
`rot` (degrees about X, then the new Y, then the new Z), both defaulting to
zero, or a list of such objects to place the part more than once. A child
is named after its part, with `_1`, `_2`, ... when placed more than once.

The header is normalized as `cad_part`'s: the assembly's name, and the
time `--@rules_brep//brep:source_date_epoch`.
""",
    attrs = {
        "parts": attr.label_keyed_string_dict(
            doc = "The parts (`cad_part` targets), each mapped to its placement(s) as JSON.",
            mandatory = True,
            providers = [CadPartInfo],
        ),
        "_epoch": attr.label(default = "//brep:source_date_epoch"),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
