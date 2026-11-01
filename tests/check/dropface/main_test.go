// SPDX-License-Identifier: Apache-2.0

package main

import "testing"

func TestDrop(t *testing.T) {
	in := "#1 = CLOSED_SHELL('',(#2,#3,\n#4));\n#9 = CLOSED_SHELL('',(#5,#6));\n"
	got, err := Drop(in)
	if want := "#1 = CLOSED_SHELL('',(#2,#3));\n#9 = CLOSED_SHELL('',(#5,#6));\n"; err != nil || got != want {
		t.Errorf("Drop: %q, %v; want %q", got, err, want)
	}
	for _, bad := range []string{"no shell", "#1 = CLOSED_SHELL('',(#2));"} {
		if _, err := Drop(bad); err == nil {
			t.Errorf("Drop(%q): no error", bad)
		}
	}
}

func TestStep(t *testing.T) {
	if p, err := Step([]string{"a/plate.step a/plate.stl"}); err != nil || p != "a/plate.step" {
		t.Errorf("Step: %q, %v", p, err)
	}
	if p, err := Step([]string{"a/plate.STP"}); err != nil || p != "a/plate.STP" {
		t.Errorf("Step(.STP): %q, %v", p, err)
	}
	for _, bad := range [][]string{{"a.stl"}, {"a.step", "b.step"}} {
		if _, err := Step(bad); err == nil {
			t.Errorf("Step(%q): no error", bad)
		}
	}
}
