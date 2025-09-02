from __future__ import annotations

import argparse
from typing import List, Tuple
import random

from ..router import ManhattanRouter
from ..program import Program, Cell
from ..lut_only import grid_from_program, LUTOnlyEmulator
from ..lut_logic import compile_expr_to_lut
from .stream_text_w2e import (
    chunk_bits_for_lanes,
    measure_delays_per_lane,
    build_parity_aligned_schedule,
    run_parallel_on_rows,
)


def make_empty_program(w: int, h: int) -> Program:
    return Program(width=w, height=h, cells=[], input_bits={}, output_bits={}, latency=0)


def emulate_impulse_w2e(grid_w: int, grid_h: int, grid) -> int:
    emu = LUTOnlyEmulator(grid)
    emu.reset()
    # Single-lane impulse on row 0
    west = [0] * grid_h
    west[0] = 1
    out = emu.step(edge_in={'W': west})
    if out['E'][0]:
        return 0
    for t in range(1, 256):
        out = emu.step(edge_in={'W': [0] * grid_h})
        if out['E'][0]:
            return t
    return -1


def run_single(w: int, h: int, row: int, blocked: List[Tuple[int,int]] | None = None, export: str | None = None) -> None:
    prog = make_empty_program(w, h)
    r = ManhattanRouter(w, h)
    # Occupy pre-allocated cells
    if blocked:
        for (bx, by) in blocked:
            r.occupy(bx, by)
    cells, hops = r.wire_edge_to_edge('W', row, 'E', row)
    prog.cells.extend(cells)
    g = grid_from_program(prog, strict=True)
    if export:
        g.save(export)
    # Measure arrival in steps
    emu = LUTOnlyEmulator(g)
    emu.reset()
    # Step 0: impulse
    wvec = [0]*h
    wvec[row] = 1
    out = emu.step(edge_in={'W': wvec})
    if out['E'][row]:
        delay = 0
    else:
        delay = -1
        for t in range(1, 256):
            out = emu.step(edge_in={'W': [0]*h})
            if out['E'][row]:
                delay = t
                break
    print(f"wired W[{row}]→E[{row}] with {hops} hops; arrival delay = {delay} steps (~{delay/2 if delay>=0 else -1:.1f} cycles)")


