from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
import json


# High-level graph of multi-bit operations

@dataclass
class Signal:
    name: str
    width: int


@dataclass
class Node:
    id: str
    op: str  # 'AND','OR','XOR','NOT','SHL','SHR','ADD','CONST','INPUT','OUTPUT','ASSIGN'
    inputs: List[str]  # node ids or signal names for leaf INPUT/CONST
    params: Dict[str, Any] = field(default_factory=dict)  # e.g., shift amount, const value
    width: int = 1


@dataclass
class Graph:
    nodes: Dict[str, Node] = field(default_factory=dict)
    inputs: Dict[str, Signal] = field(default_factory=dict)
    outputs: Dict[str, Signal] = field(default_factory=dict)

    def add_input(self, name: str, width: int):
        self.inputs[name] = Signal(name, width)
        self.nodes[name] = Node(id=name, op='INPUT', inputs=[], width=width)

    def add_const(self, id_: str, value: int, width: int):
        self.nodes[id_] = Node(id=id_, op='CONST', inputs=[], params={'value': value}, width=width)

    def add_node(self, node: Node):
        self.nodes[node.id] = node

    def set_output(self, name: str, source_id: str, width: int):
        self.outputs[name] = Signal(name, width)
        self.nodes[name] = Node(id=name, op='OUTPUT', inputs=[source_id], width=width)

    def to_json(self) -> str:
        data = {
            'nodes': {nid: {
                'op': n.op,
                'inputs': n.inputs,
                'params': n.params,
                'width': n.width,
            } for nid, n in self.nodes.items()},
            'inputs': {k: v.width for k, v in self.inputs.items()},
            'outputs': {k: v.width for k, v in self.outputs.items()},
        }
        return json.dumps(data, indent=2)

    @staticmethod
    def from_json(s: str) -> 'Graph':
        j = json.loads(s)
        g = Graph()
        for name, w in j.get('inputs', {}).items():
            g.add_input(name, w)
        for nid, d in j.get('nodes', {}).items():
            if nid in g.nodes:  # skip inputs already added
                continue
            g.nodes[nid] = Node(id=nid, op=d['op'], inputs=d['inputs'], params=d.get('params', {}), width=d.get('width', 1))
        for name, w in j.get('outputs', {}).items():
            # outputs are nodes with id=name already in nodes
            g.outputs[name] = Signal(name, w)
        return g

    def save(self, path: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

    @staticmethod
    def load(path: str) -> 'Graph':
        with open(path, 'r', encoding='utf-8') as f:
            return Graph.from_json(f.read())
