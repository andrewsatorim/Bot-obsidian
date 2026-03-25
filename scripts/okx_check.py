"""Quick OKX connectivity and data check.

Usage:
    pip install ccxt
    python scripts/okx_check.py

Verifies: API access, market data, funding rates, open interest.
"""
from __future__ import annotations

import json
import ccxt


def main():
    exchange = ccxt.okx({"enableRateLimit": True})

    print("=== OKX Exchange Check ===\n")

    # 1. Markets
    markets = exchange.load_markets()
    swap_markets = [m for m in markets if markets[m].get("swap")]
    print(f"Total markets: {len(markets)}")
    print(f"Perpetual swaps: {len(swap_markets)}")

    # 2. Ticker
    symbol = "BTC/USDT:USDT"
    ticker = exchange.fetch_ticker(symbol)
    print(f"\n--- {symbol} Ticker ---")
    print(f"  Last:    ${ticker['last']:,.2f}")
    print(f"  Bid:     ${ticker['bid']:,.2f}")
    print(f"  Ask:     ${ticker['ask']:,.2f}")
    print(f"  Volume:  {ticker['quoteVolume']:,.0f} USDT (24h)")
    print(f"  Change:  {ticker['percentage']:+.2f}%")

    # 3. OHLCV
    candles = exchange.fetch_ohlcv(symbol, "1h", limit=5)
    print(f"\n--- Last 5 hourly candles ---")
    for c in candles:
        from datetime import datetime
        ts = datetime.utcfromtimestamp(c[0] / 1000).strftime("%Y-%m-%d %H:%M")
        print(f"  {ts} | O:{c[1]:,.0f} H:{c[2]:,.0f} L:{c[3]:,.0f} C:{c[4]:,.0f} V:{c[5]:,.0f}")

    # 4. Funding rate
    try:
        funding = exchange.fetch_funding_rate(symbol)
        print(f"\n--- Funding Rate ---")
        print(f"  Current: {funding.get('fundingRate', 0):.6f}")
        print(f"  Next:    {funding.get('nextFundingRate', 'N/A')}")
    except Exception as e:
        print(f"\n  Funding rate error: {e}")

    # 5. Open Interest
    try:
        oi = exchange.fetch_open_interest(symbol)
        print(f"\n--- Open Interest ---")
        print(f"  OI: {oi.get('openInterestAmount', 0):,.2f} BTC")
        print(f"  OI Value: ${oi.get('openInterestValue', 0):,.0f}")
    except Exception as e:
        print(f"\n  Open interest error: {e}")

    # 6. Order book
    ob = exchange.fetch_order_book(symbol, limit=5)
    print(f"\n--- Order Book (top 5) ---")
    print(f"  Bids: {ob['bids'][0][0]:,.2f} ({ob['bids'][0][1]:.4f})")
    print(f"  Asks: {ob['asks'][0][0]:,.2f} ({ob['asks'][0][1]:.4f})")
    spread = ob['asks'][0][0] - ob['bids'][0][0]
    print(f"  Spread: ${spread:.2f} ({spread / ticker['last'] * 100:.4f}%)")

    # 7. Available perpetual pairs
    print(f"\n--- Top perpetual pairs by volume ---")
    tickers = exchange.fetch_tickers([m for m in swap_markets[:20]])
    sorted_tickers = sorted(tickers.values(), key=lambda t: t.get("quoteVolume", 0) or 0, reverse=True)
    for t in sorted_tickers[:10]:
        vol = t.get("quoteVolume", 0) or 0
        print(f"  {t['symbol']:30s} Vol: ${vol:>15,.0f}  Change: {t.get('percentage', 0) or 0:+.2f}%")

    print("\n=== OKX check complete ===")


if __name__ == "__main__":
    main()
