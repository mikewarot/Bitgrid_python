from __future__ import annotations

import argparse
import json
from typing import Dict, Any
from ..program import Program


def main():
    ap = argparse.ArgumentParser(description='Inspect a Program: dims, I/O names, cells with LUTs and sources.')
    ap.add_argument('--program', required=True)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    prog = Program.load(args.program)
    rep: Dict[str, Any] = {
        'width': prog.width,
        'height': prog.height,
        'inputs': list(prog.input_bits.keys()),
        'outputs': list(prog.output_bits.keys()),
        'cells': [],
    }
    for c in prog.cells:
        rep['cells'].append({
            'x': c.x, 'y': c.y, 'op': c.op,
            'params': c.params,
            'inputs': c.inputs,
        })

    s = json.dumps(rep, indent=2)
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(s)
        print(f'Wrote {args.out}')
    else:
        print(s)


if __name__ == '__main__':
    main()
