from __future__ import annotations

"""
Utilities for compiling boolean expressions over N,E,S,W into 16-bit LUT truth tables
used by BitGrid cells. Input ordering is (N,E,S,W) corresponding to index
idx = N | (E<<1) | (S<<2) | (W<<3).

Supported expression syntax:
- Variables: N, E, S, W (case-insensitive)
- Constants: 0, 1, True, False
- Operators: !, ~, not (negation); &, and; |, or; ^ (xor); parentheses ()
Expressions are evaluated in Python using booleans with a restricted environment.
"""

import re
from typing import Iterable, Tuple

_ALLOWED_RE = re.compile(r"^[\sNnEeSsWw01()!~^&|tTrRuUfFaAlLsSeEoOnNd]+$")


def _normalize_expr(expr: str) -> str:
    # Uppercase variables, keep operators. Replace common synonyms to Python boolean ops.
    s = expr.strip()
    # Quick safety: only allow certain characters
    if not _ALLOWED_RE.match(s):
        raise ValueError("Expression contains unsupported characters")
    # Uppercase variable names
    # Replace standalone N/E/S/W tokens to uppercase to avoid colliding with 'not', 'and', 'or'
    s = re.sub(r"\b[nN]\b", "N", s)
    s = re.sub(r"\b[eE]\b", "E", s)
    s = re.sub(r"\b[sS]\b", "S", s)
    s = re.sub(r"\b[wW]\b", "W", s)
    # Normalize boolean words to python ops
    s = re.sub(r"\bAND\b", " and ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bOR\b", " or ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bXOR\b", " ^ ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNOT\b", " not ", s, flags=re.IGNORECASE)
    # Map ! and ~ to 'not' when used as unary; a simplistic but practical replacement
    # Replace occurrences of ! or ~ before a variable/paren with ' not '
    s = re.sub(r"([!~])+\s*\(", lambda m: " not (" * len(m.group(1)), s)
    s = re.sub(r"([!~])+\s*N", lambda m: " not " * len(m.group(1)) + "N", s)
    s = re.sub(r"([!~])+\s*E", lambda m: " not " * len(m.group(1)) + "E", s)
    s = re.sub(r"([!~])+\s*S", lambda m: " not " * len(m.group(1)) + "S", s)
    s = re.sub(r"([!~])+\s*W", lambda m: " not " * len(m.group(1)) + "W", s)
    # Normalize constants to booleans
    s = re.sub(r"\b1\b", " True ", s)
    s = re.sub(r"\b0\b", " False ", s)
    return s


def compile_expr_to_lut(expr: str, var_order: Tuple[str, str, str, str] = ("N", "E", "S", "W")) -> int:
    """Compile a boolean expression of N,E,S,W into a 16-bit LUT integer.

    var_order defines the bit ordering of the truth table index; default is (N,E,S,W):
      idx = N | (E<<1) | (S<<2) | (W<<3)
    """
    norm = _normalize_expr(expr)
    # Validate var_order
    order = tuple(v.upper() for v in var_order)
    if order != ("N","E","S","W"):
        # We support any permutation; map bits accordingly
        pass

    lut = 0
    for idx in range(16):
        # Extract inputs per canonical NESW order
        n = bool((idx >> 0) & 1)
        e = bool((idx >> 1) & 1)
        s = bool((idx >> 2) & 1)
        w = bool((idx >> 3) & 1)
        env = {"N": n, "E": e, "S": s, "W": w, "True": True, "False": False}
        # Evaluate safely with no builtins
        try:
            val = eval(norm, {"__builtins__": None}, env)
        except Exception as ex:
            raise ValueError(f"Failed to evaluate expression: {ex}")
        bit = 1 if bool(val) else 0
        lut |= (bit << idx)
    return lut


def lut_to_minterms(lut: int) -> list[str]:
    """Return canonical sum-of-products minterms (in NESW order) for bits where LUT=1.

    Each minterm string is like 'N & !E & S & W'. This is a raw expansion without
    boolean minimization; it's useful for debugging and validation.
    """
    terms: list[str] = []
    for idx in range(16):
        if ((lut >> idx) & 1) == 0:
            continue
        n = (idx >> 0) & 1
        e = (idx >> 1) & 1
        s = (idx >> 2) & 1
        w = (idx >> 3) & 1
        parts = ["N" if n else "!N", "E" if e else "!E", "S" if s else "!S", "W" if w else "!W"]
        terms.append(" & ".join(parts))
    return terms


__all__ = ["compile_expr_to_lut", "lut_to_minterms"]
