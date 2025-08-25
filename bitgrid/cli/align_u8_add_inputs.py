from __future__ import annotations

import argparse
from ..int.u8_add import build_u8_add_graph
from ..mapper import Mapper
from ..router import ManhattanRouter
from ..program import Program, Cell

# Simple post-map aligner for the 8-bit adder inputs using ROUTE4 delay ladders.
# Strategy:
# - Do not move existing cells; grow the canvas east/south if needed.
# - For each bit i at (x_add, y=i), compute lag(i) from parity of (x_add+y0).
# - Insert k two-hop detours (down/up) near the sink to delay a[i] and b[i] before they land on the adder cell.
# - Rewire the adder cell's input pins to the output of the last hop.


def compute_lags(x_add: int, y0: int, bits: int = 8) -> list[int]:
    # One-hop per cycle pipeline: bit i computes i cycles after bit 0.
    # Delay each bit i by i cycles to align a[i]/b[i] with the carry wave.
    return [i for i in range(bits)]


def align_u8_program(prog: Program) -> Program:
    # Find the adder column: look for cells that have two non-const inputs and LUTs set for sum/carry
    # In our mapper, adder is one column with y=0..7; inputs[0]=a[i], inputs[1]=b[i], inputs[2]=carry_in.
    add_cells = [c for c in prog.cells if c.op == 'LUT' and len(c.inputs) >= 3]
    # Heuristic: pick the column x with the most such rows
    by_x: dict[int, list[Cell]] = {}
    for c in add_cells:
        by_x.setdefault(c.x, []).append(c)
    if not by_x:
        return prog
    x_add = max(by_x.items(), key=lambda kv: len(kv[1]))[0]
    rows = sorted([c for c in by_x[x_add]], key=lambda c: c.y)
    if len(rows) < 8:
        return prog
    y0 = rows[0].y
    lags = compute_lags(x_add, y0, 8)

    # Ensure we have space: extend width for delay chains
    # We use single-hop horizontal chains. For bit i we place i cells for A on odd offsets and i cells for B on even offsets.
    # Worst-case extra columns needed east of adder column: 2*max_lag + 2 (to fit both A and B tracks).
    max_lag = max(lags) if lags else 0
    # input delay columns east of adder
    in_cols = 2 * max_lag + 2
    # leave a small gap then output delay columns (deskew) based on max_out_delay (for bit 0)
    max_out_delay = 7
    out_cols = 2 * max_out_delay + 2
    gap_cols = 2
    total_cols = in_cols + gap_cols + out_cols
    new_w = max(prog.width, x_add + 1 + total_cols)
    # Need one extra row below for bounce ladders
    min_h = y0 + 9  # rows 0..8 accessed
    new_h = max(prog.height, min_h)
    # Router requires even dimensions
    if new_w % 2 != 0:
        new_w += 1
    if new_h % 2 != 0:
        new_h += 1

    # Build a router context seeded with current occupancy
    router = ManhattanRouter(new_w, new_h)
    for c in prog.cells:
        router.occupy(c.x, c.y)

    new_cells: list[Cell] = []

    # For each bit row, insert detours for inputs[0] (a) and inputs[1] (b)
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    for i, c in enumerate(rows[:8]):
        k = lags[i]
        if k <= 0:
            # no change
            pass
        sx, sy = c.x, c.y
        prev_a = c.inputs[0]
        prev_b = c.inputs[1]
        # Build k single-hop horizontal delays (half-step each) for each net on separate track columns.
        # A uses odd offsets (sx+1, sx+3, ...), B uses even offsets (sx+2, sx+4, ...).
        for t in range(k):
            # A track
            nx_a, ny_a = sx + 1 + 2*t, sy
            cell_a, created_a = router._add_or_merge_route4(nx_a, ny_a, out_dir='E', in_pin='W', upstream=prev_a)
            if created_a:
                new_cells.append(cell_a)
            prev_a = {"type":"cell","x":nx_a,"y":ny_a,"out":dir_to_idx['E']}
            # B track
            nx_b, ny_b = sx + 2 + 2*t, sy
            cell_b, created_b = router._add_or_merge_route4(nx_b, ny_b, out_dir='E', in_pin='W', upstream=prev_b)
            if created_b:
                new_cells.append(cell_b)
            prev_b = {"type":"cell","x":nx_b,"y":ny_b,"out":dir_to_idx['E']}
        # Rewire adder inputs to the delayed sources
        c.inputs[0] = prev_a
        c.inputs[1] = prev_b

        # Output deskew: delay sum bit i by (max_out_delay - i) cycles on an output track starting after input tracks + gap
        out_delay = max_out_delay - i
        prev_out = {"type":"cell","x":sx,"y":sy,"out":0}
        for t in range(out_delay):
            nx_o, ny_o = sx + in_cols + gap_cols + 1 + 2*t, sy
            cell_o, created_o = router._add_or_merge_route4(nx_o, ny_o, out_dir='E', in_pin='W', upstream=prev_out)
            if created_o:
                new_cells.append(cell_o)
            prev_out = {"type":"cell","x":nx_o,"y":ny_o,"out":dir_to_idx['E']}
        # Update program outputs for this bit if present under 's'
        if 's' in prog.output_bits and len(prog.output_bits['s']) > i:
            prog.output_bits['s'][i] = prev_out

    # Return updated program
    # Bump latency to account for input and output deskew chains
    new_latency = prog.latency + max_lag + max_out_delay
    return Program(width=new_w, height=new_h, cells=prog.cells + new_cells,
                   input_bits=prog.input_bits, output_bits=prog.output_bits, latency=new_latency)


def main():
    ap = argparse.ArgumentParser(description='Align u8 adder inputs with ROUTE4 delay ladders (throughput-first)')
    ap.add_argument('--in', dest='inp', required=True, help='Input Program JSON')
    ap.add_argument('--out', dest='out', required=True, help='Output Program JSON (aligned)')
    args = ap.parse_args()

    prog = Program.load(args.inp)
    aligned = align_u8_program(prog)
    aligned.save(args.out)
    print(f"Aligned program written to {args.out} (W={aligned.width}, H={aligned.height})")


if __name__ == '__main__':
    main()
