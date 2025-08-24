from __future__ import annotations

import argparse
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts


def main():
    ap = argparse.ArgumentParser(description='Stream a pulse across ROUTE4 chain W->E')
    ap.add_argument('--width', type=int, default=12)
    ap.add_argument('--height', type=int, default=4)
    ap.add_argument('--row', type=int, default=1, help='row (y) to route along')
    ap.add_argument('--len', type=int, default=8, help='number of hops')
    ap.add_argument('--cps', type=int, default=2, help='cycles per step (2 needed for one hop/step)')
    args = ap.parse_args()

    W, H = args.width, args.height
    if W % 2 or H % 2:
        raise SystemExit("Grid width and height must be even.")
    y = args.row
    L = args.len
    cps = args.cps
    if not (0 <= y < H):
        raise SystemExit(f"row must be within [0,{H-1}]")
    if L < 1 or (1+L) >= W:
        raise SystemExit("len must be >=1 and path must fit within width")

    cells = []
    # West-edge injector at (0,y): use input bit 'west' as West input, route out East
    inj = Cell(x=0, y=y,
               inputs=[{"type":"const","value":0}, {"type":"const","value":0}, {"type":"const","value":0}, {"type":"input","name":"west","bit":0}],
               op='ROUTE4', params={'luts': route_luts('E','W')})
    cells.append(inj)

    # Build a straight E path of ROUTE4 forwarding E<-W
    for x in range(1, 1+L):
        cell = Cell(x=x, y=y,
                    inputs=[{"type":"const","value":0}, {"type":"const","value":0}, {"type":"const","value":0}, {"type":"cell","x":x-1,"y":y,"out":1}],
                    op='ROUTE4', params={'luts': route_luts('E','W')})
        cells.append(cell)

    # Observe last cell's East output as 'east'
    out_map = {"east": [{"type":"cell","x":1+L-1,"y":y,"out":1}]}

    prog = Program(width=W, height=H, cells=cells, input_bits={'west':[{'type':'input','name':'west','bit':0}]}, output_bits=out_map, latency=W+H)
    emu = Emulator(prog)

    # Stream: one cycle per step, pulse west=1 at t0, then 0s
    steps = [{"west": 1}] + [{"west": 0} for _ in range(L+4)]
    samples = emu.run_stream(steps, cycles_per_step=cps, reset=True)
    for t, s in enumerate(samples):
        print(f"t={t}: east={s['east']}")


if __name__ == '__main__':
    main()
