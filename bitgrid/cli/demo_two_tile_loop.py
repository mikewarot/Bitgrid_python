from __future__ import annotations

import argparse
from typing import Dict, List
from ..program import Program, Cell
from ..emulator import Emulator
from ..router import route_luts
from ..interop import EdgeHeader, EdgeFrame, make_framed_tx, parse_framed_rx
from ..barrier import NeighborBarrier
from ..trace import TraceLogger, TraceEvent


DIR_IDX = {'N': 0, 'E': 1, 'S': 2, 'W': 3}


def build_left_tile(width: int, height: int, lanes: int) -> Program:
    # Lanes mapped top-to-bottom on Y = 0..lanes-1; export on East edge from x=width-1
    cells: List[Cell] = []
    for y in range(lanes):
        x = width - 1
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        # Drive West pin from input 'a[y]'
        inputs[DIR_IDX['W']] = {"type": "input", "name": "a", "bit": y}
        luts = route_luts('E', 'W')
        cells.append(Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts}))
    input_bits = {"a": [{"type": "input", "name": "a", "bit": b} for b in range(lanes)]}
    output_bits: Dict[str, List[Dict]] = {}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=width + height)


def build_right_tile(width: int, height: int, lanes: int) -> Program:
    # Lanes mapped top-to-bottom on Y = 0..lanes-1; import on West edge as input 'west', expose output 'out' from E pin
    cells: List[Cell] = []
    out_bits: List[Dict] = []
    for y in range(lanes):
        x = 0
        inputs = [{"type": "const", "value": 0} for _ in range(4)]
        inputs[DIR_IDX['W']] = {"type": "input", "name": "west", "bit": y}
        luts = route_luts('E', 'W')
        c = Cell(x=x, y=y, inputs=inputs, op='ROUTE4', params={'luts': luts})
        cells.append(c)
        out_bits.append({"type": "cell", "x": x, "y": y, "out": DIR_IDX['E']})
    input_bits = {"west": [{"type": "input", "name": "west", "bit": b} for b in range(lanes)]}
    output_bits = {"out": out_bits}
    return Program(width=width, height=height, cells=cells, input_bits=input_bits, output_bits=output_bits, latency=width + height)


def edge_east_frame(width: int, height: int, emu: Emulator) -> List[int]:
    # Return east edge lanes top-to-bottom (len = height)
    lanes: List[int] = []
    x = emu.p.width - 1
    for y in range(height):
        lanes.append(emu.cell_out.get((x, y), [0, 0, 0, 0])[DIR_IDX['E']] & 1)
    return lanes


