from __future__ import annotations

import argparse
from typing import Dict, List, Tuple
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts


DIR = {'N': 0, 'E': 1, 'S': 2, 'W': 3}


def build_tile(width: int, height: int) -> Program:
    # Edge pass-through cells bound to external inputs; outputs are the cell's opposite direction
    cells: List[Cell] = []
    # West import -> East output at x=0 for each y (vertical lanes)
    for y in range(height):
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        inputs[DIR['W']] = {"type": "input", "name": "west", "bit": y}
        cells.append(Cell(x=0, y=y, inputs=inputs, op='ROUTE4', params={'luts': route_luts('E', 'W')}))
    # East import -> West output at x=width-1 for each y
    for y in range(height):
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        inputs[DIR['E']] = {"type": "input", "name": "east", "bit": y}
        cells.append(Cell(x=width - 1, y=y, inputs=inputs, op='ROUTE4', params={'luts': route_luts('W', 'E')}))
    # North import -> South output at y=0 for each x (horizontal lanes)
    for x in range(width):
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        inputs[DIR['N']] = {"type": "input", "name": "north", "bit": x}
        cells.append(Cell(x=x, y=0, inputs=inputs, op='ROUTE4', params={'luts': route_luts('S', 'N')}))
    # South import -> North output at y=height-1 for each x
    for x in range(width):
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        inputs[DIR['S']] = {"type": "input", "name": "south", "bit": x}
        cells.append(Cell(x=x, y=height - 1, inputs=inputs, op='ROUTE4', params={'luts': route_luts('N', 'S')}))

    input_bits = {
        'west': [{"type": "input", "name": "west", "bit": b} for b in range(height)],
        'east': [{"type": "input", "name": "east", "bit": b} for b in range(height)],
        'north': [{"type": "input", "name": "north", "bit": b} for b in range(width)],
        'south': [{"type": "input", "name": "south", "bit": b} for b in range(width)],
    }
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits={}, latency=width + height)


def pack_bits(bits: List[int]) -> int:
    v = 0
    for i, b in enumerate(bits):
        v |= ((b & 1) << i)
    return v


def edge_frame(emu: Emulator, side: str, len_dim: int) -> List[int]:
    if side == 'E':
        x = emu.p.width - 1
        return [emu.cell_out.get((x, y), [0, 0, 0, 0])[DIR['E']] & 1 for y in range(len_dim)]
    if side == 'W':
        x = 0
        return [emu.cell_out.get((x, y), [0, 0, 0, 0])[DIR['W']] & 1 for y in range(len_dim)]
    if side == 'N':
        y = 0
        return [emu.cell_out.get((x, y), [0, 0, 0, 0])[DIR['N']] & 1 for x in range(len_dim)]
    if side == 'S':
        y = emu.p.height - 1
        return [emu.cell_out.get((x, y), [0, 0, 0, 0])[DIR['S']] & 1 for x in range(len_dim)]
    raise ValueError('side')


