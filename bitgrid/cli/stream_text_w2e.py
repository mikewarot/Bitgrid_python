from __future__ import annotations

import argparse
from typing import List, Tuple, Optional

from ..lut_only import LUTGrid, LUTOnlyEmulator
from ..router import route_luts


def build_pass_grid(width: int, height: int) -> LUTGrid:
    g = LUTGrid(width, height)
    for y in range(height):
        for x in range(width):
            # Make E output equal to W input; other sides 0
            luts = route_luts('E', 'W')
            g.add_cell(x, y, luts)
    return g


def text_to_bits(s: str, msb_first: bool = True) -> List[int]:
    bits: List[int] = []
    for ch in s.encode('utf-8'):
        if msb_first:
            bits.extend([(ch >> b) & 1 for b in range(7, -1, -1)])
        else:
            bits.extend([(ch >> b) & 1 for b in range(8)])
    return bits


def bits_to_text(bits: List[int], msb_first: bool = True) -> str:
    out = bytearray()
    # Pad to multiple of 8
    n = len(bits)
    if n % 8:
        bits = bits + [0] * (8 - (n % 8))
    for i in range(0, len(bits), 8):
        byte_bits = bits[i:i+8]
        if msb_first:
            val = 0
            for b in range(8):
                val = (val << 1) | (byte_bits[b] & 1)
        else:
            val = 0
            for b in range(8):
                val |= (byte_bits[b] & 1) << b
        out.append(val)
    try:
        return out.decode('utf-8', errors='ignore')
    except Exception:
        return out.decode('latin-1', errors='ignore')


def measure_delay(emu: LUTOnlyEmulator, height: int) -> int:
    # Send a single 1 on west row 0, zeros elsewhere; then zeros after.
    # Count steps until east edge sees a 1 on any row.
    emu.reset()
    # Step 0: impulse
    west = [0] * height
    west[0] = 1
    out = emu.step(edge_in={'W': west})
    if any(out['E']):
        return 0
    # Continue with zeros until it appears (put a cap for safety)
    for steps in range(1, 256):
        out = emu.step(edge_in={'W': [0] * height})
        if any(out['E']):
            return steps
    return -1  # not found


def measure_delays_per_lane(emu: LUTOnlyEmulator, height: int) -> List[int]:
    delays: List[int] = []
    for lane in range(height):
        emu.reset()
        # Drive a 2-step held impulse on this lane to ensure capture across phases
        west = [0] * height
        west[lane] = 1
        out = emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': west})
        if out['E'][lane]:
            delays.append(1)  # observed at t=1 relative to first step of held impulse
            continue
        found = -1
        for steps in range(2, 256):
            out = emu.step(edge_in={'W': [0] * height})
            if out['E'][lane]:
                found = steps
                break
        delays.append(found)
    return delays


def run_stream(emu: LUTOnlyEmulator, height: int, bits: List[int]) -> List[int]:
    east_bits: List[int] = []
    for b in bits:
        out = emu.step(edge_in={'W': [b] + [0]*(height-1)})
        east_bits.append(out['E'][0])
    return east_bits


def chunk_bits_for_lanes(bits: List[int], lanes: int) -> List[List[int]]:
    """Split a bitstream into frames, each frame has `lanes` bits mapped to rows [0..lanes-1].
    Pads the final frame with zeros if needed."""
    frames: List[List[int]] = []
    for i in range(0, len(bits), lanes):
        frame = bits[i:i+lanes]
        if len(frame) < lanes:
            frame = frame + [0] * (lanes - len(frame))
        frames.append(frame)
    return frames


def run_parallel_stream(emu: LUTOnlyEmulator, lanes: int, frames: List[List[int]]) -> List[List[int]]:
    """Drive one frame per step on the West edge (length == lanes). Return East frames per step."""
    east_frames: List[List[int]] = []
    for frame in frames:
        out = emu.step(edge_in={'W': frame})
        east_frames.append(out['E'][:lanes])
    return east_frames


def run_parallel_on_rows(emu: LUTOnlyEmulator, height: int, rows: List[int], frames: List[List[int]]) -> List[List[int]]:
    """Drive frames on selected row indices only; other rows are held at 0.
    Returns East samples for those rows per step in the same order as rows.
    """
    east_frames: List[List[int]] = []
    for frame in frames:
        west = [0] * height
        for i, row in enumerate(rows):
            if 0 <= row < height and i < len(frame):
                west[row] = frame[i]
        out = emu.step(edge_in={'W': west})
        east_frames.append([out['E'][row] for row in rows])
    return east_frames


