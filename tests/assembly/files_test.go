// SPDX-License-Identifier: Apache-2.0

// Package files_test reads the STEP file cad_assembly writes.
package files_test

import (
	"flag"
	"os"
	"strings"
	"testing"

	"github.com/bazelbuild/rules_go/go/runfiles"
)

var step = flag.String("step", "", "stand.step, as a runfiles path")

func TestAssemblyStep(t *testing.T) {
	p, err := runfiles.Rlocation(*step)
	if err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	s := string(b)
	for _, want := range []string{
		"FILE_NAME('stand','1970-01-01T00:00:00'",
		"'plate'",
		"'post_1'",
		"'post_2'",
		"NEXT_ASSEMBLY_USAGE_OCCURRENCE",
	} {
		if !strings.Contains(s, want) {
			t.Errorf("stand.step lacks %q", want)
		}
	}
	if n := strings.Count(s, "MANIFOLD_SOLID_BREP"); n < 2 {
		t.Errorf("%d solids; the plate and the post (placed twice) are in it", n)
	}
	for _, bad := range []string{"bazel-out", "/sandbox/", "execroot"} {
		if strings.Contains(s, bad) {
			t.Errorf("stand.step holds a build path (%q)", bad)
		}
	}
}
