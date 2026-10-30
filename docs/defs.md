<!-- Generated with Stardoc: http://skydoc.bazel.build -->

Public API of rules_brep.

Load every rule from this file:

```starlark
load("@rules_brep//brep:defs.bzl", "determinism_test", "swap_test", "tool_toolchain")
```

The rules arrive in milestone M4 (see the issues of
https://github.com/filmil/bazel_rules_brep). This file is the only public
entry point; everything under `//brep/private` may change without notice.

<a id="cad_toolchain"></a>

## cad_toolchain

<pre>
load("@rules_brep//brep:defs.bzl", "cad_toolchain")

cad_toolchain(<a href="#cad_toolchain-name">name</a>, <a href="#cad_toolchain-python_version">python_version</a>, <a href="#cad_toolchain-runner">runner</a>)
</pre>

The CAD toolchain, for `@rules_brep//brep:toolchain_type`.

Its tool, `runner --part PART.py [--params JSON] [--summary OUT]`, imports
a part script, calls its `build(params)` function, and checks that the
result is a valid build123d shape. rules_brep registers one on the
hermetic Python of rules_python, with build123d and OCP locked by hash.

**ATTRIBUTES**


| Name  | Description | Type | Mandatory | Default |
| :------------- | :------------- | :------------- | :------------- | :------------- |
| <a id="cad_toolchain-name"></a>name |  A unique name for this target.   | <a href="https://bazel.build/concepts/labels#target-names">Name</a> | required |  |
| <a id="cad_toolchain-python_version"></a>python_version |  The runner's Python version.   | String | required |  |
| <a id="cad_toolchain-runner"></a>runner |  The CAD runner.   | <a href="https://bazel.build/concepts/labels">Label</a> | required |  |


<a id="tool_toolchain"></a>

## tool_toolchain

<pre>
load("@rules_brep//brep:defs.bzl", "tool_toolchain")

tool_toolchain(<a href="#tool_toolchain-name">name</a>, <a href="#tool_toolchain-tools">tools</a>)
</pre>

A toolchain that offers tools by name, for `run_tool`.

Example, a toolchain for another build of the CAD runner (the toolchain
type arrives with this module's toolchain issue):

```starlark
tool_toolchain(
    name = "my_cad_runner_impl",
    tools = {"//third_party/cad_runner:cad_runner": "cad_runner"},
)

toolchain(
    name = "my_cad_runner",
    toolchain = ":my_cad_runner_impl",
    toolchain_type = "@rules_brep//brep:toolchain_type",
)
```

**ATTRIBUTES**


| Name  | Description | Type | Mandatory | Default |
| :------------- | :------------- | :------------- | :------------- | :------------- |
| <a id="tool_toolchain-name"></a>name |  A unique name for this target.   | <a href="https://bazel.build/concepts/labels#target-names">Name</a> | required |  |
| <a id="tool_toolchain-tools"></a>tools |  Executable targets, each mapped to the name rules use for it.   | <a href="https://bazel.build/rules/lib/core/dict">Dictionary: Label -> String</a> | required |  |


<a id="CadToolchainInfo"></a>

## CadToolchainInfo

<pre>
load("@rules_brep//brep:defs.bzl", "CadToolchainInfo")

CadToolchainInfo(<a href="#CadToolchainInfo-python_version">python_version</a>)
</pre>

What the CAD toolchain offers beyond its `runner` tool.

**FIELDS**

| Name  | Description |
| :------------- | :------------- |
| <a id="CadToolchainInfo-python_version"></a>python_version |  string: the runner's Python version, such as "3.12".    |


<a id="determinism_test"></a>

## determinism_test

<pre>
load("@rules_brep//brep:defs.bzl", "determinism_test")

determinism_test(<a href="#determinism_test-name">name</a>, <a href="#determinism_test-target">target</a>, <a href="#determinism_test-kwargs">**kwargs</a>)
</pre>

Checks that two builds of `target` give byte-identical outputs.

The target is built twice in one build, under two configurations that
differ only in a setting no rule reads, so every action runs twice.
The test compares the SHA-256 of every output file, directories walked,
and fails on any difference (spec D1).

Two runs in the same second can hide a time stamp with a one-second
resolution, so pair this with a header scan where a format has one. CI
also builds every determinism_test target in two fresh output bases and
compares the results.

Example:

```starlark
determinism_test(
    name = "bracket_determinism_test",
    target = ":bracket",
)
```


**PARAMETERS**


| Name  | Description | Default Value |
| :------------- | :------------- | :------------- |
| <a id="determinism_test-name"></a>name |  the test's name.   |  none |
| <a id="determinism_test-target"></a>target |  the target whose outputs must not change between builds.   |  none |
| <a id="determinism_test-kwargs"></a>kwargs |  common test attributes, such as `size` and `tags`.   |  none |


<a id="swap_test"></a>

## swap_test

<pre>
load("@rules_brep//brep:defs.bzl", "swap_test")

swap_test(<a href="#swap_test-name">name</a>, <a href="#swap_test-targets">targets</a>, <a href="#swap_test-kwargs">**kwargs</a>)
</pre>

Builds targets with every tool swapped for a stub, and checks them.

The targets are built with `--@rules_brep//brep/toolchains:use_stub`,
so each tool toolchain that honors the flag resolves to the stub tool.
The stub writes a record into every output, files and directories
alike. The test fails if any output file of the targets lacks the
record: some action made it without a toolchain tool.

Example:

```starlark
swap_test(
    name = "swap_test",
    targets = [":gerbers", ":bom"],
)
```


**PARAMETERS**


| Name  | Description | Default Value |
| :------------- | :------------- | :------------- |
| <a id="swap_test-name"></a>name |  the test's name.   |  none |
| <a id="swap_test-targets"></a>targets |  targets whose outputs must all come from the stub.   |  none |
| <a id="swap_test-kwargs"></a>kwargs |  common test attributes, such as `size` and `tags`.   |  none |


