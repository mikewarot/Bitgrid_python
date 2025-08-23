from __future__ import annotations

import struct
import binascii
from typing import Tuple, List, Dict, Any, Optional

# Transport-agnostic control frame for runtime protocol
# Header (little-endian):
#   0  : 4s magic 'BGCF'
#   4  : B  version (1)
#   5  : B  msg_type
#   6  : B  flags
#   7  : B  reserved
#   8  : H  seq
#   10 : H  length (payload bytes)
#   12 : I  crc32 (of header fields 4..11 + payload)
#   16 : payload...

MAGIC = b'BGCF'
VERSION = 1
HDR_FMT = '<4sBBBBHHI'
HDR_SIZE = struct.calcsize(HDR_FMT)


class MsgType:
    HELLO = 0x01        # device->host or host->device (request/response)
    LOAD_CHUNK = 0x02   # host->device (bitstream chunk)
    APPLY = 0x03        # host->device (apply loaded bitstream)
    STEP = 0x04         # host->device (advance cycles)
    SET_INPUTS = 0x05   # host->device (TLV string->u64)
    GET_OUTPUTS = 0x06  # host->device (request outputs)
    OUTPUTS = 0x07      # device->host (TLV string->u64)
    QUIT = 0x08         # host->device (close current connection)
    SHUTDOWN = 0x09     # host->device (stop listener and exit server)
    LINK = 0x0A         # host->device (establish inter-server link)
    UNLINK = 0x0B       # host->device (tear down inter-server link)
    LINK_ACK = 0x0C     # device->host (link established ok)
    ERROR = 0x7F        # device->host error


def _crc(data: bytes) -> int:
    return binascii.crc32(data) & 0xFFFFFFFF


def pack_frame(msg_type: int, payload: bytes = b'', seq: int = 0, flags: int = 0) -> bytes:
    if not (0 <= seq <= 0xFFFF):
        raise ValueError('seq out of range')
    if not (0 <= flags <= 0xFF):
        raise ValueError('flags out of range')
    length = len(payload)
    # Build header with placeholder CRC
    hdr_wo_crc = struct.pack('<BBBBHH', VERSION, msg_type & 0xFF, flags & 0xFF, 0, seq & 0xFFFF, length & 0xFFFF)
    crc = _crc(hdr_wo_crc + payload)
    header = struct.pack(HDR_FMT, MAGIC, VERSION, msg_type & 0xFF, flags & 0xFF, 0, seq & 0xFFFF, length & 0xFFFF, crc)
    return header + payload


def try_parse_frame(buffer: bytes) -> Tuple[Optional[Dict[str, Any]], bytes]:
    """
    Try to parse one frame from buffer. Returns (frame_dict_or_None, remaining_bytes).
    frame_dict: {'version','type','flags','seq','payload','crc_ok'}
    If not enough data, returns (None, buffer).
    If bad magic, drops one byte and retries (resync).
    """
    buf = buffer
    while True:
        if len(buf) < HDR_SIZE:
            return None, buf
        if buf[:4] != MAGIC:
            # resync: drop first byte
            buf = buf[1:]
            continue
        magic, ver, mtype, flags, _res, seq, length, crc = struct.unpack(HDR_FMT, buf[:HDR_SIZE])
        if ver != VERSION:
            # unsupported version; drop magic and continue
            buf = buf[4:]
            continue
        total = HDR_SIZE + length
        if len(buf) < total:
            return None, buf
        payload = buf[HDR_SIZE:total]
        hdr_wo_crc = struct.pack('<BBBBHH', ver, mtype, flags, 0, seq, length)
        crc_calc = _crc(hdr_wo_crc + payload)
        frame = {
            'version': ver,
            'type': mtype,
            'flags': flags,
            'seq': seq,
            'payload': payload,
            'crc_ok': (crc_calc == crc),
        }
        return frame, buf[total:]


