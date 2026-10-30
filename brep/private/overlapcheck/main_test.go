// SPDX-License-Identifier: Apache-2.0

package main

import (
	"strings"
	"testing"
)

const report = `pair base pin 0.000000
pair base lid 2.500000
pair pin lid 0.000400
`

func TestParse(t *testing.T) {
	p, err := Parse(strings.NewReader(report))
	if err != nil || len(p) != 3 || p[1] != (Pair{"base", "lid", 2.5}) {
		t.Fatalf("Parse = %v, %v", p, err)
	}
	for _, bad := range []string{"pair a b\n", "pear a b 1\n", "pair a b x\n"} {
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
