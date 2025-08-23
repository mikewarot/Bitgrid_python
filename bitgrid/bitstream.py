from __future__ import annotations

from typing import Dict, List, Tuple, Iterable, Optional, Any
import struct
import binascii
from .program import Program, Cell


DirOrder = ('N','E','S','W')  # output index order 0..3

# Bitstream header (little-endian) for cross-language interop
MAGIC = b'BGBS'  # BitGrid BitStream
VERSION = 1
HEADER_SIZE = 24  # bytes
ORDER_CODES = {'row-major': 0, 'col-major': 1, 'snake': 2}
ORDER_BY_CODE = {v: k for k, v in ORDER_CODES.items()}


def _cell_luts(cell: Cell) -> List[int]:
    p = cell.params or {}
    if 'luts' in p and isinstance(p['luts'], (list, tuple)):
        l = p['luts']
        return [int(l[0]) if len(l)>0 else 0,
                int(l[1]) if len(l)>1 else 0,
                int(l[2]) if len(l)>2 else 0,
                int(l[3]) if len(l)>3 else 0]
    if 'lut' in p:
        v = int(p.get('lut') or 0)
        return [v, 0, 0, 0]
    return [0, 0, 0, 0]


def _iter_cells_scan(program: Program, order: str = 'row-major') -> Iterable[Tuple[int,int,Cell]]:
    if order not in ('row-major','col-major','snake'):
        raise ValueError('order must be row-major|col-major|snake')
    W, H = program.width, program.height
    # Build lookup by (x,y)
    grid: Dict[Tuple[int,int], Cell] = {(c.x, c.y): c for c in program.cells}
    if order == 'row-major':
        for y in range(H):
            for x in range(W):
                yield x, y, grid.get((x,y)) or Cell(x=x, y=y, inputs=[], op='LUT', params={'luts':[0,0,0,0]})
    elif order == 'col-major':
        for x in range(W):
            for y in range(H):
                yield x, y, grid.get((x,y)) or Cell(x=x, y=y, inputs=[], op='LUT', params={'luts':[0,0,0,0]})
    else:  # snake (row snake)
        for y in range(H):
            xs = range(W) if (y % 2 == 0) else range(W-1, -1, -1)
            for x in xs:
                yield x, y, grid.get((x,y)) or Cell(x=x, y=y, inputs=[], op='LUT', params={'luts':[0,0,0,0]})


def pack_program_bitstream(program: Program, order: str = 'row-major') -> bytes:
    """
    Pack 4x16-bit LUTs per cell into a serial bitstream.
    Per cell order: outputs [N,E,S,W], each LUT 16 bits, LSB-first (index 0..15 matching emulator: idx=N|(E<<1)|(S<<2)|(W<<3)).
    Scan order: row-major (y=0..H-1, x=0..W-1) by default.
    Missing cells default to zero LUTs.
    """
    bits: List[int] = []
    for _x, _y, cell in _iter_cells_scan(program, order=order):
        l0, l1, l2, l3 = _cell_luts(cell)
        for lut in (l0, l1, l2, l3):
            for i in range(16):
                bits.append((lut >> i) & 1)
    # pack bits LSB-first per byte
    out = bytearray()
    cur = 0
    nb = 0
    for b in bits:
        cur |= (b & 1) << nb
        nb += 1
        if nb == 8:
            out.append(cur)
            cur = 0
            nb = 0
    if nb:
        out.append(cur)
    return bytes(out)


def has_bitstream_header(data: bytes) -> bool:
    return len(data) >= HEADER_SIZE and data[:4] == MAGIC


def parse_bitstream_header(data: bytes) -> Dict[str, Any]:
    """
    Parse and validate the fixed header. Returns a dict with fields and 'header_size'.
    Layout (< little-endian):
      0  : 4s  magic 'BGBS'
      4  : H   version (1)
      6  : H   header_size (24)
      8  : H   width
      10 : H   height
      12 : B   order (0=row,1=col,2=snake)
      13 : B   flags (bit0: 0=LSB-first LUT bits)
      14 : I   payload_bits (width*height*4*16)
      18 : I   payload_crc32 (IEEE, of payload bytes)
      22 : H   reserved (0)
    """
    if not has_bitstream_header(data):
        raise ValueError('missing or invalid bitstream magic header')
    if len(data) < HEADER_SIZE:
        raise ValueError('incomplete header')
    magic, ver, hsz, w, h, order_code, flags, payload_bits, payload_crc32, reserved = struct.unpack(
        '<4sHHHHBBIIH', data[:HEADER_SIZE]
    )
    if magic != MAGIC:
        raise ValueError('bad magic')
    if ver != VERSION:
        raise ValueError(f'unsupported version {ver}')
    if hsz != HEADER_SIZE:
        raise ValueError(f'unexpected header size {hsz}')
    if order_code not in ORDER_BY_CODE:
        raise ValueError(f'unknown order code {order_code}')
    order = ORDER_BY_CODE[order_code]
    return {
        'version': ver,
        'header_size': hsz,
        'width': w,
        'height': h,
        'order': order_code,
        'order_name': order,
        'flags': flags,
        'payload_bits': payload_bits,
        'payload_crc32': payload_crc32,
    }


