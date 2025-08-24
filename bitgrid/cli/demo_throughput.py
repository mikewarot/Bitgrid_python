from __future__ import annotations

import argparse
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import ManhattanRouter, route_luts


def main():
    ap = argparse.ArgumentParser(description='Throughput demo: stream along a routed path with ROUTE4')
    ap.add_argument('--width', type=int, default=16)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--src', type=str, default='0,1')
    ap.add_argument('--dst', type=str, default='14,6')
    ap.add_argument('--train', type=int, default=8, help='number of consecutive 1s to inject')
    ap.add_argument('--cps', type=int, default=2, help='cycles per step (2 for one hop/step parity)')
    ap.add_argument('--turn', type=float, default=0.25, help='turn penalty for router (bias straighter paths)')
    args = ap.parse_args()

    W, H = args.width, args.height
    if W % 2 or H % 2:
        raise SystemExit('Grid width and height must be even.')
    sx, sy = map(int, args.src.split(','))
    dx, dy = map(int, args.dst.split(','))
    if not (0 <= sx < W and 0 <= sy < H and 0 <= dx < W and 0 <= dy < H):
        raise SystemExit('src/dst must be within grid bounds')

    cells = []
    # Source beacon cell at (sx,sy): drive its East output from input 'west' via ROUTE4
    src_in = [
        {"type":"const","value":0},  # N
        {"type":"const","value":0},  # E
        {"type":"const","value":0},  # S
        {"type":"input","name":"west","bit":0},  # W
    ]
    src_cell = Cell(x=sx, y=sy, inputs=src_in, op='ROUTE4', params={'luts': route_luts('E','W')})
    cells.append(src_cell)

    router = ManhattanRouter(W, H)
    router.occupy(sx, sy)
    # Route to destination with small turn penalty
    path = router.route((sx, sy), (dx, dy), turn_penalty=float(args.turn))

    # Translate path into inserted ROUTE4 cells
    cur = (sx, sy)
    prev_src = {"type": "cell", "x": sx, "y": sy, "out": 1}  # East output from src_cell
    last_dir = 'E'
    dir_to_idx = {'N':0,'E':1,'S':2,'W':3}
    opposite_of = {'E':'W','W':'E','N':'S','S':'N'}

    for nxt in path:
        dxv = nxt[0] - cur[0]
        dyv = nxt[1] - cur[1]
        if dxv == 1:
            direction = 'E'
        elif dxv == -1:
            direction = 'W'
        elif dyv == 1:
            direction = 'S'
        elif dyv == -1:
            direction = 'N'
        else:
            raise SystemExit('Non-adjacent hop encountered in route')
        x, y = nxt
        router.occupy(x, y)
        inputs = [ {"type":"const","value":0} for _ in range(4) ]
        opposite = opposite_of[direction]
        inputs[dir_to_idx[opposite]] = prev_src
        luts = route_luts(direction, opposite)
        cells.append(Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts}))
        prev_src = {"type":"cell","x":x,"y":y,"out":dir_to_idx[direction]}
        last_dir = direction
        cur = nxt

    out_idx = dir_to_idx[last_dir]
    prog = Program(width=W, height=H, cells=cells,
                   input_bits={'west':[{'type':'input','name':'west','bit':0}]},
                   output_bits={'east':[{'type':'cell','x':dx,'y':dy,'out':out_idx}]},
                   latency=W+H)
    emu = Emulator(prog)

    # Build a step sequence: train ones, then zeros
    steps = [{"west":1} for _ in range(max(1,args.train))] + [{"west":0} for _ in range(W+H)]
    samples = emu.run_stream(steps, cycles_per_step=max(1,args.cps), reset=True)
    for t, s in enumerate(samples):
        print(f"t={t}: east={s['east']}")


if __name__ == '__main__':
    main()
