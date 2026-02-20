"""
Zentraler Accessor für den Trace-Contract-V1-Toggle.

Governance: trace_contract_v1.md / Phase 9
Default: OFF (0). Alle Trace/Correlation-Writes und ID-Enforcement-Raises
MÜSSEN hinter dieser Funktion stehen.

Liest os.getenv bei jedem Aufruf (kein Modul-Level-Cache),
damit Tests via monkeypatch.setenv umschalten können.
"""

import os


def trace_contract_v1_enabled() -> bool:
    """True nur wenn TRACE_CONTRACT_V1_ENABLED=1."""
    return os.getenv("TRACE_CONTRACT_V1_ENABLED", "0") == "1"