def pack_program_bitstream_with_header(program: Program, order: str = 'row-major', flags: int = 0) -> bytes:
    if order not in ORDER_CODES:
        raise ValueError('order must be row-major|col-major|snake')
    payload = pack_program_bitstream(program, order=order)
    crc = binascii.crc32(payload) & 0xFFFFFFFF
    payload_bits = program.width * program.height * 4 * 16
    header = struct.pack(
        '<4sHHHHBBIIH',
        MAGIC,
        VERSION,
        HEADER_SIZE,
        program.width,
        program.height,
        ORDER_CODES[order],
        flags & 0xFF,
        payload_bits,
        crc,
        0,
    )
    return header + payload


def unpack_bitstream_with_header(data: bytes) -> Tuple[Dict[Tuple[int, int], List[int]], Dict[str, int]]:
    hdr = parse_bitstream_header(data)
    w = hdr['width']
    h = hdr['height']
    order = ORDER_BY_CODE[hdr['order']]
    payload = data[hdr['header_size']:]
    # Optional CRC check (only if payload length is at least the expected bytes)
    expected_bytes = (w * h * 4 * 16 + 7) // 8
    if len(payload) >= expected_bytes:
        crc = binascii.crc32(payload[:expected_bytes]) & 0xFFFFFFFF
        if crc != hdr['payload_crc32']:
            raise ValueError('payload CRC mismatch')
    luts = unpack_bitstream_to_luts(payload, w, h, order=order)
    return luts, hdr


def apply_bitstream_to_program(
    program: Program,
    data: bytes,
    order: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Apply a bitstream (headered or raw) to the given Program by updating per-cell LUTs.
    - If header is present, dims/order are taken from it and must match program dims.
    - If raw payload, dims default to provided width/height or program's dims, and order defaults to provided order or 'row-major'.
    Returns a small dict with metadata: {'used_header': bool, 'order': str, 'width': int, 'height': int}.
    """
    if has_bitstream_header(data):
        luts_by_cell, hdr = unpack_bitstream_with_header(data)
        w = int(hdr['width'])
        h = int(hdr['height'])
        ord_name = ORDER_BY_CODE[int(hdr['order'])]
        if (program.width, program.height) != (w, h):
            raise ValueError(f'bitstream dims {w}x{h} do not match program dims {program.width}x{program.height}')
        apply_luts_to_program(program, luts_by_cell)
        return {'used_header': True, 'order': ord_name, 'width': w, 'height': h}
    # Raw payload path
    w = int(width or program.width)
    h = int(height or program.height)
    if (program.width, program.height) != (w, h):
        raise ValueError(f'raw bitstream dims {w}x{h} do not match program dims {program.width}x{program.height}')
    ord_name = order or 'row-major'
    luts_by_cell = unpack_bitstream_to_luts(data, w, h, order=ord_name)
    apply_luts_to_program(program, luts_by_cell)
    return {'used_header': False, 'order': ord_name, 'width': w, 'height': h}


def unpack_bitstream_to_luts(bitstream: bytes, width: int, height: int, order: str = 'row-major') -> Dict[Tuple[int,int], List[int]]:
    """
    Inverse of pack: returns a map (x,y) -> [l0,l1,l2,l3].
    Does not modify wiring; use apply_luts_to_program to update an existing Program.
    """
    total_cells = width * height
    total_luts = total_cells * 4
    total_bits = total_luts * 16
    # Read bits LSB-first
    bits: List[int] = []
    for byte in bitstream:
        for i in range(8):
            bits.append((byte >> i) & 1)
            if len(bits) >= total_bits:
                break
        if len(bits) >= total_bits:
            break
    # Iterate cells
    luts_by_cell: Dict[Tuple[int,int], List[int]] = {}
    idx = 0
    # Build a scan list of coordinates only
    coords: List[Tuple[int,int]] = []
    dummy_prog = Program(width=width, height=height, cells=[], input_bits={}, output_bits={}, latency=0)
    for x, y, _ in _iter_cells_scan(dummy_prog, order=order):
        coords.append((x,y))
    for (x,y) in coords:
        cell_luts: List[int] = []
        for _k in range(4):
            v = 0
            for i in range(16):
                if idx < len(bits) and bits[idx]:
                    v |= (1 << i)
                idx += 1
            cell_luts.append(v)
        luts_by_cell[(x,y)] = cell_luts
    return luts_by_cell


def apply_luts_to_program(program: Program, luts_by_cell: Dict[Tuple[int,int], List[int]]) -> Program:
    m = {(c.x, c.y): c for c in program.cells}
    for (x,y), luts in luts_by_cell.items():
        c = m.get((x,y))
        if not c:
            # Create a LUT cell placeholder if not present
            program.cells.append(Cell(x=x, y=y, inputs=[], op='LUT', params={'luts': [int(l) for l in luts]}))
        else:
            p = c.params or {}
            p['luts'] = [int(l) for l in luts]
            c.params = p
    return program
