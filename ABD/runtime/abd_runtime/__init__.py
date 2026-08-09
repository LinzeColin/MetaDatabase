"""ABD runtime control plane.

This package is intentionally separate from frozen acceptance modules. It only
exposes an observation-only HTTP surface and contains no market, Gmail, TAB,
account, recommendation, or order capability.
"""

from .server import VERSION, build_runtime_state, create_server

__all__ = ["VERSION", "build_runtime_state", "create_server"]
