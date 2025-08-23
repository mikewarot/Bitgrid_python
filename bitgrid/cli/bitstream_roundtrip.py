from __future__ import annotations

import argparse
import os
from ..program import Program
from ..bitstream import (
    pack_program_bitstream,
    unpack_bitstream_to_luts,
    apply_luts_to_program,
    pack_program_bitstream_with_header,
    unpack_bitstream_with_header,
    has_bitstream_header,
)


def main():
    ap = argparse.ArgumentParser(description='Pack and unpack a Program LUT bitstream to verify round-trip.')
    ap.add_argument('--program', type=str, required=True, help='Path to Program JSON')
    ap.add_argument('--order', type=str, default='row-major', choices=['row-major','col-major','snake'], help='Cell scan order for bitstream serialization')
    ap.add_argument('--out', type=str, default='out/bitstream.bin', help='Output bitstream file path')
    ap.add_argument('--header', action='store_true', help='Write a fixed header (magic/version/dims/order/CRC)')
    args = ap.parse_args()

    prog = Program.load(args.program)
    if args.header:
        blob = pack_program_bitstream_with_header(prog, order=args.order)
    else:
        blob = pack_program_bitstream(prog, order=args.order)

    out_dir = os.path.dirname(args.out) or '.'
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, 'wb') as f:
        f.write(blob)

    if has_bitstream_header(blob):
        luts, hdr = unpack_bitstream_with_header(blob)
    else:
        luts = unpack_bitstream_to_luts(blob, prog.width, prog.height, order=args.order)
    prog2 = apply_luts_to_program(Program(width=prog.width, height=prog.height, cells=[], input_bits=prog.input_bits, output_bits=prog.output_bits, latency=prog.latency), luts)

    base, ext = os.path.splitext(args.program)
    rehydrated_path = f"{base}_rehydrated{ext or '.json'}"
    prog2.save(rehydrated_path)

    print(f"wrote {args.out} ({len(blob)} bytes); rehydrated -> {rehydrated_path}")


if __name__ == '__main__':
    main()
