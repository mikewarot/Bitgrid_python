from __future__ import annotations

from typing import Dict, Tuple
from ..graph import Graph, Node

# Build a graph for f32 multiply: prod = a * b (IEEE-754 single)
# Simplified: handles normal numbers and zero; rounding: truncation
# Bit layout: [31]=sign, [30:23]=exp (8 bits), [22:0]=frac (23 bits)

EXP_BITS = 8
FRAC_BITS = 23
BIAS = 127


def build_f32_mul_graph(a_name: str = 'a', b_name: str = 'b', out_name: str = 'prod') -> Graph:
    g = Graph()
    # inputs as 32-bit unsigned words
    g.add_input(a_name, 32)
    g.add_input(b_name, 32)

    def add_node(id_: str, op: str, inputs, width: int, params=None):
        g.add_node(Node(id=id_, op=op, inputs=list(inputs), width=width, params=params or {}))

    # Extract sign, exp, frac
    def bit(id_, i):
        nid = f"{id_}_b{i}"
        add_node(nid, 'BIT', [id_], 1, {'index': i})
        return nid

    def slice_bits(id_, lo, hi):
        bits = [bit(id_, i) for i in range(lo, hi+1)]
        acc = None
        for i, b in enumerate(bits):
            if i == 0:
                acc = b
            else:
                # shift acc by 1 and add b
                s = f"s_{id_}_{lo+i}"
                add_node(s, 'SHL', [acc, const(1, 1)], i+1, {'amount': 1})
                a = f"a_{id_}_{lo+i}"
                add_node(a, 'ADD', [s, b], i+1)
                acc = a
        return acc, len(bits)

    def const(v: int, w: int = 32):
        nid = f"c_{v}_{w}_{len(g.nodes)}"
        g.add_const(nid, v, w)
        return nid

    # sign
    sa = bit(a_name, 31)
    sb = bit(b_name, 31)
    sp = f"sp"
    add_node(sp, 'XOR', [sa, sb], 1)

    # exponents (8 bits)
    # Use simple mask and shr to align exponent; then treat as unsigned
    # Extract by building right shifts and mask via BIT assembly
    # Build explicit exponent nodes via bit assembly
    ea_bits = [bit(a_name, i) for i in range(23, 31)]
    eb_bits = [bit(b_name, i) for i in range(23, 31)]

    # Convert bit-vectors to integers by summing shifted bits
    def assemble(prefix: str, bits):
        acc = None
        for i, b in enumerate(bits):
            if acc is None:
                acc = b
            else:
                sid = f"{prefix}_sh{i}"
                add_node(sid, 'SHL', [acc, const(1)], i+1, {'amount': 1})
                aid = f"{prefix}_ad{i}"
                add_node(aid, 'ADD', [sid, b], i+1)
                acc = aid
        return acc, len(bits)

    ea, _ = assemble('ea', ea_bits)
    eb, _ = assemble('eb', eb_bits)

    # fraction fields (23 bits), add implicit leading 1 if exponent != 0 (skip subnormals for now: assume normals)
    ma_bits = [bit(a_name, i) for i in range(0, 23)]
    mb_bits = [bit(b_name, i) for i in range(0, 23)]

    one = const(1, 1)
    # Build mantissa by placing hidden 1 at bit 23: (1<<23) | frac
    def build_m(prefix: str, frac_bits):
        acc = one
        for i in range(23):
            sid = f"{prefix}_sh{i}"
            add_node(sid, 'SHL', [acc, const(1)], i+2, {'amount': 1})
            aid = f"{prefix}_ad{i}"
            add_node(aid, 'ADD', [sid, frac_bits[i]], i+2)
            acc = aid
        return acc

    ma = build_m('ma', ma_bits)
    mb = build_m('mb', mb_bits)

    # mantissa multiply (24x24 -> 48 bits)
    mm_id, mm_w = ExprMulHelper(g).mul(ma, 24, mb, 24)

    # exponent add: ea + eb - bias
    e_sum = 'e_sum'
    add_node(e_sum, 'ADD', [ea, eb], 9)
    e_tmp = 'e_tmp'
    add_node(e_tmp, 'ADD', [e_sum, const(-BIAS, 9)], 9)  # allow growth, use negative const

    # normalize: if top bit of mm_id at position 47 is 1, shift right 24 to get 23 frac bits; else shift right 23
    top47 = 'top47'
    add_node(top47, 'BIT', [mm_id], 1, {'index': 47})
    # path A: shift 24
    mA = 'mA'
    add_node(mA, 'SHR', [mm_id, const(24, 5)], mm_w)
    eA = 'eA'
    add_node(eA, 'ADD', [e_tmp, const(1, 1)], 9)
    # path B: shift 23
    mB = 'mB'
    add_node(mB, 'SHR', [mm_id, const(23, 5)], mm_w)
    # select path by top47: out = (top47 ? mA : mB)
    # Implement as (mB AND ~top) OR (mA AND top) bitwise — approximate mux
    top_not = 'top_not'
    add_node(top_not, 'NOT', [top47], 1)
    selA = 'selA'
    add_node(selA, 'AND', [mA, top47], mm_w)
    selB = 'selB'
    add_node(selB, 'AND', [mB, top_not], mm_w)
    mN = 'mN'
    add_node(mN, 'OR', [selA, selB], mm_w)
    selEA = 'selEA'
    add_node(selEA, 'AND', [eA, top47], 9)
    selEB = 'selEB'
    add_node(selEB, 'AND', [e_tmp, top_not], 9)
    eN = 'eN'
    add_node(eN, 'OR', [selEA, selEB], 9)

    # pack: sign (1) | exponent (8) | frac (23)
    # Take lower 23 bits of mN as frac
    frac_bits_out = []
    for i in range(23):
        bi = f"fp_b{i}"
        add_node(bi, 'BIT', [mN], 1, {'index': i})
        frac_bits_out.append(bi)
    # assemble exponent back to 8 bits (eN low 8)
    exp_bits_out = []
    for i in range(8):
        bi = f"fe_b{i}"
        add_node(bi, 'BIT', [eN], 1, {'index': i})
        exp_bits_out.append(bi)

    # Compose final 32-bit via bitwise OR of shifted fields; represent as running integer
    acc = 'out_acc'
    g.add_const(acc, 0, 32)
    # insert frac
    acc = ExprMulHelper(g).or_bits_into(acc, frac_bits_out, 0)
    # insert exp
    acc = ExprMulHelper(g).or_bits_into(acc, exp_bits_out, 23)
    # insert sign at 31
    acc = ExprMulHelper(g).or_bits_into(acc, [sp], 31)

    g.set_output(out_name, acc, 32)
    return g


