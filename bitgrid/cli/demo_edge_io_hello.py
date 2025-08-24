from __future__ import annotations

import argparse
from typing import List, Dict
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts


def build_edge_stream_program(width: int, height: int, row0: int, lanes: int, length: int) -> Program:
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes != 8:
        raise ValueError('This demo uses 8 lanes for 8-bit ASCII.')
    if row0 < 0 or (row0 + lanes - 1) >= height:
        raise ValueError('Row range out of bounds for lanes.')
    if length < 1 or (1 + length) >= width:
        raise ValueError('Path length must be >=1 and fit within width (1+len < width).')

    cells: List[Cell] = []
    dir_to_idx = {'N':0, 'E':1, 'S':2, 'W':3}

    # Build 8 parallel horizontal lanes from x=0 to x=length at rows row0..row0+7
    for i in range(lanes):
        y = row0 + i
        # Injector at west edge: drive from input 'west' bit i into W pin, route to E
        inj_inputs = [
            {"type":"const","value":0},  # N
            {"type":"const","value":0},  # E
            {"type":"const","value":0},  # S
            {"type":"input","name":"west","bit":i},  # W gets west bit i
        ]
        inj = Cell(x=0, y=y, inputs=inj_inputs, op='ROUTE4', params={'luts': route_luts('E','W')})
        cells.append(inj)
        # Build straight chain forwarding W->E
        prev_src = {"type":"cell","x":0,"y":y,"out":dir_to_idx['E']}
        for x in range(1, 1 + length):
            c_inputs = [ {"type":"const","value":0} for _ in range(4) ]
            c_inputs[dir_to_idx['W']] = prev_src
            c = Cell(x=x, y=y, inputs=c_inputs, op='ROUTE4', params={'luts': route_luts('E','W')})
            cells.append(c)
            prev_src = {"type":"cell","x":x,"y":y,"out":dir_to_idx['E']}

    # Map outputs: 'east' is 8-bit wide, one bit per lane, sampled at last cell's E output
    output_bits: Dict[str, List[Dict]] = {
        'east': [ {"type":"cell","x":length,"y":row0 + i,"out":dir_to_idx['E']} for i in range(lanes) ]
    }

    prog = Program(width=width, height=height, cells=cells,
                   input_bits={'west': [{'type':'input','name':'west','bit':i} for i in range(lanes)]},
                   output_bits=output_bits, latency=width + height)
    return prog


def main():
    ap = argparse.ArgumentParser(description='Edge streaming I/O: send ASCII text over 8 parallel lanes (Hello World)')
    ap.add_argument('--width', type=int, default=16)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--row', type=int, default=0, help='starting row for 8 lanes')
    ap.add_argument('--len', type=int, default=12, help='number of hops horizontally (1..W-2)')
    ap.add_argument('--cps', type=int, default=2, help='cycles per step (2 = one hop/step)')
    ap.add_argument('--text', type=str, default='Hello World')
    args = ap.parse_args()

    W, H = args.width, args.height
    cps = max(1, int(args.cps))
    prog = build_edge_stream_program(W, H, args.row, 8, args.len)

    emu = Emulator(prog)

    # Build steps: feed each character's byte on west each step
    message = args.text
    steps = [{ 'west': ord(ch) & 0xFF } for ch in message]
    # Drain zeros to flush pipeline
    steps += [{ 'west': 0 } for _ in range(args.len + 4)]

    samples = emu.run_stream(steps, cycles_per_step=cps, reset=True)

    # Reconstruct output characters: collect first len(message) non-zero bytes
    out_bytes: List[int] = []
    for s in samples:
        b = int(s.get('east', 0)) & 0xFF
        if b != 0:
            out_bytes.append(b)
            if len(out_bytes) >= len(message):
                break

    out_text = ''.join(chr(b) for b in out_bytes)
    print(out_text)


if __name__ == '__main__':
    main()
