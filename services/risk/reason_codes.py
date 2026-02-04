"""
Reason Codes for Decision Contract v1

These codes are returned by decide_trade() when a trade is blocked.
Each code represents a specific failure condition in the risk gating logic.
"""

# Circuit Breaker / Regime
RC_001 = "RC_001"  # Circuit Breaker active or unfavorable regime

# Safety / Anomaly
RC_002 = "RC_002"  # Panic Mode: returns too low or price change too high

# Data Freshness
RC_003 = "RC_003"  # Stale Data: data older than threshold
RC_004 = "RC_004"  # Data Silence: no ticks for threshold period

# Signal Quality
RC_010 = "RC_010"  # Signal quality insufficient: pct_change or volume too low

# Portfolio / Execution
RC_020 = "RC_020"  # Daily Drawdown Limit reached
RC_021 = "RC_021"  # Total Exposure Limit reached
RC_022 = "RC_022"  # Slippage too high