def main():
    ap = argparse.ArgumentParser(description='Two-tile loopback demo: left exports east lanes from input a; right receives west lanes and exposes out')
    ap.add_argument('--width', type=int, default=8)
    ap.add_argument('--height', type=int, default=8)
    ap.add_argument('--lanes', type=int, default=8, help='number of vertical lanes (<= height)')
    ap.add_argument('--steps', type=str, default='1,3,5,170', help='comma-separated input values for a (0..255)')
    ap.add_argument('--trace', type=str, default='', help='path to write trace logs (jsonl or csv)')
    ap.add_argument('--trace-format', type=str, default='jsonl', choices=['jsonl','csv'], help='trace file format')
    ap.add_argument('--fault-type', type=str, default='', choices=['','drop','crc','epoch','phase','duplicate'], help='inject a transport fault on the L→R seam')
    ap.add_argument('--fault-epoch', type=int, default=-1, help='epoch to inject the fault')
    ap.add_argument('--fault-phase', type=str, default='', choices=['','A','B'], help='phase to inject the fault')
    args = ap.parse_args()

    W, H, L = args.width, args.height, args.lanes
    if W % 2 or H % 2:
        raise SystemExit('Width and height must be even')
    if L > H:
        raise SystemExit('lanes must be <= height')

    left = Emulator(build_left_tile(W, H, L))
    right = Emulator(build_right_tile(W, H, L))

    # Simple per-seam 2-phase barriers (each tile has only one neighbor in this demo)
    def on_barrier(event: str, payload: dict):
        if not tracer:
            return
        tracer.log(TraceEvent(
            kind=event,
            tile='demo2',
            side=payload.get('dir'),
            epoch=payload.get('epoch', -1),
            phase=payload.get('phase', None),
            lanes=None,
            indices=None,
            value=payload.get('status', 'ok')
        ))
    b_left = NeighborBarrier(expect_north=False, expect_east=True, expect_south=False, expect_west=False, on_event=on_barrier)
    b_right = NeighborBarrier(expect_north=False, expect_east=False, expect_south=False, expect_west=True, on_event=on_barrier)

    # Parse inputs for left
    seq = [int(tok.strip(), 0) & ((1 << L) - 1) for tok in args.steps.split(',') if tok.strip()]
    # Receiver buffers split by parity (even lanes consumed at A, odd lanes at B)
    buf_even = [0] * L
    buf_odd = [0] * L
    even_mask = sum([1 << i for i in range(L) if (i % 2 == 0)])
    odd_mask = sum([1 << i for i in range(L) if (i % 2 == 1)])

    # For east edge, lanes freshly computed this phase on the left are:
    # phase A: y where (W-1 + y) % 2 == 0  -> since W even, W-1 odd => y odd
    # phase B: y where (W-1 + y) % 2 == 1  -> y even
    def east_indices_fresh(phase: str) -> List[int]:
        if phase == 'A':
            return [i for i in range(L) if (i % 2 == 1)]
        return [i for i in range(L) if (i % 2 == 0)]

    # Capture partial outputs for recombination: even half at A (epoch e), odd half at B (epoch e)
    even_out_by_epoch: Dict[int, int] = {}
    odd_out_by_epoch: Dict[int, int] = {}

    tracer = None
    if args.trace:
        tracer = TraceLogger(args.trace, fmt=args.trace_format)

    def should_fault(epoch: int, phase: str) -> bool:
        return (args.fault_type and args.fault_epoch == epoch and args.fault_phase == phase)

    def inject_fault(epoch: int, phase: str, hdr: EdgeHeader, frame: EdgeFrame, blob: bytes) -> tuple[EdgeHeader, EdgeFrame, bytes, str]:
        kind = args.fault_type
        note = kind
        if kind == 'drop':
            return (hdr, frame, b'', note)
        if kind == 'crc':
            if not blob:
                blob = make_framed_tx(hdr, frame, with_crc=True)
            # Flip CRC byte
            bad = blob[:-1] + bytes([blob[-1] ^ 0xFF])
            return (hdr, frame, bad, note)
        if kind == 'epoch':
            bad_hdr = EdgeHeader(epoch=hdr.epoch + 1, phase=hdr.phase)
            bad_blob = make_framed_tx(bad_hdr, frame, with_crc=True)
            return (bad_hdr, frame, bad_blob, note)
        if kind == 'phase':
            bad_hdr = EdgeHeader(epoch=hdr.epoch, phase=('B' if hdr.phase == 'A' else 'A'))
            bad_blob = make_framed_tx(bad_hdr, frame, with_crc=True)
            return (bad_hdr, frame, bad_blob, note)
        if kind == 'duplicate':
            # Send normal once; caller will parse twice
            if not blob:
                blob = make_framed_tx(hdr, frame, with_crc=True)
            return (hdr, frame, blob, note)
        return (hdr, frame, blob, '')

    print(f"lanes={L} (top=bit0) W={W} H={H}")
    for epoch, aval in enumerate(seq):
        # Build per-lane bits for left 'a'
        a_bits = aval
        # Phase A: left computes A
        left.run_stream([{"a": a_bits}], cycles_per_step=1, reset=(epoch == 0))
        east_after_a = edge_east_frame(W, H, left)
        # Send framed odd lanes with header (epoch, phase=A)
        hdrA = EdgeHeader(epoch=epoch, phase='A')
        frameA = EdgeFrame(north=[], east=[east_after_a[i] for i in range(L)], south=[], west=[0]*L)
        blobA = make_framed_tx(hdrA, frameA, with_crc=True)
        dupA = False
        if should_fault(epoch, 'A'):
            hdrA, frameA, blobA, note = inject_fault(epoch, 'A', hdrA, frameA, blobA)
            dupA = (args.fault_type == 'duplicate')
            if tracer:
                tracer.log(TraceEvent(kind='fault_injected', tile='L', side='E', epoch=epoch, phase='A', lanes=frameA.east, indices=east_indices_fresh('A'), value=None))
        if tracer:
            tracer.log(TraceEvent(kind='tx', tile='L', side='E', epoch=epoch, phase='A', lanes=frameA.east, indices=east_indices_fresh('A'), value=None))
        parsedA = parse_framed_rx(blobA, width=0, height=L, with_crc=True) if blobA else None
        if parsedA is not None:
            _hA, fA = parsedA
            for i in east_indices_fresh('A'):
                buf_odd[i] = (fA.east[i] & 1)
            if tracer:
                tracer.log(TraceEvent(kind='rx', tile='R', side='W', epoch=epoch, phase='A', lanes=fA.east, indices=east_indices_fresh('A'), value=None))
            # Use header to mark neighbor-done with validation
            b_right.mark_neighbor_header('W', _hA.epoch, _hA.phase)
            if dupA:
                # parse duplicate once more
                parsedA2 = parse_framed_rx(blobA, width=0, height=L, with_crc=True)
                if parsedA2 is not None:
                    _hA2, _ = parsedA2
                    b_right.mark_neighbor_header('W', _hA2.epoch, _hA2.phase)
        # Mark barriers done for A and advance
        b_left.local_done()
        b_right.local_done(); b_left.mark_neighbor_done('E', epoch, 'A')
        b_left.advance(); b_right.advance()
        # Right consumes even lanes at A using buf_even
        west_val_A = sum([(buf_even[i] & 1) << i for i in range(L)])
        ra = right.run_stream([{"west": west_val_A}], cycles_per_step=1, reset=(epoch == 0))[-1]
        even_out_by_epoch[epoch] = ra.get('out', 0) & even_mask

        # Phase B: left computes B
        left.run_stream([{"a": a_bits}], cycles_per_step=1, reset=False)
        east_after_b = edge_east_frame(W, H, left)
        # Send framed even lanes with header (epoch, phase=B)
        hdrB = EdgeHeader(epoch=epoch, phase='B')
        frameB = EdgeFrame(north=[], east=[east_after_b[i] for i in range(L)], south=[], west=[0]*L)
        blobB = make_framed_tx(hdrB, frameB, with_crc=True)
        dupB = False
        if should_fault(epoch, 'B'):
            hdrB, frameB, blobB, note = inject_fault(epoch, 'B', hdrB, frameB, blobB)
            dupB = (args.fault_type == 'duplicate')
            if tracer:
                tracer.log(TraceEvent(kind='fault_injected', tile='L', side='E', epoch=epoch, phase='B', lanes=frameB.east, indices=east_indices_fresh('B'), value=None))
        if tracer:
            tracer.log(TraceEvent(kind='tx', tile='L', side='E', epoch=epoch, phase='B', lanes=frameB.east, indices=east_indices_fresh('B'), value=None))
        parsedB = parse_framed_rx(blobB, width=0, height=L, with_crc=True) if blobB else None
        if parsedB is not None:
            _hB, fB = parsedB
            for i in east_indices_fresh('B'):
                buf_even[i] = (fB.east[i] & 1)
            if tracer:
                tracer.log(TraceEvent(kind='rx', tile='R', side='W', epoch=epoch, phase='B', lanes=fB.east, indices=east_indices_fresh('B'), value=None))
            # Use header to mark neighbor-done with validation
            b_right.mark_neighbor_header('W', _hB.epoch, _hB.phase)
            if dupB:
                parsedB2 = parse_framed_rx(blobB, width=0, height=L, with_crc=True)
                if parsedB2 is not None:
                    _hB2, _ = parsedB2
                    b_right.mark_neighbor_header('W', _hB2.epoch, _hB2.phase)
        # Mark barriers done for B and advance
        b_left.local_done()
        b_right.local_done(); b_left.mark_neighbor_done('E', epoch, 'B')
        b_left.advance(); b_right.advance()
        # Right consumes odd lanes at B using buf_odd
        west_val_B = sum([(buf_odd[i] & 1) << i for i in range(L)])
        rb = right.run_stream([{"west": west_val_B}], cycles_per_step=1, reset=False)[-1]
        odd_out_by_epoch[epoch] = rb.get('out', 0) & odd_mask

        # Print partials and aligned when available (aligned for epoch-1 = odd@B of e-1 OR even@A of e)
        aligned_str = ''
        if (epoch - 1) in odd_out_by_epoch:
            aligned = (odd_out_by_epoch[epoch - 1] & odd_mask) | (even_out_by_epoch.get(epoch, 0) & even_mask)
            aligned_str = f" aligned[e-1]=0x{aligned:0{(L+3)//4}X}"
        print(f"epoch={epoch} a=0x{aval:0{(L+3)//4}X} A_even=0x{(even_out_by_epoch[epoch] & even_mask):0{(L+3)//4}X} B_odd=0x{(odd_out_by_epoch[epoch] & odd_mask):0{(L+3)//4}X}{aligned_str}")
        if tracer and (epoch - 1) in odd_out_by_epoch:
            aligned = (odd_out_by_epoch[epoch - 1] & odd_mask) | (even_out_by_epoch.get(epoch, 0) & even_mask)
            tracer.log(TraceEvent(kind='aligned', tile='R', side='W', epoch=epoch-1, phase=None, lanes=None, indices=None, value=aligned))

    if tracer:
        tracer.close()


if __name__ == '__main__':
    main()
