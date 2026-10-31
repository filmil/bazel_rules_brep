# SPDX-License-Identifier: Apache-2.0
"""Strict parsing of numbers that rules take as strings."""

_DIGITS = "0123456789"

def _digits(s):
    return s != "" and all([c in _DIGITS for c in s.elems()])

def parse_number(text):
    """text as a float, or None when it is not a plain decimal number.

    The form is an optional sign, digits with an optional fraction (or a
    fraction alone), and an optional exponent: "3", "-0.5", ".25", "1e-3".
    "nan", "inf", "1.2.3" and "1e" are not numbers, and neither is one
    whose digits before the point, with the exponent, reach above 308
    ("1e308", "1e999"): Starlark's float() would fail on some of these with
    an error that names no attribute.

    Args:
      text: the string to parse.

    Returns:
      The number as a float, or None.
    """
    s = text.strip()
    if s[:1] in ["+", "-"]:
        s = s[1:]
    mantissa, exponent = s, None
    for e in ["e", "E"]:
        if e in s:
            mantissa, exponent = s.split(e, 1)
            break
    scale = 0
    if exponent != None:
        sign = 1
        if exponent[:1] in ["+", "-"]:
            sign = -1 if exponent[0] == "-" else 1
            exponent = exponent[1:]
        if not _digits(exponent) or len(exponent) > 4:
            return None
        scale = sign * int(exponent)
    whole, dot, frac = mantissa.partition(".")
    if dot:
        if not (_digits(whole) or whole == "") or not (_digits(frac) or frac == "") or (whole == "" and frac == ""):
            return None
    elif not _digits(whole):
        return None

    # The number is below 10 to the power of its digits before the point
    # plus its exponent; at most 308 of them keep float() from overflowing.
    if len(whole.lstrip("0")) + scale > 308:
        return None
    return float(text.strip())
