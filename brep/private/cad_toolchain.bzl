# SPDX-License-Identifier: Apache-2.0
"""The CAD toolchain: the runner that builds part scripts (issue #7)."""

CadToolchainInfo = provider(
    doc = "What the CAD toolchain offers beyond its `runner` tool.",
    fields = {
        "python_version": "string: the runner's Python version, such as \"3.12\".",
    },
)

def _cad_toolchain_impl(ctx):
    return [platform_common.ToolchainInfo(
        tools = {"runner": ctx.attr.runner[DefaultInfo].files_to_run},
        # run_tool passes these to the runner: no .pyc files written beside
        # the sources, and the same hash seed in every run.
        env = {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
        cad = CadToolchainInfo(python_version = ctx.attr.python_version),
    )]

cad_toolchain = rule(
    implementation = _cad_toolchain_impl,
    doc = """The CAD toolchain, for `@rules_brep//brep:toolchain_type`.

Its tool, `runner --part PART.py [--params JSON] [--summary OUT]`, imports
a part script, calls its `build(params)` function, and checks that the
result is a valid build123d shape. rules_brep registers one on the
hermetic Python of rules_python, with build123d and OCP locked by hash.
""",
    attrs = {
        "runner": attr.label(
            doc = "The CAD runner.",
            mandatory = True,
            executable = True,
            cfg = "exec",
        ),
        "python_version": attr.string(
            doc = "The runner's Python version.",
            mandatory = True,
        ),
    },
)