def select_active_rows(height: int, phase_a_only: bool, lanes: Optional[int] = None) -> List[int]:
    """Choose which row indices carry data. If phase_a_only, use even rows (y%2==0).
    Optionally truncate to 'lanes' rows.
    """
    if phase_a_only:
        rows = [y for y in range(height) if (y % 2 == 0)]
    else:
        rows = list(range(height))
    if lanes is not None and lanes > 0:
        rows = rows[:lanes]
    return rows


def run_stream_cycle(emu: LUTOnlyEmulator, height: int, bits: List[int]) -> List[int]:
    """Serial row-0 stream with cycle-synchronous I/O: hold each bit for 2 steps, sample after the 2nd."""
    out_bits: List[int] = []
    for b in bits:
        west = [b] + [0]*(height-1)
        emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': west})
        out_bits.append(out['E'][0])
    return out_bits


def run_parallel_stream_cycle(emu: LUTOnlyEmulator, lanes: int, frames: List[List[int]]) -> List[List[int]]:
    """Parallel lanes with cycle-synchronous I/O across first `lanes` rows: hold frame for 2 steps, sample after 2nd."""
    east_frames: List[List[int]] = []
    for fr in frames:
        emu.step(edge_in={'W': fr})
        out = emu.step(edge_in={'W': fr})
        east_frames.append(out['E'][:lanes])
    return east_frames


def run_parallel_on_rows_cycle(emu: LUTOnlyEmulator, height: int, rows: List[int], frames: List[List[int]]) -> List[List[int]]:
    """Drive selected rows only with cycle-synchronous I/O (2 steps per frame)."""
    east_frames: List[List[int]] = []
    for fr in frames:
        west = [0]*height
        for i, row in enumerate(rows):
            if i < len(fr):
                west[row] = fr[i]
        emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': west})
        east_frames.append([out['E'][row] for row in rows])
    return east_frames


def measure_delay_cycles(emu: LUTOnlyEmulator, height: int) -> int:
    """Measure latency in cycles (2 steps per cycle) from W row 0 to E row 0.
    Drive a one-cycle held 1, then zeros; return the number of cycles until observed at East.
    """
    emu.reset()
    # Cycle 0: drive 1 on row 0
    west1 = [0]*height
    west1[0] = 1
    emu.step(edge_in={'W': west1})
    out = emu.step(edge_in={'W': west1})
    if out['E'][0]:
        return 1
    # Subsequent cycles: zeros
    for cyc in range(2, 129):
        emu.step(edge_in={'W': [0]*height})
        out = emu.step(edge_in={'W': [0]*height})
        if out['E'][0]:
            return cyc
    return -1


def measure_cycle_delays_for_rows(emu: LUTOnlyEmulator, height: int, rows: List[int]) -> List[int]:
    """Measure per-selected-row latency in cycles using cycle-synchronous I/O.
    Returns a list of cycles until the first '1' is observed at East[row] when West[row] is held at 1 for one cycle.
    """
    delays: List[int] = []
    for row in rows:
        emu.reset()
        # Cycle 1: drive 1 on this row
        west = [0]*height
        west[row] = 1
        emu.step(edge_in={'W': west})
        out = emu.step(edge_in={'W': west})
        if out['E'][row]:
            delays.append(1)
            continue
        found = -1
        for cyc in range(2, 129):
            emu.step(edge_in={'W': [0]*height})
            out = emu.step(edge_in={'W': [0]*height})
            if out['E'][row]:
                found = cyc
                break
        delays.append(found)
    return delays


