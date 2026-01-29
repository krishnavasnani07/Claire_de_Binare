#!/usr/bin/env bash
# =====================================================================
# Network Setup - Create External cdb_network
# =====================================================================
# Creates the external Docker network required by BLUE/RED stacks
#
# Usage:
#   ./infrastructure/scripts/setup-network.sh
# =====================================================================

set -euo pipefail

NETWORK_NAME="cdb_network"

echo "=========================================="
echo "NETWORK SETUP"
echo "=========================================="
echo ""

if docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    echo "✅ Network '${NETWORK_NAME}' already exists"
    echo ""
    docker network inspect "${NETWORK_NAME}" --format '{{.Name}}: {{.Driver}} ({{.Scope}})'
    exit 0
fi

echo "Creating external network: ${NETWORK_NAME}"
docker network create "${NETWORK_NAME}"

echo ""
echo "✅ Network created successfully"
echo ""
docker network inspect "${NETWORK_NAME}" --format '{{.Name}}: {{.Driver}} ({{.Scope}})'
echo ""
echo "You can now start BLUE/RED stacks:"
echo "  docker compose -f compose.blue.yml up -d"
echo "  docker compose -f compose.red.yml up -d"
