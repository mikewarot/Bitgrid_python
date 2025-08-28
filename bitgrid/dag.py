from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Callable, Optional

from .graph import Graph, Node


@dataclass
class DAGAnalysis:
    topo_order: List[str]
    levels: Dict[str, int]
    level_nodes: List[List[str]]
    node_weight: Dict[str, int]
    dist: Dict[str, int]
    pred: Dict[str, Optional[str]]
    critical_path_len: int
    critical_path: List[str]
    per_output_depth: Dict[str, int]


def build_edges(g: Graph) -> List[Tuple[str, str]]:
    edges: List[Tuple[str, str]] = []
    for nid, n in g.nodes.items():
        for i in n.inputs:
            if i in g.nodes:  # only link to known nodes/inputs/consts/outputs
                edges.append((i, nid))
    return edges


def topo_sort(g: Graph) -> List[str]:
    indeg: Dict[str, int] = {nid: 0 for nid in g.nodes}
    for _, dst in build_edges(g):
        indeg[dst] += 1
    q: List[str] = [nid for nid, d in indeg.items() if d == 0]
    order: List[str] = []
    while q:
        nid = q.pop(0)
        order.append(nid)
        for src, dst in build_edges(g):
            if src == nid:
                indeg[dst] -= 1
                if indeg[dst] == 0:
                    q.append(dst)
    if len(order) != len(g.nodes):
        # cycle or disconnected? For our graphs, this indicates an error.
        # Return the partial order for diagnostics.
        return order
    return order


def levelize(g: Graph, order: Optional[List[str]] = None) -> Tuple[Dict[str, int], List[List[str]]]:
    if order is None:
        order = topo_sort(g)
    level: Dict[str, int] = {}
    for nid in order:
        n = g.nodes[nid]
        if n.op in ('INPUT', 'CONST'):
            level[nid] = 0
        else:
            parent_levels = [level[i] for i in n.inputs if i in level]
            level[nid] = (max(parent_levels) + 1) if parent_levels else 0
    max_level = max(level.values()) if level else 0
    buckets: List[List[str]] = [[] for _ in range(max_level + 1)]
    for nid, lv in level.items():
        buckets[lv].append(nid)
    return level, buckets


def longest_paths(
    g: Graph,
    weight_fn: Optional[Callable[[Node], int]] = None,
    order: Optional[List[str]] = None,
) -> Tuple[Dict[str, int], Dict[str, Optional[str]]]:
    if order is None:
        order = topo_sort(g)
    if weight_fn is None:
        def default_weight(n: Node) -> int:
            # Count logic ops as 1, treat INPUT/CONST as 0, also OUTPUT as 0 (acts as tap)
            return 0 if n.op in ('INPUT', 'CONST', 'OUTPUT') else 1
        weight_fn = default_weight
    dist: Dict[str, int] = {nid: 0 for nid in g.nodes}
    pred: Dict[str, Optional[str]] = {nid: None for nid in g.nodes}
    for nid in order:
        n = g.nodes[nid]
        w = weight_fn(n)
        best_parent = None
        best = 0
        for i in n.inputs:
            if i in dist:
                if dist[i] > best:
                    best = dist[i]
                    best_parent = i
        dist[nid] = best + w
        pred[nid] = best_parent
    return dist, pred


def reconstruct_path(pred: Dict[str, Optional[str]], end: str) -> List[str]:
    path: List[str] = []
    cur: Optional[str] = end
    while cur is not None:
        path.append(cur)
        cur = pred.get(cur)
    path.reverse()
    return path


def analyze_dag(g: Graph) -> DAGAnalysis:
    order = topo_sort(g)
    levels_map, level_nodes = levelize(g, order)
    dist, pred = longest_paths(g, order=order)
    # Choose a critical endpoint as the max over OUTPUT nodes if present, else any node
    endpoints = list(g.outputs.keys()) or list(g.nodes.keys())
    end = max(endpoints, key=lambda nid: dist.get(nid, 0))
    crit_len = dist.get(end, 0)
    crit_path = reconstruct_path(pred, end)
    # Per-output depth
    per_out: Dict[str, int] = {name: dist.get(name, 0) for name in g.outputs}
    # Node weights map for reference
    node_weight = {nid: (0 if g.nodes[nid].op in ('INPUT', 'CONST', 'OUTPUT') else 1) for nid in g.nodes}
    return DAGAnalysis(
        topo_order=order,
        levels=levels_map,
        level_nodes=level_nodes,
        node_weight=node_weight,
        dist=dist,
        pred=pred,
        critical_path_len=crit_len,
        critical_path=crit_path,
        per_output_depth=per_out,
    )


def to_dot(g: Graph, levels: Optional[Dict[str, int]] = None) -> str:
    if levels is None:
        levels, _ = levelize(g)
    # Basic Graphviz DOT for a directed acyclic graph
    lines: List[str] = ["digraph G {", "  rankdir=LR;"]
    # ranks per level
    inv_levels: Dict[int, List[str]] = {}
    for nid, lv in levels.items():
        inv_levels.setdefault(lv, []).append(nid)
    for lv, nodes in sorted(inv_levels.items()):
        lines.append("  { rank=same; " + ' '.join(f'"{n}"' for n in nodes) + " }")
    # node styles
    def color(op: str) -> str:
        if op in ('INPUT', 'CONST'):
            return 'lightgray'
        if op in ('OUTPUT',):
            return 'gold'
        if op in ('ADD','SUB'):
            return 'lightblue'
        if op in ('AND','OR','XOR','NOT'):
            return 'palegreen'
        if op in ('SHL','SHR','SAR','BIT'):
            return 'khaki'
        if op in ('MUL',):
            return 'salmon'
        return 'white'
    for nid, n in g.nodes.items():
        label = f"{nid}\n{n.op}[{n.width}]"
        lines.append(f'  "{nid}" [label="{label}", style=filled, fillcolor={color(n.op)}];')
    # edges
    for src, dst in build_edges(g):
        lines.append(f'  "{src}" -> "{dst}";')
    lines.append("}")
    return "\n".join(lines)
