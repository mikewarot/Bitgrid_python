from __future__ import annotations

import argparse
import os
from typing import List, Dict
from ..program import Program, Cell
from ..router import route_luts


def build_left_program(width: int, height: int, row0: int, lanes: int, length: int) -> Program:
    # Zero-latency left: directly expose input bus 'din' as output bus 'east'.
    # This avoids propagation/phase alignment complexity for the linked hello test scenario.
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes != 8:
        raise ValueError('This demo uses 8 lanes for 8-bit ASCII.')
    input_bits: Dict[str, List[Dict]] = {'din': [{'type': 'input', 'name': 'din', 'bit': i} for i in range(lanes)]}
    output_bits: Dict[str, List[Dict]] = {'east': [{'type': 'input', 'name': 'din', 'bit': i} for i in range(lanes)]}
    return Program(width=width, height=height, cells=[], input_bits=input_bits, output_bits=output_bits, latency=0)


def build_right_program(width: int, height: int, lanes: int) -> Program:
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes != 8:
        raise ValueError('This demo uses 8 lanes for 8-bit ASCII.')
    # Trivial: just expose an input bus 'west' and mirror it to an output 'east'
    input_bits = {'west': [ {'type':'input','name':'west','bit':i} for i in range(lanes) ]}
    output_bits = {'east': [ {'type':'input','name':'west','bit':i} for i in range(lanes) ]}
    return Program(width=width, height=height, cells=[], input_bits=input_bits, output_bits=output_bits, latency=0)


def build_left_program_edge_io(width: int, height: int, lanes: int) -> Program:
    """Edge-true left: expose only edge buses: west (in) and east (out). east mirrors west.
    Suitable for physical edge-only I/O models.
    """
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    input_bits: Dict[str, List[Dict]] = {'west': [{'type':'input','name':'west','bit':i} for i in range(lanes)]}
    output_bits: Dict[str, List[Dict]] = {'east': [{'type':'input','name':'west','bit':i} for i in range(lanes)]}
    return Program(width=width, height=height, cells=[], input_bits=input_bits, output_bits=output_bits, latency=0)


def build_right_program_edge_io(width: int, height: int, lanes: int) -> Program:
    """Edge-true right: expose only edge buses.
    Input:  west
    Output: east
    """
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    input_bits = {'west': [ {'type':'input','name':'west','bit':i} for i in range(lanes) ]}
    # Provide only 'east' as the output mirror
    output_bits = {
        'east': [ {'type':'input','name':'west','bit':i} for i in range(lanes) ],
    }
    return Program(width=width, height=height, cells=[], input_bits=input_bits, output_bits=output_bits, latency=0)


def main():
    ap = argparse.ArgumentParser(description='Generate left/right Programs for two-server Hello test (8-bit lanes).')
    ap.add_argument('--left', default='out/left_program.json', help='Path to write left Program JSON')
    ap.add_argument('--right', default='out/right_program.json', help='Path to write right Program JSON')
    ap.add_argument('--width', type=int, default=16)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--row', type=int, default=0)
    ap.add_argument('--len', type=int, default=10)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.left), exist_ok=True)
    os.makedirs(os.path.dirname(args.right), exist_ok=True)

    left = build_left_program(args.width, args.height, args.row, 8, args.len)
    right = build_right_program(max(8, args.width//2)*2, args.height, 8)
    left.save(args.left)
    right.save(args.right)
    print(f'Wrote {args.left} and {args.right}')


if __name__ == '__main__':
    main()
