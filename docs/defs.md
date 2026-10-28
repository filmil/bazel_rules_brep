<!-- Generated with Stardoc: http://skydoc.bazel.build -->

Public API of rules_brep.

Load every rule from this file. For now it holds only the API version:

```starlark
load("@rules_brep//brep:defs.bzl", "RULES_BREP_API_VERSION")
```

The rules arrive in milestone M4 (see the issues of
https://github.com/filmil/bazel_rules_brep). This file is the only public
entry point; everything under `//brep/private` may change without notice.

