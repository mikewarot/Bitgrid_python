from __future__ import annotations

import argparse
from typing import List, Dict, Tuple
from ..expr_to_graph import ExprToGraph
from ..mapper import Mapper
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import ManhattanRouter, route_luts


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


# removed vertical spreading to preserve carry parity (alternating rows)


def route_inputs_local_adjacent(prog: Program) -> Program:
    # For each cell input referencing input 'a' or 'b', create a local ROUTE4 injector adjacent to the sink:
    # - 'a' injectors placed at West neighbor (x-1,y) forwarding W->E
    # - 'b' injectors placed at East neighbor (x+1,y) forwarding E->W
    new_cells: List[Cell] = []
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    for sink in prog.cells:
        for idx, src in enumerate(sink.inputs):
            if src.get('type') != 'input':
                continue
            name = str(src.get('name'))
            bit = int(src.get('bit', 0))
            if name == 'a':
                x, y = sink.x - 1, sink.y
                inj_in = [{"type":"const","value":0},{"type":"const","value":0},{"type":"const","value":0},{"type":"input","name":"a","bit":bit}]
                inj = Cell(x=x, y=y, inputs=inj_in, op='ROUTE4', params={'luts': route_luts('E','W')})
                new_cells.append(inj)
                sink.inputs[idx] = {"type":"cell","x":x,"y":y,"out":dir_to_idx['E']}
            elif name == 'b':
                # Place b injector at North neighbor forwarding N->S to avoid blocking East side
                x, y = sink.x, sink.y - 1
                inj_in = [{"type":"input","name":"b","bit":bit},{"type":"const","value":0},{"type":"const","value":0},{"type":"const","value":0}]
                inj = Cell(x=x, y=y, inputs=inj_in, op='ROUTE4', params={'luts': route_luts('S','N')})
                new_cells.append(inj)
                sink.inputs[idx] = {"type":"cell","x":x,"y":y,"out":dir_to_idx['S']}
    return Program(width=prog.width, height=prog.height, cells=prog.cells + new_cells, input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)


def route_outputs_to_east(prog: Program, out_name: str) -> Program:
    # Build straight W->E ROUTE4 chains along a mostly free row to x = width-1.
    used = {(c.x, c.y) for c in prog.cells}
    new_cells: List[Cell] = []
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    east_x = prog.width - 1
    if out_name not in prog.output_bits:
        return prog
    new_out_bits: List[Dict] = []
    for src in prog.output_bits[out_name]:
        if src.get('type') != 'cell':
            new_out_bits.append(src)
            continue
        sx, sy = int(src['x']), int(src['y'])
        # Pick a row: prefer sy; if occupied along path, try sy+1 then sy-1 within bounds
        def path_free(yrow: int) -> bool:
            return all((x, yrow) not in used for x in range(sx+1, east_x+1))
        yrow = sy
        if not path_free(yrow):
            if sy + 1 < prog.height and path_free(sy + 1):
                yrow = sy + 1
            elif sy - 1 >= 0 and path_free(sy - 1):
                yrow = sy - 1
        # If yrow != sy, add a vertical hop first
        prev = {"type":"cell","x":sx,"y":sy,"out":0}
        if yrow != sy:
            direction = 'S' if yrow > sy else 'N'
            opposite = 'N' if direction == 'S' else 'S'
            inputs = [{"type":"const","value":0} for _ in range(4)]
            inputs[dir_to_idx[opposite]] = prev
            new_cells.append(Cell(x=sx, y=yrow, inputs=inputs, op='ROUTE4', params={'luts': route_luts(direction, opposite)}))
            used.add((sx, yrow))
            prev = {"type":"cell","x":sx,"y":yrow,"out":dir_to_idx[direction]}
        # Go east along yrow
        cur_x = sx
        while cur_x < east_x:
            nx = cur_x + 1
            inputs = [{"type":"const","value":0} for _ in range(4)]
            inputs[dir_to_idx['W']] = prev
            new_cells.append(Cell(x=nx, y=yrow, inputs=inputs, op='ROUTE4', params={'luts': route_luts('E','W')}))
            used.add((nx, yrow))
            prev = {"type":"cell","x":nx,"y":yrow,"out":dir_to_idx['E']}
            cur_x = nx
        new_out_bits.append(prev)
    new_output_bits = dict(prog.output_bits)
    new_output_bits[out_name] = new_out_bits
    return Program(width=prog.width, height=prog.height, cells=prog.cells + new_cells, input_bits=prog.input_bits, output_bits=new_output_bits, latency=prog.latency)


def main():
    ap = argparse.ArgumentParser(description='Stream pairs of 8-bit numbers from west edge into an 8-bit adder, read sum at east edge')
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

    # Embed into a larger canvas with margin on west/east
    x_off, y_off = 8, 4
    prog = embed_program(base_prog, new_w=W, new_h=H, x_off=x_off, y_off=y_off)

    # Route inputs a and b via local adjacent injectors next to each sink
    prog = route_inputs_local_adjacent(prog)

    # Route sum outputs to east edge lanes
    prog = route_outputs_to_east(prog, 'sum')

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
    # Drain zeros
    steps += [ {'a':0,'b':0} for _ in range(16) ]

    samples = emu.run_stream(steps, cycles_per_step=max(1,args.cps), reset=True)
    for t, s in enumerate(samples):
        print(f"t={t}: sum=0x{s.get('sum',0):02X}")


if __name__ == '__main__':
    main()
