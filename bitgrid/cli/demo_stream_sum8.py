from __future__ import annotations

import argparse
from collections import deque
from typing import List, Dict, Tuple
from ..expr_to_graph import ExprToGraph
from ..mapper import Mapper
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts


def embed_program(prog: Program, new_w: int, new_h: int, x_off: int, y_off: int) -> Program:
    # Shift all cell coordinates by offsets and update cell references in inputs and outputs.
    def shift_src(src: Dict) -> Dict:
        if src.get('type') == 'cell':
            return {"type":"cell","x":int(src['x'])+x_off,"y":int(src['y'])+y_off,"out":int(src.get('out',0))}
        return src
    new_cells: List[Cell] = []
    for c in prog.cells:
        new_inputs = [shift_src(s) for s in c.inputs]
        new_cells.append(Cell(x=c.x + x_off, y=c.y + y_off, inputs=new_inputs, op=c.op, params=c.params))
    # shift output_bits cell refs
    new_outputs: Dict[str, List[Dict]] = {}
    for name, bits in prog.output_bits.items():
        new_outputs[name] = [shift_src(s) for s in bits]
    return Program(width=new_w, height=new_h, cells=new_cells, input_bits=prog.input_bits, output_bits=new_outputs, latency=new_w + new_h)


def find_adder_column(prog: Program) -> Tuple[int, int, int]:
    ys = [c.y for c in prog.cells if c.op == 'ADD_BIT']
    xs = [c.x for c in prog.cells if c.op == 'ADD_BIT']
    if not ys or not xs:
        raise SystemExit('No ADD_BIT cells found in mapped program')
    x = xs[0]
    y_min, y_max = min(ys), max(ys)
    return x, y_min, y_max


# Note: We don't build custom pipelines here. We stream inputs directly into the mapped adder
# and align the per-row sum bits in software to account for carry ripple and hop latency.


def wire_adder_to_pipelines(prog: Program, x_adder: int, y_min: int, y_max: int):
    # No-op in this simplified streaming demo (kept for compatibility if needed later)
    return


def main():
    ap = argparse.ArgumentParser(description='Stream pairs of 8-bit numbers into a pipelined 8-bit adder and print aligned sums (cps=2)')
    ap.add_argument('--width', type=int, default=64)
    ap.add_argument('--height', type=int, default=32)
    ap.add_argument('--cps', type=int, default=2)
    ap.add_argument('--pairs', type=str, default='(1,2),(3,4),(10,20),(255,1)')
    args = ap.parse_args()

    W, H = args.width, args.height
    if W % 2 or H % 2:
        raise SystemExit('Grid width and height must be even.')

    # Build 8-bit adder program
    etg = ExprToGraph({'a':8,'b':8}, {'a':False,'b':False})
    g = etg.parse('sum = a + b')
    mapper = Mapper(grid_width=W, grid_height=H)
    base_prog = mapper.map(g)

    # Embed into a larger canvas with margin on sides
    x_off, y_off = 8, 4
    prog = embed_program(base_prog, new_w=W, new_h=H, x_off=x_off, y_off=y_off)

    # Locate adder column and bit range
    x_add, y_min, y_max = find_adder_column(prog)
    bit_count = (y_max - y_min + 1)

    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    lsb_even = ((x_add + y_min) % 2 == 0)
    def cycle_i(i: int) -> int:
        return (i // 2) if lsb_even else ((i + 1) // 2)
    new_cells: List[Cell] = []

    # Equalize sum bit timing by delaying lower bits further to the east so all bits align in the same step.
    sum_bits = list(prog.output_bits.get('sum', []))
    new_sum_bits: List[Dict] = []
    for c in prog.cells:
        pass  # ensure we don't accidentally reorder
    # Align all sum bits to K cycles after step start
    K = max(cycle_i(i) for i in range(bit_count))
    for src in sum_bits:
        if src.get('type') != 'cell':
            new_sum_bits.append(src)
            continue
        y = int(src['y'])
        i = y - y_min
        delay = K - cycle_i(i)
        prev = src
        for k in range(delay):
            x = x_add + bit_count + 2 + k  # place far enough to the right
            inputs = [{"type":"const","value":0} for _ in range(4)]
            inputs[dir_to_idx['W']] = prev
            cell = Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': route_luts('E','W')})
            new_cells.append(cell)
            prev = {"type":"cell","x":x,"y":y,"out":dir_to_idx['E']}
        new_sum_bits.append(prev)

    prog = Program(width=prog.width, height=prog.height, cells=prog.cells + new_cells,
                   input_bits=prog.input_bits, output_bits={**prog.output_bits, 'sum': new_sum_bits},
                   latency=prog.latency)

    # Stream pairs
    emu = Emulator(prog)
    # Parse pairs like (x,y),(u,v)
    pairs: List[Tuple[int,int]] = []
    for tok in args.pairs.split(')'):
        tok = tok.strip().lstrip(',')
        if not tok:
            continue
        tok = tok.strip(' ,(')
        if not tok:
            continue
        parts = tok.split(',')
        if len(parts) != 2:
            continue
        a = int(parts[0], 0)
        b = int(parts[1], 0)
        pairs.append((a & 0xFF, b & 0xFF))
    steps = [ {'a': a, 'b': b} for (a,b) in pairs ]
    # Drain zeros to flush the pipeline
    steps += [ {'a':0,'b':0} for _ in range(16) ]

    # Derive K (max per-bit step lag) from adder placement and parity
    xs = [c.x for c in prog.cells if c.op == 'ADD_BIT']
    ys = [c.y for c in prog.cells if c.op == 'ADD_BIT']
    if not xs or not ys:
        raise SystemExit('No ADD_BIT cells found')
    x_add = xs[0]; y_min = min(ys); y_max = max(ys)
    bit_count = (y_max - y_min + 1)
    lsb_even = ((x_add + y_min) % 2 == 0)
    def lag(i: int) -> int:
        return (i // 2) if lsb_even else ((i + 1) // 2)
    K = max(lag(i) for i in range(bit_count))

    # Hold each input pair steady for K+1 steps, then sample the sum at the end of the window
    hold = K + 1
    replay: List[Dict[str,int]] = []
    for (a,b) in pairs:
        replay.extend([{ 'a': a, 'b': b } for _ in range(hold)])
    # add a drain block to reset
    replay.extend([{ 'a': 0, 'b': 0 } for _ in range(hold)])

    samples = emu.run_stream(replay, cycles_per_step=max(1,args.cps), reset=True)
    results: List[int] = []
    for i in range(len(pairs)):
        idx = (i+1)*hold - 1
        if idx < len(samples):
            results.append(samples[idx].get('sum', 0) & 0xFF)
    for i in range(min(len(results), len(pairs))):
        a,b = pairs[i]
        print(f"i={i}: a={a} b={b} -> sum=0x{results[i]:02X}")

    # Optionally print compact list of produced sums
    # print('sums:', [f"0x{v:02X}" for v in produced])


if __name__ == '__main__':
    main()
