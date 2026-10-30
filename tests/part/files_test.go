// SPDX-License-Identifier: Apache-2.0

// Package files_test reads the STEP and STL files cad_part writes.
package files_test

import (
	"encoding/binary"
	"flag"
	"os"
	"strings"
	"testing"

	"github.com/bazelbuild/rules_go/go/runfiles"
)

var files = flag.String("files", "", "the outputs of :bracket, as runfiles paths")

// read returns the output whose name ends in suffix.
func read(t *testing.T, suffix string) []byte {
	t.Helper()
	var rpath string
	// Bazel splits the expanded paths into arguments: the first is the
	// flag's value, the others are positional.
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

// The name is the target's, the time is the epoch, the system is build123d,
// and no path of the build is in the file.
func TestStep(t *testing.T) {
	s := string(read(t, ".step"))
	for _, want := range []string{
		"ISO-10303-21;",
		"FILE_NAME('bracket','1970-01-01T00:00:00'",
		"'build123d'",
		"MANIFOLD_SOLID_BREP",
	} {
		if !strings.Contains(s, want) {
			t.Errorf("bracket.step lacks %q", want)
		}
	}
	for _, bad := range []string{"bazel-out", "/sandbox/", "execroot"} {
		if strings.Contains(s, bad) {
			t.Errorf("bracket.step holds a build path (%q)", bad)
		}
	}
}

// Binary STL: an 80-byte header, a triangle count, 50 bytes per triangle.
func TestStl(t *testing.T) {
	b := read(t, ".stl")
	if len(b) < 84 {
		t.Fatalf("bracket.stl is %d bytes", len(b))
	}
	n := binary.LittleEndian.Uint32(b[80:84])
	if n < 100 {
		t.Errorf("%d triangles; a bracket with two holes has far more", n)
	}
	if want := 84 + 50*int(n); len(b) != want {
		t.Errorf("bracket.stl is %d bytes, want %d for %d triangles", len(b), want, n)
	}
}
