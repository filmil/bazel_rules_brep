// SPDX-License-Identifier: Apache-2.0

// Command overlapcheck is interference_test's checker (issue #13).
//
// It reads the runner's interference report, one line per pair of
// children, fields separated by tabs: "pair", A, B, VOLUME, the volume in
// mm^3 that A and B share. A pair shares volume when VOLUME is above
// OVERLAP_EPSILON; one exactly at it does not.
//
// OVERLAP_EXPECT is "none" (the default): the test fails, naming each pair
// that shares volume. It is "overlap" for a known-bad assembly: the test
// fails when no pair shares any.
//
// Environment: OVERLAP_REPORT (the report's runfiles path), OVERLAP_EPSILON
// (mm^3), OVERLAP_EXPECT.
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

// Pair is two children and the volume they share.
type Pair struct {
	A, B   string
	Volume float64
}

// Parse reads a report.
func Parse(r io.Reader) ([]Pair, error) {
	var out []Pair
	s := bufio.NewScanner(r)
	for n := 1; s.Scan(); n++ {
		if strings.TrimSpace(s.Text()) == "" {
			continue
		}
		f := strings.Split(s.Text(), "\t")
		if len(f) != 4 || f[0] != "pair" {
			return nil, fmt.Errorf("line %d: want pair, A, B and VOLUME separated by tabs, got %q", n, s.Text())
		}
		v, err := strconv.ParseFloat(f[3], 64)
		if err != nil {
			return nil, fmt.Errorf("line %d: %v", n, err)
		}
		if math.IsNaN(v) || math.IsInf(v, 0) || v < 0 {
			return nil, fmt.Errorf("line %d: volume %v is not a finite number, 0 or more", n, v)
		}
		out = append(out, Pair{f[1], f[2], v})
	}
	return out, s.Err()
}

// Check returns the pairs sharing more than epsilon, and an error when
// that does not match expect.
func Check(pairs []Pair, epsilon float64, expect string) ([]Pair, error) {
	var over []Pair
	for _, p := range pairs {
		if p.Volume > epsilon {
			over = append(over, p)
		}
	}
	switch expect {
	case "none":
		if len(over) > 0 {
			var b strings.Builder
			fmt.Fprintf(&b, "%d pair(s) of parts overlap by more than %g mm^3:", len(over), epsilon)
			for _, p := range over {
				fmt.Fprintf(&b, "\n  %s and %s share %.6f mm^3", p.A, p.B, p.Volume)
			}
			return over, fmt.Errorf("%s", b.String())
		}
	case "overlap":
		if len(over) == 0 {
			return nil, fmt.Errorf("expected parts that overlap by more than %g mm^3; none do (%d pairs)", epsilon, len(pairs))
		}
	default:
		return nil, fmt.Errorf("OVERLAP_EXPECT=%q: want none or overlap", expect)
	}
	return over, nil
}

func run() error {
	path, err := runfiles.Rlocation(os.Getenv("OVERLAP_REPORT"))
	if err != nil {
		return err
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	pairs, err := Parse(f)
	if err != nil {
		return err
	}
	eps, err := strconv.ParseFloat(os.Getenv("OVERLAP_EPSILON"), 64)
	if err != nil || eps < 0 || math.IsNaN(eps) || math.IsInf(eps, 0) {
		return fmt.Errorf("OVERLAP_EPSILON=%q: want a number, 0 or more", os.Getenv("OVERLAP_EPSILON"))
	}
	expect := os.Getenv("OVERLAP_EXPECT")
	if expect == "" {
		expect = "none"
	}
	over, err := Check(pairs, eps, expect)
	if err != nil {
		return err
	}
	fmt.Printf("%d pairs checked; %d overlap by more than %g mm^3 (expected: %s)\n", len(pairs), len(over), eps, expect)
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "interference_test:", err)
		os.Exit(1)
	}
}
