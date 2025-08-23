from __future__ import annotations

import argparse
from typing import List, Dict
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts


def build_4bit_edge_program(width: int, height: int, row0: int, length: int) -> Program:
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if row0 < 0 or (row0 + 3) >= height:
        raise ValueError('Row range out of bounds for 4 lanes.')
    if length < 1 or (1 + length) >= width:
        raise ValueError('Path length must be >=1 and fit within width (1+len < width).')

    cells: List[Cell] = []
    dir_to_idx = {'N':0, 'E':1, 'S':2, 'W':3}

    # Build 4 parallel horizontal lanes from x=0 to x=length at rows row0..row0+3
    for i in range(4):
        y = row0 + i
        inj_inputs = [
            {"type":"const","value":0},  # N
            {"type":"const","value":0},  # E
            {"type":"const","value":0},  # S
            {"type":"input","name":"din4","bit":i},  # W gets din bit i
        ]
        inj = Cell(x=0, y=y, inputs=inj_inputs, op='ROUTE4', params={'luts': route_luts('E','W')})
        cells.append(inj)
        prev_src = {"type":"cell","x":0,"y":y,"out":dir_to_idx['E']}
        for x in range(1, 1 + length):
            c_inputs = [ {"type":"const","value":0} for _ in range(4) ]
            c_inputs[dir_to_idx['W']] = prev_src
            c = Cell(x=x, y=y, inputs=c_inputs, op='ROUTE4', params={'luts': route_luts('E','W')})
            cells.append(c)
            prev_src = {"type":"cell","x":x,"y":y,"out":dir_to_idx['E']}

    output_bits: Dict[str, List[Dict]] = {
        'dout4': [ {"type":"cell","x":length,"y":row0 + i,"out":dir_to_idx['E']} for i in range(4) ]
    }

    prog = Program(width=width, height=height, cells=cells,
                   input_bits={'din4': [{'type':'input','name':'din4','bit':i} for i in range(4)]},
                   output_bits=output_bits, latency=width + height)
    return prog


def parse_steps_hex_list(arg: str) -> List[int]:
    # Expect comma-separated nibbles like "0,1,2,3,a,b,f"
    vals: List[int] = []
    for tok in arg.split(','):
        tok = tok.strip()
        if tok.startswith('0x') or tok.startswith('0X'):
            v = int(tok, 16)
        else:
            v = int(tok, 16) if any(c in tok.lower() for c in 'abcdef') else int(tok, 10)
        vals.append(v & 0xF)
    return vals


def main():
    ap = argparse.ArgumentParser(description='Edge streaming I/O: 4-bit lanes W->E, print input/output per step')
    ap.add_argument('--width', type=int, default=12)
    ap.add_argument('--height', type=int, default=6)
    ap.add_argument('--row', type=int, default=1, help='starting row for 4 lanes')
    ap.add_argument('--len', type=int, default=8, help='number of hops horizontally (1..W-2)')
    ap.add_argument('--cps', type=int, default=2, help='cycles per step (2 = one hop/step)')
    ap.add_argument('--steps', type=str, default='1,2,4,8,0,3,5,9,a,b,c,d,e,f,0',
                    help='comma-separated 4-bit values (hex digits ok) to stream in')
    args = ap.parse_args()

    W, H = args.width, args.height
    cps = max(1, int(args.cps))
    prog = build_4bit_edge_program(W, H, args.row, args.len)

    emu = Emulator(prog)

    in_vals = parse_steps_hex_list(args.steps)
    steps = [ {'din4': v} for v in in_vals ]
    # Drain zeros to flush pipeline
    steps += [ {'din4': 0} for _ in range(args.len + 4) ]

    samples = emu.run_stream(steps, cycles_per_step=cps, reset=True)

    # Print per-step IO
    for t, (inv, s) in enumerate(zip(in_vals + [None]*(len(samples)-len(in_vals)), samples)):
        dout = int(s.get('dout4', 0)) & 0xF
        if t < len(in_vals):
            print(f"t={t:02d} in={in_vals[t]:X} out={dout:X}")
        else:
            print(f"t={t:02d} in=  out={dout:X}")


if __name__ == '__main__':
    main()
