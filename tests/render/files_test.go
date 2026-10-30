// SPDX-License-Identifier: Apache-2.0

// Package files_test reads the PNG files cad_render writes.
package files_test

import (
	"bytes"
	"encoding/binary"
	"flag"
	"image"
	"image/png"
	"os"
	"strings"
	"testing"

	"github.com/bazelbuild/rules_go/go/runfiles"
)

var files = flag.String("files", "", "the outputs of :views, as runfiles paths")

var views = []string{"front", "back", "left", "right", "top", "bottom"}

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

// chunks lists the chunk types of a PNG file.
func chunks(t *testing.T, b []byte) []string {
	t.Helper()
	if !bytes.HasPrefix(b, []byte("\x89PNG\r\n\x1a\n")) {
		t.Fatal("not a PNG file")
	}
	var kinds []string
	for i := 8; i < len(b); {
		n := int(binary.BigEndian.Uint32(b[i:]))
		kinds = append(kinds, string(b[i+4:i+8]))
		i += 12 + n
	}
	return kinds
}

// lit counts the pixels that are not the white background.
func lit(img image.Image) int {
	n := 0
	r := img.Bounds()
	for y := r.Min.Y; y < r.Max.Y; y++ {
		for x := r.Min.X; x < r.Max.X; x++ {
			if cr, cg, cb, _ := img.At(x, y).RGBA(); cr != 0xffff || cg != 0xffff || cb != 0xffff {
				n++
			}
		}
	}
	return n
}

// Each view is a 128 x 128 PNG with no chunk that could hold a time, a
// path or a software name, and the model covers part of it.
func TestViews(t *testing.T) {
	seen := map[string]string{}
	for _, v := range views {
		b := read(t, "views_"+v+".png")
		if got := strings.Join(chunks(t, b), " "); got != "IHDR IDAT IEND" {
			t.Errorf("%s: chunks %q, want IHDR IDAT IEND", v, got)
		}
		img, err := png.Decode(bytes.NewReader(b))
		if err != nil {
			t.Fatalf("%s: %v", v, err)
		}
		if s := img.Bounds().Size(); s.X != 128 || s.Y != 128 {
			t.Errorf("%s: %v, want 128 x 128", v, s)
		}
		// The model fills the picture to its margin on one side, so it covers
		// some of it, and not all.
		if n := lit(img); n < 128*128/10 || n > 128*128*9/10 {
			t.Errorf("%s: %d of %d pixels show the model", v, n, 128*128)
		}
		if other, ok := seen[string(b)]; ok {
			t.Errorf("%s is the same picture as %s", v, other)
		}
		seen[string(b)] = v
	}
}
