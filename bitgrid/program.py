from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any
import json

# BitGrid program representation

@dataclass
class Cell:
    x: int
    y: int
    # 4 inputs come from a list of sources
    # Each source is a dict: {"type": "const|input|cell", "value" or "name" or {"x","y","out"}}
    inputs: List[Dict[str, Any]]
    # LUT truth table or op descriptor; for prototype we store an op name and mapping to outputs
    op: str  # 'BUF','NOT','AND','OR','XOR','ADD_BIT','SHL_BIT','SHR_BIT'
    params: Dict[str, Any] = field(default_factory=dict)
    # 4 outputs names for wiring referencing; out indices 0..3
    out_names: List[str] = field(default_factory=lambda: ["o0","o1","o2","o3"])


@dataclass
class Program:
    width: int
    height: int
    cells: List[Cell]
    # mapping from signal bit to a source: {"type": "input|cell|const", ...}
    input_bits: Dict[str, List[Dict[str, Any]]]  # name -> list per bit
    output_bits: Dict[str, List[Dict[str, Any]]]  # name -> list per bit
    latency: int

    def to_json(self) -> str:
        return json.dumps({
            'width': self.width,
            'height': self.height,
            'cells': [
                {
                    'x': c.x, 'y': c.y,
                    'inputs': c.inputs,
                    'op': c.op,
                    'params': c.params,
                    'out_names': c.out_names,
                } for c in self.cells
            ],
            'input_bits': self.input_bits,
            'output_bits': self.output_bits,
            'latency': self.latency,
        }, indent=2)

    @staticmethod
    def from_json(s: str) -> 'Program':
        j = json.loads(s)
        return Program(
            width=j['width'],
            height=j['height'],
            cells=[Cell(x=c['x'], y=c['y'], inputs=c['inputs'], op=c['op'], params=c.get('params', {}), out_names=c.get('out_names', ["o0","o1","o2","o3"])) for c in j['cells']],
            input_bits=j['input_bits'],
            output_bits=j['output_bits'],
            latency=j['latency'],
        )

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @staticmethod
    def load(path: str) -> 'Program':
        with open(path, 'r', encoding='utf-8') as f:
            return Program.from_json(f.read())


def passthrough_luts(direction: str) -> List[int]:
    # Build 4 LUTs (16-bit) that route a single input to the specified output direction
    # direction in {'N','E','S','W'} selects which output gets the chosen input; others 0
    # Inputs order: N,E,S,W; index = N | (E<<1) | (S<<2) | (W<<3)
    lutN = lutE = lutS = lutW = 0
    for idx in range(16):
        n = (idx >> 0) & 1
        e = (idx >> 1) & 1
        s = (idx >> 2) & 1
        w = (idx >> 3) & 1
        if direction == 'N':
            lutN |= (n << idx)
        elif direction == 'E':
            lutE |= (e << idx)
        elif direction == 'S':
            lutS |= (s << idx)
        elif direction == 'W':
            lutW |= (w << idx)
    return [lutN, lutE, lutS, lutW]
