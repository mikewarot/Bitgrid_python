from __future__ import annotations

import argparse
from ..program import Program
from ..emulator import Emulator


def main():
    ap = argparse.ArgumentParser(description='Load a LUT bitstream into a Program and run the emulator on CSV inputs.')
    ap.add_argument('--program', required=True, help='Program JSON (provides dims and I/O mapping)')
    ap.add_argument('--bitstream', required=True, help='Bitstream file (with or without header)')
    ap.add_argument('--inputs', required=True, help='Input CSV (header matches var names)')
    ap.add_argument('--outputs', required=True, help='Output CSV file')
    ap.add_argument('--order', choices=['row-major','col-major','snake'], help='Scan order for raw bitstreams (ignored if header present)')
    ap.add_argument('--width', type=int, help='Width for raw bitstreams (defaults to Program width)')
    ap.add_argument('--height', type=int, help='Height for raw bitstreams (defaults to Program height)')
    args = ap.parse_args()

    prog = Program.load(args.program)
    emu = Emulator(prog)

    with open(args.bitstream, 'rb') as f:
        data = f.read()
    meta = emu.load_bitstream(data, order=args.order, width=args.width, height=args.height)
    print(f"Loaded bitstream: used_header={meta['used_header']} order={meta['order']} dims={meta['width']}x{meta['height']}")

    # Defer to run_emulator for CSV I/O behavior by importing its helpers
    import csv
    from .run_emulator import parse_int

    vectors = []
    with open(args.inputs, 'r', newline='') as f:
        r = csv.DictReader(f)
        for row in r:
            vectors.append({k: parse_int(v) for k, v in row.items()})

    results = emu.run(vectors)

    out_fields = list(prog.output_bits.keys())
    with open(args.outputs, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        for res in results:
            w.writerow({k: res[k] for k in out_fields})

    print(f'Wrote outputs to {args.outputs}')


if __name__ == '__main__':
    main()