def schedule_aligned_inputs(orig_frames: List[List[int]], per_lane_delays: List[int]) -> List[List[int]]:
    """Create a per-step West drive schedule so that frame k's bits on all lanes
    arrive at East on the same step. Assumes per_lane_delays[r] is the measured
    delay (in steps) from West[r] to East[r]. Returns a list of West vectors
    (length == lanes) for each step.

    Injection step for lane r and frame k is: k + max_delay - delay[r].
    Total steps = len(frames) + max_delay to flush the tail.
    """
    if not orig_frames:
        return []
    lanes = len(orig_frames[0])
    # sanitize delays: replace negatives with max of non-negative (or 0)
    nonneg = [d for d in per_lane_delays if d is not None and d >= 0]
    default_delay = max(nonneg) if nonneg else 0
    delays = [d if d is not None and d >= 0 else default_delay for d in per_lane_delays]
    max_delay = max(delays) if delays else 0
    steps = len(orig_frames) + max_delay
    schedule: List[List[int]] = []
    for t in range(steps):
        west = [0] * lanes
        for r in range(lanes):
            k = t - (max_delay - delays[r])
            if 0 <= k < len(orig_frames):
                west[r] = orig_frames[k][r]
        schedule.append(west)
    return schedule


def build_two_phase_aligned_schedule(orig_frames: List[List[int]]) -> Tuple[List[List[int]], List[int]]:
    """Build a schedule that accounts for the emulator's checkerboard two-phase update.
    Strategy for width=2 W->E pass-through:
      - Use two steps per frame.
      - Step 2k    : drive odd rows (y%2==1) with frame bits, even rows 0.
      - Step 2k + 1: drive both odd and even rows with frame bits.
      - Arrival for frame k at East is step 2k + 2 for all rows.
    Returns (schedule, arrival_indices_per_frame).
    """
    if not orig_frames:
        return [], []
    lanes = len(orig_frames[0])
    schedule: List[List[int]] = []
    arrival_idx: List[int] = []
    for k, fr in enumerate(orig_frames):
        step_even = [fr[r] if (r % 2 == 1) else 0 for r in range(lanes)]
        step_odd = [fr[r] for r in range(lanes)]
        schedule.append(step_even)
        schedule.append(step_odd)
        arrival_idx.append(2*k + 2)
    # Add one extra flush step of zeros to allow the last frame to emerge
    schedule.append([0]*lanes)
    return schedule, arrival_idx


def build_parity_aligned_schedule(orig_frames: List[List[int]], per_lane_delays: List[int]) -> Tuple[List[List[int]], List[int]]:
    """Schedule injections so that for each frame k, all lanes arrive at the same East step.
    Uses measured per-lane delays (in steps). For checkerboard two-phase grids with width=2,
    delays typically alternate like [1,2,1,2,...]. We choose arrival A_k = 2*k + c with
    c = max_delay to ensure non-negative times and consistent parity, and drive lane r at
    step t = A_k - delay[r]. Returns (schedule, arrival_indices_per_frame).
    """
    if not orig_frames:
        return [], []
    lanes = len(orig_frames[0])
    nonneg = [d for d in per_lane_delays if d is not None and d >= 0]
    max_delay = max(nonneg) if nonneg else 0
    n = len(orig_frames)
    steps = 2*n + max_delay
    schedule: List[List[int]] = [[0]*lanes for _ in range(steps)]
    arrivals: List[int] = []
    for k in range(n):
        A_k = 2*k + max_delay
        arrivals.append(A_k)
        for r in range(lanes):
            d = per_lane_delays[r] if r < len(per_lane_delays) and per_lane_delays[r] is not None else max_delay
            t = A_k - int(d)
            if 0 <= t < steps:
                schedule[t][r] = orig_frames[k][r]
    # Add a final flush step
    schedule.append([0]*lanes)
    return schedule, arrivals


