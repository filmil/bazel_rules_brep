// SPDX-License-Identifier: Apache-2.0

// Command fitcheck is pcb_fit_test's checker (issue #14).
//
// It reads the runner's fit report (tab-separated lines: "overlap V",
// "clearance D", "hole X Y R", "mount X Y R KIND" with KIND "hole" or
// "pin") and checks that:
//
//   - the board and the enclosure share no more than FIT_EPSILON mm^3;
//   - the board's outline keeps FIT_MIN_CLEARANCE mm from the enclosure;
//   - the board has a mounting hole, and every one has a mount (a boss's
//     hole for a screw, or a pin) whose center is within
//     FIT_HOLE_TOLERANCE mm of the hole's and that is no wider than the
//     hole (by more than the same tolerance).
//
// Every check that fails is listed. FIT_EXPECT is "pass" (the default), or
// "fail" for a known-bad fit (spec T3). FIT_REPORT is the report's
// runfiles path.
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

// Circle is a hole or a mount: its center and radius, mm. Kind is a
// mount's: "hole" (for a screw) or "pin".
type Circle struct {
	X, Y, R float64
	Kind    string
}

// Report is a parsed fit report.
type Report struct {
	Overlap, Clearance float64
	Holes, Mounts      []Circle
}

func finite(s string, inf bool) (float64, error) {
	v, err := strconv.ParseFloat(s, 64)
	if err != nil || math.IsNaN(v) || (math.IsInf(v, 0) && !(inf && v > 0)) {
		return 0, fmt.Errorf("%q is not a finite number", s)
	}
	return v, nil
}

// Parse reads a report.
func Parse(r io.Reader) (Report, error) {
	var rep Report
	seen := map[string]bool{}
	s := bufio.NewScanner(r)
	for n := 1; s.Scan(); n++ {
		if strings.TrimSpace(s.Text()) == "" {
			continue
		}
		f := strings.Split(s.Text(), "\t")
		bad := func(err error) error { return fmt.Errorf("line %d (%q): %v", n, s.Text(), err) }
		switch {
		case seen[f[0]] && (f[0] == "overlap" || f[0] == "clearance"):
			return rep, bad(fmt.Errorf("%s appears twice", f[0]))
		case f[0] == "overlap" && len(f) == 2:
			v, err := finite(f[1], false)
			if err != nil || v < 0 {
				return rep, bad(fmt.Errorf("want a volume, 0 or more"))
			}
			rep.Overlap = v
		case f[0] == "clearance" && len(f) == 2:
			// +Inf: nothing of the enclosure is beside the board.
			v, err := finite(f[1], true)
			if err != nil || v < 0 {
				return rep, bad(fmt.Errorf("want a distance, 0 or more"))
			}
			rep.Clearance = v
		case (f[0] == "hole" && len(f) == 4) || (f[0] == "mount" && len(f) == 5):
			var c [3]float64
			for i := range c {
				v, err := finite(f[i+1], false)
				if err != nil {
					return rep, bad(err)
				}
				c[i] = v
			}
			if c[2] <= 0 {
				return rep, bad(fmt.Errorf("a radius must be above 0"))
			}
			if f[0] == "hole" {
				rep.Holes = append(rep.Holes, Circle{X: c[0], Y: c[1], R: c[2]})
			} else {
				if f[4] != "hole" && f[4] != "pin" {
					return rep, bad(fmt.Errorf("a mount is a hole or a pin, not %q", f[4]))
				}
				rep.Mounts = append(rep.Mounts, Circle{X: c[0], Y: c[1], R: c[2], Kind: f[4]})
			}
		default:
			return rep, bad(fmt.Errorf("not a fit report line"))
		}
		seen[f[0]] = true
	}
	if !seen["overlap"] || !seen["clearance"] {
		return rep, fmt.Errorf("the report lacks overlap or clearance")
	}
	return rep, s.Err()
}

// Check returns each check that fails, described.
func Check(rep Report, epsilon, minClearance, holeTolerance float64) []string {
	var bad []string
	if rep.Overlap > epsilon {
		bad = append(bad, fmt.Sprintf("the board and the enclosure share %.6f mm^3 (more than %g)", rep.Overlap, epsilon))
	}
	if rep.Clearance < minClearance {
		bad = append(bad, fmt.Sprintf("the board's outline is %.6f mm from the enclosure, under the minimum %g", rep.Clearance, minClearance))
	}
	if len(rep.Holes) == 0 {
		bad = append(bad, "the board has no mounting holes (whole holes along Z) to line up")
	}
	for _, h := range rep.Holes {
		best, wide := math.Inf(1), 0.0
		for _, m := range rep.Mounts {
			d := math.Hypot(h.X-m.X, h.Y-m.Y)
			if d > holeTolerance {
				best = math.Min(best, d)
				continue
			}
			if m.R > h.R+holeTolerance {
				// On the axis, but too wide to go through the hole: the
				// outside of a boss, say.
				wide = math.Max(wide, m.R)
				continue
			}
			best = -1
			break
		}
		if best < 0 {
			continue
		}
		where := "no mount at all"
		switch {
		case wide > 0:
			where = fmt.Sprintf("the mount on its axis is %.6f mm in radius, wider than the hole's %.6f", wide, h.R)
		case !math.IsInf(best, 1):
			where = fmt.Sprintf("the nearest mount is %.6f mm off", best)
		}
		bad = append(bad, fmt.Sprintf("the hole at (%.6f, %.6f) has no mount within %g mm: %s", h.X, h.Y, holeTolerance, where))
	}
	return bad
}

func setting(env string) (float64, error) {
	v, err := finite(os.Getenv(env), false)
	if err != nil || v < 0 {
		return 0, fmt.Errorf("%s=%q: want a finite number, 0 or more", env, os.Getenv(env))
	}
	return v, nil
}

func run() error {
	eps, err := setting("FIT_EPSILON")
	if err != nil {
		return err
	}
	minClear, err := setting("FIT_MIN_CLEARANCE")
	if err != nil {
		return err
	}
	tol, err := setting("FIT_HOLE_TOLERANCE")
	if err != nil {
		return err
	}
	path, err := runfiles.Rlocation(os.Getenv("FIT_REPORT"))
	if err != nil {
		return err
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	rep, err := Parse(f)
	if err != nil {
		return err
	}
	bad := Check(rep, eps, minClear, tol)
	switch expect := os.Getenv("FIT_EXPECT"); expect {
	case "", "pass":
		if len(bad) > 0 {
			return fmt.Errorf("the board does not fit:\n  %s", strings.Join(bad, "\n  "))
		}
		fmt.Printf("the board fits: %d holes on mounts, clearance %.6f mm, overlap %.6f mm^3\n", len(rep.Holes), rep.Clearance, rep.Overlap)
	case "fail":
		if len(bad) == 0 {
			return fmt.Errorf("expected the fit to fail; the board fits")
		}
		fmt.Printf("as expected, the board does not fit:\n  %s\n", strings.Join(bad, "\n  "))
	default:
		return fmt.Errorf("FIT_EXPECT=%q: want pass or fail", expect)
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, "pcb_fit_test:", err)
		os.Exit(1)
	}
}
