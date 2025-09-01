from __future__ import annotations

import argparse
from typing import List, Dict

from ..expr_to_graph import ExprToGraph
from ..mapper import Mapper
from ..router import ManhattanRouter
from ..program import Program, Cell
from ..lut_only import grid_from_program, LUTOnlyEmulator
from .demo_lowercase import build_lowercase_expr


def route_inputs_outputs_to_edges(prog: Program, in_name: str, out_name: str, west_rows: List[int], east_rows: List[int]) -> Program:
    # Ensure even dims for router
    W = prog.width + (prog.width % 2)
    H = prog.height + (prog.height % 2)
    # Re-mint Program with padded dims to keep dataclass consistent
    prog = Program(width=W, height=H, cells=list(prog.cells), input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)

    router = ManhattanRouter(W, H)
    for c in prog.cells:
        router.occupy(c.x, c.y)

    new_cells: List[Cell] = []
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}

    # Route every sink usage of input bits to come from West edge at given row
    for sink in prog.cells:
        for i, src in enumerate(sink.inputs):
            if src.get('type') == 'input' and src.get('name') == in_name:
                bit = int(src.get('bit', 0))
                row = west_rows[bit] if 0 <= bit < len(west_rows) else bit
                cells, last_dir, last_xy, _ = router.wire_from_edge_to('W', row, (sink.x, sink.y))
                new_cells.extend(cells)
                sink.inputs[i] = {'type': 'cell', 'x': last_xy[0], 'y': last_xy[1], 'out': dir_to_idx[last_dir]}

    # Route outputs to East edge at rows provided
    outs = prog.output_bits.get(out_name, [])
    for bit, src in enumerate(outs):
        row = east_rows[bit] if 0 <= bit < len(east_rows) else bit
        if src.get('type') == 'cell':
            sx, sy, so = int(src['x']), int(src['y']), int(src.get('out', 0))
            cells = router.wire_to_edge_from((sx, sy), 'E', row, src_out=so)
            new_cells.extend(cells)
        elif src.get('type') == 'const':
            # Emit a constant by placing a LUT cell near the edge and wiring it out
            val = int(src.get('value', 0)) & 1
            # Find a free spot to place a const cell near column 0..W-2
            x, y = 0, row if 0 <= row < H else 0
            while not router.is_free(x, y) and x < W-1:
                x += 1
            # Simple LUT driving E output equal to W input, with W fed by const
            const_cell = Cell(x=x, y=y, inputs=[{'type':'const','value':0},{'type':'const','value':0},{'type':'const','value':0},{'type':'const','value':val}], op='LUT', params={'luts':[0,0,0,0xCCCC]})
            new_cells.append(const_cell)
            router.occupy(x, y)
            more = router.wire_to_edge_from((x, y), 'E', row, src_out=1)  # use E out (index 1)
            new_cells.extend(more)

    prog = Program(width=W, height=H, cells=prog.cells + new_cells, input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency)
    return prog


def run_lutonly(text: str) -> str:
    expr = build_lowercase_expr()
    etg = ExprToGraph({'x': 8})
    g = etg.parse(expr)
    m = Mapper(96, 48)
    p = m.map(g)
    # Route named input 'x' to West rows 0..7 and output 'out' to East rows 0..7
    p_edge = route_inputs_outputs_to_edges(p, 'x', 'out', west_rows=list(range(8)), east_rows=list(range(8)))
    grid = grid_from_program(p_edge, strict=True)
    emu = LUTOnlyEmulator(grid)
    out_bytes: List[int] = []
    # Conservative cycle budget: ManhattanRouter path + logic columns; use grid width + 4
    cycles = grid.W + 4
    for ch in text.encode('utf-8', errors='ignore'):
        emu.reset()
        # Drive West rows with LSB..MSB of ch for the entire duration
        west = [(ch >> i) & 1 for i in range(8)] + [0] * (grid.H - 8)
        for _ in range(cycles):
            emu.step(edge_in={'W': west})
        # Sample East rows 0..7 to reconstruct byte
        # One more settle step to sample after last phase
        emu.step(edge_in={'W': west})
        east = []
        # emu.step returns edge_out; but we need last sampled state; so just collect with no-op input
        out = emu.step(edge_in={'W': [0]*grid.H})
        east = out['E'][:8]
        val = 0
        for i, b in enumerate(east):
            val |= (b & 1) << i
        out_bytes.append(val)
    return bytes(out_bytes).decode('utf-8', errors='ignore')


def main():
    ap = argparse.ArgumentParser(description='Lowercase via LUT-only emulator by routing Program I/O to edges.')
    ap.add_argument('--text', type=str, default='Hello, WORLD! 123_[]')
    ap.add_argument('--export-grid', type=str, help='Optional path to save the routed LUTGrid JSON')
    args = ap.parse_args()

    # Build once to optionally export
    expr = build_lowercase_expr()
    etg = ExprToGraph({'x': 8})
    g = etg.parse(expr)
    m = Mapper(96, 48)
    p = m.map(g)
    p_edge = route_inputs_outputs_to_edges(p, 'x', 'out', list(range(8)), list(range(8)))
    grid = grid_from_program(p_edge, strict=True)
    if args.export_grid:
        grid.save(args.export_grid)
        print(f'Saved LUTGrid to {args.export_grid} ({grid.W}x{grid.H})')

    # Now run once through LUT-only emulator
    emu = LUTOnlyEmulator(grid)
    cycles = grid.W + 4
    out_chars: List[int] = []
    for ch in args.text.encode('utf-8', errors='ignore'):
        emu.reset()
        west = [(ch >> i) & 1 for i in range(8)] + [0] * (grid.H - 8)
        for _ in range(cycles):
            emu.step(edge_in={'W': west})
        # final settle/sample
        out = emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': [0]*grid.H})
        east = out['E'][:8]
        val = 0
        for i, b in enumerate(east):
            val |= (b & 1) << i
        out_chars.append(val)
    out_text = bytes(out_chars).decode('utf-8', errors='ignore')
    print(f'in : {args.text}')
    print(f'out: {out_text}')


if __name__ == '__main__':
    main()
