# BitGrid Python Prototype

IMPORTANT: This is *almost entirely written by ChatGPT 5*, not me

A small Python toolchain to:

- Parse a math/bitwise expression into a directed graph.
- Map that graph into a 2D BitGrid of 4-input/4-output LUT cells.
- Emulate the grid with two-phase updates (A: x+y even, B: x+y odd).
- Route long wires by inserting neighbor-only ROUTE4 hops.
- Drive simple streaming I/O demos from the grid edges.

Status: prototype focused on bitwise ops (&, |, ^, ~), shifts (<<, >>), add/sub, and multiply via shift-and-add. Signed math is supported by prefixing widths with 's' (e.g., a:s8).

Important: Grid width and height must be even (A/B parity preserved across the array). The emulator evaluates each cell via 16‑bit truth tables (LUT-first), allowing any function of up to 4 inputs per output.

## Quick start

Compile an expression to a graph and grid program, then run it against a CSV of inputs.

```bash
# Be sure to include the full path (do not omit the 'out/' folder).
python -m bitgrid.cli.compile_expr --expr "out = (a & b) ^ (~c) + 3" --vars "a:16,b:16,c:16" --out out \
	--graph out/graph.json --program out/program.json

python -m bitgrid.cli.run_emulator --program out/program.json --inputs inputs.csv \
	--outputs out/results.csv --log out/debug.log
```

Input CSV header must match variables, e.g.:

```csv
a,b,c
0x00FF,0x0F0F,0xAAAA
0x1234,0x5678,0x9ABC
```

Output formatting options:

```bash
# Hex (default)
python -m bitgrid.cli.run_emulator --program out/smul_program.json --inputs inputs_mul.csv --outputs out/smul_hex.csv

# Signed decimal for specific outputs (two's complement by declared bit width)
python -m bitgrid.cli.run_emulator --program out/smul_program.json --inputs inputs_mul.csv --outputs out/smul_dec.csv --format dec --signed prod

# Binary
python -m bitgrid.cli.run_emulator --program out/smul_program.json --inputs inputs_mul.csv --outputs out/smul_bin.csv --format bin
```

## Examples

### Multiply (unsigned)

Prepare a CSV of multiplicand/multiplier pairs (an example `inputs_mul.csv` is included):

```csv
a,b
6,7
12,13
0x0F,0x10
```

Compile and run:

```bash
python -m bitgrid.cli.compile_expr --expr "prod = a * b" --vars "a:8,b:8" --graph out/mul_graph.json --program out/mul_program.json
python -m bitgrid.cli.run_emulator --program out/mul_program.json --inputs inputs_mul.csv --outputs out/mul_results.csv
```

### Signed math

