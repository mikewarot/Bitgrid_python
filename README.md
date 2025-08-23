# BitGrid Python Prototype

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
- Demos: demo_route4, demo_stream, demo_throughput, demo_edge_io_hello, demo_edge_io_4bit, demo_sum8_correct, demo_stream_sum8
- Tools: bench_cycles (raw two‑phase loop benchmark)

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
