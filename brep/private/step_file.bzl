# SPDX-License-Identifier: Apache-2.0
"""The STEP file of a model: a cad_part's, or the one file a target names."""

load(":part.bzl", "CadPartInfo")

def step_file(ctx, target, attr):
    """The STEP file of a model.

    Anything but a cad_part, or a target whose files hold exactly one .step
    or .stp file, fails analysis with a message that names attr.

    Args:
      ctx: the rule context.
      target: the model: a cad_part, or a target that names one STEP file.
      attr: the name of the attribute target came from, for the message.

    Returns:
      The STEP File.
    """
    if CadPartInfo in target:
        return target[CadPartInfo].step
    steps = [f for f in target[DefaultInfo].files.to_list() if f.extension in ["step", "stp"]]
    if len(steps) != 1:
        fail("%s: %s must be a cad_part or name one STEP file; %s has %d" % (ctx.label, attr, target.label, len(steps)))
    return steps[0]
