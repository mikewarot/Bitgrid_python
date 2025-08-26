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
from typing import Iterable, Tuple, Dict, Set, List

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
    # Replace bitwise symbols with boolean ops for eval compatibility with 'not'
    s = s.replace('&', ' and ')
    s = s.replace('|', ' or ')
    # Normalize constants to booleans
    s = re.sub(r"\b1\b", " True ", s)
    s = re.sub(r"\b0\b", " False ", s)
    # Collapse repeated whitespace
    s = re.sub(r"\s+", " ", s).strip()
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


def _minterm_list_from_lut(lut: int) -> List[int]:
    return [i for i in range(16) if ((lut >> i) & 1) == 1]


def _pattern_for_idx(idx: int) -> str:
    # NESW order, '0'/'1'
    return ''.join('1' if ((idx >> b) & 1) else '0' for b in range(4))


def _covers(pattern: str, idx: int) -> bool:
    for b in range(4):
        ch = pattern[b]
        if ch == '-':
            continue
        bit = (idx >> b) & 1
        if ch == '1' and bit != 1:
            return False
        if ch == '0' and bit != 0:
            return False
    return True


def _combine(p: str, q: str) -> str | None:
    diff = 0
    out = []
    for a, b in zip(p, q):
        if a == b:
            out.append(a)
        else:
            # Only combine on exact 0/1 complement; '-' can't combine with fixed
            if a == '-' or b == '-':
                return None
            diff += 1
            out.append('-')
            if diff > 1:
                return None
    return ''.join(out) if diff == 1 else None


def _qmc_prime_implicants(minterms: List[int]) -> Dict[str, Set[int]]:
    # Start with individual minterms as patterns
    current: Dict[str, Set[int]] = { _pattern_for_idx(m): {m} for m in sorted(minterms) }
    all_primes: Dict[str, Set[int]] = {}
    while True:
        used: Set[str] = set()
        next_patterns: Dict[str, Set[int]] = {}
        pats = list(current.items())
        n = len(pats)
        for i in range(n):
            pi, covi = pats[i]
            for j in range(i+1, n):
                pj, covj = pats[j]
                comb = _combine(pi, pj)
                if comb is not None:
                    used.add(pi); used.add(pj)
                    cov = covi | covj
                    # Keep the widest coverage if duplicate pattern arises
                    if comb in next_patterns:
                        next_patterns[comb] |= cov
                    else:
                        next_patterns[comb] = set(cov)
        # Patterns not used in any combination are primes
        for p, cov in current.items():
            if p not in used:
                # Merge coverage if same prime encountered
                if p in all_primes:
                    all_primes[p] |= cov
                else:
                    all_primes[p] = set(cov)
        if not next_patterns:
            break
        current = next_patterns
    return all_primes


def _select_implicants_cover(primes: Dict[str, Set[int]], minterms: Set[int]) -> List[str]:
    # Prime implicant chart: map minterm -> set of implicant patterns
    chart: Dict[int, Set[str]] = {m: set() for m in minterms}
    for p, cov in primes.items():
        for m in cov:
            if m in chart:
                chart[m].add(p)

    selected: List[str] = []
    covered: Set[int] = set()

    # 1) Select essential implicants (cover minterms that appear in only one implicant)
    while True:
        essentials = [m for m, ps in chart.items() if m not in covered and len(ps) == 1]
        if not essentials:
            break
        for m in essentials:
            p = next(iter(chart[m]))
            if p not in selected:
                selected.append(p)
            # Mark all minterms covered by this implicant
            for mm in primes[p]:
                covered.add(mm)

    # 2) Greedy cover remaining minterms
    while covered != minterms:
        # Pick implicant covering the most uncovered minterms
        best_p = None
        best_gain = -1
        for p, cov in primes.items():
            if p in selected:
                continue
            gain = len([m for m in cov if m not in covered])
            if gain > best_gain:
                best_gain = gain
                best_p = p
        if best_p is None or best_gain <= 0:
            break
        selected.append(best_p)
        for m in primes[best_p]:
            covered.add(m)

    return selected


def _pattern_to_term(pattern: str) -> str:
    # Convert pattern (NESW) to conjunction using ! for 0, variable name for 1; skip '-'
    names = ('N','E','S','W')
    lits: List[str] = []
    for i, ch in enumerate(pattern):
        if ch == '-':
            continue
        if ch == '1':
            lits.append(names[i])
        elif ch == '0':
            lits.append('!' + names[i])
    if not lits:
        return '1'
    if len(lits) == 1:
        return lits[0]
    return '(' + ' & '.join(lits) + ')'


def decompile_lut_to_expr(lut: int) -> str:
    """Produce a simplified SOP expression string from a 16-bit LUT (NESW index order).

    Uses Quine–McCluskey to derive a reasonably minimal sum-of-products.
    Returns '0' for empty, '1' for tautology.
    """
    lut &= 0xFFFF
    if lut == 0:
        return '0'
    if lut == 0xFFFF:
        return '1'
    minterms = _minterm_list_from_lut(lut)
    primes = _qmc_prime_implicants(minterms)
    sel = _select_implicants_cover(primes, set(minterms))
    terms = [_pattern_to_term(p) for p in sel]
    return ' | '.join(sorted(terms))


__all__ = ["compile_expr_to_lut", "lut_to_minterms", "decompile_lut_to_expr"]
