from __future__ import annotations

import argparse
from typing import Tuple, Optional

from ..lut_only import LUTGrid, LUTOnlyEmulator


def earliest_stable_step(trace: list[list[int]], expected: int) -> Tuple[Optional[int], Optional[int]]:
    """Given an edge trace (list of vectors per step), find the earliest step and position
    where the output equals `expected` and remains equal for the rest of the steps.
    Returns (step_index, position). If none found, returns (None, None).
    """
    if not trace:
        return None, None
    steps = len(trace)
    width = len(trace[0]) if steps > 0 else 0
    for pos in range(width):
        for s in range(steps):
            ok = True
            for t in range(s, steps):
                if trace[t][pos] != expected:
                    ok = False
                    break
            if ok:
                return s, pos
    return None, None


def main():
    ap = argparse.ArgumentParser(description='Measure timing for 1-bit full adder LUTGrid by sweeping all inputs.')
    ap.add_argument('--in', dest='inp', required=True, help='Input LUTGrid JSON (physicalized fa1)')
    ap.add_argument('--steps', type=int, default=8, help='Number of subcycles to run per vector (hold inputs)')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    emu = LUTOnlyEmulator(g)

    print('a b cin | sum cout | E_delay@pos  S_delay@pos')
    print('-------+----------+---------------------------')
    for a in (0, 1):
        for b in (0, 1):
            for cin in (0, 1):
                # Build held edge inputs for H=W=2 grid: west/east are length H (y), north/south are length W (x)
                west = [a, 0]  # a at y=0
                east = [b, 0]  # b at y=0
                north = [cin, 0]  # cin at x=0

                # Run held for steps, record E and S traces
                emu.reset()
                E_trace: list[list[int]] = []
                S_trace: list[list[int]] = []
                edge = {'W': west, 'E': east, 'N': north}
                for _ in range(args.steps):
                    out = emu.step(edge_in=edge)
                    E_trace.append(list(out['E']))
                    S_trace.append(list(out['S']))

                sum_exp = (a ^ b) ^ cin
                cout_exp = (a & b) | (a & cin) | (b & cin)
                e_step, e_pos = earliest_stable_step(E_trace, sum_exp)
                s_step, s_pos = earliest_stable_step(S_trace, cout_exp)
                e_str = f"{e_step if e_step is not None else '-'}@{e_pos if e_pos is not None else '-'}"
                s_str = f"{s_step if s_step is not None else '-'}@{s_pos if s_pos is not None else '-'}"
                print(f"{a} {b}  {cin}  |  {sum_exp}    {cout_exp}  | {e_str:>10}   {s_str:>10}")


if __name__ == '__main__':
    main()
