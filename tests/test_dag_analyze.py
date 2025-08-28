from __future__ import annotations

from bitgrid.expr_to_graph import ExprToGraph
from bitgrid.dag import analyze_dag


def test_dag_simple_and_xor():
    etg = ExprToGraph({'a': 1, 'b': 1, 'c': 1})
    g = etg.parse('out = (a & b) ^ c')
    a = analyze_dag(g)
    # Expect INPUTs at level 0, two ops AND and XOR increasing levels
    assert a.critical_path_len >= 1
    assert 'out' in a.per_output_depth
    assert a.per_output_depth['out'] >= 1
