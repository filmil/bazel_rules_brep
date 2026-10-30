// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const box = `volume 6000.000000
area 2200.000000
center 0.000000 0.000000 0.000000
min -5.000000 -10.000000 -15.000000
max 5.000000 10.000000 15.000000
solids 1
faces 6
`

func parse(t *testing.T, s string) []Line {
	t.Helper()
	l, err := Parse(s)
	if err != nil {
		t.Fatal(err)
	}
	return l
}

func TestEqual(t *testing.T) {
	d, err := Compare(parse(t, box), parse(t, box), Tolerance{})
	if err != nil || len(d) != 0 {
		t.Errorf("Compare(box, box) = %v, %v", d, err)
	}
}

func TestWithinTolerance(t *testing.T) {
	b := strings.Replace(box, "volume 6000.000000", "volume 6000.005000", 1)
	b = strings.Replace(b, "min -5.000000", "min -5.000001", 1)
	// 0.005 of 6000 is under 1e-6 relative (0.006); 1e-6 of 5 mm is not, so
	// the absolute tolerance covers it.
	if d, err := Compare(parse(t, box), parse(t, b), Tolerance{Abs: 1e-6, Rel: 1e-6}); err != nil || len(d) != 0 {
		t.Errorf("within tolerance: %v, %v", d, err)
	}
	d, err := Compare(parse(t, box), parse(t, b), Tolerance{})
	if err != nil || len(d) != 2 {
		t.Fatalf("no tolerance: %v, %v", d, err)
	}
	if !strings.HasPrefix(d[0], "volume: 6000.000000 != 6000.005000") || !strings.HasPrefix(d[1], "min[0]: ") {
		t.Errorf("diffs %q", d)
	}
}

func TestCountsExact(t *testing.T) {
	b := strings.Replace(box, "faces 6", "faces 7", 1)
	d, err := Compare(parse(t, box), parse(t, b), Tolerance{Abs: 10, Rel: 1})
	if err != nil || len(d) != 1 || !strings.Contains(d[0], "faces: 6 != 7 (a count") {
		t.Errorf("Compare = %q, %v", d, err)
	}
}

func TestMovedHole(t *testing.T) {
	// Same volume, area and box; the center moved.
	b := strings.Replace(box, "center 0.000000 0.000000", "center 0.000000 0.500000", 1)
	d, err := Compare(parse(t, box), parse(t, b), Tolerance{Abs: 1e-6, Rel: 1e-6})
	if err != nil || len(d) != 1 || !strings.HasPrefix(d[0], "center[1]: ") {
		t.Errorf("Compare = %q, %v", d, err)
	}
}

func TestNotComparable(t *testing.T) {
	for _, c := range []struct{ b, want string }{
		{strings.Replace(box, "faces 6\n", "", 1), "7 and 6 lines"},
		{strings.Replace(box, "solids 1", "shells 1", 1), `line 6 is "solids" in a and "shells" in b`},
		{strings.Replace(box, "area 2200.000000", "area 2200.000000 1.000000", 1), "area has 1 values in a and 2 in b"},
		{strings.Replace(box, "area 2200.000000", "area x.y", 1), "area in b"},
	} {
		_, err := Compare(parse(t, box), parse(t, c.b), Tolerance{})
		if err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("Compare(%q): %v, want %q", c.want, err, c.want)
		}
	}
	if _, err := Parse("volume\n"); err == nil || !strings.Contains(err.Error(), "line 1") {
		t.Errorf("Parse(volume) = %v", err)
	}
	if _, err := Parse(""); err == nil || !strings.Contains(err.Error(), "no measurements") {
		t.Errorf("Parse(\"\") = %v", err)
	}
}

func TestNotCountsOrNumbers(t *testing.T) {
	for _, c := range []struct{ a, b, want string }{
		{"faces NaN\n", "faces NaN\n", `"NaN" is neither a count nor a number`},
		{"volume NaN.0\n", "volume NaN.0\n", `"NaN.0" is not a finite number`},
		{"volume 1e-5\n", "volume 1e-5\n", `"1e-5" is neither a count`},
		{"volume +Inf.\n", "volume 1.0\n", "is not a finite number"},
		{"faces 6\n", "faces 6.0\n", "a count and a number"},
	} {
		_, err := Compare(parse(t, c.a), parse(t, c.b), Tolerance{})
		if err == nil || !strings.Contains(err.Error(), c.want) {
			t.Errorf("Compare(%q, %q) = %v, want %q", c.a, c.b, err, c.want)
		}
	}
}

func TestSixthDecimal(t *testing.T) {
	// 5.000001 - 5.000000 is 1.0000000001e-06 in binary: still within 1e-6.
	if !(Tolerance{Abs: 1e-6}).Within(5.000001, 5.0) {
		t.Error("5.000001 and 5.000000 are not within 1e-6")
	}
	if (Tolerance{Abs: 1e-6}).Within(5.000002, 5.0) {
		t.Error("5.000002 and 5.000000 are within 1e-6")
	}
}

// runWith runs the test program on a and b with env set.
func runWith(t *testing.T, a, b string, env map[string]string) error {
	t.Helper()
	d := t.TempDir()
	pa, pb := filepath.Join(d, "a.txt"), filepath.Join(d, "b.txt")
	if err := os.WriteFile(pa, []byte(a), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(pb, []byte(b), 0o644); err != nil {
		t.Fatal(err)
	}
	// Absolute paths pass through the runfiles library unchanged.
	all := map[string]string{"GEQ_A": pa, "GEQ_B": pb, "GEQ_ABS": "0", "GEQ_REL": "0", "GEQ_EXPECT": ""}
	for k, v := range env {
		all[k] = v
	}
	for k, v := range all {
		t.Setenv(k, v)
	}
	return run()
}

func TestRun(t *testing.T) {
	moved := strings.Replace(box, "center 0.000000 0.000000", "center 0.000000 0.500000", 1)
	for _, c := range []struct {
		name, b string
		env     map[string]string
		want    string // "" for success
	}{
		{"equal", box, nil, ""},
		{"differ", moved, nil, "the shapes differ (abs 0, rel 0):\n  center[1]: "},
		{"differ as expected", moved, map[string]string{"GEQ_EXPECT": "different"}, ""},
		{"equal but expected to differ", box, map[string]string{"GEQ_EXPECT": "different"}, "but should differ"},
		{"loose", moved, map[string]string{"GEQ_ABS": "0.5"}, ""},
		{"bad expect", box, map[string]string{"GEQ_EXPECT": "same"}, `GEQ_EXPECT="same": want equal or different`},
		{"bad abs", box, map[string]string{"GEQ_ABS": "x"}, `GEQ_ABS="x": want a number, 0 or more`},
		{"negative rel", box, map[string]string{"GEQ_REL": "-1"}, `GEQ_REL="-1"`},
		{"no a", box, map[string]string{"GEQ_A": ""}, "GEQ_A is not set"},
		{"empty b", "", nil, "no measurements"},
	} {
		err := runWith(t, box, c.b, c.env)
		if c.want == "" && err != nil {
			t.Errorf("%s: %v", c.name, err)
		}
		if c.want != "" && (err == nil || !strings.Contains(err.Error(), c.want)) {
			t.Errorf("%s: %v, want %q", c.name, err, c.want)
		}
	}
}

func TestWithin(t *testing.T) {
	tol := Tolerance{Abs: 0.1, Rel: 0.01}
	for _, c := range []struct {
		a, b float64
		want bool
	}{
		{100, 101.1, true},  // 0.1 + 1.011
		{100, 101.2, false}, // over 1.112
		{0, 0.1, true},      // absolute
		{0, 0.11, false},
		{-100, -101.1, true}, // by size
	} {
		if got := tol.Within(c.a, c.b); got != c.want {
			t.Errorf("Within(%g, %g) = %v", c.a, c.b, got)
		}
	}
}
