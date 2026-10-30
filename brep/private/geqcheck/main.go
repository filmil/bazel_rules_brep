// SPDX-License-Identifier: Apache-2.0

// Command geqcheck is the test program of geometry_equal_test.
//
// It compares two measurements written by the CAD measurer, given as
// runfiles paths (rlocation paths) in GEQ_A and GEQ_B. Each line is
// "key value...". A count is an integer and must be equal; a number has a
// decimal point and may differ by GEQ_ABS plus GEQ_REL times the larger of
// the two in size. The measurer rounds numbers to 6 decimals, so the
// comparison allows for that rounding's last bit as well. With
// GEQ_EXPECT=equal (the default) it fails on any difference beyond that;
// with GEQ_EXPECT=different it fails when there is none, which is how
// geometry_equal_test checks itself on two different parts.
package main

import (
	"bufio"
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"

	"github.com/bazelbuild/rules_go/go/runfiles"
)

// Line is one measurement: its key, and its values as written.
type Line struct {
	Key    string
	Values []string
}

// Parse reads the measurer's lines.
func Parse(text string) ([]Line, error) {
	var out []Line
	sc := bufio.NewScanner(strings.NewReader(text))
	for n := 1; sc.Scan(); n++ {
		f := strings.Fields(sc.Text())
		if len(f) < 2 {
			return nil, fmt.Errorf("line %d: %q: want a key and one or more values", n, sc.Text())
		}
		out = append(out, Line{Key: f[0], Values: f[1:]})
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if len(out) == 0 {
		return nil, fmt.Errorf("no measurements")
	}
	return out, nil
}

// value is one value as written: a count (an integer) or a number (with a
// decimal point, finite).
type value struct {
	count  bool
	n      int64
	number float64
}

func parseValue(s string) (value, error) {
	if !strings.Contains(s, ".") {
		n, err := strconv.ParseInt(s, 10, 64)
		if err != nil {
			return value{}, fmt.Errorf("%q is neither a count nor a number with a decimal point", s)
		}
		return value{count: true, n: n}, nil
	}
	f, err := strconv.ParseFloat(s, 64)
	if err != nil || math.IsNaN(f) || math.IsInf(f, 0) {
		return value{}, fmt.Errorf("%q is not a finite number", s)
	}
	return value{number: f}, nil
}

// Tolerance says how far two numbers may be apart.
type Tolerance struct {
	Abs, Rel float64
}

// Allowed returns how far a and b may be apart: the tolerance, plus a
// little for numbers that were written with 6 decimals and read back, so
// that 5.000001 - 5.000000 (1.0000000001e-06 in binary) is within 1e-6.
func (t Tolerance) Allowed(a, b float64) float64 {
	m := math.Max(math.Abs(a), math.Abs(b))
	return (t.Abs+t.Rel*m)*(1+1e-9) + 1e-12*math.Max(1, m)
}

// Within reports whether a and b are within t of each other.
func (t Tolerance) Within(a, b float64) bool {
	return math.Abs(a-b) <= t.Allowed(a, b)
}

// Compare returns one line per measurement of a and b that differs beyond
// t, and an error when the two cannot be compared at all.
func Compare(a, b []Line, t Tolerance) ([]string, error) {
	if len(a) != len(b) {
		return nil, fmt.Errorf("the measurements have %d and %d lines", len(a), len(b))
	}
	var diffs []string
	for i := range a {
		la, lb := a[i], b[i]
		if la.Key != lb.Key {
			return nil, fmt.Errorf("line %d is %q in a and %q in b", i+1, la.Key, lb.Key)
		}
		if len(la.Values) != len(lb.Values) {
			return nil, fmt.Errorf("%s has %d values in a and %d in b", la.Key, len(la.Values), len(lb.Values))
		}
		for j := range la.Values {
			va, vb := la.Values[j], lb.Values[j]
			name := la.Key
			if len(la.Values) > 1 {
				name = fmt.Sprintf("%s[%d]", la.Key, j)
			}
			pa, err := parseValue(va)
			if err != nil {
				return nil, fmt.Errorf("%s in a: %v", name, err)
			}
			pb, err := parseValue(vb)
			if err != nil {
				return nil, fmt.Errorf("%s in b: %v", name, err)
			}
			if pa.count != pb.count {
				return nil, fmt.Errorf("%s is %q in a and %q in b: a count and a number", name, va, vb)
			}
			if pa.count {
				if pa.n != pb.n {
					diffs = append(diffs, fmt.Sprintf("%s: %s != %s (a count; it must be equal)", name, va, vb))
				}
				continue
			}
			if !t.Within(pa.number, pb.number) {
				diffs = append(diffs, fmt.Sprintf("%s: %s != %s (difference %g, allowed %g)",
					name, va, vb, math.Abs(pa.number-pb.number), t.Allowed(pa.number, pb.number)))
			}
		}
	}
	return diffs, nil
}

func read(env string) ([]Line, error) {
	rpath := os.Getenv(env)
	if rpath == "" {
		return nil, fmt.Errorf("%s is not set", env)
	}
	p, err := runfiles.Rlocation(rpath)
	if err != nil {
		return nil, fmt.Errorf("%s=%q: %v", env, rpath, err)
	}
	b, err := os.ReadFile(p)
	if err != nil {
		return nil, err
	}
	l, err := Parse(string(b))
	if err != nil {
		return nil, fmt.Errorf("%s: %v", p, err)
	}
	return l, nil
}

func number(env string) (float64, error) {
	v, err := strconv.ParseFloat(os.Getenv(env), 64)
	if err != nil || v < 0 || math.IsInf(v, 0) || math.IsNaN(v) {
		return 0, fmt.Errorf("%s=%q: want a number, 0 or more", env, os.Getenv(env))
	}
	return v, nil
}

func run() error {
	a, err := read("GEQ_A")
	if err != nil {
		return err
	}
	b, err := read("GEQ_B")
	if err != nil {
		return err
	}
	var t Tolerance
	if t.Abs, err = number("GEQ_ABS"); err != nil {
		return err
	}
	if t.Rel, err = number("GEQ_REL"); err != nil {
		return err
	}
	diffs, err := Compare(a, b, t)
	if err != nil {
		return err
	}
	expect := os.Getenv("GEQ_EXPECT")
	if expect == "" {
		expect = "equal"
	}
	switch expect {
	case "equal":
		if len(diffs) > 0 {
			return fmt.Errorf("the shapes differ (abs %g, rel %g):\n  %s", t.Abs, t.Rel, strings.Join(diffs, "\n  "))
		}
		fmt.Printf("the shapes are equal within abs %g, rel %g (%d measurements)\n", t.Abs, t.Rel, len(a))
	case "different":
		if len(diffs) == 0 {
			return fmt.Errorf("the shapes are equal within abs %g, rel %g, but should differ", t.Abs, t.Rel)
		}
		fmt.Printf("the shapes differ, as expected:\n  %s\n", strings.Join(diffs, "\n  "))
	default:
		return fmt.Errorf("GEQ_EXPECT=%q: want equal or different", expect)
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "geometry_equal_test:", err)
		os.Exit(1)
	}
}
