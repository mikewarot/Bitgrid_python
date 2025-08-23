from __future__ import annotations

import argparse
from ..interop import EdgeFrame, EdgeHeader, make_framed_tx, parse_framed_rx


def main():
    ap = argparse.ArgumentParser(description="Pack/unpack inter-tile framed edge data")
    ap.add_argument('--width', type=int, default=8)
    ap.add_argument('--height', type=int, default=6)
    ap.add_argument('--epoch', type=int, default=1)
    ap.add_argument('--phase', type=str, default='A')
    args = ap.parse_args()

    width, height = args.width, args.height
    # Build a test pattern: north=0..W-1, east=0..H-1, south=1s, west=alternating
    north = [ (i & 1) for i in range(width) ]
    east = [ ((i>>1) & 1) for i in range(height) ]
    south = [ 1 for _ in range(width) ]
    west = [ (i & 1) ^ 1 for i in range(height) ]

    hdr = EdgeHeader(epoch=args.epoch, phase=args.phase)
    fr = EdgeFrame(north=north, east=east, south=south, west=west)

    blob = make_framed_tx(hdr, fr, with_crc=True)
    parsed = parse_framed_rx(blob, width, height, with_crc=True)
    if parsed is None:
        print('CRC error or parse error')
        return
    ph, pf = parsed
    print(f"hdr: epoch={ph.epoch} phase={ph.phase}")
    print('north:', pf.north)
    print('east :', pf.east)
    print('south:', pf.south)
    print('west :', pf.west)


if __name__ == '__main__':
    main()
