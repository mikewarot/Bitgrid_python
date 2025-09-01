from __future__ import annotations

import argparse
from typing import List, Tuple

from ..lut_only import LUTGrid, LUTOnlyEmulator
from ..router import route_luts


def build_pass_grid(width: int, height: int) -> LUTGrid:
    g = LUTGrid(width, height)
    for y in range(height):
        for x in range(width):
            g.add_cell(x, y, route_luts('E', 'W'))
    return g


def text_to_bits(s: str, msb_first: bool = True) -> List[int]:
    bits: List[int] = []
    for ch in s.encode('utf-8'):
        if msb_first:
            bits.extend([(ch >> b) & 1 for b in range(7, -1, -1)])
        else:
            bits.extend([(ch >> b) & 1 for b in range(8)])
    return bits


def bits_to_text(bits: List[int], msb_first: bool = True) -> str:
    out = bytearray()
    n = len(bits)
    if n % 8:
        bits = bits + [0] * (8 - (n % 8))
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i+8]
        if msb_first:
            val = 0
            for b in range(8):
                val = (val << 1) | (byte_bits[b] & 1)
        else:
            val = 0
            for b in range(8):
                val |= (byte_bits[b] & 1) << b
        out.append(val)
    try:
        return out.decode('utf-8', errors='ignore')
    except Exception:
        return out.decode('latin-1', errors='ignore')


def chunk_bits_for_lanes(bits: List[int], lanes: int) -> List[List[int]]:
    frames: List[List[int]] = []
    for i in range(0, len(bits), lanes):
        fr = bits[i:i+lanes]
        if len(fr) < lanes:
            fr = fr + [0] * (lanes - len(fr))
        frames.append(fr)
    return frames


def run_parallel_on_rows_cycle(emu: LUTOnlyEmulator, height: int, rows: List[int], frames: List[List[int]]) -> List[List[int]]:
    """Cycle-synchronous: for each frame, drive two steps with same values; sample after the second step."""
    east_frames: List[List[int]] = []
    for fr in frames:
        west = [0] * height
        for i, row in enumerate(rows):
            if i < len(fr) and 0 <= row < height:
                west[row] = fr[i]
        emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': west})
        east_frames.append([out['E'][row] for row in rows])
    return east_frames


def measure_delays_per_lane(emu: LUTOnlyEmulator, height: int, rows: List[int]) -> List[int]:
    delays: List[int] = []
    for row in rows:
        emu.reset()
        west = [0] * height
        west[row] = 1
        # drive two steps to ensure capture regardless of phase
        emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': west})
        if out['E'][row]:
            delays.append(1)
            continue
        found = -1
        for steps in range(2, 256):
            out = emu.step(edge_in={'W': [0]*height})
            if out['E'][row]:
                found = steps
                break
        delays.append(found)
    return delays


def build_parity_aligned_schedule(orig_frames: List[List[int]], per_lane_delays: List[int]) -> Tuple[List[List[int]], List[int]]:
    """Schedule frames so that for each frame k all lanes arrive at the same East step.
    Choose arrivals A_k = 2*k + max_delay; inject lane r at t = A_k - delay[r].
    Returns (schedule, arrival_indices). Adds a trailing flush step.
    """
    if not orig_frames:
        return [], []
    lanes = len(orig_frames[0])
    nonneg = [d for d in per_lane_delays if d is not None and d >= 0]
    max_delay = max(nonneg) if nonneg else 0
    n = len(orig_frames)
    steps = 2*n + max_delay
    schedule: List[List[int]] = [[0]*lanes for _ in range(steps)]
    arrivals: List[int] = []
    for k in range(n):
        A_k = 2*k + max_delay
        arrivals.append(A_k)
        for r in range(lanes):
            d = per_lane_delays[r] if r < len(per_lane_delays) and per_lane_delays[r] is not None else max_delay
            t = A_k - int(d)
            if 0 <= t < steps:
                schedule[t][r] = orig_frames[k][r]
    schedule.append([0]*lanes)
    return schedule, arrivals


def run_parallel_on_rows(emu: LUTOnlyEmulator, height: int, rows: List[int], frames: List[List[int]]) -> List[List[int]]:
    east_frames: List[List[int]] = []
    for fr in frames:
        west = [0] * height
        for i, row in enumerate(rows):
            if i < len(fr) and 0 <= row < height:
                west[row] = fr[i]
        out = emu.step(edge_in={'W': west})
        east_frames.append([out['E'][row] for row in rows])
    return east_frames


def main():
    ap = argparse.ArgumentParser(description='LUT-only: stream 8 parallel bits W->E and decode output')
    ap.add_argument('--text', type=str, default='Hello, World!', help='Text to stream')
    ap.add_argument('--width', type=int, default=2, help='Grid width; 2 recommended for simple pass-through')
    ap.add_argument('--height', type=int, default=8, help='Grid height (rows); must be >= lanes')
    ap.add_argument('--lanes', type=int, default=8, help='Parallel lanes (rows 0..lanes-1)')
    ap.add_argument('--save', type=str, help='Optional path to save LUTGrid JSON')
    ap.add_argument('--msb-first', action='store_true', help='Use MSB-first bit order (default)')
    ap.add_argument('--lsb-first', action='store_true', help='Use LSB-first bit order')
    args = ap.parse_args()

    if args.lanes <= 0:
        args.lanes = 8
    if args.height < args.lanes:
        raise SystemExit(f"height ({args.height}) must be >= lanes ({args.lanes})")

    g = build_pass_grid(args.width, args.height)
    if args.save:
        g.save(args.save)

    emu = LUTOnlyEmulator(g)
    msb_first = not args.lsb_first
    bits = text_to_bits(args.text, msb_first=msb_first)
    frames = chunk_bits_for_lanes(bits, args.lanes)
    rows = list(range(args.lanes))
    # measure per-lane delays and align
    per_lane = measure_delays_per_lane(emu, g.H, rows)
    schedule, arrivals = build_parity_aligned_schedule(frames, per_lane)
    emu.reset()
    east_frames = run_parallel_on_rows(emu, g.H, rows, schedule)
    aligned: List[List[int]] = []
    for idx in arrivals:
        if 0 <= idx < len(east_frames):
            aligned.append(east_frames[idx])
    out_bits_full = [b for fr in aligned for b in fr]
    out_bits = out_bits_full[:len(bits)]
    decoded = bits_to_text(out_bits, msb_first=msb_first)
    print(f"Decoded East: {decoded}")


if __name__ == '__main__':
    main()
