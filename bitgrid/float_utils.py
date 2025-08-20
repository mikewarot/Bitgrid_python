from __future__ import annotations

import struct


def pack_f32(x: float) -> int:
    return struct.unpack('<I', struct.pack('<f', float(x)))[0]


def unpack_f32(u: int) -> float:
    return struct.unpack('<f', struct.pack('<I', int(u) & 0xFFFFFFFF))[0]
