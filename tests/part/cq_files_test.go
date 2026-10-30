// SPDX-License-Identifier: Apache-2.0

// Package cq_files_test reads the STEP and STL files of a CadQuery part.
package cq_files_test

import (
	"encoding/binary"
	"flag"
	"os"
	"strings"
	"testing"

	"github.com/bazelbuild/rules_go/go/runfiles"
)

var files = flag.String("files", "", "the outputs of :cq_block, as runfiles paths")

func read(t *testing.T, suffix string) []byte {
	t.Helper()
	var rpath string
	for _, f := range append(strings.Fields(*files), flag.Args()...) {
		if strings.HasSuffix(f, suffix) {
			rpath = f
		}
	}
	if rpath == "" {
		t.Fatalf("no output ends in %s: %s %v", suffix, *files, flag.Args())
	}
	p, err := runfiles.Rlocation(rpath)
	if err != nil {
		t.Fatal(err)
	}
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

// The name is the target's, the time is the epoch, the system is CadQuery,
// and no path of the build is in the file.
func TestStep(t *testing.T) {
	s := string(read(t, ".step"))
	for _, want := range []string{
		"ISO-10303-21;",
		"FILE_NAME('cq_block','1970-01-01T00:00:00'",
		"'cadquery'",
		"MANIFOLD_SOLID_BREP",
	} {
		if !strings.Contains(s, want) {
			t.Errorf("the STEP file lacks %q", want)
		}
	}
	for _, bad := range []string{"bazel-out", "/execroot/", "/sandbox/"} {
		if strings.Contains(s, bad) {
			t.Errorf("the STEP file holds a path of the build: %q", bad)
		}
	}
}

// Binary STL: an 80-byte header, a count, 50 bytes per triangle.
func TestStl(t *testing.T) {
	b := read(t, ".stl")
	if len(b) < 84 {
		t.Fatalf("%d bytes", len(b))
	}
	n := binary.LittleEndian.Uint32(b[80:84])
	if n < 12 || len(b) != 84+50*int(n) {
		t.Errorf("%d triangles in %d bytes", n, len(b))
	}
}
