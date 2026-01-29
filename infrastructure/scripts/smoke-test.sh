#!/usr/bin/env bash
# =====================================================================
# SMOKE TEST - BLUE/RED Stack Health Verification
# =====================================================================
# Tests:
#   1. Network connectivity (cdb_network)
#   2. BLUE stack health endpoints (postgres, redis, candles, regime, allocation, risk, execution)
#   3. Optional: RED stack health (signal, backtest) if running
#
# Usage:
#   ./infrastructure/scripts/smoke-test.sh [--red]
#
# Exit codes:
#   0 = All checks passed
#   1 = Critical failure (BLUE stack unhealthy)
#   2 = Warning (RED stack unhealthy, optional)
# =====================================================================

set -euo pipefail

RED_CHECK=false
if [[ "${1:-}" == "--red" ]]; then
    RED_CHECK=true
fi

BLUE_SERVICES=(
    "cdb_postgres:5432"
    "cdb_redis:6379"
    "cdb_candles:5004"
    "cdb_regime:5005"
    "cdb_allocation:5006"
    "cdb_risk:5002"
    "cdb_execution:5003"
)

RED_SERVICES=(
    "cdb_signal:5001"
)

FAIL_COUNT=0
WARN_COUNT=0

echo "=========================================="
echo "BLUE/RED STACK SMOKE TEST"
echo "=========================================="
echo ""

# Check external network
echo "[1/3] Checking cdb_network..."
if docker network inspect cdb_network >/dev/null 2>&1; then
    echo "✅ cdb_network exists"
else
    echo "❌ cdb_network NOT FOUND"
    echo ""
    echo "Create network with:"
    echo "  docker network create cdb_network"
    exit 1
fi
echo ""

# Check BLUE stack
echo "[2/3] Checking BLUE stack services..."
for service in "${BLUE_SERVICES[@]}"; do
    name="${service%:*}"
    port="${service#*:}"
    
    echo -n "  ${name}:${port} ... "
    
    # Check if container running
    if ! docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
        echo "❌ NOT RUNNING"
        ((FAIL_COUNT++))
        continue
    fi
    
    # Check health endpoint (skip for postgres/redis)
    if [[ "${name}" == "cdb_postgres" ]] || [[ "${name}" == "cdb_redis" ]]; then
        echo "✅ RUNNING"
        continue
    fi
    
    health_url="http://localhost:${port}/health"
    if curl -sf "${health_url}" >/dev/null 2>&1; then
        echo "✅ HEALTHY"
    else
        echo "❌ UNHEALTHY (${health_url} unreachable)"
        ((FAIL_COUNT++))
    fi
done
echo ""

# Check RED stack (optional)
if [[ "${RED_CHECK}" == "true" ]]; then
    echo "[3/3] Checking RED stack services..."
    for service in "${RED_SERVICES[@]}"; do
        name="${service%:*}"
        port="${service#*:}"
        
        echo -n "  ${name}:${port} ... "
        
        if ! docker ps --format '{{.Names}}' | grep -q "^${name}$"; then
            echo "⚠️  NOT RUNNING (optional)"
            ((WARN_COUNT++))
            continue
        fi
        
        health_url="http://localhost:${port}/health"
        if curl -sf "${health_url}" >/dev/null 2>&1; then
            echo "✅ HEALTHY"
        else
            echo "⚠️  UNHEALTHY (optional)"
            ((WARN_COUNT++))
        fi
    done
    echo ""
else
    echo "[3/3] Skipping RED stack (use --red to check)"
    echo ""
fi

# Summary
echo "=========================================="
echo "SMOKE TEST RESULTS"
echo "=========================================="
if [[ ${FAIL_COUNT} -eq 0 ]]; then
    echo "✅ BLUE stack: ALL CHECKS PASSED"
    if [[ "${RED_CHECK}" == "true" ]]; then
        if [[ ${WARN_COUNT} -eq 0 ]]; then
            echo "✅ RED stack: ALL CHECKS PASSED"
        else
            echo "⚠️  RED stack: ${WARN_COUNT} warnings (non-critical)"
        fi
    fi
    echo ""
    echo "System ready for trading operations."
    exit 0
else
    echo "❌ BLUE stack: ${FAIL_COUNT} CRITICAL FAILURES"
    echo ""
    echo "System NOT ready. Fix BLUE stack before proceeding."
    exit 1
fi
