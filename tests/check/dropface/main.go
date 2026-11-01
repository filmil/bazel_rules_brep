// SPDX-License-Identifier: Apache-2.0

// Command dropface makes a known-bad STEP file for cad_check_test's tests:
// a copy of a part's STEP file whose first CLOSED_SHELL lists one face
// fewer, so the solid is bounded by an open shell.
//
//	dropface OUT.step IN...
//
// Of the IN files (a cad_part's outputs), it reads the one .step or .stp
// file. The STEP text is the one build123d writes: CLOSED_SHELL(”,(#a,#b,...)).
package main

import (
	"fmt"
	"os"
	"regexp"
	"strings"
)

var shell = regexp.MustCompile(`CLOSED_SHELL\('[^']*',\(([^)]*)\)`)

// Drop removes the last face from the first CLOSED_SHELL of a STEP file's
// text.
func Drop(step string) (string, error) {
	m := shell.FindStringSubmatchIndex(step)
	if m == nil {
		return "", fmt.Errorf("no CLOSED_SHELL")
	}
	list := step[m[2]:m[3]]
	refs := strings.Split(list, ",")
	if len(refs) < 2 {
		return "", fmt.Errorf("the CLOSED_SHELL has %d face(s); want 2 or more", len(refs))
	}
	return step[:m[2]] + strings.Join(refs[:len(refs)-1], ",") + step[m[3]:], nil
}

// Step returns the one .step file among paths.
func Step(paths []string) (string, error) {
	var steps []string
	for _, p := range paths {
		// $(execpaths) gives one argument of paths split by spaces;
		// Bazel's own paths have no spaces.
		for _, f := range strings.Fields(p) {
			if l := strings.ToLower(f); strings.HasSuffix(l, ".step") || strings.HasSuffix(l, ".stp") {
				steps = append(steps, f)
			}
		}
	}
	if len(steps) != 1 {
		return "", fmt.Errorf("want one .step file among the inputs, got %q", steps)
	}
	return steps[0], nil
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "usage: dropface OUT.step IN...")
		os.Exit(2)
	}
	path, err := Step(os.Args[2:])
	if err == nil {
		var in []byte
		if in, err = os.ReadFile(path); err == nil {
			var out string
			if out, err = Drop(string(in)); err == nil {
				err = os.WriteFile(os.Args[1], []byte(out), 0o644)
			}
		}
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "dropface:", err)
		os.Exit(1)
	}
}
