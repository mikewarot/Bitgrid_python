"""DEPRECATED: whole-cell modes were removed.

This module intentionally raises on import to prevent use. Configure each
cell side's LUT independently via per-side logic in the physicalizer.
"""

raise ImportError(
    "bitgrid.cell_modes has been removed. Use per-side LUT assignment; do not"
    " treat cells atomically."
)
