// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const good = "overlap\t0\nclearance\t5\n" +
	"hole\t-20\t-10\t1.6\nhole\t20\t10\t1.6\n" +
	"mount\t-20\t-10\t1.25\thole\nmount\t-20\t-10\t2.5\thole\nmount\t20.02\t10\t1.25\thole\n"

func TestCheck(t *testing.T) {
	rep, err := Parse(strings.NewReader(good))
	if err != nil {
		t.Fatal(err)
	}
	if bad := Check(rep, 0.001, 5, 0.05); len(bad) != 0 {
		t.Errorf("good fit: %v", bad)
	}
	// Tighter: the 0.02 mm offset is out, clearance 5 is under 6.
	bad := Check(rep, 0.001, 6, 0.01)
	all := strings.Join(bad, "\n")
	if len(bad) != 2 || !strings.Contains(all, "(20.000000, 10.000000) has no mount within 0.01 mm: the nearest mount is 0.020000 mm off") || !strings.Contains(all, "under the minimum 6") {
		t.Errorf("tight: %v", bad)
	}
	rep.Overlap = 1
	if bad := Check(rep, 0.001, 5, 0.05); len(bad) != 1 || !strings.Contains(bad[0], "share 1.000000") {
		t.Errorf("overlap: %v", bad)
	}
	rep.Overlap, rep.Mounts = 0, nil
	if bad := Check(rep, 0.001, 5, 0.05); len(bad) != 2 || !strings.Contains(bad[0], "no mount at all") {
		t.Errorf("no mounts: %v", bad)
	}
	// Only a boss's outside on the axis: too wide to go through the hole.
	rep.Holes = rep.Holes[:1]
	rep.Mounts = []Circle{{X: -20, Y: -10, R: 2.5, Kind: "pin"}}
	if bad := Check(rep, 0.001, 5, 0.05); len(bad) != 1 || !strings.Contains(bad[0], "2.500000 mm in radius, wider than the hole's 1.600000") {
		t.Errorf("wide mount: %v", bad)
	}
	// A pin that goes through the hole.
	rep.Mounts = []Circle{{X: -20, Y: -10, R: 1.5, Kind: "pin"}}
	if bad := Check(rep, 0.001, 5, 0.05); len(bad) != 0 {
		t.Errorf("pin: %v", bad)
	}
	rep.Holes = nil
	if bad := Check(rep, 0.001, 5, 0.05); len(bad) != 1 || !strings.Contains(bad[0], "no mounting holes") {
		t.Errorf("no holes: %v", bad)
	}
}

func TestParse(t *testing.T) {
	if r, err := Parse(strings.NewReader("overlap\t0\nclearance\tinf\nhole\t1\t2\t3\n")); err != nil || r.Clearance < 1e300 {
		t.Errorf("inf clearance: %v %v", r, err)
	}
	for _, bad := range []string{
		"clearance\t1\n",                          // no overlap
		"overlap\t-1\nclearance\t1\n",             // negative
		"overlap\tNaN\nclearance\t1\n",            // NaN
		"overlap\t0\nclearance\t1\nhole\t1\t2\n",  // short
		"overlap\t0\nclearance\t1\nspoke\t1\n",    // unknown
		"overlap\t0\nclearance\t1\nmount\tinf\t0\t1\thole\n",
		"overlap\t0\nclearance\t1\nmount\t0\t0\t1\n",         // no kind
		"overlap\t0\nclearance\t1\nmount\t0\t0\t1\tpeg\n",   // unknown kind
		"overlap\t0\nclearance\t1\nhole\t0\t0\t0\n",          // radius 0
		"overlap\t0\nclearance\t1\nhole\t0\t0\t-1\n",         // negative radius
		"overlap\t0\noverlap\t1\nclearance\t1\n",               // twice
		"overlap\t0\nclearance\t1\nclearance\t2\n",             // twice
	} {
		if _, err := Parse(strings.NewReader(bad)); err == nil {
			t.Errorf("Parse(%q): want an error", bad)
		}
	}
}

func TestRun(t *testing.T) {
	path := filepath.Join(t.TempDir(), "r.txt")
	os.WriteFile(path, []byte(good), 0o644)
	set := func(eps, clear, tol, expect string) {
		t.Setenv("FIT_REPORT", path)
		t.Setenv("FIT_EPSILON", eps)
		t.Setenv("FIT_MIN_CLEARANCE", clear)
		t.Setenv("FIT_HOLE_TOLERANCE", tol)
		t.Setenv("FIT_EXPECT", expect)
	}
	for _, c := range []struct {
		eps, clear, tol, expect string
		ok                      bool
	}{
		{"0.001", "5", "0.05", "", true},
		{"0.001", "6", "0.05", "", false},
		{"0.001", "6", "0.05", "fail", true},
		{"0.001", "5", "0.05", "fail", false},
		{"x", "5", "0.05", "", false},
		{"0.001", "5", "NaN", "", false},
		{"0.001", "5", "0.05", "maybe", false},
	} {
		set(c.eps, c.clear, c.tol, c.expect)
		if err := run(); (err == nil) != c.ok {
			t.Errorf("%+v: err %v", c, err)
		}
	}
	// A board without holes fails, so a known-bad test can expect it.
	os.WriteFile(path, []byte("overlap\t0\nclearance\t5\n"), 0o644)
	set("0.001", "5", "0.05", "")
	if err := run(); err == nil || !strings.Contains(err.Error(), "no mounting holes") {
		t.Errorf("no holes: %v", err)
	}
	set("0.001", "5", "0.05", "fail")
	if err := run(); err != nil {
		t.Errorf("no holes, expect fail: %v", err)
	}
}
