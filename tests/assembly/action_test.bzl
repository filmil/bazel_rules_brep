# SPDX-License-Identifier: Apache-2.0
"""Analysis test: cad_assembly's children, spec and action."""

load("@bazel_skylib//lib:unittest.bzl", "analysistest", "asserts")
load("//brep:defs.bzl", "CadAssemblyInfo")

def _assembly_action_impl(ctx):
    env = analysistest.begin(ctx)
    info = analysistest.target_under_test(env)[CadAssemblyInfo]
    asserts.equals(env, ctx.attr.children, [c.name for c in info.children])
    asserts.equals(env, [[float(x) for x in v.split(",")] for v in ctx.attr.positions], [c.pos for c in info.children])
    actions = [a for a in analysistest.target_actions(env) if a.mnemonic == "BrepAssembly"]
    asserts.equals(env, 1, len(actions), "BrepAssembly actions")
    argv = actions[0].argv
    sep = argv.index("--")
    asserts.true(env, "SOURCE_DATE_EPOCH=0" in argv[:sep], "the epoch reaches the runner")
    args = argv[sep + 2:]
    asserts.equals(env, ["--assemble"], args[:1])
    asserts.equals(env, info.step.path, args[args.index("--step") + 1])
    steps = sorted([f.basename for f in actions[0].inputs.to_list() if f.extension == "step"])
    asserts.equals(env, ["plate.step", "post.step"], steps)
    writes = [a for a in analysistest.target_actions(env) if a.mnemonic == "FileWrite"]
    asserts.equals(env, 1, len(writes), "the spec is written")
    spec = json.decode(writes[0].content)
    asserts.equals(env, ctx.attr.children, [c["name"] for c in spec["children"]])
    return analysistest.end(env)

assembly_action_test = analysistest.make(
    _assembly_action_impl,
    attrs = {
        "children": attr.string_list(mandatory = True),
        "positions": attr.string_list(mandatory = True, doc = "Each child's pos as \"x,y,z\"."),
    },
)