def main():
    ap = argparse.ArgumentParser(description='2x2 tiled loopback demo with parity-split seam transfers (N/E/S/W)')
    ap.add_argument('--width', type=int, default=8)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--steps', type=str, default='1,3,5,0xAA', help='comma-separated values for TL west (vertical lanes) and TL north (horizontal lanes)')
    args = ap.parse_args()

    W, H = args.width, args.height
    if W % 2 or H % 2:
        raise SystemExit('Width and height must be even')

    # Build four tiles
    TL = Emulator(build_tile(W, H))
    TR = Emulator(build_tile(W, H))
    BL = Emulator(build_tile(W, H))
    BR = Emulator(build_tile(W, H))

    # Buffers per seam: store even and odd halves separately
    tl_tr_even = [0] * H  # vertical lanes (y)
    tl_tr_odd = [0] * H
    tl_bl_even = [0] * W  # horizontal lanes (x)
    tl_bl_odd = [0] * W
    tr_br_even = [0] * W
    tr_br_odd = [0] * W
    bl_br_even = [0] * H
    bl_br_odd = [0] * H

    # Helper: indices freshly computed this phase for a given edge
    # West edge x=0 (even): fresh A -> y even; East edge x=W-1 (odd): fresh A -> y odd
    def fresh_y(side: str, phase: str) -> List[int]:
        if side == 'E':
            return [i for i in range(H) if (i % 2 == (1 if phase == 'A' else 0))]
        if side == 'W':
            return [i for i in range(H) if (i % 2 == (0 if phase == 'A' else 1))]
        raise ValueError('bad side for y')

    # North edge y=0 (even): fresh A -> x even; South edge y=H-1 (odd): fresh A -> x odd
    def fresh_x(side: str, phase: str) -> List[int]:
        if side == 'N':
            return [i for i in range(W) if (i % 2 == (0 if phase == 'A' else 1))]
        if side == 'S':
            return [i for i in range(W) if (i % 2 == (1 if phase == 'A' else 0))]
        raise ValueError('bad side for x')

    seq = [int(tok.strip(), 0) for tok in args.steps.split(',') if tok.strip()]
    print(f"W={W} H={H} (top row/left col are index 0)")
    for e, val in enumerate(seq):
        a_west = val & ((1 << H) - 1)  # vertical lanes for TL west
        a_north = val & ((1 << W) - 1)  # horizontal lanes for TL north

        # Phase A: run all tiles with current inputs, consuming even halves at sinks
        TL.run_stream([{ 'west': a_west, 'north': a_north, 'east': 0, 'south': 0 }], cycles_per_step=1, reset=(e == 0))
        TR.run_stream([{ 'west': pack_bits(tl_tr_even), 'north': 0, 'east': 0, 'south': 0 }], cycles_per_step=1, reset=(e == 0))
        BL.run_stream([{ 'west': 0, 'north': pack_bits(tl_bl_even), 'east': 0, 'south': 0 }], cycles_per_step=1, reset=(e == 0))
        BR.run_stream([{ 'west': pack_bits(bl_br_even), 'north': pack_bits(tr_br_even), 'east': 0, 'south': 0 }], cycles_per_step=1, reset=(e == 0))

        # Export freshly computed halves from sources (phase A)
        for i in fresh_y('E', 'A'):
            tl_tr_odd[i] = edge_frame(TL, 'E', H)[i]
        for i in fresh_x('S', 'A'):
            tl_bl_odd[i] = edge_frame(TL, 'S', W)[i]
        for i in fresh_x('S', 'A'):
            tr_br_odd[i] = edge_frame(TR, 'S', W)[i]
        for i in fresh_y('E', 'A'):
            bl_br_odd[i] = edge_frame(BL, 'E', H)[i]

        # Partial aligned after A: even halves at TR (from TL), BL (from TL)
        tr_even = TR.run_stream([{ 'west': pack_bits(tl_tr_even), 'north': 0, 'east': 0, 'south': 0 }], cycles_per_step=0, reset=False)
        bl_even = BL.run_stream([{ 'west': 0, 'north': pack_bits(tl_bl_even), 'east': 0, 'south': 0 }], cycles_per_step=0, reset=False)

        # Phase B: consume odd halves at sinks
        TL.run_stream([{ 'west': a_west, 'north': a_north, 'east': 0, 'south': 0 }], cycles_per_step=1, reset=False)
        TR.run_stream([{ 'west': pack_bits(tl_tr_odd), 'north': 0, 'east': 0, 'south': 0 }], cycles_per_step=1, reset=False)
        BL.run_stream([{ 'west': 0, 'north': pack_bits(tl_bl_odd), 'east': 0, 'south': 0 }], cycles_per_step=1, reset=False)
        BR.run_stream([{ 'west': pack_bits(bl_br_odd), 'north': pack_bits(tr_br_odd), 'east': 0, 'south': 0 }], cycles_per_step=1, reset=False)

        # Export freshly computed halves from sources (phase B)
        for i in fresh_y('E', 'B'):
            tl_tr_even[i] = edge_frame(TL, 'E', H)[i]
        for i in fresh_x('S', 'B'):
            tl_bl_even[i] = edge_frame(TL, 'S', W)[i]
        for i in fresh_x('S', 'B'):
            tr_br_even[i] = edge_frame(TR, 'S', W)[i]
        for i in fresh_y('E', 'B'):
            bl_br_even[i] = edge_frame(BL, 'E', H)[i]

        # Aligned outputs for epoch e-1 at TR and BL (from TL)
        if e > 0:
            aligned_tr = pack_bits(tl_tr_even) | pack_bits([ (tl_tr_odd[i] if (i % 2 == 1) else 0) for i in range(H) ])
            aligned_bl = pack_bits(tl_bl_even) | pack_bits([ (tl_bl_odd[i] if (i % 2 == 1) else 0) for i in range(W) ])
            print(f"e={e} TL→TR aligned[e-1]=0x{aligned_tr:0{(H+3)//4}X} TL→BL aligned[e-1]=0x{aligned_bl:0{(W+3)//4}X}")

        # Also report per-phase partials at BR from TR and BL seams
        even_mask_w = sum([1 << i for i in range(W) if i % 2 == 0])
        odd_mask_w = sum([1 << i for i in range(W) if i % 2 == 1])
        even_mask_h = sum([1 << i for i in range(H) if i % 2 == 0])
        odd_mask_h = sum([1 << i for i in range(H) if i % 2 == 1])
        print(f"   TR→BR A_even={pack_bits(tr_br_even) & even_mask_w:0{(W+3)//4}X} B_odd={pack_bits(tr_br_odd) & odd_mask_w:0{(W+3)//4}X}; BL→BR A_even={pack_bits(bl_br_even) & even_mask_h:0{(H+3)//4}X} B_odd={pack_bits(bl_br_odd) & odd_mask_h:0{(H+3)//4}X}")


if __name__ == '__main__':
    main()
