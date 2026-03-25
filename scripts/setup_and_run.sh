#!/usr/bin/env bash
set -e

# ═══════════════════════════════════════════════════════
# Bot-Obsidian: Full Setup & Test Script
# Run this from the project root: bash scripts/setup_and_run.sh
# ═══════════════════════════════════════════════════════

echo "═══ Bot-Obsidian Setup ═══"
echo ""

# 1. Create virtual environment
echo "[1/6] Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
echo "  ✓ venv activated"

# 2. Install dependencies
echo "[2/6] Installing dependencies..."
pip install --upgrade pip -q
pip install -e ".[dev]" -q
echo "  ✓ dependencies installed"

# 3. Run tests
echo "[3/6] Running tests..."
echo ""
pytest tests/ -v --tb=short 2>&1 || echo "  ⚠ some tests may need adjustment"
echo ""

# 4. Check OKX connectivity
echo "[4/6] Checking OKX exchange..."
echo ""
python scripts/okx_check.py 2>&1 || echo "  ⚠ OKX check failed (network issue?)"
echo ""

# 5. Download data and run backtest
echo "[5/6] Running backtest on OKX data..."
echo ""
mkdir -p data
python scripts/okx_backtest.py 2>&1 || echo "  ⚠ backtest failed"
echo ""

# 6. Start paper trading (runs for 60 seconds as demo)
echo "[6/6] Starting paper trading demo (60 seconds)..."
echo "  Press Ctrl+C to stop early"
echo ""
timeout 60 python -m app.main 2>&1 || true
echo ""
echo "═══ Setup Complete ═══"
echo ""
echo "Next steps:"
echo "  • Review backtest results above"
echo "  • If Sharpe > 1.5: ready for testnet"
echo "  • To run bot:  source .venv/bin/activate && python -m app.main"
echo "  • To configure: cp .env.example .env && edit .env"
echo ""