# Simple TLV helpers for name->u64 maps (UTF-8 names up to 255 bytes)
def encode_name_u64_map(d: Dict[str, int]) -> bytes:
    parts: List[bytes] = []
    parts.append(struct.pack('<H', len(d)))
    for name, val in d.items():
        nb = name.encode('utf-8')[:255]
        parts.append(struct.pack('<B', len(nb)))
        parts.append(nb)
        parts.append(struct.pack('<Q', int(val) & 0xFFFFFFFFFFFFFFFF))
    return b''.join(parts)


def decode_name_u64_map(b: bytes) -> Tuple[Dict[str, int], bytes]:
    if len(b) < 2:
        return {}, b
    n = struct.unpack('<H', b[:2])[0]
    off = 2
    out: Dict[str, int] = {}
    for _ in range(n):
        if off >= len(b):
            break
        ln = b[off]
        off += 1
        name = b[off:off+ln].decode('utf-8', errors='ignore')
        off += ln
        if off + 8 > len(b):
            break
        val = struct.unpack('<Q', b[off:off+8])[0]
        off += 8
        out[name] = val
    return out, b[off:]


# Payload helpers for common messages
def payload_hello(grid_w: int, grid_h: int, proto_version: int = VERSION, features: int = 0) -> bytes:
    return struct.pack('<HHHI', grid_w & 0xFFFF, grid_h & 0xFFFF, proto_version & 0xFFFF, features & 0xFFFFFFFF)


def payload_load_chunk(session_id: int, total_bytes: int, offset: int, chunk: bytes) -> bytes:
    return struct.pack('<HIIH', session_id & 0xFFFF, total_bytes & 0xFFFFFFFF, offset & 0xFFFFFFFF, len(chunk) & 0xFFFF) + chunk


def payload_step(cycles: int) -> bytes:
    return struct.pack('<I', cycles & 0xFFFFFFFF)


def payload_error(code: int, msg: str = '') -> bytes:
    b = msg.encode('utf-8')[:255]
    return struct.pack('<HB', code & 0xFFFF, len(b)) + b


# Inter-server link payload helpers
# Layout (< little-endian):
#   u8 dir_code (0=N,1=E,2=S,3=W)
#   u8 reserved
#   u16 local_out_len, bytes local_out_name (UTF-8)
#   u16 remote_in_len, bytes remote_in_name (UTF-8)
#   u16 host_len, bytes host (ASCII/UTF-8)
#   u16 port
#   u16 lanes (0 = auto)

def payload_link(dir_code: int, local_out: str, remote_in: str, host: str, port: int, lanes: int = 0) -> bytes:
    lo = local_out.encode('utf-8')
    ri = remote_in.encode('utf-8')
    hh = host.encode('utf-8')
    parts = [struct.pack('<BB', dir_code & 0xFF, 0)]
    parts.append(struct.pack('<H', len(lo))); parts.append(lo)
    parts.append(struct.pack('<H', len(ri))); parts.append(ri)
    parts.append(struct.pack('<H', len(hh))); parts.append(hh)
    parts.append(struct.pack('<HH', int(port) & 0xFFFF, int(lanes) & 0xFFFF))
    return b''.join(parts)


def parse_link_payload(b: bytes) -> Dict[str, Any]:
    if len(b) < 2:
        raise ValueError('link payload too short')
    dir_code = b[0]
    _res = b[1]
    off = 2
    def read_str() -> str:
        nonlocal off
        if off + 2 > len(b):
            raise ValueError('link payload truncated')
        ln = struct.unpack('<H', b[off:off+2])[0]
        off += 2
        s = b[off:off+ln].decode('utf-8', errors='ignore')
        off += ln
        return s
    local_out = read_str()
    remote_in = read_str()
    host = read_str()
    if off + 4 > len(b):
        raise ValueError('link payload truncated (port/lanes)')
    port, lanes = struct.unpack('<HH', b[off:off+4])
    return {
        'dir_code': dir_code,
        'local_out': local_out,
        'remote_in': remote_in,
        'host': host,
        'port': port,
        'lanes': lanes,
    }


def payload_link_ack(lanes: int) -> bytes:
    # Minimal ACK payload: u16 lanes accepted
    return struct.pack('<H', int(lanes) & 0xFFFF)
