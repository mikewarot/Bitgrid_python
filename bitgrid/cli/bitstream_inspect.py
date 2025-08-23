from __future__ import annotations

import argparse
import os
import binascii
from ..bitstream import (
    has_bitstream_header,
    parse_bitstream_header,
    ORDER_BY_CODE,
    HEADER_SIZE,
)


def main():
    ap = argparse.ArgumentParser(description='Inspect a BitGrid LUT bitstream (headered or raw).')
    ap.add_argument('path', help='Bitstream file path')
    ap.add_argument('--order', choices=['row-major','col-major','snake'], help='If no header: scan order to interpret payload')
    ap.add_argument('--width', type=int, help='If no header: grid width')
    ap.add_argument('--height', type=int, help='If no header: grid height')
    args = ap.parse_args()

    p = args.path
    if not os.path.isfile(p):
        print(f'error: file not found: {p}')
        return 2
    data = open(p, 'rb').read()
    size = len(data)
    print(f'file: {p}')
    print(f'size: {size} bytes')

    if has_bitstream_header(data):
        hdr = parse_bitstream_header(data)
        order_code = int(hdr['order'])
        order_name = ORDER_BY_CODE[order_code]
        payload_bits = int(hdr['payload_bits'])
        payload_bytes = (payload_bits + 7) // 8
        payload = data[HEADER_SIZE:]
        crc_calc = binascii.crc32(payload[:payload_bytes]) & 0xFFFFFFFF
        crc_hdr = int(hdr['payload_crc32'])
        extra = len(payload) - payload_bytes
        print('header: present')
        print(f"  version       : {hdr['version']}")
        print(f"  dims          : {hdr['width']} x {hdr['height']}")
        print(f"  order         : {order_code} ({order_name})")
        print(f"  flags         : 0x{int(hdr['flags']):02X}")
        print(f"  payload_bits  : {payload_bits}")
        print(f"  payload_bytes : {payload_bytes}")
        print(f"  crc32(header) : 0x{crc_hdr:08X}")
        print(f"  crc32(calc)   : 0x{crc_calc:08X}  [{'OK' if crc_calc==crc_hdr else 'MISMATCH'}]")
        if extra < 0:
            print(f"  payload status: TRUNCATED by {-extra} bytes")
        elif extra > 0:
            print(f"  payload status: {extra} trailing byte(s) after expected payload")
        else:
            print("  payload status: exact length")
    else:
        print('header: none (raw payload)')
        if args.width and args.height:
            w = int(args.width)
            h = int(args.height)
            bits = w * h * 4 * 16
            bytes_needed = (bits + 7) // 8
            payload_bytes = size
            print(f'  assumed dims  : {w} x {h}')
            print(f"  assumed order : {args.order or 'row-major'}")
            print(f'  payload_bits  : {bits}')
            print(f'  expected_bytes: {bytes_needed}')
            if payload_bytes == bytes_needed:
                print('  length check  : OK (exact)')
            elif payload_bytes < bytes_needed:
                print(f'  length check  : TOO SHORT by {bytes_needed - payload_bytes} bytes')
            else:
                print(f'  length check  : {payload_bytes - bytes_needed} extra trailing byte(s)')
        else:
            print('  tip: pass --width/--height/--order to validate size and interpret payload')


if __name__ == '__main__':
    main()
