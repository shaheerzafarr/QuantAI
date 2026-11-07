import requests

def test_live_whale_trades():
    r = requests.get("https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT&limit=500")
    trades = r.json()
    whales = []
    whale_buys = 0.0
    whale_sells = 0.0
    for t in trades:
        p = float(t['p'])
        q = float(t['q'])
        notional = p * q
        if notional >= 50_000.0:
            is_taker_sell = t['m'] # True means buyer was maker, taker was seller
            if not is_taker_sell:
                whale_buys += notional
            else:
                whale_sells += notional
            whales.append({
                "price": p,
                "qty": q,
                "notional": notional,
                "side": "SELL" if is_taker_sell else "BUY"
            })
    print(f"Total aggTrades: {len(trades)}")
    print(f"Large Whale Trades (>= $50k): {len(whales)}")
    print(f"Whale Buy Volume : ${whale_buys:,.2f}")
    print(f"Whale Sell Volume: ${whale_sells:,.2f}")
    print(f"Whale Net Delta  : ${whale_buys - whale_sells:+,.2f}")
    for w in whales[:3]:
        print(f"  -> {w['side']} @ ${w['price']:,.2f} | Notional: ${w['notional']:,.2f}")

if __name__ == "__main__":
    test_live_whale_trades()

