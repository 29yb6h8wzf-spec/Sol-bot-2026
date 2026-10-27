"""Public, unauthenticated Binance USDT-M Futures data via ccxt."""
import time
import math


class MarketDataError(RuntimeError):
    pass


def closed_futures_bars(symbol, timeframe, limit=1001):
    import ccxt
    exchange = ccxt.binanceusdm({'enableRateLimit': True, 'timeout': 15000})
    try:
        markets = exchange.load_markets()
        market = markets.get(symbol)
        if not market or not market.get('swap') or not market.get('linear') or market.get('active') is False or market.get('settle') != 'USDT':
            raise MarketDataError('not an active linear perpetual futures symbol')
        if timeframe not in exchange.timeframes:
            raise MarketDataError('unsupported timeframe')
        duration = exchange.parse_timeframe(timeframe) * 1000
        rows = None
        for attempt in range(3):
            try:
                rows = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                break
            except (ccxt.RateLimitExceeded, ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable):
                if attempt == 2:
                    raise MarketDataError('exchange temporarily unavailable after retries')
                time.sleep(0.5 * (2 ** attempt))
        if not rows:
            raise MarketDataError('empty OHLCV response')
        now = exchange.milliseconds()
        for row in rows:
            if (not isinstance(row, (list, tuple)) or len(row) < 6
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) for x in row[:6])
                or row[0] < 0 or row[0] % duration
                or min(row[1:5]) <= 0 or row[5] < 0
                or not row[3] <= row[1] <= row[2]
                or not row[3] <= row[4] <= row[2]):
                raise MarketDataError('invalid futures candle')
        closed = [row for row in rows if row[0] + duration <= now]
        if len(closed) < 1000:
            raise MarketDataError('insufficient closed candles')
        if now - (closed[-1][0] + duration) > duration + 120000:
            raise MarketDataError('stale futures candles')
        for i, row in enumerate(closed):
            if (len(row) < 6 or row[0] % duration or min(row[1:5]) <= 0
                or not row[3] <= row[4] <= row[2] or row[5] < 0
                or (i and row[0] - closed[i-1][0] != duration)):
                raise MarketDataError('invalid or gapped futures candles')
        return exchange, market, closed
    except Exception:
        exchange.close() if hasattr(exchange, 'close') else None
        raise
