from __future__ import annotations

import argparse
from typing import Dict, List
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts


DIR_IDX = {'N': 0, 'E': 1, 'S': 2, 'W': 3}


def build_left_tile(width: int, height: int, lanes: int) -> Program:
    # Lanes mapped top-to-bottom on Y = 0..lanes-1; export on East edge from x=width-1
    cells: List[Cell] = []
    for y in range(lanes):
        x = width - 1
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        # Drive West pin from input 'a[y]'
        inputs[DIR_IDX['W']] = {"type": "input", "name": "a", "bit": y}
        luts = route_luts('E', 'W')
        cells.append(Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts}))
    input_bits = {"a": [{"type": "input", "name": "a", "bit": b} for b in range(lanes)]}
    output_bits: Dict[str, List[Dict]] = {}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=width + height)


def build_right_tile(width: int, height: int, lanes: int) -> Program:
    # Lanes mapped top-to-bottom on Y = 0..lanes-1; import on West edge as input 'west', expose output 'out' from E pin
    cells: List[Cell] = []
    out_bits: List[Dict] = []
    for y in range(lanes):
        x = 0
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        inputs[DIR_IDX['W']] = {"type": "input", "name": "west", "bit": y}
        luts = route_luts('E', 'W')
        c = Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts})
        cells.append(c)
        out_bits.append({"type": "cell", "x": x, "y": y, "out": DIR_IDX['E']})
    input_bits = {"west": [{"type": "input", "name": "west", "bit": b} for b in range(lanes)]}
    output_bits = {"out": out_bits}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=width + height)


def edge_east_frame(width: int, height: int, emu: Emulator) -> List[int]:
    # Return east edge lanes top-to-bottom (len = height)
    lanes: List[int] = []
    x = emu.p.width - 1
    for y in range(height):
        lanes.append(emu.cell_out.get((x, y), [0, 0, 0, 0])[DIR_IDX['E']] & 1)
    return lanes


def main():
    ap = argparse.ArgumentParser(description='Two-tile loopback demo: left exports east lanes from input a; right receives west lanes and exposes out')
    ap.add_argument('--width', type=int, default=8)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--lanes', type=int, default=8, help='number of vertical lanes (<= height)')
    ap.add_argument('--steps', type=str, default='1,3,5,170', help='comma-separated input values for a (0..255)')
    args = ap.parse_args()

    W, H, L = args.width, args.height, args.lanes
    if W % 2 or H % 2:
        raise SystemExit('Width and height must be even')
    if L > H:
        raise SystemExit('lanes must be <= height')

    left = Emulator(build_left_tile(W, H, L))
    right = Emulator(build_right_tile(W, H, L))

    # Parse inputs for left
    seq = [int(tok.strip(), 0) & ((1 << L) - 1) for tok in args.steps.split(',') if tok.strip()]
    # Initial imported lanes for right (zeros)
    right_west_prev = [0] * L

    print(f"lanes={L} (top=bit0) W={W} H={H}")
    for epoch, aval in enumerate(seq):
        # Build per-lane bits for left 'a'
        a_bits = aval
        # Phase A: feed left a, right uses last imported lanes
        la = left.run_stream([{"a": a_bits}], cycles_per_step=1, reset=(epoch == 0))[-1]
        ra = right.run_stream([{"west": sum([(right_west_prev[i] & 1) << i for i in range(L)])}], cycles_per_step=1, reset=(epoch == 0))[-1]
        # Export east lanes from left after A; these will be used by right on B
        east_after_a = edge_east_frame(W, H, left)

        # Phase B: left keeps inputs stable within the epoch; right consumes newly arrived east lanes
        lb = left.run_stream([{"a": a_bits}], cycles_per_step=1, reset=False)[-1]
        right_west_now = east_after_a  # deliver seam data for B
        rb = right.run_stream([{"west": sum([(right_west_now[i] & 1) << i for i in range(L)])}], cycles_per_step=1, reset=False)[-1]

        # Sample right's out after B
        out_val = rb.get('out', 0) & ((1 << L) - 1)
        print(f"epoch={epoch} a=0x{aval:0{(L+3)//4}X} -> out=0x{out_val:0{(L+3)//4}X}")

        # Prepare import for next epoch A: use east lanes after B
        right_west_prev = edge_east_frame(W, H, left)


if __name__ == '__main__':
    main()
