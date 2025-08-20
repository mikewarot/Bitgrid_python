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
    ast.Mult: 'MUL',  # will be lowered to shift-add partial products
}
SUPPORTED_UNARYOPS = {
    ast.Invert: 'NOT',
}


class ExprToGraph:
    def __init__(self, var_widths: Dict[str, int], var_signed: Dict[str, bool] | None = None):
        self.var_widths = var_widths
        self.var_signed = var_signed or {k: False for k in var_widths}
        self.counter = 0
        self.graph = Graph()
        self.signed: Dict[str, bool] = {}
        for v, w in var_widths.items():
            self.graph.add_input(v, w)
            self.signed[v] = bool(self.var_signed.get(v, False))

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
            self.signed[cid] = (val < 0)
            return cid, width
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Invert):
                op = 'NOT'
            else:
                raise ValueError(f'Unsupported unary op: {ast.dump(node.op)}')
            a_id, a_w = self._visit(node.operand)
            nid = self._new_id(op.lower())
            self.graph.add_node(Node(id=nid, op=op, inputs=[a_id], width=a_w))
            self.signed[nid] = self.signed.get(a_id, False)
            return nid, a_w
        if isinstance(node, ast.BinOp) and type(node.op) in SUPPORTED_BINOPS:
            op = SUPPORTED_BINOPS[type(node.op)]
            left_id, lw = self._visit(node.left)
            right_id, rw = self._visit(node.right)
            width = max(lw, rw)
            params = {}
            if op == 'MUL':
                if self.signed.get(left_id, False) or self.signed.get(right_id, False):
                    return self._lower_mul_signed(left_id, lw, right_id, rw)
                return self._lower_mul(left_id, lw, right_id, rw)
            if op in ('SHL', 'SHR'):
                # Right must be const for prototype
                rid_node = node.right
                if not isinstance(rid_node, ast.Constant) or not isinstance(rid_node.value, int):
                    raise ValueError('Shift amount must be constant integer')
                params['amount'] = rid_node.value
                if op == 'SHR' and self.signed.get(left_id, False):
                    op = 'SAR'
                # set width conservatively
                if op == 'SHL':
                    width = max(1, lw + int(params['amount']))
                else:
                    width = max(1, lw)
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
            # signedness propagation
            if op in ('AND','OR','XOR'):
                self.signed[nid] = self.signed.get(left_id, False) or self.signed.get(right_id, False)
            elif op in ('ADD',):
                self.signed[nid] = self.signed.get(left_id, False) or self.signed.get(right_id, False)
            elif op in ('SHL','SHR','SAR'):
                self.signed[nid] = self.signed.get(left_id, False)
            else:
                self.signed[nid] = False
            return nid, width
        raise ValueError(f'Unsupported expression node: {ast.dump(node)}')

    def _lower_mul(self, left_id: str, lw: int, right_id: str, rw: int):
        # shift-and-add partial products: sum_{i=0..rw-1} ((left << i) AND bit(right,i))
        result_w = lw + rw
        partials = []
        for i in range(rw):
            # bit extract node
            bit_id = self._new_id('bit')
            self.graph.add_node(Node(id=bit_id, op='BIT', inputs=[right_id], params={'index': i}, width=1))
            # shift left by i
            if i == 0:
                shl_id = left_id
                shl_w = lw
            else:
                amt_id = self._new_id('const')
                self.graph.add_const(amt_id, i, max(1, i.bit_length()))
                shl_id = self._new_id('shl')
                self.graph.add_node(Node(id=shl_id, op='SHL', inputs=[left_id, amt_id], params={'amount': i}, width=result_w))
                shl_w = result_w
            # mask by bit (broadcast handled in mapper)
            and_id = self._new_id('and')
            self.graph.add_node(Node(id=and_id, op='AND', inputs=[shl_id, bit_id], width=result_w))
            partials.append((and_id, result_w))
        if not partials:
            zero_id = self._new_id('const')
            self.graph.add_const(zero_id, 0, 1)
            return zero_id, 1
        # accumulate via adds
        acc_id, acc_w = partials[0]
        for pid, pw in partials[1:]:
            add_id = self._new_id('add')
            self.graph.add_node(Node(id=add_id, op='ADD', inputs=[acc_id, pid], width=result_w))
            acc_id = add_id
            acc_w = result_w
        return acc_id, result_w

    def _lower_mul_signed(self, left_id: str, lw: int, right_id: str, rw: int):
        # Signed multiply via abs/abs * then negate if signs differ
        # Get sign bits
        sL_id = self._new_id('bit')
        self.graph.add_node(Node(id=sL_id, op='BIT', inputs=[left_id], params={'index': lw - 1}, width=1))
        sR_id = self._new_id('bit')
        self.graph.add_node(Node(id=sR_id, op='BIT', inputs=[right_id], params={'index': rw - 1}, width=1))
        # abs(a) = (a XOR sL) + sL
        ax_xor_id = self._new_id('xor')
        self.graph.add_node(Node(id=ax_xor_id, op='XOR', inputs=[left_id, sL_id], width=lw))
        ax_id = self._new_id('add')
        self.graph.add_node(Node(id=ax_id, op='ADD', inputs=[ax_xor_id, sL_id], width=lw))
        # abs(b) = (b XOR sR) + sR
        bx_xor_id = self._new_id('xor')
        self.graph.add_node(Node(id=bx_xor_id, op='XOR', inputs=[right_id, sR_id], width=rw))
        bx_id = self._new_id('add')
        self.graph.add_node(Node(id=bx_id, op='ADD', inputs=[bx_xor_id, sR_id], width=rw))
        # unsigned multiply abs values
        uprod_id, uprod_w = self._lower_mul(ax_id, lw, bx_id, rw)
        # sign of product
        sP_id = self._new_id('xor')
        self.graph.add_node(Node(id=sP_id, op='XOR', inputs=[sL_id, sR_id], width=1))
        # negate product if sP==1: prod = (uprod XOR sP) + sP
        pxor_id = self._new_id('xor')
        self.graph.add_node(Node(id=pxor_id, op='XOR', inputs=[uprod_id, sP_id], width=uprod_w))
        p_id = self._new_id('add')
        self.graph.add_node(Node(id=p_id, op='ADD', inputs=[pxor_id, sP_id], width=uprod_w))
        self.signed[p_id] = True
        return p_id, uprod_w
