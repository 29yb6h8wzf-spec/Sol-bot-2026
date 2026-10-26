import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://data-api.binance.vision/api/v3/klines'
SYMBOL = 'SOLUSDT'

def fetch(interval, limit):
    query = urllib.parse.urlencode({'symbol': SYMBOL, 'interval': interval, 'limit': limit})
    with urllib.request.urlopen(BASE + '?' + query, timeout=15) as r:
        raw = json.load(r)
    return [{'time': int(x[0]), 'high': float(x[2]), 'low': float(x[3]), 'close': float(x[4]), 'volume': float(x[5])} for x in raw[:-1]]

def ema(values, length):
    alpha = 2 / (length + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result

def telegram(message):
    token = os.environ['TELEGRAM_BOT_TOKEN']
    chat_id = os.environ['TELEGRAM_CHAT_ID']
    payload = urllib.parse.urlencode({'chat_id': chat_id, 'text': message}).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=payload, method='POST')
    with urllib.request.urlopen(request, timeout=15) as r:
        return json.load(r)

def main():
    if '--test' in sys.argv:
        telegram('✅ SOL Alert Bot מחובר! הודעת בדיקה בלבד. אין כאן איתות מסחר.')
        print('Test message sent')
        return
    four = fetch('4h', 100)
    five = fetch('5m', 50)
    trend20 = ema([x['close'] for x in four], 20)
    trend50 = ema([x['close'] for x in four], 50)
    last = five[-1]
    prev = five[-13:-1]
    high = max(x['high'] for x in prev)
    low = min(x['low'] for x in prev)
    avg_vol = sum(x['volume'] for x in prev) / len(prev)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    age_min = (now_ms - last['time']) / 60000
    if not 5 <= age_min <= 12:
        print('Last closed candle too old/new; no alert')
        return
    direction = None
    if trend20 > trend50 and last['close'] > high and last['volume'] >= avg_vol * 1.5:
        direction = 'LONG'
        stop = low
    elif trend20 < trend50 and last['close'] < low and last['volume'] >= avg_vol * 1.5:
        direction = 'SHORT'
        stop = high
    else:
        print('No setup')
        return
    entry = last['close']
    stop_pct = abs(entry - stop) / entry * 100
    if not 0.25 <= stop_pct <= 1.5:
        print(f'Stop distance {stop_pct:.2f}% outside filter')
        return
    target = entry + (2 * abs(entry - stop) * (1 if direction == 'LONG' else -1))
    # $40 capital, max 2x, $1 planned risk, before fees/slippage
    notional = min(80, 1 / (stop_pct / 100))
    planned_loss = notional * stop_pct / 100
    candle_time = datetime.fromtimestamp(last['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    telegram(f'🔔 SOLUSDT {direction} — מועמד לבדיקה, לא הוראת מסחר\n'
             f'נר 5 דקות: {candle_time}\n'
             f'כניסה תיאורטית: ${entry:.3f}\n'
             f'סטופ תיאורטי: ${stop:.3f} ({stop_pct:.2f}%)\n'
             f'יעד 2R: ${target:.3f}\n'
             f'חשיפה מרבית לדוגמה: ${notional:.2f}\n'
             f'הפסד מתוכנן לפני עמלות: ${planned_loss:.2f}\n'
             f'EMA20/50 4h: {trend20:.3f}/{trend50:.3f}\n'
             '⚠️ לא נבדקה נזילות, Funding או חדשות. אין ביצוע אוטומטי.')
    print('Alert sent')

if __name__ == '__main__':
    main()
