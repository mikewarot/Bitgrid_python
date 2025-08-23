from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
from typing import Dict, Tuple, Optional, IO

from ..protocol import (
    try_parse_frame,
    MsgType,
    decode_name_u64_map,
    parse_link_payload,
)


MTYPE_NAMES = {v: k for k, v in MsgType.__dict__.items() if not k.startswith('__') and isinstance(v, int)}


def _parse_load_chunk_payload(payload: bytes) -> Tuple[int, int, int, int]:
    import struct
    if len(payload) < 12:
        raise ValueError('LOAD_CHUNK payload too short')
    session_id, total_bytes, offset, clen = struct.unpack('<HIIH', payload[:12])
    return session_id, total_bytes, offset, clen


def _parse_hello_payload(payload: bytes) -> Tuple[int, int, int, int]:
    import struct
    if len(payload) < 10:
        return 0, 0, 0, 0
    width, height, proto_version, features = struct.unpack('<HHHI', payload[:10])
    return width, height, proto_version, features


def _parse_step_payload(payload: bytes) -> int:
    import struct
    if len(payload) < 4:
        return 1
    return struct.unpack('<I', payload[:4])[0]


def _parse_error_payload(payload: bytes) -> Tuple[int, str]:
    import struct
    if len(payload) < 3:
        return 0, ''
    code, mlen = struct.unpack('<HB', payload[:3])
    msg = payload[3:3+mlen].decode('utf-8', errors='replace')
    return code, msg


def summarize_frame(frame: Dict) -> Dict:
    t = frame.get('type')
    payload = frame.get('payload', b'')
    summary: Dict[str, object] = {
        'dir': frame.get('dir'),
        'type': t,
        'type_name': MTYPE_NAMES.get(int(t) if isinstance(t, int) else -1, f"0x{(t if isinstance(t, int) else 0):02X}"),
        'flags': frame.get('flags'),
        'seq': frame.get('seq'),
        'length': frame.get('length'),
        'crc_ok': frame.get('crc_ok'),
    }
    try:
        if t == MsgType.HELLO:
            w, h, pv, feat = _parse_hello_payload(payload)
            summary['hello'] = {'width': w, 'height': h, 'proto_version': pv, 'features': feat}
        elif t == MsgType.LOAD_CHUNK:
            sid, total, off, clen = _parse_load_chunk_payload(payload)
            summary['load_chunk'] = {'session': sid, 'total': total, 'offset': off, 'chunk_len': clen}
        elif t == MsgType.APPLY:
            summary['apply'] = True
        elif t == MsgType.SET_INPUTS:
            m, _ = decode_name_u64_map(payload)
            summary['set_inputs'] = m
        elif t == MsgType.STEP:
            summary['step'] = {'cycles': _parse_step_payload(payload)}
        elif t == MsgType.GET_OUTPUTS:
            summary['get_outputs'] = True
        elif t == MsgType.OUTPUTS:
            m, _ = decode_name_u64_map(payload)
            summary['outputs'] = m
        elif t == MsgType.QUIT:
            summary['quit'] = True
        elif t == MsgType.SHUTDOWN:
            summary['shutdown'] = True
        elif t == MsgType.LINK:
            cfg = parse_link_payload(payload)
            summary['link'] = cfg
        elif t == MsgType.UNLINK:
            summary['unlink'] = True
        elif t == MsgType.LINK_ACK:
            import struct
            lanes = struct.unpack('<H', payload[:2])[0] if len(payload) >= 2 else 0
            summary['link_ack'] = {'lanes': lanes}
        elif t == MsgType.ERROR:
            code, msg = _parse_error_payload(payload)
            summary['error'] = {'code': code, 'msg': msg}
    except Exception as e:
        summary['parse_error'] = str(e)
    return summary


def dump_file(path: str, out: IO[str]) -> None:
    data = open(path, 'rb').read()
    buf = b''
    buf += data
    while True:
        frame, buf = try_parse_frame(buf)
        if frame is None:
            break
        frame['dir'] = 'file'
        out.write(json.dumps(summarize_frame(frame)) + "\n")
    if buf:
        out.write(json.dumps({'note': 'trailing_bytes', 'len': len(buf)}) + "\n")


def _forward_and_parse(src: socket.socket, dst: socket.socket, direction: str, out: IO[str], stop_event: threading.Event):
    buf = b''
    try:
        while not stop_event.is_set():
            data = src.recv(4096)
            if not data:
                break
            # Forward
            dst.sendall(data)
            # Parse
            buf += data
            while True:
                frame, buf = try_parse_frame(buf)
                if frame is None:
                    break
                frame['dir'] = direction
                out.write(json.dumps(summarize_frame(frame)) + "\n")
                out.flush()
    except Exception as e:
        out.write(json.dumps({'dir': direction, 'proxy_error': str(e)}) + "\n")
    finally:
        stop_event.set()
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def run_proxy(listen_host: str, listen_port: int, target_host: str, target_port: int, out: IO[str]):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as ls:
        ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        ls.bind((listen_host, listen_port))
        ls.listen(1)
        print(f'[dump] listening on {listen_host}:{listen_port} -> {target_host}:{target_port}')
        conn, addr = ls.accept()
        print(f'[dump] client connected: {addr}')
        with conn:
            with socket.create_connection((target_host, target_port), timeout=5.0) as upstream:
                print(f'[dump] connected to target: {target_host}:{target_port}')
                stop_event = threading.Event()
                t1 = threading.Thread(target=_forward_and_parse, args=(conn, upstream, 'c2s', out, stop_event), daemon=True)
                t2 = threading.Thread(target=_forward_and_parse, args=(upstream, conn, 's2c', out, stop_event), daemon=True)
                t1.start(); t2.start()
                # Wait until either side finishes
                t1.join(); t2.join()
        print('[dump] proxy session ended')


def main():
    ap = argparse.ArgumentParser(description='BGCF packet dumper: parse from file or run a TCP proxy that logs frames.')
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--file', help='Parse frames from a binary file and dump JSONL to stdout or --out')
    g.add_argument('--proxy', action='store_true', help='Run as a TCP proxy and dump frames in both directions')
    ap.add_argument('--listen-host', default='127.0.0.1')
    ap.add_argument('--listen-port', type=int, default=9001)
    ap.add_argument('--target-host', default='127.0.0.1')
    ap.add_argument('--target-port', type=int, default=9000)
    ap.add_argument('--out', help='Write JSONL logs to this file (default stdout)')
    args = ap.parse_args()

    out: IO[str]
    if args.out:
        out = open(args.out, 'w', encoding='utf-8')
    else:
        out = sys.stdout

    if args.file:
        dump_file(args.file, out)
    else:
        run_proxy(args.listen_host, args.listen_port, args.target_host, args.target_port, out)


if __name__ == '__main__':
    main()
