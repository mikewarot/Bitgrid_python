from __future__ import annotations

from typing import List, Dict
from ..program import Program, Cell
from ..router import route_luts


def build_identity_program(width: int, height: int, lanes: int = 9, row0: int = 0) -> Program:
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if row0 < 0 or (row0 + lanes - 1) >= height:
        raise ValueError('Row range out of bounds for lanes.')
    # Zero-latency identity for test: directly mirror west -> east via I/O mapping
    cells: List[Cell] = []
    input_bits: Dict[str, List[Dict]] = {
        'west': [ {'type':'input','name':'west','bit':i} for i in range(lanes) ]
    }
    output_bits: Dict[str, List[Dict]] = {
        'east': [ {'type':'input','name':'west','bit':i} for i in range(lanes) ]
    }
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def build_identity_program_edges(width: int, height: int, src: str, dst: str, lanes: int = 9) -> Program:
    """Build a zero-latency identity mapping from input bus 'src' to output bus 'dst'."""
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    cells: List[Cell] = []
    input_bits = {src: [ {'type':'input','name':src,'bit':i} for i in range(lanes) ]}
    output_bits = {dst: [ {'type':'input','name':src,'bit':i} for i in range(lanes) ]}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def build_identity_program_4way(width: int, height: int, lanes: int = 9) -> Program:
    """Zero-latency identity for all four edges: each output mirrors the same-named input."""
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    cells: List[Cell] = []
    input_bits = {
        'west':  [ {'type':'input','name':'west','bit':i}  for i in range(lanes) ],
        'east':  [ {'type':'input','name':'east','bit':i}  for i in range(lanes) ],
        'north': [ {'type':'input','name':'north','bit':i} for i in range(lanes) ],
        'south': [ {'type':'input','name':'south','bit':i} for i in range(lanes) ],
    }
    output_bits = {
        'east':  [ {'type':'input','name':'east','bit':i}  for i in range(lanes) ],
        'west':  [ {'type':'input','name':'west','bit':i}  for i in range(lanes) ],
        'south': [ {'type':'input','name':'south','bit':i} for i in range(lanes) ],
        'north': [ {'type':'input','name':'north','bit':i} for i in range(lanes) ],
    }
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def build_edge_mirror(width: int, height: int, edge: str, lanes: int = 9) -> Program:
    """Zero-latency identity for a single edge: output[edge] mirrors input[edge]."""
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    edge = str(edge)
    cells: List[Cell] = []
    input_bits = {edge: [ {'type':'input','name':edge,'bit':i} for i in range(lanes) ]}
    output_bits = {edge: [ {'type':'input','name':edge,'bit':i} for i in range(lanes) ]}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def build_inout_program(width: int, height: int, lanes: int = 9) -> Program:
    """Zero-latency program with 8 channel names: *_in and *_out for N/E/S/W.
    Each output mirrors the identically named input, so tests can both drive and observe per channel.
    Channels: west_in, east_in, north_in, south_in, west_out, east_out, north_out, south_out
    """
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    cells: List[Cell] = []
    names = ['west_in','east_in','north_in','south_in','west_out','east_out','north_out','south_out']
    input_bits = { name: [ {'type':'input','name':name,'bit':i} for i in range(lanes) ] for name in names }
    output_bits = { name: [ {'type':'input','name':name,'bit':i} for i in range(lanes) ] for name in names }
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def main():
    import argparse, os
    ap = argparse.ArgumentParser(description='Generate identity pass-through Program with 9-bit west->east rows (includes present flag).')
    ap.add_argument('--out', default='out/identity_program.json')
    ap.add_argument('--width', type=int, default=16)
    ap.add_argument('--height', type=int, default=10)
    ap.add_argument('--lanes', type=int, default=9)
    ap.add_argument('--row', type=int, default=0)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    prog = build_identity_program(args.width, args.height, args.lanes, args.row)
    prog.save(args.out)
    print(f'Wrote {args.out}')


if __name__ == '__main__':
    main()
