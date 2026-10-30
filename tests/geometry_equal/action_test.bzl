# SPDX-License-Identifier: Apache-2.0
"""Analysis test: geometry_equal_test's measure actions and test environment."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")

def _measure_action_impl(ctx):
    env = analysistest.begin(ctx)
    actions = [a for a in analysistest.target_actions(env) if a.mnemonic == "BrepMeasure"]
    asserts.equals(env, 2, len(actions), "BrepMeasure actions")
    for action, side, step in zip(actions, ["a", "b"], ctx.attr.steps):
        args = action.argv[action.argv.index("--") + 2:]
        asserts.true(env, args[args.index("--step") + 1].endswith(step), "%s measures %s: %s" % (side, step, args))
        out = [f.basename for f in action.outputs.to_list()]
        asserts.equals(env, ["%s.%s.txt" % (ctx.attr.name_under_test, side)], out)
    run_env = analysistest.target_under_test(env)[RunEnvironmentInfo].environment
    asserts.equals(env, ctx.attr.want_env, {k: run_env[k] for k in ctx.attr.want_env})
    return analysistest.end(env)

measure_action_test = analysistest.make(
    _measure_action_impl,
    attrs = {
        "name_under_test": attr.string(mandatory = True),
        "steps": attr.string_list(mandatory = True),
        "want_env": attr.string_dict(mandatory = True),
    },
)
