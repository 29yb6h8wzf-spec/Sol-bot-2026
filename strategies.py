"""Rule-based indicator strategies. Scores are heuristic, not probabilities."""
def ema_series(values, n):
    out = [values[0]]
    a = 2 / (n + 1)
    for v in values[1:]:
        out.append(a * v + (1 - a) * out[-1])
    return out

def rsi(values, n=14):
    if len(values) < n + 2:
        return 50.0
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gain = sum(max(x, 0) for x in changes[:n]) / n
    loss = sum(max(-x, 0) for x in changes[:n]) / n
    for x in changes[n:]:
        gain = (gain * (n - 1) + max(x, 0)) / n
        loss = (loss * (n - 1) + max(-x, 0)) / n
    return 100 if loss == 0 else 100 - 100 / (1 + gain / loss)

def bands(values, n=20):
    sample = values[-n:]
    avg = sum(sample) / len(sample)
    std = (sum((x - avg) ** 2 for x in sample) / len(sample)) ** .5
    return avg - 2 * std, avg + 2 * std

def atr(candles, n=14):
    tr = []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i-1]
        tr.append(max(c['high']-c['low'], abs(c['high']-p['close']), abs(c['low']-p['close'])))
    return sum(tr[-n:]) / n

def adx(candles, n=14):
    if len(candles) < 2*n + 2:
        return 0
    trs, pdm, mdm = [], [], []
    for i in range(1, len(candles)):
        c, p = candles[i], candles[i-1]
        up, down = c['high'] - p['high'], p['low'] - c['low']
        pdm.append(up if up > down and up > 0 else 0)
        mdm.append(down if down > up and down > 0 else 0)
        trs.append(max(c['high']-c['low'], abs(c['high']-p['close']), abs(c['low']-p['close'])))
    def smooth(xs):
        out = [sum(xs[:n])]
        for v in xs[n:]:
            out.append(out[-1] - out[-1] / n + v)
        return out
    t, plus, minus = smooth(trs), smooth(pdm), smooth(mdm)
    dx = []
    for a, b, v in zip(plus, minus, t):
        p, m = (100*a/v if v else 0), (100*b/v if v else 0)
        dx.append(100*abs(p-m)/(p+m) if p+m else 0)
    if len(dx) < n:
        return 0
    result = sum(dx[:n])/n
    for d in dx[n:]:
        result = (result*(n-1)+d)/n
    return result

def candidates(five, four):
    closes = [c['close'] for c in five]
    four_closes = [c['close'] for c in four]
    e20, e50 = ema_series(four_closes,20)[-1], ema_series(four_closes,50)[-1]
    e9 = ema_series(closes,9)
    e21 = ema_series(closes,21)
    macd = [a-b for a,b in zip(ema_series(closes,12),ema_series(closes,26))]
    signal = ema_series(macd,9)
    lo, hi = bands(closes)
    strength, volatility, momentum = adx(four), atr(five), rsi(closes)
    avg_vol = sum(c['volume'] for c in five[-13:-1])/12
    vol_ratio = five[-1]['volume']/avg_vol if avg_vol else 0
    price = closes[-1]
    setups = []
    def add(name, side, condition, score, reason):
        if condition:
            setups.append({'strategy':name,'direction':side,'score':round(min(95,score)),
                           'reason':reason,'atr':volatility})
    # Strong 4h trend + 5m EMA pullback/reclaim, with ADX strength.
    for side in ('LONG','SHORT'):
        up = side == 'LONG'
        trend = e20 > e50 if up else e20 < e50
        reclaim = (closes[-2] <= e9[-2] and price > e9[-1]) if up else (closes[-2] >= e9[-2] and price < e9[-1])
        aligned = e9[-1] > e21[-1] if up else e9[-1] < e21[-1]
        add('EMA_ADX',side,trend and reclaim and aligned and strength >= 20 and vol_ratio >= 0.8,
            60 + min(15,(strength-20)) + min(15,vol_ratio*8),
            f'4h ADX {strength:.1f}; EMA reclaim; volume x{vol_ratio:.2f}')
    # Mean reversion only if market is not strongly trending.
    add('RSI_BOLL','LONG',strength < 25 and closes[-2] < bands(closes[:-1])[0] and price > lo and momentum < 45,
        65+max(0,45-momentum)/3,f'RSI {momentum:.1f}; lower band reclaim; ADX {strength:.1f}')
    add('RSI_BOLL','SHORT',strength < 25 and closes[-2] > bands(closes[:-1])[1] and price < hi and momentum > 55,
        65+max(0,momentum-55)/3,f'RSI {momentum:.1f}; upper band reclaim; ADX {strength:.1f}')
    # Confirmed MACD histogram crossover with minimum volume.
    add('MACD_VOLUME','LONG',macd[-2] <= signal[-2] and macd[-1] > signal[-1] and vol_ratio >= 1.2 and momentum > 50,
        65+min(20,vol_ratio*10),f'MACD bullish crossover; volume x{vol_ratio:.2f}')
    add('MACD_VOLUME','SHORT',macd[-2] >= signal[-2] and macd[-1] < signal[-1] and vol_ratio >= 1.2 and momentum < 50,
        65+min(20,vol_ratio*10),f'MACD bearish crossover; volume x{vol_ratio:.2f}')
    return setups, {'adx':strength,'rsi':momentum,'volume':vol_ratio,'atr':volatility,'macd':macd[-1]-signal[-1]}
