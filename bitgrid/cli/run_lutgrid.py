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
    # Streaming variants: semicolon-separated frames, each frame is a comma-separated bit list
    ap.add_argument('--west-seq', help='Semicolon-separated frames for west edge (each H-length, e.g., 1,0,0;0,1,0)')
    ap.add_argument('--north-seq', help='Semicolon-separated frames for north edge (each W-length)')
    ap.add_argument('--east-seq', help='Semicolon-separated frames for east edge (each H-length)')
    ap.add_argument('--south-seq', help='Semicolon-separated frames for south edge (each W-length)')
    ap.add_argument('--hold', action='store_true', help='Keep driving provided edge bits every step (sticky inputs)')
    args = ap.parse_args()

    g = LUTGrid.load(args.inp)
    emu = LUTOnlyEmulator(g)

    def parse_bits(s: str | None, n: int):
        if not s:
            return None
        v = [int(x) & 1 for x in s.split(',') if x.strip() != '']
        if len(v) > n:
            raise SystemExit(f"Expected at most {n} bits, got {len(v)}")
        # pad with zeros to length n for convenience
        return v + [0] * (n - len(v))

    def parse_seq(s: str | None, n: int):
        if not s:
            return None
        frames = []
        for frame in s.split(';'):
            frame = frame.strip()
            if frame == '':
                continue
            frames.append(parse_bits(frame, n))
        return frames if frames else None

    # Pre-parse single-frame and streaming inputs
    single = {
        'N': parse_bits(args.north, g.W),
        'E': parse_bits(args.east, g.H),
        'S': parse_bits(args.south, g.W),
        'W': parse_bits(args.west, g.H),
    }
    streams = {
        'N': parse_seq(args.north_seq, g.W),
        'E': parse_seq(args.east_seq, g.H),
        'S': parse_seq(args.south_seq, g.W),
        'W': parse_seq(args.west_seq, g.H),
    }
    # If any stream is provided, it takes precedence for that side
    # Build a function to provide edge inputs per step
    def inputs_for_step(step: int):
        out = {}
        for side, seq in streams.items():
            if seq:
                idx = min(step, len(seq) - 1)
                out[side] = seq[idx]
        for side, vec in single.items():
            if vec is not None and side not in out:
                out[side] = vec
        return out or None

    edge_this = inputs_for_step(0)
    for i in range(args.steps):
        out = emu.step(edge_in=edge_this)
        print(f"step {i}: N={out['N']} E={out['E']} S={out['S']} W={out['W']}")
        if args.hold:
            # keep edge_this as-is
            pass
        else:
            edge_this = inputs_for_step(i + 1)


if __name__ == '__main__':
    main()