- Signed multiply (two's complement):

```bash
python -m bitgrid.cli.compile_expr --expr "prod = a * b" --vars "a:s8,b:s8" --graph out/smul_graph.json --program out/smul_program.json
```

- Arithmetic right shift when the left operand is signed:

```bash
python -m bitgrid.cli.compile_expr --expr "q = a >> 1" --vars "a:s8" --graph out/sar_graph.json --program out/sar_program.json
```

### f32 (IEEE‑754) multiply (prototype)

Inputs/outputs are 32‑bit integers (hex or decimal).

```bash
python -m bitgrid.cli.run_f32_mul --inputs inputs_f32_mul.csv --outputs out/f32_mul_results.csv
```

Example `inputs_f32_mul.csv`:

```csv
a,b
0x3F800000,0x40000000  # 1.0 * 2.0 = 2.0
0x40400000,0x40400000  # 3.0 * 3.0 = 9.0
```

Notes: prototype handles normal numbers and zero, truncates rounding, and omits NaN/Inf/subnormals for now.

## Concepts

- Graph JSON: high‑level DAG of multi‑bit operations.
- Program JSON: BitGrid cells (LUTs), wiring, and I/O mapping. Includes an estimated propagation latency in cycles.
- Emulator: two‑phase updates per cycle; run for `latency` cycles per input vector before sampling outputs.
- LUT‑first evaluation: each cell can provide up to 4 outputs from per‑output 16‑bit truth tables. Legacy op codes are still understood.
- Even dimensions required: width and height must be even to preserve two‑phase parity across the array.

## Routing and streaming

### Directional routing (ROUTE4) demo

Each cell can act as a 4‑input/4‑output directional router using four small LUTs (one per direction: N/E/S/W). This enables multi‑direction pass‑through while still allowing logic on other outputs.

```bash
python -m bitgrid.cli.demo_route4 --width 16 --height 8 --src 0,0 --dst 5,3
```

Prints whether the bit arrives at the destination output (expected: 1). Uses a simple A* Manhattan router that inserts ROUTE4 pass‑through cells along the path.

### Streaming throughput demo

Measure streaming behavior over a routed path. Cycles‑per‑step (cps) controls how many emulator cycles advance per input step. With the current two‑phase model, cps=2 advances one hop per step.

```bash
python -m bitgrid.cli.demo_throughput --width 16 --height 8 --src 0,1 --dst 10,6 --train 6 --cps 2
python -m bitgrid.cli.demo_throughput --turn 0.25  # prefer straighter paths
```

### Edge streaming I/O

Hello World over 8 parallel lanes (west→east):

```bash
python -m bitgrid.cli.demo_edge_io_hello --width 16 --height 8 --row 0 --len 10 --cps 2 --text "Hello World"
```

4‑bit lane demo (per‑step I/O shown):

```bash
python -m bitgrid.cli.demo_edge_io_4bit --width 16 --height 8 --row 0 --cps 2
```

### 8+8 → sum demos

- Correctness‑first (map → route → run per vector):

```bash
python -m bitgrid.cli.demo_sum8_correct --width 64 --height 64 --pairs "(1,2),(3,4),(10,20),(255,1)"
```

- Streaming prototype (ongoing):

```bash
python -m bitgrid.cli.demo_stream_sum8 --width 64 --height 32 --cps 2 --pairs "(1,2),(3,4),(10,20),(255,1)"
```

#### Streaming sums at cps=2 (latency‑aware)

The streaming demo now derives the adder’s per‑bit step latency from two‑phase parity and holds each input pair steady for K+1 steps, sampling the sum at the end of each window. This yields correct results at cps=2 without changing the mapped adder.

- K is the maximum per‑bit step lag across the 8 rows; with vertical ripple and two‑phase timing, K is small (typically 4 for 8 bits depending on placement parity).
- The demo prints one sum per input pair. Example output:

```
i=0: a=1 b=2 -> sum=0x03
i=1: a=3 b=4 -> sum=0x07
i=2: a=10 b=20 -> sum=0x1E
i=3: a=255 b=1 -> sum=0x00
```

Notes:
- For fully pipelined 1‑per‑step streaming, either increase cps to cover the ripple depth or implement pipeline registers in the adder and/or add explicit ROUTE4 delays to align bit arrivals.

How it works:
- Two‑phase timing means neighbors exchange data once per full cycle; vertical ripple in the adder causes MSB sum bits to stabilize a few steps after LSBs.
- Let the LSB row be at y_min and the adder column at x_add. If (x_add + y_min) is even, the LSB updates in phase A; otherwise in phase B. The per‑bit step lag is:
	- lag(i) = i//2 if LSB is even, else lag(i) = (i+1)//2, with i = bit index (0..7).
- K = max(lag(i)) over all bits. By holding inputs for K+1 steps, every bit of the sum has time to settle; sampling at the end of the window gives the correct sum.

Try it with visibility:

```bash
python -m bitgrid.cli.demo_stream_sum8 --width 64 --height 32 --cps 2 \
	--pairs "(1,2),(3,4),(10,20),(255,1)" --show-k
```

You’ll see a line like `K=4 (lsb_even=False) lags=[0,1,1,2,2,3,3,4]` printed (values depend on placement), followed by one sum per input pair.

### Tiled interop demo (two tiles, parity-split seam)

Exchange only the lanes computed in the current phase across a tile seam and recombine on the receiver.

```bash
python -m bitgrid.cli.demo_two_tile_loop --width 8 --height 8 --lanes 8 --steps "1,3,5,170"
```

What it shows:
- Phase A emits odd-index lanes at the east edge (since W is even → x=W-1 is odd, so A updates odd y).
- Phase B emits even-index lanes.
- The receiver buffers even/odd halves and submits the appropriate half each subphase. After B, you can recombine to get a fully aligned vector (odd from B of epoch e-1 OR even from A of epoch e). The demo prints per-phase partials and an aligned value when available.

This halves seam bandwidth versus sending both parities every phase, and aligns with the global two-phase barrier described in `docs/tiling-and-interop.md`.

### Tracing data flow and barriers

You can log seam transfers and barrier sync events to a JSONL or CSV trace for debugging.

Two-tile with trace:

```bash
python -m bitgrid.cli.demo_two_tile_loop --width 8 --height 8 --lanes 8 \
	--steps "1,3,5,170" --trace out/two_tile_trace.jsonl --trace-format jsonl
```

2×2 with trace:

```bash
python -m bitgrid.cli.demo_four_tile_loop --width 8 --height 8 \
	--steps "1,3,5,0xAA" --trace out/four_tile_trace.jsonl
```

Trace event kinds:
- `tx`/`rx`: framed seam transfers (epoch, phase, side, lanes, indices of fresh lanes)
- `aligned`: recombined value availability at the sink (epoch e-1)
- Barrier: `barrier_local_done`, `barrier_neighbor_done`, `barrier_neighbor_hdr` (with `value` = ok|epoch_mismatch|phase_mismatch|duplicate), `barrier_advance`, `barrier_cannot_advance` (value = blocked)

Summarize a trace:

```bash
python -m bitgrid.cli.trace_summary out/four_tile_trace.jsonl
```

### Fault injection (test error handling)

Inject seam faults in the two-tile demo to validate barrier mismatch handling:

```bash
# Corrupt CRC at epoch 1, phase B (frame is dropped, neighbor won't mark done)
python -m bitgrid.cli.demo_two_tile_loop --width 8 --height 8 --lanes 8 \
	--steps "1,3,5,170" --fault-type crc --fault-epoch 1 --fault-phase B \
	--trace out/two_tile_fault_crc.jsonl

# Epoch mismatch at epoch 1, phase A (header shows wrong epoch)
python -m bitgrid.cli.demo_two_tile_loop --width 8 --height 8 --lanes 8 \
	--steps "1,3,5,170" --fault-type epoch --fault-epoch 1 --fault-phase A \
	--trace out/two_tile_fault_epoch.jsonl

# Phase mismatch, drop, or duplicate header
python -m bitgrid.cli.demo_two_tile_loop --fault-type phase --fault-epoch 2 --fault-phase B --steps "1,3,5"
python -m bitgrid.cli.demo_two_tile_loop --fault-type drop  --fault-epoch 2 --fault-phase A --steps "1,3,5"
python -m bitgrid.cli.demo_two_tile_loop --fault-type duplicate --fault-epoch 2 --fault-phase A --steps "1,3,5"
```

Look for `barrier_neighbor_hdr` status (e.g., `epoch_mismatch`) and `barrier_cannot_advance` lines in the trace to confirm detection.

## Routing pass (neighbor‑only wiring)

Expression‑mapped programs previously allowed long‑range references. A routing pass now inserts ROUTE4 hops to enforce neighbor‑only connections.

```bash
python -m bitgrid.cli.compile_expr --expr "sum = a + b" --vars "a:8,b:8" --graph out/sum_graph.json --program out/sum_program.json
python -m bitgrid.cli.route_program --in out/sum_program.json --out out/sum_program_routed.json
python -m bitgrid.cli.run_emulator --program out/sum_program_routed.json --inputs inputs_mul.csv --outputs out/sum_results.csv --format hex
```

The router uses A* Manhattan paths and inserts ROUTE4 cells per hop. Basic occupancy is considered; congestion/rip‑up and parity‑aware costs are planned.

## CLI catalog

- bitgrid.cli.compile_expr — compile expression to graph/program JSON
- bitgrid.cli.run_emulator — emulate with CSV I/O and formatting controls
- bitgrid.cli.run_f32_mul — run the f32 multiply prototype
- bitgrid.cli.route_program — insert ROUTE4 hops post‑map (neighbor‑only wiring)
- bitgrid.cli.bitstream_roundtrip — pack/unpack LUT bitstreams and rehydrate to verify format/round‑trip
- bitgrid.cli.emu_load_bitstream — load a bitstream into a Program and run the emulator on CSV inputs
- bitgrid.cli.bitstream_inspect — inspect a bitstream header (dims/order/flags/bits/CRC)
- bitgrid.cli.serve_tcp — serve the emulator over TCP using the BGCF runtime protocol
- bitgrid.cli.bgcf_dump — BGCF packet dumper: parse files or run a TCP proxy that logs frames
- Demos: demo_route4, demo_stream, demo_throughput, demo_edge_io_hello, demo_edge_io_4bit, demo_sum8_correct, demo_stream_sum8
- Tools: bench_cycles (raw two‑phase loop benchmark)

## Bitstream programming (ASIC/RAM alignment)

You can serialize a Program's per-output 16-bit LUTs into a compact bitstream suitable for ASIC serial configuration chains or a RAM-backed emulator, and rehydrate from that bitstream.

Format:
- Per cell, outputs are ordered [N, E, S, W] (indices 0..3).
- For each output, the LUT is 16 bits, packed LSB-first, where bit i corresponds to input index `i = N | (E<<1) | (S<<2) | (W<<3)`.
- Cells are scanned in row-major order by default (y=0..H-1, x=0..W-1). Optional orders: `col-major`, `snake`.
- Missing cells are treated as zero-LUTs to keep scan position stable.

Optional fixed header (for cross-language interop):

```
Offset Size Type  Name             Notes
0      4    char  magic            'BGBS'
4      2    u16   version          1
6      2    u16   header_size      24 bytes
8      2    u16   width            cells
10     2    u16   height           cells
12     1    u8    order            0=row, 1=col, 2=snake
13     1    u8    flags            bit0=0 means LUT bits LSB-first (current)
14     4    u32   payload_bits     width*height*4*16
18     4    u32   payload_crc32    CRC-32 of payload bytes (IEEE)
22     2    u16   reserved         0
24     ...  u8[]  payload          packed LUT bits
```

- Endianness: little-endian for all multi-byte fields.
- CRC covers only the payload, not the header.
- Payload length can be derived as `(payload_bits+7)//8`.

Pascal/Delphi reference with a packed record and loader sketch:
- docs/bitstream_header_pascal.md

CLI round-trip checker:

```bash
# Raw payload only
python -m bitgrid.cli.bitstream_roundtrip --program out/program.json --out out/bitstream.bin --order row-major

# With fixed header + CRC (recommended for interop)
python -m bitgrid.cli.bitstream_roundtrip --program out/program.json --out out/bitstream_hdr.bin --order row-major --header
```

Emulator direct load (compare against Pascal):

```bash
python -m bitgrid.cli.emu_load_bitstream --program out/program.json --bitstream out/bitstream_hdr.bin \
	--inputs inputs.csv --outputs out/results_from_bitstream.csv

# For raw payloads, specify the scan order and (optionally) dims if they differ from Program
python -m bitgrid.cli.emu_load_bitstream --program out/program.json --bitstream out/bitstream.bin \
	--order row-major --inputs inputs.csv --outputs out/results_from_raw.csv
```

Inspect a headered bitstream:

```bash
python -m bitgrid.cli.bitstream_inspect out/bitstream_hdr.bin
```

Serve the emulator over TCP (BGCF protocol):

```bash
python -m bitgrid.cli.serve_tcp --program out/program.json --host 127.0.0.1 --port 9000 --verbose
```

Quick client examples (talk to the server):

```bash
# HELLO round-trip
python -m bitgrid.cli.client_tcp --hello

# Load a bitstream and apply
python -m bitgrid.cli.client_tcp --load out/bitstream_hdr.bin

# Set inputs, advance, and fetch outputs
python -m bitgrid.cli.client_tcp --set a=1,b=2 --step 2 --get

# Ask server to close the connection and stop serving this client
python -m bitgrid.cli.client_tcp --quit

# Ask server to stop its listener (server process exits after current connection)
python -m bitgrid.cli.client_tcp --shutdown

BGCF packet dump / proxy:

```powershell
# File mode: parse a captured byte stream (BGCF-framed) and write JSONL summaries
py -m bitgrid.cli.bgcf_dump --file path\to\capture.bin --out out\capture.jsonl

# Proxy mode: sit between client and server, logging all frames to a JSONL file
# Client connects to 127.0.0.1:9001; proxy forwards to server at 127.0.0.1:9000
py -m bitgrid.cli.bgcf_dump --proxy --listen-port 9001 --target-port 9000 --out out\proxy_log.jsonl

# Then point your client at the proxy
py -m bitgrid.cli.client_tcp --host 127.0.0.1 --port 9001 --hello --quit
```
```

Client outline (Pascal/C++): connect to host:port and speak BGCF frames:
- Send HELLO; expect HELLO reply with dims/features.
- Send LOAD_CHUNK frames until the bitstream is sent; then APPLY.
- For each step: SET_INPUTS, STEP (cycles), GET_OUTPUTS and read OUTPUTS.

This writes `out/bitstream.bin` and a `*_rehydrated.json` next to your input Program. The rehydrated Program has the same dimensions and I/O mapping but with LUTs reconstructed from the bitstream.

Library API (if you need programmatic access):
- `bitgrid.bitstream.pack_program_bitstream(program, order='row-major') -> bytes`
- `bitgrid.bitstream.unpack_bitstream_to_luts(bitstream, width, height, order='row-major') -> {(x,y): [l0,l1,l2,l3]}`
- `bitgrid.bitstream.apply_luts_to_program(program, luts_by_cell) -> Program`

## Repository layout

- `bitgrid/graph.py` — DAG structures and JSON serialization
- `bitgrid/expr_to_graph.py` — parse expression to graph
- `bitgrid/mapper.py` — map graph to BitGrid program JSON
- `bitgrid/program.py` — program/cell dataclasses and JSON I/O
- `bitgrid/emulator.py` — two‑phase grid emulator, LUT‑first evaluation
- `bitgrid/router.py` — Manhattan router and ROUTE4 helpers
- `bitgrid/float/` — f32 multiply prototype utilities
- `bitgrid/cli/` — CLI tools and demos listed above

## Development

- No external dependencies; Python 3.9+ recommended.
- Windows PowerShell: replace `python` with `py` if needed.
- Keep width and height even across tools.

## Design

### Cell model and LUTs

- Each BitGrid cell has up to 4 inputs and 4 outputs.
- Evaluation is LUT-first: each output is defined by a 16-bit truth table addressed by the 4 input bits. Bit i of the LUT corresponds to the output value for input index i (0..15).
- Parameter forms in Program JSON:
	- `params.luts`: array of four 16-bit integers for outputs [0,1,2,3].
	- `params.lut`: single 16-bit integer (legacy scalar ops), applied to output 0.
- Direction indexing used across the repo: N=0, E=1, S=2, W=3.
- The helper `route_luts(out_dir, in_pin)` creates the 4 per-output LUTs that forward a chosen input pin to a chosen output direction (used by ROUTE4).

### Two-phase timing

- The emulator updates in two phases per cycle: phase A updates cells where (x+y) is even; phase B updates cells where (x+y) is odd.
- Neighbor communication effectively advances by one cell every two phases (one full cycle). As a result, cps=2 in streaming demos advances a routed signal by one hop per step.
- For non-trivial logic (e.g., adders), additional internal ripple/carry latency applies. The `latency` field in Program JSON is used by vector runs to determine how many cycles to run before sampling outputs.
- Even grid dimensions are required so that A/B parity tiles perfectly across the array without drift.

Two‑phase checkerboard (A=even, B=odd):

```
 x+y parity:

	 y→   0 1 2 3
 x ↓
 0     A B A B
 1     B A B A
 2     A B A B
 3     B A B A

One full cycle = A then B. A neighbor hop takes one cycle.
```

### Mapping and routing

- Mapper places bit-sliced logic and uses vertical ripple-carry for add/sub to align with two-phase timing.
- Initially, mapped programs could reference distant cells directly. The `route_program` pass rewrites such long edges into neighbor-only wiring by inserting ROUTE4 pass-through cells along Manhattan paths.
- Router: A* Manhattan search with basic occupancy and optional `--turn` penalty for fewer turns.

### Program JSON sketch

- Top-level: `{ "width": int, "height": int, "latency": int, "cells": [...], "input_bits": {name:[...]}, "output_bits": {name:[...]} }`
- Cell: `{ "x": int, "y": int, "op": "LUT"|"ROUTE4"|..., "inputs": [src,src,src,src], "params": { "luts": [u16,u16,u16,u16] } }`
- Source (`src`) can be:
	- Constant: `{ "type": "const", "value": 0|1 }`
	- Input bit: `{ "type": "input", "name": "a", "bit": 3 }`
	- Cell output: `{ "type": "cell", "x": 10, "y": 5, "out": 1 }`

This is a compact overview; see code in `bitgrid/program.py`, `bitgrid/emulator.py`, and `bitgrid/router.py` for exact semantics.

### LUT indexing example

- Input bit order is `[N, E, S, W]` and the LUT index is computed as: `idx = N | (E<<1) | (S<<2) | (W<<3)`.
- Example: if N=1, E=0, S=1, W=0 then `idx = 1 | (0<<1) | (1<<2) | (0<<3) = 5`. The output bit equals `(lut >> 5) & 1`.

### ROUTE4 forwarding LUT example

Forward west input to east output (W→E pass‑through). Only the east output LUT needs bits; others are zero:

```json
"op": "ROUTE4",
"params": { "luts": [ 0, 0xFF00, 0, 0 ] }
```

Why 0xFF00? For index 0..15, the west input equals bit `(idx>>3)&1`. That is 0 for idx 0..7 and 1 for idx 8..15, which sets the upper 8 bits of the 16‑bit LUT (0xFF00). Similar patterns:

- Forward S→N: N LUT = 0xF0F0 (since `(idx>>2)&1` toggles every 4). 
- Forward E→W: W LUT = 0xCCCC (since `(idx>>1)&1` toggles every 2). 
- Forward N→S: S LUT = 0xAAAA (since `(idx>>0)&1` toggles every 1).

## Troubleshooting

- Grid dimension error: width and height must both be even. Adjust CLI `--width/--height` to even values.
- "No route found": increase grid size, adjust `--turn`, or reduce occupancy (e.g., change offsets). Use `bitgrid.cli.route_program` to insert ROUTE4 hops after mapping.
- CSV issues: headers must match variable names; use `0x` for hex; for signed decimal output, pass `--format dec --signed <out_name>`.
- Streaming shows zeros: ensure `--cps` is high enough for the logic latency. Pure routing needs cps≈2 per hop; adders add internal ripple cycles. Use the correctness demo or increase `--cps`.
- ROUTE4 forwarding unexpected: check direction indices (N=0,E=1,S=2,W=3) and ensure the intended input pin is wired when generating LUTs via `route_luts`.
- Performance: use `bitgrid.cli.bench_cycles` for a raw two-phase loop sanity check. Avoid verbose logging when benchmarking.
