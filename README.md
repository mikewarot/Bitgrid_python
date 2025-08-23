# BitGrid Python Prototype

This repository provides a prototype toolchain to:

1. Parse a math/bitwise expression into a directed graph of operations.
2. Map that graph into a 2D "BitGrid" of 4-input 4-output LUT cells.
3. Emulate the BitGrid with 2-phase updates (A: x+y even, B: x+y odd).
4. Provide CLI tools to compile expressions and run emulations with I/O files and optional debug logs.

Status: prototype focused on bitwise ops (&, |, ^, ~), shifts (<<, >>), addition (+), subtraction (two's complement), and multiplication (*) via shift-and-add. Signed math is supported by prefixing widths with 's' (e.g., a:s8).

## Quick start

- Compile an expression to a graph and grid program:

```
python -m bitgrid.cli.compile_expr --expr "out = (a & b) ^ (~c) + 3" --vars "a:16,b:16,c:16" --out out --graph out/graph.json --program out/program.json
```

- Prepare a CSV with inputs (header must match variables):

```
a,b,c
0x00FF,0x0F0F,0xAAAA
0x1234,0x5678,0x9ABC
```

- Run the emulator and write outputs:

```
python -m bitgrid.cli.run_emulator --program out/program.json --inputs inputs.csv --outputs out/results.csv --log out/debug.log
```

- Output formatting:

```
# Hex (default)
python -m bitgrid.cli.run_emulator --program out/smul_program.json --inputs inputs_mul.csv --outputs out/smul_hex.csv

# Signed decimal for specific outputs (two's complement by declared bit width)
python -m bitgrid.cli.run_emulator --program out/smul_program.json --inputs inputs_mul.csv --outputs out/smul_dec.csv --format dec --signed prod

# Binary
python -m bitgrid.cli.run_emulator --program out/smul_program.json --inputs inputs_mul.csv --outputs out/smul_bin.csv --format bin
```

### Multiply example (unsigned)

- Prepare a CSV of multiplicand/multiplier pairs (an example `inputs_mul.csv` is included):

```
a,b
6,7
12,13
0x0F,0x10
```

- Compile a multiply program and run it:

```
python -m bitgrid.cli.compile_expr --expr "prod = a * b" --vars "a:8,b:8" --graph out/mul_graph.json --program out/mul_program.json
python -m bitgrid.cli.run_emulator --program out/mul_program.json --inputs inputs_mul.csv --outputs out/mul_results.csv
```

### Signed math examples
### f32 (IEEE‑754) multiply (prototype)

- Build and run f32 multiply (inputs/outputs as 32-bit integers in hex or decimal):

```
python -m bitgrid.cli.run_f32_mul --inputs inputs_f32_mul.csv --outputs out/f32_mul_results.csv
```

- Example `inputs_f32_mul.csv`:

```
a,b
0x3F800000,0x40000000  # 1.0 * 2.0 = 2.0
0x40400000,0x40400000  # 3.0 * 3.0 = 9.0
```

Notes: prototype handles normal numbers and zero, uses truncation rounding, and omits NaN/Inf/subnormals for now.


- Signed multiply (two's complement):

```
python -m bitgrid.cli.compile_expr --expr "prod = a * b" --vars "a:s8,b:s8" --graph out/smul_graph.json --program out/smul_program.json
```

- Signed right shift uses arithmetic shift when the left operand is signed:

```
python -m bitgrid.cli.compile_expr --expr "q = a >> 1" --vars "a:s8" --graph out/sar_graph.json --program out/sar_program.json
```

```

## Concepts

- Graph JSON: a high-level DAG of multi-bit operations.
- Program JSON: BitGrid configuration with cells (LUTs), wiring, and I/O mapping. Includes an estimated latency (cycles) for values to propagate.
- Emulator: performs two-phase updates per cycle; run for `latency` cycles per input vector before sampling outputs.

### Directional routing (ROUTE4) demo

- Each BitGrid cell can also act as a 4-input/4-output directional router using 4 small LUTs (one per direction: N/E/S/W). This enables simultaneous multi-direction pass-through while still allowing logic on other outputs.

- Try a minimal routing demo that wires a constant '1' from a source cell to a destination cell using neighbor-only hops:

```
python -m bitgrid.cli.demo_route4 --width 16 --height 8 --src 0,0 --dst 5,3
```

It prints whether the bit arrives at the destination output (expected: 1). This uses a simple Manhattan router that inserts ROUTE4 pass-through cells along the path.

## Limits and notes

- Each LUT cell has 4 inputs and 4 outputs. We map operations per bit, usually using one cell/bit for binary ops and one cell/bit for adders (carry ripple vertically).
- Signals can be sourced from global inputs, constants, neighbor outputs, or explicit cell references. The mapper favors vertical carry chains for add.
- Routing:
	- Expression-mapped programs: previously allowed long-range references. Work is in progress to enforce neighbor-only routing by inserting ROUTE4 hops.
	- The current demo uses a simple Manhattan (L-shaped) path and inserts ROUTE4 cells per hop. Congestion handling, parity-aware hops, and rip-up/reroute are planned.

## Repository layout

- `bitgrid/graph.py` — DAG structures and JSON serialization.
- `bitgrid/expr_to_graph.py` — parses expression to graph.
- `bitgrid/mapper.py` — maps graph to BitGrid program JSON.
- `bitgrid/emulator.py` — two-phase grid emulator.
- `bitgrid/router.py` — simple Manhattan router that inserts ROUTE4 pass-through cells.
- `bitgrid/cli/compile_expr.py` — CLI to compile expression to graph/program.
- `bitgrid/cli/run_emulator.py` — CLI to emulate with CSV I/O.
- `bitgrid/cli/demo_route4.py` — CLI to demo directional routing with ROUTE4.

## Branches

- main — active BitGrid toolchain (expression → graph → grid → emulator).
- master — legacy code (older GUI-based simulator). Kept for history.

## Development

- No external dependencies; Python 3.9+ recommended.
- Run unit smoke via the commands above.
