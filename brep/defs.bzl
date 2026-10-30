# SPDX-License-Identifier: Apache-2.0
"""Public API of hdlf_rules_brep.

Load every rule from this file:

```starlark
load("@hdlf_rules_brep//brep:defs.bzl", "determinism_test", "swap_test", "tool_toolchain")
```

The rules arrive in milestone M4 (see the issues of
https://github.com/filmil/bazel_rules_brep). This file is the only public
entry point; everything under `//brep/private` may change without notice.
"""

load("//brep/private:assembly.bzl", _CadAssemblyInfo = "CadAssemblyInfo", _cad_assembly = "cad_assembly")
load("//brep/private:cad_toolchain.bzl", _CadToolchainInfo = "CadToolchainInfo", _cad_toolchain = "cad_toolchain")
load("//brep/private:check.bzl", _cad_check_test = "cad_check_test")
load("//brep/private:determinism.bzl", _determinism_test = "determinism_test")
load("//brep/private:geometry_equal.bzl", _geometry_equal_test = "geometry_equal_test")
load("//brep/private:interference.bzl", _interference_test = "interference_test")
load("//brep/private:part.bzl", _CadPartInfo = "CadPartInfo", _cad_part = "cad_part")
load("//brep/private:pcb_fit.bzl", _pcb_fit_test = "pcb_fit_test")
load("//brep/private:render.bzl", _cad_render = "cad_render")
load("//brep/private:swap_test.bzl", _swap_test = "swap_test")
load("//brep/private:toolchains.bzl", _tool_toolchain = "tool_toolchain")

CadAssemblyInfo = _CadAssemblyInfo
CadPartInfo = _CadPartInfo
CadToolchainInfo = _CadToolchainInfo
cad_assembly = _cad_assembly
cad_check_test = _cad_check_test
cad_part = _cad_part
cad_render = _cad_render
cad_toolchain = _cad_toolchain
determinism_test = _determinism_test
geometry_equal_test = _geometry_equal_test
interference_test = _interference_test
pcb_fit_test = _pcb_fit_test
swap_test = _swap_test
tool_toolchain = _tool_toolchain

# The release this file belongs to. It lets a consumer check, in a test,
# that the module it resolved is the one it expects.
RULES_BREP_API_VERSION = "0"
