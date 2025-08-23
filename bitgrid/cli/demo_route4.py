from __future__ import annotations

import argparse
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import ManhattanRouter


def main():
    ap = argparse.ArgumentParser(description='Demo ROUTE4 routing between two points')
    ap.add_argument('--width', type=int, default=16)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--src', type=str, default='0,0')
    ap.add_argument('--dst', type=str, default='5,3')
    args = ap.parse_args()

    W, H = args.width, args.height
    if W % 2 or H % 2:
        raise SystemExit("Grid width and height must be even.")
    sx, sy = map(int, args.src.split(','))
    dx, dy = map(int, args.dst.split(','))

    # Create a program with a single source cell (BUF producing bit 1) and a sink sampled as output
    cells = []
    # Source at (sx,sy)
    src_cell = Cell(x=sx, y=sy, inputs=[{"type":"const","value":1},{"type":"const","value":0},{"type":"const","value":0},{"type":"const","value":0}], op='BUF', params={})
    cells.append(src_cell)

    router = ManhattanRouter(W, H)
    router.occupy(sx, sy)
    route_cells, last_dir = router.wire_with_route4((sx, sy), (dx, dy))
    cells.extend(route_cells)
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    out_idx = dir_to_idx.get(last_dir, 1)

    prog = Program(width=W, height=H, cells=cells,
                   input_bits={"dummy": []},
                   output_bits={"out": [{"type":"cell", "x": dx, "y": dy, "out": out_idx}]},
                   latency=W+H)

    emu = Emulator(prog)
    out = emu.run([{}])[0]
    print(f"Output at {dx},{dy} ({last_dir} out) = {out['out']}")


if __name__ == '__main__':
    main()
