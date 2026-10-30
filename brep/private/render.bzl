# SPDX-License-Identifier: Apache-2.0
"""cad_render: views of a model as PNG, without OpenGL (issue #10)."""

load(":run_tool.bzl", "RUN_TOOL_TOOLCHAINS", "run_tool")
load(":step_file.bzl", "step_file")

_CAD = Label("//brep:toolchain_type")

# The views the renderer draws, in the order of its outputs.
RENDER_VIEWS = ["front", "back", "left", "right", "top", "bottom"]

def _cad_render_impl(ctx):
    views = ctx.attr.views
    if not views:
        fail("%s: views is empty; give one or more of %s" % (ctx.label, RENDER_VIEWS))
    for v in views:
        if v not in RENDER_VIEWS:
            fail("%s: views has %r; each view is one of %s" % (ctx.label, v, RENDER_VIEWS))
    if len({v: True for v in views}) != len(views):
        fail("%s: views names a view twice: %s" % (ctx.label, views))
    if ctx.attr.size < 64 or ctx.attr.size > 4096:
        fail("%s: size = %d: want 64 to 4096 pixels" % (ctx.label, ctx.attr.size))

    step = step_file(ctx, ctx.attr.src, "src")
    args = ctx.actions.args()
    args.add("--step", step)
    args.add("--size", str(ctx.attr.size))
    outs = []
    for v in views:
        png = ctx.actions.declare_file("%s_%s.png" % (ctx.label.name, v))
        outs.append(png)
        args.add("--out", "%s=%s" % (v, png.path))
    run_tool(
        ctx,
        _CAD,
        "renderer",
        arguments = [args],
        inputs = [step],
        outputs = outs,
        # matplotlib writes its font cache here, in the private home.
        home_env = ["MPLCONFIGDIR"],
        mnemonic = "BrepRender",
        progress_message = "Rendering %{label}",
    )
    return [DefaultInfo(files = depset(outs))]

cad_render = rule(
    implementation = _cad_render_impl,
    doc = """Views of a model as PNG: `<name>_<view>.png`.

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
""",
    attrs = {
        "src": attr.label(
            doc = "The model: a `cad_part`, or a target that names one STEP file.",
            mandatory = True,
            allow_files = [".step", ".stp"],
        ),
        "views": attr.string_list(
            doc = "The views to draw, each one of " + ", ".join(RENDER_VIEWS) + ".",
            default = RENDER_VIEWS,
        ),
        "size": attr.int(
            doc = "The width and height of each view, in pixels: 64 to 4096.",
            default = 512,
        ),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
