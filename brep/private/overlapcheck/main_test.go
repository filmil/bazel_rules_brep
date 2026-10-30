// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const report = "pair\tbase\tpin\t0\n" +
	"pair\tbase\tlid\t2.5\n" +
	"pair\tpin\tlid\t0.0004\n"

func TestParse(t *testing.T) {
	p, err := Parse(strings.NewReader(report))
	if err != nil || len(p) != 3 || p[1] != (Pair{"base", "lid", 2.5}) {
		t.Fatalf("Parse = %v, %v", p, err)
	}
	for _, bad := range []string{
		"pair\ta\tb\n", "pear\ta\tb\t1\n", "pair\ta\tb\tx\n",
		"pair\ta\tb\tNaN\n", "pair\ta\tb\t+Inf\n", "pair\ta\tb\t-1\n",
		"pair a b 1\n", // spaces, not tabs
	} {
		if _, err := Parse(strings.NewReader(bad)); err == nil {
			t.Errorf("Parse(%q): want an error", bad)
		}
	}
}

func TestCheck(t *testing.T) {
	p, _ := Parse(strings.NewReader(report))
	// lid's 0.0004 with pin is under the epsilon; base and lid are not.
	_, err := Check(p, 0.001, "none")
	if err == nil || !strings.Contains(err.Error(), "base and lid share 2.500000") || strings.Contains(err.Error(), "pin and lid") {
		t.Errorf("none: %v", err)
	}
	if _, err := Check(p, 0.001, "overlap"); err != nil {
		t.Errorf("overlap: %v", err)
	}
	clean := []Pair{{"a", "b", 0}}
	if _, err := Check(clean, 0.001, "none"); err != nil {
		t.Errorf("clean: %v", err)
	}
	if _, err := Check(clean, 0.001, "overlap"); err == nil {
		t.Error("a clean assembly expected to overlap must fail")
	}
	if _, err := Check(clean, 0.001, "maybe"); err == nil {
		t.Error("an unknown expect must fail")
	}
}

// A name with a space is one field; a volume exactly at the epsilon is clean.
func TestNamesAndBoundary(t *testing.T) {
	p, err := Parse(strings.NewReader("pair\tleft arm\tright arm\t0.001\n"))
	if err != nil || len(p) != 1 || p[0].A != "left arm" {
		t.Fatalf("Parse: %v, %v", p, err)
	}
	if _, err := Check(p, 0.001, "none"); err != nil {
		t.Errorf("a volume equal to the epsilon must pass: %v", err)
	}
}

// run reads its settings from the environment.
func TestRun(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "r.txt")
	os.WriteFile(path, []byte("pair\ta\tb\t500\n"), 0o644)
	for _, c := range []struct {
		eps, expect string
		ok          bool
	}{
		{"0.001", "", false},
		{"0.001", "overlap", true},
		{"500", "none", true},
		{"NaN", "none", false},
		{"+Inf", "none", false},
		{"-1", "none", false},
	} {
		t.Setenv("OVERLAP_REPORT", path) // absolute: Rlocation returns it as is
		t.Setenv("OVERLAP_EPSILON", c.eps)
		t.Setenv("OVERLAP_EXPECT", c.expect)
		if err := run(); (err == nil) != c.ok {
			t.Errorf("eps %s expect %q: err %v, want ok=%v", c.eps, c.expect, err, c.ok)
		}
	}
}