def run_cross(w: int, h: int, r1: int, r2: int, blocked: List[Tuple[int,int]] | None = None, export: str | None = None) -> None:
    prog = make_empty_program(w, h)
    r = ManhattanRouter(w, h)
    if blocked:
        for (bx, by) in blocked:
            r.occupy(bx, by)
    # First path
    c1, h1 = r.wire_edge_to_edge('W', r1, 'E', r2)
    prog.cells.extend(c1)
    # Second path (orthogonal), choose columns via N→S
    mid_col = max(1, w//2)
    # Route N[mid_col] to S[mid_col]
    c2, h2 = r.wire_edge_to_edge('N', mid_col if mid_col < w else w-1, 'S', mid_col if mid_col < w else w-1)
    prog.cells.extend(c2)
    g = grid_from_program(prog, strict=True)
    if export:
        g.save(export)
    emu = LUTOnlyEmulator(g)
    # Measure delays independently to avoid interference
    # West path delay to E[r2]
    emu.reset()
    wvec = [0]*h
    if 0 <= r1 < h:
        wvec[r1] = 1
    out = emu.step(edge_in={'W': wvec})
    delay_we = 0 if out['E'][r2] else -1
    if delay_we < 0:
        for t in range(1, 256):
            out = emu.step(edge_in={'W': [0]*h})
            if out['E'][r2]:
                delay_we = t
                break
    # North path delay to S[mid]
    emu.reset()
    nvec = [0]*w
    if 0 <= mid_col < w:
        nvec[mid_col] = 1
    out = emu.step(edge_in={'N': nvec})
    delay_ns = 0 if out['S'][mid_col] else -1
    if delay_ns < 0:
        for t in range(1, 256):
            out = emu.step(edge_in={'N': [0]*w})
            if out['S'][mid_col]:
                delay_ns = t
                break
    print(f"cross: W[{r1}]→E[{r2}] hops={h1}, delay={delay_we} steps; N[{mid_col}]→S[{mid_col}] hops={h2}, delay={delay_ns} steps")


def run_parallel8(w: int, h: int, lanes: int, blocked: List[Tuple[int,int]] | None = None, export: str | None = None) -> None:
    lanes = min(lanes, h)
    prog = make_empty_program(w, h)
    r = ManhattanRouter(w, h)
    if blocked:
        for (bx, by) in blocked:
            r.occupy(bx, by)
    hop_counts: List[int] = []
    for row in range(lanes):
        try:
            cells, hops = r.wire_edge_to_edge('W', row, 'E', row)
            hop_counts.append(hops)
            prog.cells.extend(cells)
        except RuntimeError as e:
            hop_counts.append(-1)
            print(f"lane {row}: routing failed: {e}")
    g = grid_from_program(prog, strict=True)
    if export:
        g.save(export)
    emu = LUTOnlyEmulator(g)
    # Prepare test text
    text = "HELLO-ROUTER"
    bits: List[int] = []
    for ch in text.encode('utf-8'):
        bits.extend(((ch >> b) & 1) for b in range(7, -1, -1))
    frames = chunk_bits_for_lanes(bits, lanes)
    # Measure per-lane delays and build aligned schedule
    per_lane_all = measure_delays_per_lane(emu, h)
    per_lane = per_lane_all[:lanes]
    schedule, arrivals = build_parity_aligned_schedule(frames, per_lane)
    print(f"per-lane delays (steps): {per_lane}; schedule steps={len(schedule)}, arrivals={arrivals[:min(8,len(arrivals))]}...")
    emu.reset()
    east_frames = run_parallel_on_rows(emu, h, list(range(lanes)), schedule)
    aligned: List[List[int]] = []
    for idx in arrivals:
        if 0 <= idx < len(east_frames):
            aligned.append(east_frames[idx])
    out_bits = [b for fr in aligned for b in fr][:len(bits)]
    out = bytearray()
    for i in range(0, len(out_bits), 8):
        val = 0
        for b in range(8):
            if i+b < len(out_bits):
                val = (val << 1) | (out_bits[i+b] & 1)
        out.append(val)
    print(f"parallel{lanes}: hops per lane: {hop_counts}")
    try:
        print(f"decoded: {out.decode('utf-8', errors='ignore')}")
    except Exception:
        print(f"decoded(bytes): {list(out)}")


def run_invert_mid(w: int, h: int, row: int, blocked: List[Tuple[int,int]] | None = None, export: str | None = None) -> None:
    prog = make_empty_program(w, h)
    r = ManhattanRouter(w, h)
    if blocked:
        for (bx, by) in blocked:
            r.occupy(bx, by)
    # Route from W row to neighbor of middle cell
    mid = (w//2, row)
    # Wire from W edge to a cell adjacent to mid
    cells_in, last_dir, last_xy, _ = r.wire_from_edge_to('W', row, mid)
    prog.cells.extend(cells_in)
    # Place a LUT compute cell at mid: E = !W (others 0)
    lutE = compile_expr_to_lut('!W')
    compute = Cell(x=mid[0], y=mid[1], inputs=[{"type":"const","value":0} for _ in range(4)], op='LUT', params={'luts':[0, lutE, 0, 0]})
    # Connect compute W input to the last route cell output facing mid
    # last_dir is the direction from last_xy towards dst(mid); input pin on compute is opposite of that.
    pin_map = {'N':0,'E':1,'S':2,'W':3}
    opposite = {'N':'S','S':'N','E':'W','W':'E'}[last_dir]
    compute.inputs[pin_map[opposite]] = {"type":"cell","x": last_xy[0], "y": last_xy[1], "out": pin_map[last_dir]}
    prog.cells.append(compute)
    # Route from compute to E edge at same row
    cells_out = r.wire_to_edge_from(mid, 'E', row, src_out=1)  # src_out=1 is E output of compute
    prog.cells.extend(cells_out)
    # Build grid and emulate
    g = grid_from_program(prog, strict=True)
    if export:
        g.save(export)
    emu = LUTOnlyEmulator(g)
    emu.reset()
    west = [0]*h
    # Drive a bit 1 and sample after two steps; expect inverted at East
    west[row] = 1
    emu.step(edge_in={'W': west})
    out = emu.step(edge_in={'W': west})
    print(f"invert-mid row {row}: E[{row}] after driving 1 = {out['E'][row]} (expect 0). Now drive 0…")
    # Now 0
    emu.step(edge_in={'W': [0]*h})
    out2 = emu.step(edge_in={'W': [0]*h})
    print(f"invert-mid row {row}: E[{row}] after driving 0 = {out2['E'][row]} (expect 1)")


def main():
    ap = argparse.ArgumentParser(description='LUT-only router demos (ManhattanRouter + ROUTE4 hops)')
    ap.add_argument('--width', type=int, default=8)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--mode', type=str, default='single', choices=['single','cross','parallel8','invert'])
    ap.add_argument('--row', type=int, default=0)
    ap.add_argument('--row2', type=int, default=3)
    ap.add_argument('--lanes', type=int, default=8)
    ap.add_argument('--block-random', type=int, default=0, help='Occupy this many random interior cells before routing')
    ap.add_argument('--seed', type=int, default=0, help='Random seed for --block-random')
    ap.add_argument('--block', action='append', default=[], help='Block a specific cell as x,y (repeatable)')
    ap.add_argument('--export', type=str, help='Optional path to save routed LUTGrid JSON')
    args = ap.parse_args()

    blocked: List[Tuple[int,int]] = []
    # Explicit blocks first
    for item in args.block:
        try:
            sx, sy = str(item).split(',')
            bx, by = int(sx), int(sy)
            if 0 <= bx < args.width and 0 <= by < args.height:
                blocked.append((bx, by))
        except Exception:
            pass
    if args.block_random > 0:
        rng = random.Random(args.seed)
        # Interior region: avoid outer ring so edges stay free (x:1..W-2,y:1..H-2)
        candidates = [(x, y) for x in range(2, args.width-2) for y in range(2, args.height-2)
                      if (x, y) not in set(blocked)]
        rng.shuffle(candidates)
        blocked.extend(candidates[:args.block_random])
        if blocked:
            print(f"blocked cells: {blocked}")

    if args.mode == 'single':
        run_single(args.width, args.height, args.row, blocked=blocked, export=args.export)
    elif args.mode == 'cross':
        run_cross(args.width, args.height, args.row, args.row2, blocked=blocked, export=args.export)
    elif args.mode == 'parallel8':
        run_parallel8(args.width, args.height, args.lanes, blocked=blocked, export=args.export)
    elif args.mode == 'invert':
        run_invert_mid(args.width, args.height, args.row, blocked=blocked, export=args.export)


if __name__ == '__main__':
    main()
