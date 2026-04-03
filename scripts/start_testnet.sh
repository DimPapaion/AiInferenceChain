#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start_testnet.sh — Start a 3-node InferenceChain testnet on localhost
#
# Starts all three nodes in the background with output piped to log files:
#   data/logs/node0.log, node1.log, node2.log
#
# Usage:
#   chmod +x scripts/start_testnet.sh
#   ./scripts/start_testnet.sh
#
# Stop all nodes:
#   ./scripts/stop_testnet.sh
#   (or: pkill -f node_runner.py)
#
# After startup:
#   Dashboard : http://localhost:8000/ui/
#   API docs  : http://localhost:8000/docs
# ─────────────────────────────────────────────────────────────────────────────

set -e

PYTHON=${PYTHON:-python3}
CONFIG=config/testnet.yaml

mkdir -p data/logs

echo "Starting InferenceChain testnet (3 nodes)..."
echo ""

# Node 0 — genesis bootstrap node (use f=0 for instant commits in dev)
echo "[node-0] Starting on :8000..."
$PYTHON node_runner.py \
  --config $CONFIG \
  --port 8000 \
  --db-path data/node0.db \
  --f 0 \
  > data/logs/node0.log 2>&1 &
echo $! > data/logs/node0.pid

sleep 2   # let node-0 come up before peers try to connect

# Node 1
echo "[node-1] Starting on :8001..."
$PYTHON node_runner.py \
  --config $CONFIG \
  --port 8001 \
  --db-path data/node1.db \
  --f 0 \
  > data/logs/node1.log 2>&1 &
echo $! > data/logs/node1.pid

# Node 2
echo "[node-2] Starting on :8002..."
$PYTHON node_runner.py \
  --config $CONFIG \
  --port 8002 \
  --db-path data/node2.db \
  --f 0 \
  > data/logs/node2.log 2>&1 &
echo $! > data/logs/node2.pid

echo ""
echo "All nodes started."
echo ""
echo "  Dashboard : http://localhost:8000/ui/"
echo "  Logs      : tail -f data/logs/node0.log"
echo "  Stop all  : pkill -f node_runner.py"
echo ""
echo "Dev wallets:"
echo "  python wallet.py import 947f6967eba35761053563545933a3899ed077c4cdb900b90d70f1adf62ccabf --out node0.json"
echo "  python wallet.py import 36b88f136b9e0d1b27f3dbe7856d06968d402960354fe67b0d1df0384158bd69 --out node1.json"
echo "  python wallet.py import a6982723df7dc426f0822073a4bf2ac14d4efd09c72e56451d35e8ea3ba6bb5f --out node2.json"
