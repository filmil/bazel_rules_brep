# SPDX-License-Identifier: Apache-2.0
"""Analysis test: cad_part's action, its arguments and its outputs."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//brep:defs.bzl", "CadPartInfo")

def _part_action_impl(ctx):
    env = analysistest.begin(ctx)
    actions = [a for a in analysistest.target_actions(env) if a.mnemonic == "BrepPart"]
    asserts.equals(env, 1, len(actions), "BrepPart actions")
    argv = actions[0].argv
    sep = argv.index("--")
    launcher, args = argv[:sep], argv[sep + 2:]
    asserts.true(env, "SOURCE_DATE_EPOCH=0" in launcher, "the epoch reaches the runner: %s" % launcher)

    def value(flag):
        return args[args.index(flag) + 1]

    asserts.equals(env, ctx.attr.params_json, value("--params"))
    asserts.equals(env, "bracket", value("--name"))
    asserts.true(env, value("--part").endswith("tests/part/bracket.py"), value("--part"))
    info = analysistest.target_under_test(env)[CadPartInfo]
    asserts.equals(env, [info.step.path, info.stl.path], [value("--step"), value("--stl")])
    asserts.equals(env, ["bracket.step", "bracket.stl"], [info.step.basename, info.stl.basename])
    inputs = [f.basename for f in actions[0].inputs.to_list()]
    asserts.true(env, "dims.py" in inputs, "deps are inputs: %s" % inputs)
    return analysistest.end(env)

part_action_test = analysistest.make(
    _part_action_impl,
    attrs = {"params_json": attr.string(mandatory = True)},
)

def _cq_runner_impl(ctx):
    """The CadQuery part's action runs the CadQuery runner, not build123d's."""
    env = analysistest.begin(ctx)
    actions = [a for a in analysistest.target_actions(env) if a.mnemonic == "BrepPart"]
    asserts.equals(env, 1, len(actions), "BrepPart actions")
    argv = actions[0].argv
    tool = argv[argv.index("--") + 1]
    asserts.true(env, tool.endswith("/cq_runner"), "the tool is the CadQuery runner: %s" % tool)
    return analysistest.end(env)

cq_runner_test = analysistest.make(_cq_runner_impl)
