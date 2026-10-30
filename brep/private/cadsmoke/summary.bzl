# SPDX-License-Identifier: Apache-2.0
"""A test-only rule: a part's volume and size, through the CAD toolchain."""

load("//brep/private:run_tool.bzl", "RUN_TOOL_TOOLCHAINS", "run_tool")

_CAD = Label("//brep:toolchain_type")

def _part_summary_impl(ctx):
    out = ctx.actions.declare_file(ctx.label.name + ".txt")
    run_tool(
        ctx,
        _CAD,
        "runner",
        arguments = [
            "--part",
            ctx.file.part.path,
            "--params",
            json.encode(ctx.attr.params),
            "--summary",
            out.path,
        ],
        inputs = [ctx.file.part],
        outputs = [out],
        mnemonic = "BrepPartSummary",
        progress_message = "Building %{label}",
    )
    return [DefaultInfo(files = depset([out]))]

part_summary = rule(
    implementation = _part_summary_impl,
    doc = "Writes `<name>.txt`: the volume and bounding box of a part script's shape.",
    attrs = {
        "part": attr.label(mandatory = True, allow_single_file = [".py"]),
        "params": attr.string_dict(),
    },
    toolchains = [_CAD] + RUN_TOOL_TOOLCHAINS,
)
