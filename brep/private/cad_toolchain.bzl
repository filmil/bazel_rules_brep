# SPDX-License-Identifier: Apache-2.0
"""The CAD toolchain: the runner that builds part scripts (issue #7), and the renderer (issue #10)."""

CadToolchainInfo = provider(
    doc = "What the CAD toolchain offers beyond its `runner` and `renderer` tools.",
    fields = {
        "python_version": "string: the Python version of the runner and the renderer, such as \"3.12\".",
    },
)

def _cad_toolchain_impl(ctx):
    libs = ctx.files.libs
    path_env = {}
    if libs:
        # The libraries OCP loads that its wheel does not bundle (GL, X11).
        dirs = {f.dirname: True for f in libs}
        if len(dirs) != 1:
            fail("%s: libs must be in one directory, not %s" % (ctx.label, sorted(dirs.keys())))
        path_env["LD_LIBRARY_PATH"] = dirs.keys()[0]
    return [platform_common.ToolchainInfo(
        path_env = path_env,
        tool_inputs = depset(libs),
        tools = {
            "renderer": ctx.attr.renderer[DefaultInfo].files_to_run,
            "runner": ctx.attr.runner[DefaultInfo].files_to_run,
        },
        # run_tool passes these to the runner: no .pyc files written beside
        # the sources, the same hash seed in every run, and one thread in
        # the numeric libraries, so a sum is added up in the same order.
        env = {
            "MKL_NUM_THREADS": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
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
result is a valid build123d shape. Its tool `renderer --step IN.step
--out VIEW=OUT.png [--out VIEW=OUT.png]... [--size PIXELS]` draws views of a
model as PNG, with no OpenGL.
rules_brep registers one on the
hermetic Python of rules_python, with build123d and OCP locked by hash,
and the GL and X11 libraries OCP loads, from pinned Debian 11 packages.
""",
    attrs = {
        "runner": attr.label(
            doc = "The CAD runner.",
            mandatory = True,
            executable = True,
            cfg = "exec",
        ),
        "renderer": attr.label(
            doc = "The CAD renderer.",
            mandatory = True,
            executable = True,
            cfg = "exec",
        ),
        "python_version": attr.string(
            doc = "The Python version of the runner and the renderer.",
            mandatory = True,
        ),
        "libs": attr.label(
            doc = "Shared libraries the runner and the renderer (through OCP) load from the " +
                  "host otherwise, all in one directory; it goes on their LD_LIBRARY_PATH.",
            allow_files = True,
            cfg = "exec",
        ),
    },
)
