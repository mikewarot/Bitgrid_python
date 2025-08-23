from __future__ import annotations

import argparse
import time


def bench_raw(width: int, height: int, cycles: int) -> float:
    # Two-phase (A: even parity, B: odd parity) raw loop; minimal per-cell work
    acc = 0
    start = time.perf_counter()
    for cyc in range(cycles):
        phase_even = (cyc & 1) == 0
        # Process only cells where (x+y)%2 == (0 if phase_even else 1)
        target_parity = 0 if phase_even else 1
        for y in range(height):
            ypar = y & 1
            # compute x start so (x+y)%2 == target_parity
            x_start = target_parity ^ ypar
            # iterate every other x
            for x in range(x_start, width, 2):
                # minimal work to keep the loop from being optimized away
                acc ^= (x + y + cyc) & 1
    end = time.perf_counter()
    # use acc to prevent dead code elimination
    if acc == -1:  # impossible path, keeps acc live
        print("acc", acc)
    return end - start


def main():
    ap = argparse.ArgumentParser(description='Benchmark two-phase grid stepping without cell allocation')
    ap.add_argument('--width', type=int, default=1024)
    ap.add_argument('--height', type=int, default=1024)
    ap.add_argument('--cycles', type=int, default=100)
    args = ap.parse_args()

    W, H, C = args.width, args.height, args.cycles
    if W % 2 or H % 2:
        raise SystemExit('Grid width and height must be even.')
    total_cells = W * H
    total_visits = (total_cells // 2) * C  # half the cells per cycle

    elapsed = bench_raw(W, H, C)
    per_visit_us = (elapsed / total_visits) * 1e6 if total_visits else 0.0

    print(f"Grid: {W}x{H}, cycles: {C}")
    print(f"Time: {elapsed:.3f} s")
    print(f"Per cell-visit: {per_visit_us:.3f} µs")


if __name__ == '__main__':
    main()
