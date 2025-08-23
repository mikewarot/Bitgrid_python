from __future__ import annotations

import argparse
import socket
from typing import Dict
from ..protocol import (
    pack_frame,
    try_parse_frame,
    MsgType,
    encode_name_u64_map,
    decode_name_u64_map,
    payload_hello,
    payload_link,
)


def send_and_recv(sock: socket.socket, frame: bytes, timeout: float = 2.0):
    sock.sendall(frame)
    sock.settimeout(timeout)
    buf = b''
    while True:
        frame_parsed, buf = try_parse_frame(buf)
        if frame_parsed is not None:
            return frame_parsed
        try:
            data = sock.recv(4096)
        except socket.timeout:
            return None
        if not data:
            return None
        buf += data


def do_hello(sock: socket.socket) -> Dict:
    f = pack_frame(MsgType.HELLO, payload_hello(0, 0))
    resp = send_and_recv(sock, f)
    return resp or {}


def do_load(sock: socket.socket, path: str, session_id: int = 1, chunk_size: int = 1024) -> bool:
    import os, struct
    data = open(path, 'rb').read()
    total = len(data)
    off = 0
    while off < total:
        chunk = data[off:off+chunk_size]
        payload = struct.pack('<HIIH', session_id & 0xFFFF, total, off, len(chunk)) + chunk
        sock.sendall(pack_frame(MsgType.LOAD_CHUNK, payload))
        off += len(chunk)
    # APPLY
    sock.sendall(pack_frame(MsgType.APPLY))
    return True


def do_set_inputs(sock: socket.socket, kv: Dict[str, int]):
    payload = encode_name_u64_map(kv)
    sock.sendall(pack_frame(MsgType.SET_INPUTS, payload))


def do_step(sock: socket.socket, cycles: int):
    import struct
    sock.sendall(pack_frame(MsgType.STEP, struct.pack('<I', int(cycles) & 0xFFFFFFFF)))


def do_get_outputs(sock: socket.socket, timeout: float = 2.0) -> Dict[str, int]:
    sock.sendall(pack_frame(MsgType.GET_OUTPUTS))
    resp = send_and_recv(sock, b'', timeout=timeout)
    if not resp or resp.get('type') != MsgType.OUTPUTS:
        return {}
    m, _ = decode_name_u64_map(resp['payload'])
    return m


def do_quit(sock: socket.socket):
    sock.sendall(pack_frame(MsgType.QUIT))


def do_shutdown(sock: socket.socket):
    sock.sendall(pack_frame(MsgType.SHUTDOWN))


def do_link(sock: socket.socket, dir_code: int, local_out: str, remote_in: str, host: str, port: int, lanes: int = 0):
    payload = payload_link(dir_code, local_out, remote_in, host, port, lanes)
    sock.sendall(pack_frame(MsgType.LINK, payload))
    # Await LINK_ACK or ERROR (optional best-effort)
    resp = send_and_recv(sock, b'', timeout=3.0)
    if not resp:
        print('LINK: no response')
        return
    t = resp.get('type')
    if t == MsgType.LINK_ACK:
        lanes_ack = 0
        pl = resp.get('payload', b'')
        if len(pl) >= 2:
            import struct
            lanes_ack = struct.unpack('<H', pl[:2])[0]
        print(f'LINK: ok (lanes={lanes_ack})')
    elif t == MsgType.ERROR:
        # Decode error message
        pl = resp.get('payload', b'')
        code = msg = None
        if len(pl) >= 3:
            import struct
            code, mlen = struct.unpack('<HB', pl[:3])
            msg = pl[3:3+mlen].decode('utf-8', errors='replace')
        print(f'LINK: error code={code} msg={msg}')
    else:
        print(f'LINK: unexpected response type={t}')


def do_unlink(sock: socket.socket):
    sock.sendall(pack_frame(MsgType.UNLINK))


def main():
    ap = argparse.ArgumentParser(description='Simple BGCF TCP client for the BitGrid server')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=9000)
    ap.add_argument('--hello', action='store_true', help='Send HELLO and print reply')
    ap.add_argument('--load', dest='bitstream', help='Load and apply a bitstream file (headered or raw)')
    ap.add_argument('--set', dest='set_inputs', help='Comma-separated name=value inputs (u64), e.g., a=1,b=2')
    ap.add_argument('--step', dest='cycles', type=int, help='Advance cycles (with current inputs)')
    ap.add_argument('--get', dest='get_outputs', action='store_true', help='Fetch outputs and print')
    ap.add_argument('--quit', action='store_true', help='Send QUIT to stop the server connection')
    ap.add_argument('--shutdown', action='store_true', help='Send SHUTDOWN to stop the server listener')
    ap.add_argument('--link', metavar='DIR,LO,RI,HOST,PORT[,LANES]', help='Establish inter-server link. DIR=N|E|S|W numeric (0-3) or letter; LO=local_out, RI=remote_in')
    ap.add_argument('--unlink', action='store_true', help='Tear down inter-server link')
    args = ap.parse_args()

    with socket.create_connection((args.host, args.port), timeout=2.0) as sock:
        if args.hello:
            resp = do_hello(sock)
            print('HELLO reply:', resp)
        if args.bitstream:
            ok = do_load(sock, args.bitstream)
            print('LOAD/APPLY:', 'ok' if ok else 'failed')
        if args.set_inputs:
            kv: Dict[str, int] = {}
            for pair in args.set_inputs.split(','):
                if not pair.strip():
                    continue
                if '=' not in pair:
                    continue
                k, v = pair.split('=', 1)
                kv[k.strip()] = int(v.strip(), 0)
            do_set_inputs(sock, kv)
        if args.cycles is not None:
            do_step(sock, args.cycles)
        if args.get_outputs:
            outs = do_get_outputs(sock)
            print('OUTPUTS:', outs)
        if args.quit:
            do_quit(sock)
        if args.shutdown:
            do_shutdown(sock)
        if args.link:
            # Parse DIR,LO,RI,HOST,PORT[,LANES]
            parts = [p.strip() for p in args.link.split(',')]
            if len(parts) < 5:
                print('invalid --link; expected DIR,LO,RI,HOST,PORT[,LANES]')
            else:
                dir_s, lo, ri, h, p, *rest = parts
                if dir_s.isdigit():
                    dir_code = int(dir_s) & 0xFF
                else:
                    m = {'N':0,'E':1,'S':2,'W':3}
                    dir_code = m.get(dir_s.upper(), 1)
                lanes = int(rest[0], 0) if rest else 0
                do_link(sock, dir_code, lo, ri, h, int(p), lanes)
        if args.unlink:
            do_unlink(sock)


if __name__ == '__main__':
    main()
