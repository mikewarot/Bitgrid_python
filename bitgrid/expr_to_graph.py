from __future__ import annotations

import ast
from typing import Dict, Tuple
from .graph import Graph, Node


SUPPORTED_BINOPS = {
    ast.BitAnd: 'AND',
    ast.BitOr: 'OR',
    ast.BitXor: 'XOR',
    ast.LShift: 'SHL',
    ast.RShift: 'SHR',
    ast.Add: 'ADD',
    ast.Sub: 'SUB',  # will be lowered to ADD with two's complement
}
SUPPORTED_UNARYOPS = {
    ast.Invert: 'NOT',
}


class ExprToGraph:
    def __init__(self, var_widths: Dict[str, int]):
        self.var_widths = var_widths
        self.counter = 0
        self.graph = Graph()
        for v, w in var_widths.items():
            self.graph.add_input(v, w)

    def _new_id(self, prefix: str) -> str:
        self.counter += 1
        return f"{prefix}_{self.counter}"

    def parse(self, expr: str) -> Graph:
        tree = ast.parse(expr, mode='exec')
        # Expect a single assignment like out = <expr>
        if not tree.body or not isinstance(tree.body[0], ast.Assign):
            raise ValueError('Expression must be an assignment like: out = a & b')
        assign = tree.body[0]
        if len(assign.targets) != 1 or not isinstance(assign.targets[0], ast.Name):
            raise ValueError('Left side must be a single variable name')
        out_name = assign.targets[0].id
        out_id, out_width = self._visit(assign.value)
        self.graph.set_output(out_name, out_id, out_width)
        return self.graph

    def _visit(self, node) -> Tuple[str, int]:
        if isinstance(node, ast.Name):
            if node.id not in self.var_widths:
                raise ValueError(f'Unknown variable {node.id}')
            return node.id, self.var_widths[node.id]
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            # width: minimal to hold value, at least 1
            val = node.value
            width = max(1, val.bit_length())
            cid = self._new_id('const')
            self.graph.add_const(cid, val, width)
            return cid, width
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Invert):
                op = 'NOT'
            else:
                raise ValueError(f'Unsupported unary op: {ast.dump(node.op)}')
            a_id, a_w = self._visit(node.operand)
            nid = self._new_id(op.lower())
            self.graph.add_node(Node(id=nid, op=op, inputs=[a_id], width=a_w))
            return nid, a_w
        if isinstance(node, ast.BinOp) and type(node.op) in SUPPORTED_BINOPS:
            op = SUPPORTED_BINOPS[type(node.op)]
            left_id, lw = self._visit(node.left)
            right_id, rw = self._visit(node.right)
            width = max(lw, rw)
            params = {}
            if op in ('SHL', 'SHR'):
                # Right must be const for prototype
                rid_node = node.right
                if not isinstance(rid_node, ast.Constant) or not isinstance(rid_node.value, int):
                    raise ValueError('Shift amount must be constant integer')
                params['amount'] = rid_node.value
            if op == 'SUB':
                # Lower to ADD with two's complement of right; extend width+1 for carry
                width = max(lw, rw) + 1
                # create inverter and +1
                not_id = self._new_id('not')
                self.graph.add_node(Node(id=not_id, op='NOT', inputs=[right_id], width=rw))
                one_id = self._new_id('const')
                self.graph.add_const(one_id, 1, 1)
                add1_id = self._new_id('add')
                self.graph.add_node(Node(id=add1_id, op='ADD', inputs=[not_id, one_id], width=max(rw, 1)))
                right_id = add1_id
                op = 'ADD'
            nid = self._new_id(op.lower())
            self.graph.add_node(Node(id=nid, op=op, inputs=[left_id, right_id], params=params, width=width))
            return nid, width
        raise ValueError(f'Unsupported expression node: {ast.dump(node)}')