def main():
    ap = argparse.ArgumentParser(description='Stream text bits W->E through a pass-through grid and measure emulated delay.')
    ap.add_argument('--width', type=int, default=2, help='Grid width (columns)')
    ap.add_argument('--height', type=int, default=1, help='Grid height (rows)')
    ap.add_argument('--text', type=str, default='Hello, World', help='Text to stream as bits (UTF-8)')
    ap.add_argument('--msb-first', action='store_true', help='Use MSB-first bit order (default). If omitted, LSB-first can be chosen via --lsb-first.')
    ap.add_argument('--lsb-first', action='store_true', help='Use LSB-first bit order.')
    ap.add_argument('--save', type=str, help='Optional path to save the LUTGrid JSON')
    ap.add_argument('--parallel', action='store_true', help='Use all rows as parallel lanes (W/E vectors per step)')
    ap.add_argument('--pad-align', dest='pad_align', action='store_true', help='Append zeros to flush pipeline and decode output exactly matching input after removing delay')
    ap.add_argument('--align-lanes', dest='align_lanes', action='store_true', help='Measure per-lane delays and schedule injections so each frame arrives in-phase on East')
    ap.add_argument('--phase-a-only', dest='phase_a_only', action='store_true', default=True, help='[default] Use only Phase-A rows (even y) as lanes to avoid cross-phase skew')
    ap.add_argument('--all-rows', dest='phase_a_only', action='store_false', help='Use all rows as lanes (may require alignment)')
    ap.add_argument('--lanes', type=int, default=0, help='Limit number of parallel lanes to this count (mapped onto selected rows)')
    ap.add_argument('--cycle-io', dest='cycle_io', action='store_true', default=True, help='[default] Hold inputs stable for two substeps (A+B) and sample outputs once per cycle')
    ap.add_argument('--step-io', dest='cycle_io', action='store_false', help='Drive/sense each subphase (expert mode)')
    args = ap.parse_args()

    msb_first = True
    if args.lsb_first:
        msb_first = False
    elif args.msb_first:
        msb_first = True

    g = build_pass_grid(args.width, args.height)
    if args.save:
        g.save(args.save)

    emu = LUTOnlyEmulator(g)
    print(f"Grid: {g.W}x{g.H}")
    if args.cycle_io:
        delay_cycles = measure_delay_cycles(emu, args.height)
        if delay_cycles < 0:
            print('Could not observe impulse at East within 128 cycles')
            return
        print(f"Measured latency: {delay_cycles} cycles")
    else:
        delay_steps = measure_delay(emu, args.height)
        if delay_steps < 0:
            print('Could not observe impulse at East within 256 steps')
            return
        print(f"Measured delay: {delay_steps} steps (~ {delay_steps/2:.1f} cycles)")

    in_bits = text_to_bits(args.text, msb_first=msb_first)

    if not args.parallel:
        # Serial on row 0
        emu.reset()
        if args.cycle_io:
            out_bits = run_stream_cycle(emu, args.height, in_bits)
            decoded = bits_to_text(out_bits[:len(in_bits)], msb_first=msb_first)
            print(f"Decoded East (cycle-io): {decoded}")
        else:
            bits_driven = in_bits
            delay_steps = measure_delay(emu, args.height)
            if args.pad_align and delay_steps > 0:
                bits_driven = in_bits + [0] * delay_steps
            out_bits = run_stream(emu, args.height, bits_driven)
            print(f"Input bits (first 32): {''.join(str(b) for b in in_bits[:32])}...")
            print(f"East  bits (first 32): {''.join(str(b) for b in out_bits[:32])}...")
            if delay_steps > 0 and len(out_bits) >= delay_steps + len(in_bits):
                aligned = out_bits[delay_steps:delay_steps+len(in_bits)]
                decoded = bits_to_text(aligned, msb_first=msb_first)
                print(f"Decoded East after delay: {decoded}")
            else:
                print("Not enough bits to decode after delay alignment.")
    else:
        # Parallel lanes: use all rows per step, one frame per step
        # Choose active rows for lanes
        rows = select_active_rows(g.H, phase_a_only=bool(args.phase_a_only), lanes=(args.lanes if args.lanes > 0 else None))
        lanes = len(rows)
        if lanes == 0:
            print('No lanes selected; choose a larger height, use --all-rows, or set --lanes.')
            return
        orig_frames = chunk_bits_for_lanes(in_bits, lanes)
        if args.cycle_io:
            # measure per-lane cycle latency
            per_lane_cyc = measure_cycle_delays_for_rows(emu, g.H, rows)
            max_cyc = max(d for d in per_lane_cyc if d is not None and d >= 0) if per_lane_cyc else 0
            # schedule frames per cycle with lane offsets: drive frame k for lanes at cycle (k + max_cyc - delay[r])
            cycles = len(orig_frames) + max_cyc
            schedule: List[List[int]] = [[0]*len(rows) for _ in range(cycles)]
            for k, fr in enumerate(orig_frames):
                for r, d in enumerate(per_lane_cyc):
                    dd = d if d is not None and d >= 0 else max_cyc
                    t = k + (max_cyc - dd)
                    if 0 <= t < cycles:
                        schedule[t][r] = fr[r]
            # run cycle-synchronous with this schedule
            emu.reset()
            frames_out = run_parallel_on_rows_cycle(emu, g.H, rows, schedule)
            # collect aligned outputs at cycles [max_cyc .. max_cyc+len(orig_frames)-1]
            start_idx = max_cyc - 1 if max_cyc > 0 else 0
            aligned_frames = frames_out[start_idx:start_idx+len(orig_frames)] if len(frames_out) >= start_idx else []
            out_bits_full = [b for fr in aligned_frames for b in fr][:len(in_bits)]
            decoded = bits_to_text(out_bits_full, msb_first=msb_first)
            print(f"Per-lane cycle delays: {per_lane_cyc}")
            print(f"Decoded East (cycle-io, parallel aligned): {decoded}")
            return
        # Measure per-lane delays
        # Measure per-lane delays for selected rows by mapping one at a time
        per_lane = []
        for i, row in enumerate(rows):
            emu.reset()
            # 2-step held impulse on this row only
            west = [0] * g.H
            west[row] = 1
            out = emu.step(edge_in={'W': west})
            out = emu.step(edge_in={'W': west})
            if out['E'][row]:
                per_lane.append(1)
                continue
            found = -1
            for steps in range(2, 256):
                out = emu.step(edge_in={'W': [0] * g.H})
                if out['E'][row]:
                    found = steps
                    break
            per_lane.append(found)
        max_delay = max(d for d in per_lane if d is not None and d >= 0) if per_lane else 0
        print(f"Per-lane delays (steps): {per_lane}")

        if args.align_lanes or args.phase_a_only:
            # Build a schedule using measured per-lane delays to align arrivals
            schedule, arrivals = build_parity_aligned_schedule(orig_frames, per_lane)
            emu.reset()
            frames_out = run_parallel_on_rows(emu, g.H, rows, schedule)
            print(f"Frames scheduled (aligned): {len(schedule)}, Frames out: {len(frames_out)}")
            # Collect frames at the computed arrival indices
            aligned_frames: List[List[int]] = []
            for idx in arrivals:
                if 0 <= idx < len(frames_out):
                    aligned_frames.append(frames_out[idx])
            if aligned_frames:
                out_bits_aligned_full = [b for fr in aligned_frames for b in fr]
                out_bits_aligned = out_bits_aligned_full[:len(in_bits)]
                decoded = bits_to_text(out_bits_aligned, msb_first=msb_first)
                print(f"Decoded East after delay (aligned lanes): {decoded}")
            else:
                print("No aligned frames available for decode.")
        else:
            # Simple frame-per-step drive with optional tail padding, then reindex by per-lane delays to align
            frames_in = list(orig_frames)
            if args.pad_align and max_delay > 0:
                frames_in = frames_in + [[0]*lanes for _ in range(max_delay)]
            emu.reset()
            frames_out = run_parallel_on_rows(emu, g.H, rows, frames_in)
            # Align per lane: for each row r, take frames_out[per_lane[r] + t][r]
            frames_aligned: List[List[int]] = []
            if all(d is not None and d >= 0 for d in per_lane) and len(frames_out) >= max_delay + len(orig_frames):
                for t in range(len(orig_frames)):
                    row_vals: List[int] = []
                    for r in range(lanes):
                        d = per_lane[r]
                        val = frames_out[d + t][r] if d >= 0 else 0
                        row_vals.append(val)
                    frames_aligned.append(row_vals)
            # Flatten back to bitstream and decode
            out_bits_aligned_full = [b for fr in frames_aligned for b in fr]
            out_bits_aligned = out_bits_aligned_full[:len(in_bits)]
            print(f"Frames in: {len(frames_in)}, Frames out: {len(frames_out)}")
            if frames_in:
                print(f"First in frame (rows): {''.join(str(b) for b in frames_in[0])}")
            if frames_out:
                print(f"First out frame: {''.join(str(b) for b in frames_out[0])}")
            if frames_aligned:
                decoded = bits_to_text(out_bits_aligned, msb_first=msb_first)
                print(f"Decoded East after delay (parallel): {decoded}")
            else:
                print("Not enough frames to decode after delay alignment.")


if __name__ == '__main__':
    main()
