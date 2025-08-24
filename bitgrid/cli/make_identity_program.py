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
        'west': [ {'type':'input','name':'west','bit':i, 'x': 0, 'y': row0 + i} for i in range(lanes) ]
    }
    output_bits: Dict[str, List[Dict]] = {
        'east': [ {'type':'input','name':'west','bit':i, 'x': width-1, 'y': row0 + i} for i in range(lanes) ]
    }
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def build_identity_program_edges(width: int, height: int, src: str, dst: str, lanes: int = 9) -> Program:
    """Build a zero-latency identity mapping from input bus 'src' to output bus 'dst'."""
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    cells: List[Cell] = []
    def edge_xy(edge: str, i: int) -> Dict[str,int]:
        e = edge.lower()
        if e == 'west':
            return {'x': 0, 'y': i}
        if e == 'east':
            return {'x': width-1, 'y': i}
        if e == 'north':
            return {'x': i, 'y': 0}
        if e == 'south':
            return {'x': i, 'y': height-1}
        return {}
    input_bits = {src: [ dict({'type':'input','name':src,'bit':i}, **edge_xy(src, i)) for i in range(lanes) ]}
    output_bits = {dst: [ dict({'type':'input','name':src,'bit':i}, **edge_xy(dst, i)) for i in range(lanes) ]}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=0)


def build_identity_program_4way(width: int, height: int, lanes: int = 9) -> Program:
    """Zero-latency identity for all four edges: each output mirrors the same-named input."""
    if width % 2 or height % 2:
        raise ValueError('Grid width and height must be even.')
    if lanes <= 0:
        raise ValueError('lanes must be > 0')
    cells: List[Cell] = []
    input_bits = {
        'west':  [ {'type':'input','name':'west','bit':i,  'x':0,        'y':i}  for i in range(lanes) ],
        'east':  [ {'type':'input','name':'east','bit':i,  'x':width-1,  'y':i}  for i in range(lanes) ],
        'north': [ {'type':'input','name':'north','bit':i, 'x':i,        'y':0}  for i in range(lanes) ],
        'south': [ {'type':'input','name':'south','bit':i, 'x':i,        'y':height-1} for i in range(lanes) ],
    }
    output_bits = {
        'east':  [ {'type':'input','name':'east','bit':i,  'x':width-1,  'y':i}  for i in range(lanes) ],
        'west':  [ {'type':'input','name':'west','bit':i,  'x':0,        'y':i}  for i in range(lanes) ],
        'south': [ {'type':'input','name':'south','bit':i, 'x':i,        'y':height-1} for i in range(lanes) ],
        'north': [ {'type':'input','name':'north','bit':i, 'x':i,        'y':0}  for i in range(lanes) ],
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
    def edge_xy(edge: str, i: int) -> Dict[str,int]:
        e = edge.lower()
        if e == 'west':
            return {'x': 0, 'y': i}
        if e == 'east':
            return {'x': width-1, 'y': i}
        if e == 'north':
            return {'x': i, 'y': 0}
        if e == 'south':
            return {'x': i, 'y': height-1}
        return {}
    input_bits = {edge: [ dict({'type':'input','name':edge,'bit':i}, **edge_xy(edge, i)) for i in range(lanes) ]}
    output_bits = {edge: [ dict({'type':'input','name':edge,'bit':i}, **edge_xy(edge, i)) for i in range(lanes) ]}
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
    def coords(name: str, i: int) -> Dict[str,int]:
        n = name.lower()
        if n.startswith('west'):
            return {'x': 0, 'y': i}
        if n.startswith('east'):
            return {'x': width-1, 'y': i}
        if n.startswith('north'):
            return {'x': i, 'y': 0}
        if n.startswith('south'):
            return {'x': i, 'y': height-1}
        return {}
    input_bits = { name: [ dict({'type':'input','name':name,'bit':i}, **coords(name, i)) for i in range(lanes) ] for name in names }
    # Default same-name mirror, then override with cross-edge wiring
    output_bits = { name: [ {'type':'input','name':name,'bit':i} for i in range(lanes) ] for name in names }
    # Outward paths (send across to the opposite seam):
    # Drive each *_out from the opposite side's *_in, so e.g. west_in -> east_out
    output_bits['east_out'] = [ dict({'type':'input','name':'west_in','bit':i}, **coords('east_out', i)) for i in range(lanes) ]
    output_bits['west_out'] = [ dict({'type':'input','name':'east_in','bit':i}, **coords('west_out', i)) for i in range(lanes) ]
    output_bits['south_out'] = [ dict({'type':'input','name':'north_in','bit':i}, **coords('south_out', i)) for i in range(lanes) ]
    output_bits['north_out'] = [ dict({'type':'input','name':'south_in','bit':i}, **coords('north_out', i)) for i in range(lanes) ]
    # Inward observation paths: west_in -> east_in, east_in -> west_in, north_in -> south_in, south_in -> north_in
    output_bits['east_in'] = [ dict({'type':'input','name':'west_in','bit':i}, **coords('east_in', i)) for i in range(lanes) ]
    output_bits['west_in'] = [ dict({'type':'input','name':'east_in','bit':i}, **coords('west_in', i)) for i in range(lanes) ]
    output_bits['south_in'] = [ dict({'type':'input','name':'north_in','bit':i}, **coords('south_in', i)) for i in range(lanes) ]
    output_bits['north_in'] = [ dict({'type':'input','name':'south_in','bit':i}, **coords('north_in', i)) for i in range(lanes) ]
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