class ExprMulHelper:
    def __init__(self, g: Graph):
        self.g = g
        self.i = 0
        # unique id per helper instance to avoid node id collisions across helpers
        if not hasattr(ExprMulHelper, '_uid_counter'):
            ExprMulHelper._uid_counter = 0  # type: ignore[attr-defined]
        self.uid = ExprMulHelper._uid_counter  # type: ignore[attr-defined]
        ExprMulHelper._uid_counter += 1  # type: ignore[attr-defined]

    def nid(self, p: str) -> str:
        self.i += 1
        return f"{p}_{self.uid}_{self.i}"

    def mul(self, a: str, aw: int, b: str, bw: int):
        # shift-add unsigned
        acc = None
        for i in range(bw):
            bi = self.nid('b')
            self.g.add_node(Node(id=bi, op='BIT', inputs=[b], params={'index': i}, width=1))
            shi = self.nid('sh')
            self.g.add_node(Node(id=shi, op='SHL', inputs=[a, self.const(i, 6)], params={'amount': i}, width=aw + bw))
            andi = self.nid('and')
            self.g.add_node(Node(id=andi, op='AND', inputs=[shi, bi], width=aw + bw))
            if acc is None:
                acc = andi
            else:
                addi = self.nid('add')
                self.g.add_node(Node(id=addi, op='ADD', inputs=[acc, andi], width=aw + bw))
                acc = addi
        return acc, aw + bw

    def const(self, v: int, w: int = 32) -> str:
        nid = self.nid('c')
        self.g.add_const(nid, v, w)
        return nid

    def or_bits_into(self, base: str, bits, offset: int) -> str:
        acc = base
        for i, b in enumerate(bits):
            shi = self.nid('or_sh')
            self.g.add_node(Node(id=shi, op='SHL', inputs=[b, self.const(offset + i, 6)], params={'amount': offset + i}, width=offset + i + 1))
            accw = 32 if acc in self.g.nodes else 32
            orid = self.nid('or')
            self.g.add_node(Node(id=orid, op='OR', inputs=[acc, shi], width=32))
            acc = orid
        return acc
