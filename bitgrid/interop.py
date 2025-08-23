from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Protocol


@dataclass
class EdgeFrame:
    """Bit-packed frame of edge outputs for one emulator cycle (both phases when cps=2).

    Layout order (LSB-first per lane):
      north: width bits
      east:  height bits
      south: width bits
      west:  height bits
    """
    north: List[int]
    east: List[int]
    south: List[int]
    west: List[int]

    def pack_bits(self) -> bytes:
        bits: List[int] = []
        bits.extend(self.north)
        bits.extend(self.east)
        bits.extend(self.south)
        bits.extend(self.west)
        # pack into bytes, LSB-first
        out = bytearray()
        cur = 0
        nb = 0
        for b in bits:
            cur |= ((b & 1) << nb)
            nb += 1
            if nb == 8:
                out.append(cur)
                cur = 0
                nb = 0
        if nb:
            out.append(cur)
        return bytes(out)

    @staticmethod
    def unpack_bits(data: bytes, width: int, height: int) -> "EdgeFrame":
        total = width + height + width + height
        bits: List[int] = []
        for byte in data:
            for i in range(8):
                bits.append((byte >> i) & 1)
                if len(bits) >= total:
                    break
            if len(bits) >= total:
                break
        n = bits[:width]
        e = bits[width:width+height]
        s = bits[width+height:width+height+width]
        w = bits[width+height+width:width+height+width+height]
        return EdgeFrame(north=n, east=e, south=s, west=w)


@dataclass
class EdgeHeader:
    epoch: int  # non-negative, wraps by consumer policy
    phase: str  # 'A' or 'B'

    def pack(self) -> bytes:
        # 3 bytes: epoch low 16 bits, and phase in bit0 of third byte
        e16 = self.epoch & 0xFFFF
        b0 = e16 & 0xFF
        b1 = (e16 >> 8) & 0xFF
        b2 = 0x01 if (self.phase == 'B') else 0x00
        return bytes([b0, b1, b2])

    @staticmethod
    def unpack(data: bytes) -> "EdgeHeader":
        if len(data) < 3:
            raise ValueError("header too short")
        e16 = data[0] | (data[1] << 8)
        phase = 'B' if (data[2] & 0x01) else 'A'
        return EdgeHeader(epoch=e16, phase=phase)


class LinkEndpoint(Protocol):
    def send(self, data: bytes) -> None: ...
    def recv(self, n: int) -> bytes: ...


def crc8(data: bytes, poly: int = 0x07) -> int:
    c = 0
    for b in data:
        c ^= b
        for _ in range(8):
            if c & 1:
                c = (c >> 1) ^ (poly << 7)
            else:
                c >>= 1
        c &= 0xFF
    return c


def make_frame_tx(frame: EdgeFrame, with_crc: bool = True) -> bytes:
    payload = frame.pack_bits()
    if with_crc:
        return payload + bytes([crc8(payload)])
    return payload


def parse_frame_rx(data: bytes, width: int, height: int, with_crc: bool = True) -> EdgeFrame | None:
    if with_crc:
        if not data:
            return None
        body, rx = data[:-1], data[-1]
        if crc8(body) != rx:
            return None
        return EdgeFrame.unpack_bits(body, width, height)
    return EdgeFrame.unpack_bits(data, width, height)


def make_framed_tx(header: EdgeHeader, frame: EdgeFrame, with_crc: bool = True) -> bytes:
    payload = header.pack() + frame.pack_bits()
    if with_crc:
        return payload + bytes([crc8(payload)])
    return payload


def parse_framed_rx(data: bytes, width: int, height: int, with_crc: bool = True) -> Tuple[EdgeHeader, EdgeFrame] | None:
    if with_crc:
        if not data:
            return None
        body, rx = data[:-1], data[-1]
        if crc8(body) != rx:
            return None
        hdr = EdgeHeader.unpack(body[:3])
        fr = EdgeFrame.unpack_bits(body[3:], width, height)
        return (hdr, fr)
    hdr = EdgeHeader.unpack(data[:3])
    fr = EdgeFrame.unpack_bits(data[3:], width, height)
    return (hdr, fr)
