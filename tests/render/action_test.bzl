# SPDX-License-Identifier: Apache-2.0
"""Analysis test: cad_render's action, its arguments and its outputs."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _render_action_impl(ctx):
    env = analysistest.begin(ctx)
    actions = [a for a in analysistest.target_actions(env) if a.mnemonic == "BrepRender"]
    asserts.equals(env, 1, len(actions), "BrepRender actions")
    argv = actions[0].argv
    sep = argv.index("--")
    launcher, args = argv[:sep], argv[sep + 2:]
    asserts.true(env, "MPLCONFIGDIR" in launcher, "matplotlib's config is in the private home: %s" % launcher)

    asserts.true(env, args[args.index("--step") + 1].endswith("tests/render/block.step"), args)
    asserts.equals(env, str(ctx.attr.pixels), args[args.index("--size") + 1])
    outs = [args[i + 1] for i in range(len(args)) if args[i] == "--out"]
    names = ["%s_%s.png" % (ctx.attr.name_under_test, v) for v in ctx.attr.views]
    asserts.equals(env, names, [o.split("=", 1)[1].split("/")[-1] for o in outs])
    asserts.equals(env, ctx.attr.views, [o.split("=", 1)[0] for o in outs])

    files = analysistest.target_under_test(env)[DefaultInfo].files.to_list()
    asserts.equals(env, names, [f.basename for f in files])
    asserts.equals(env, [f.path for f in files], [f.path for f in actions[0].outputs.to_list()])
    inputs = [f.basename for f in actions[0].inputs.to_list()]
    asserts.true(env, "block.step" in inputs, "the STEP file is an input: %s" % inputs)
    asserts.false(env, "block.stl" in inputs, "the STL file is not: %s" % inputs)
    return analysistest.end(env)

render_action_test = analysistest.make(
    _render_action_impl,
    attrs = {
        "name_under_test": attr.string(mandatory = True),
        "pixels": attr.int(mandatory = True),
        "views": attr.string_list(mandatory = True),
    },
)
