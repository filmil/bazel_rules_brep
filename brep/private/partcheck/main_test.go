// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const measured = `volume 6000.000000
area 2200.000000
center 0.000000 0.000000 0.000000
min -5.000000 -10.000000 -15.000000
max 5.000000 10.000000 15.000000
solids 1
faces 6
edges 12
vertices 8
min_wall 10.000000
`

func f(v float64) *float64 { return &v }

func TestCheck(t *testing.T) {
	m, err := Parse(strings.NewReader(measured))
	if err != nil {
		t.Fatal(err)
	}
	ok := Limits{MinVolume: f(5000), MaxVolume: f(6000), MinWall: f(10), MaxSize: []float64{10, 20, 30}}
	if bad, err := Check(m, ok); err != nil || len(bad) != 0 {
		t.Errorf("at the limits: %v %v", bad, err)
	}
	tight := Limits{MinVolume: f(6001), MaxVolume: f(5999), MinWall: f(10.5), MaxSize: []float64{9, 20, 29}}
	bad, err := Check(m, tight)
	if err != nil || len(bad) != 5 {
		t.Fatalf("tight: %v %v", bad, err)
	}
	var texts []string
	for _, b := range bad {
		texts = append(texts, b.Text)
	}
	all := strings.Join(texts, "\n")
	for _, want := range []string{"below the minimum 6001", "above the maximum 5999", "size in X 10.000000", "size in Z 30.000000", "thinnest wall, 10.000000 mm"} {
		if !strings.Contains(all, want) {
			t.Errorf("no %q in %s", want, all)
		}
	}
	// No min_wall measured, but asked for: an error, not a pass.
	m2, _ := Parse(strings.NewReader(strings.Replace(measured, "min_wall 10.000000\n", "", 1)))
	if _, err := Check(m2, Limits{MinWall: f(1)}); err == nil {
		t.Error("a missing min_wall must be an error")
	}
	for _, bad := range []string{"volume NaN\n", "volume 1\nvolume 2\n", "volume\n"} {
		if _, err := Parse(strings.NewReader(bad)); err == nil {
			t.Errorf("Parse(%q): want an error", bad)
		}
	}
	inverted, _ := Parse(strings.NewReader("min 5 0 0\nmax 1 1 1\n"))
	if _, err := Check(inverted, Limits{MaxSize: []float64{10, 10, 10}}); err == nil {
		t.Error("a min above the max must be an error")
	}
}

func TestRun(t *testing.T) {
	path := filepath.Join(t.TempDir(), "m.txt")
	os.WriteFile(path, []byte(measured), 0o644)
	for _, c := range []struct {
		env map[string]string
		ok  bool
	}{
		{map[string]string{"CHECK_MAX_VOLUME": "7000"}, true},
		{map[string]string{"CHECK_MAX_VOLUME": "5000"}, false},
		{map[string]string{"CHECK_MAX_VOLUME": "5000", "CHECK_EXPECT": "fail"}, true},
		{map[string]string{"CHECK_MAX_VOLUME": "7000", "CHECK_EXPECT": "fail"}, false},
		{map[string]string{"CHECK_MAX_SIZE": "10 20"}, false},
		{map[string]string{"CHECK_MIN_WALL": "NaN"}, false},
		{map[string]string{"CHECK_EXPECT": "maybe"}, false},
		// The named limits, and only they, must fail.
		{map[string]string{"CHECK_MAX_VOLUME": "5000", "CHECK_EXPECT": "fail", "CHECK_EXPECT_FAILING": "max_volume"}, true},
		{map[string]string{"CHECK_MAX_VOLUME": "5000", "CHECK_EXPECT": "fail", "CHECK_EXPECT_FAILING": "min_wall"}, false},
		{map[string]string{"CHECK_MAX_VOLUME": "5000", "CHECK_MIN_WALL": "11", "CHECK_EXPECT": "fail", "CHECK_EXPECT_FAILING": "max_volume"}, false},
	} {
		for _, k := range []string{"CHECK_MIN_VOLUME", "CHECK_MAX_VOLUME", "CHECK_MAX_SIZE", "CHECK_MIN_WALL", "CHECK_EXPECT", "CHECK_EXPECT_FAILING"} {
			t.Setenv(k, c.env[k])
		}
		t.Setenv("CHECK_MEASURE", path)
		if err := run(); (err == nil) != c.ok {
			t.Errorf("%v: err %v, want ok=%v", c.env, err, c.ok)
		}
	}
}
