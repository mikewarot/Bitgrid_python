from __future__ import annotations

import argparse

from ..lut_only import LUTGrid, LUTOnlyEmulator


def main():
    ap = argparse.ArgumentParser(description='Run the LUT-only emulator from a LUTGrid JSON file.')
    ap.add_argument('--in', dest='inp', required=True, help='input LUTGrid JSON')
    ap.add_argument('--steps', type=int, default=4, help='Number of subcycles to run')
    ap.add_argument('--west', help='Comma-separated H-length bits to drive on west edge for step 0')
    ap.add_argument('--north', help='Comma-separated W-length bits to drive on north edge for step 0')
    ap.add_argument('--east', help='Comma-separated H-length bits to drive on east edge for step 0')
    ap.add_argument('--south', help='Comma-separated W-length bits to drive on south edge for step 0')
    ap.add_argument('--hold', action='store_true', help='Keep driving provided edge bits every step (sticky inputs)')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    emu = LUTOnlyEmulator(g)

    def parse_bits(s: str | None, n: int):
        if not s:
            return None
        v = [int(x) & 1 for x in s.split(',') if x.strip() != '']
        if len(v) != n:
            raise SystemExit(f"Expected {n} bits, got {len(v)}")
        return v

    edge = {
        'N': parse_bits(args.north, g.W),
        'E': parse_bits(args.east, g.H),
        'S': parse_bits(args.south, g.W),
        'W': parse_bits(args.west, g.H),
    }
    # Drop None entries
    edge = {k: v for k, v in edge.items() if v is not None} or None

    for i in range(args.steps):
        out = emu.step(edge_in=edge)
        print(f"step {i}: N={out['N']} E={out['E']} S={out['S']} W={out['W']}")
        if not args.hold:
            edge = None


if __name__ == '__main__':
    main()
