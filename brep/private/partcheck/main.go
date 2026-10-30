// SPDX-License-Identifier: Apache-2.0

// Command partcheck is cad_check_test's checker (issue #12).
//
// It reads the measurer's output ("key value..." per line: volume, min,
// max, and min_wall when it was measured) and checks the limits it is
// given. Every limit that does not hold is listed, with the value found.
//
// Environment: CHECK_MEASURE (the measurements' runfiles path), and the
// limits, each empty when not checked: CHECK_MIN_VOLUME, CHECK_MAX_VOLUME
// (mm^3), CHECK_MAX_SIZE ("X Y Z", the largest bounding box, mm),
// CHECK_MIN_WALL (mm). CHECK_EXPECT is "pass" (the default), or "fail" for
// a known-bad part: then the test fails when every limit holds.
package main

import (
	"bufio"
	"fmt"
	"io"
	"math"
	"os"
	"strconv"
	"strings"

	"github.com/bazelbuild/rules_go/go/runfiles"
)

// Parse reads the measurer's output into a map from key to values.
func Parse(r io.Reader) (map[string][]float64, error) {
	m := map[string][]float64{}
	s := bufio.NewScanner(r)
	for n := 1; s.Scan(); n++ {
		f := strings.Fields(s.Text())
		if len(f) == 0 {
			continue
		}
		if len(f) == 1 {
			return nil, fmt.Errorf("line %d: %s has no value", n, f[0])
		}
		if _, dup := m[f[0]]; dup {
			return nil, fmt.Errorf("line %d: %s appears twice", n, f[0])
		}
		var vs []float64
		for _, x := range f[1:] {
			v, err := strconv.ParseFloat(x, 64)
			if err != nil || math.IsNaN(v) || math.IsInf(v, 0) {
				return nil, fmt.Errorf("line %d: %q is not a finite number", n, x)
			}
			vs = append(vs, v)
		}
		m[f[0]] = vs
	}
	return m, s.Err()
}

// Limits are the checks to make; nil means not checked.
type Limits struct {
	MinVolume, MaxVolume, MinWall *float64
	MaxSize                       []float64
}

func one(m map[string][]float64, key string) (float64, error) {
	v, ok := m[key]
	if !ok || len(v) != 1 {
		return 0, fmt.Errorf("the measurements have no %s", key)
	}
	return v[0], nil
}

// Failure is a limit that does not hold: its name (min_volume,
// max_volume, max_size, min_wall) and a description.
type Failure struct{ Limit, Text string }

// Check returns each limit that does not hold.
func Check(m map[string][]float64, l Limits) ([]Failure, error) {
	var bad []Failure
	if l.MinVolume != nil || l.MaxVolume != nil {
		v, err := one(m, "volume")
		if err != nil {
			return nil, err
		}
		if l.MinVolume != nil && v < *l.MinVolume {
			bad = append(bad, Failure{"min_volume", fmt.Sprintf("volume %.6f mm^3 is below the minimum %g", v, *l.MinVolume)})
		}
		if l.MaxVolume != nil && v > *l.MaxVolume {
			bad = append(bad, Failure{"max_volume", fmt.Sprintf("volume %.6f mm^3 is above the maximum %g", v, *l.MaxVolume)})
		}
	}
	if l.MaxSize != nil {
		lo, hi := m["min"], m["max"]
		if len(lo) != 3 || len(hi) != 3 {
			return nil, fmt.Errorf("the measurements have no bounding box")
		}
		for i, axis := range []string{"X", "Y", "Z"} {
			size := hi[i] - lo[i]
			if size < 0 {
				return nil, fmt.Errorf("the bounding box's min %v is above its max %v in %s", lo[i], hi[i], axis)
			}
			if size > l.MaxSize[i] {
				bad = append(bad, Failure{"max_size", fmt.Sprintf("size in %s %.6f mm is above the maximum %g", axis, size, l.MaxSize[i])})
			}
		}
	}
	if l.MinWall != nil {
		w, err := one(m, "min_wall")
		if err != nil {
			return nil, err
		}
		if w < *l.MinWall {
			bad = append(bad, Failure{"min_wall", fmt.Sprintf("the thinnest wall, %.6f mm, is below the minimum %g", w, *l.MinWall)})
		}
	}
	return bad, nil
}

func number(env string) (*float64, error) {
	s := os.Getenv(env)
	if s == "" {
		return nil, nil
	}
	v, err := strconv.ParseFloat(s, 64)
	if err != nil || math.IsNaN(v) || math.IsInf(v, 0) || v < 0 {
		return nil, fmt.Errorf("%s=%q: want a finite number, 0 or more", env, s)
	}
	return &v, nil
}

func limits() (Limits, error) {
	var l Limits
	var err error
	if l.MinVolume, err = number("CHECK_MIN_VOLUME"); err != nil {
		return l, err
	}
	if l.MaxVolume, err = number("CHECK_MAX_VOLUME"); err != nil {
		return l, err
	}
	if l.MinWall, err = number("CHECK_MIN_WALL"); err != nil {
		return l, err
	}
	if s := os.Getenv("CHECK_MAX_SIZE"); s != "" {
		f := strings.Fields(s)
		if len(f) != 3 {
			return l, fmt.Errorf("CHECK_MAX_SIZE=%q: want X Y Z", s)
		}
		for _, x := range f {
			v, err := strconv.ParseFloat(x, 64)
			if err != nil || math.IsNaN(v) || math.IsInf(v, 0) || v < 0 {
				return l, fmt.Errorf("CHECK_MAX_SIZE=%q: want three finite numbers, 0 or more", s)
			}
			l.MaxSize = append(l.MaxSize, v)
		}
	}
	return l, nil
}

func run() error {
	path, err := runfiles.Rlocation(os.Getenv("CHECK_MEASURE"))
	if err != nil {
		return err
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	m, err := Parse(f)
	if err != nil {
		return err
	}
	l, err := limits()
	if err != nil {
		return err
	}
	bad, err := Check(m, l)
	if err != nil {
		return err
	}
	var texts []string
	failing := map[string]bool{}
	for _, b := range bad {
		texts = append(texts, b.Text)
		failing[b.Limit] = true
	}
	switch expect := os.Getenv("CHECK_EXPECT"); expect {
	case "", "pass":
		if len(bad) > 0 {
			return fmt.Errorf("%d limit(s) do not hold:\n  %s", len(bad), strings.Join(texts, "\n  "))
		}
		fmt.Println("every limit holds")
	case "fail":
		if len(bad) == 0 {
			return fmt.Errorf("expected a limit to fail; every limit holds")
		}
		// CHECK_EXPECT_FAILING names the limits that must fail, and only
		// they: a known-bad part fails for the reason it was made for.
		if want := os.Getenv("CHECK_EXPECT_FAILING"); want != "" {
			names := map[string]bool{}
			for _, n := range strings.Split(want, ",") {
				names[n] = true
			}
			for n := range names {
				if !failing[n] {
					return fmt.Errorf("expected %s to fail; it holds. Failing: %s", n, strings.Join(texts, "; "))
				}
			}
			for n := range failing {
				if !names[n] {
					return fmt.Errorf("%s fails, but only %s were expected to: %s", n, want, strings.Join(texts, "; "))
				}
			}
		}
		fmt.Printf("as expected, %d limit(s) do not hold:\n  %s\n", len(bad), strings.Join(texts, "\n  "))
	default:
		return fmt.Errorf("CHECK_EXPECT=%q: want pass or fail", expect)
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "cad_check_test:", err)
		os.Exit(1)
	}
}
