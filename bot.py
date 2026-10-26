import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://data-api.binance.vision/api/v3/klines'
SYMBOL = os.environ.get('SYMBOL', 'SOLUSDT')
if SYMBOL not in ('SOLUSDT', 'BTCUSDT', 'ETHUSDT', 'XRPUSDT'):
    raise ValueError('Unsupported trading pair')

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

def quality_score(trend20, trend50, last, high, low, volume_ratio):
    bullish = trend20 >= trend50
    direction = 'LONG' if bullish else 'SHORT'
    boundary = high if bullish else low
    breakout = (last['close'] - boundary) / boundary if bullish else (boundary - last['close']) / boundary
    trend_strength = abs(trend20 - trend50) / max(trend50, 1e-12)
    trend_points = min(25, 10 + 15 * trend_strength / 0.02)
    breakout_points = max(0, min(35, 15 + breakout * 10000)) if breakout > 0 else max(0, 15 + breakout * 10000)
    volume_points = min(30, 30 * volume_ratio / 1.5)
    score = round(min(100, trend_points + breakout_points + volume_points + 10))
    return direction, score, breakout > 0


def github_api(method, endpoint, payload=None):
    token = os.environ.get('GH_TOKEN')
    repo = os.environ.get('GITHUB_REPOSITORY')
    if not token or not repo:
        return None
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request('https://api.github.com/repos/' + repo + endpoint,
        data=data, method=method,
        headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
                 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'crypto-alert-monitor',
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r) if r.status != 204 else {}


def track_signal(candle_time, direction, entry, stop, target, score):
    if not os.environ.get('GH_TOKEN'):
        print('Tracking disabled: GH_TOKEN unavailable')
        return
    title = f'[SIGNAL] {SYMBOL} {direction} {candle_time}'
    issues = github_api('GET', '/issues?state=all&per_page=100') or []
    if any(issue.get('title') == title for issue in issues):
        print('Signal already tracked')
        return
    body = json.dumps({'symbol': SYMBOL, 'direction': direction, 'entry': entry,
                       'stop': stop, 'target': target, 'score': score,
                       'candle_time': candle_time}, ensure_ascii=False)
    github_api('POST', '/issues', {'title': title, 'body': body})
    print('Signal recorded in GitHub Issues')


def evaluate_signals():
    issues = github_api('GET', '/issues?state=open&per_page=100') or []
    matching = [i for i in issues if i.get('title', '').startswith('[SIGNAL] ' + SYMBOL + ' ')]
    if not matching:
        return
    candles = fetch('5m', 500)
    for issue in matching:
        try:
            signal = json.loads(issue.get('body', ''))
            opened_ms = int(datetime.strptime(signal['candle_time'], '%Y-%m-%d %H:%M UTC').replace(tzinfo=timezone.utc).timestamp() * 1000)
            subsequent = [x for x in candles if x['time'] > opened_ms]
            if not subsequent:
                continue
            outcome = None
            for bar in subsequent:
                if signal['direction'] == 'LONG':
                    hit_stop, hit_target = bar['low'] <= signal['stop'], bar['high'] >= signal['target']
                else:
                    hit_stop, hit_target = bar['high'] >= signal['stop'], bar['low'] <= signal['target']
                if hit_stop or hit_target:
                    outcome = 'STOP (-1R)' if hit_stop else 'TARGET (+2R)'
                    break
            if outcome:
                github_api('PATCH', f"/issues/{issue['number']}",
                           {'state': 'closed', 'state_reason': 'completed',
                            'body': issue.get('body', '') + '\\n\\nPaper outcome: ' + outcome +
                            '\\nConservative stop-first if both touched within one candle. No fees or slippage included.'})
                print(f"Paper result {SYMBOL}: {outcome}")
        except (ValueError, KeyError, TypeError) as exc:
            print('Could not evaluate issue:', exc)


def main():
    if '--test' in sys.argv:
        telegram('✅ Crypto Alert Bot מחובר! הודעת בדיקה בלבד. אין כאן איתות מסחר.')
        print('Test message sent')
        return
    if '--status' in sys.argv:
        candles = fetch('5m', 3)
        last = candles[-1]
        age_min = (datetime.now(timezone.utc).timestamp() * 1000 - (last['time'] + 300000)) / 60000
        if age_min > 30 or age_min < -1:
            raise RuntimeError(f'Binance candle data is stale or inconsistent: {age_min:.1f} minutes')
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        telegram(f'🟢 Crypto Alert Bot — בדיקת תקינות יומית\n'
                 f'זמן בדיקה: {timestamp}\n'
                 f'{SYMBOL} (נר סגור אחרון): ${last["close"]:.3f}\n'
                 f'גיל הנתונים: {max(age_min, 0):.1f} דקות\n'
                 '✅ Binance נגיש והבוט מצליח לשלוח לטלגרם.\n'
                 'ℹ️ זו בדיקת תקינות נקודתית, לא אישור שכל הסריקות במהלך היום הצליחו. אין כאן איתות מסחר.')
        print('Daily status message sent')
        return
    if '--diagnostic' in sys.argv:
        evaluate_signals()
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
    if not 5 <= age_min <= 12 and '--diagnostic' not in sys.argv:
        print(f'No signal: candle age {age_min:.1f} minutes (expected 5-12)')
        return
    direction = None
    if trend20 > trend50 and last['close'] > high and last['volume'] >= avg_vol * 1.5:
        direction = 'LONG'
        stop = low
    elif trend20 < trend50 and last['close'] < low and last['volume'] >= avg_vol * 1.5:
        direction = 'SHORT'
        stop = high
    else:
        direction = None
    long_break = last['close'] > high
    short_break = last['close'] < low
    volume_ratio = last['volume'] / avg_vol if avg_vol else 0
    candidate_direction, score, breakout_ok = quality_score(trend20, trend50, last, high, low, volume_ratio)
    reasons = []
    if direction is None:
        if trend20 > trend50:
            reasons.append('מגמת 4 שעות: עולה')
            if not long_break: reasons.append('אין פריצה מעל שיא 12 הנרות')
        elif trend20 < trend50:
            reasons.append('מגמת 4 שעות: יורדת')
            if not short_break: reasons.append('אין שבירה מתחת לשפל 12 הנרות')
        else:
            reasons.append('ממוצעי EMA שווים')
        if volume_ratio < 1.5: reasons.append(f'נפח נמוך: פי {volume_ratio:.2f} (נדרש 1.5)')
    if direction is None and '--diagnostic' not in sys.argv:
        print('No setup: ' + '; '.join(reasons))
        return
    entry = last['close']
    stop_pct = abs(entry - stop) / entry * 100 if direction else None
    if '--diagnostic' in sys.argv:
        if direction is not None and not 0.25 <= stop_pct <= 1.5:
            reasons.append(f'מרחק סטופ {stop_pct:.2f}% מחוץ לטווח 0.25%-1.5%')
        elif direction is not None:
            reasons.append('התנאים מתקיימים בנר הנבדק (לא אות כניסה בזמן אמת)')
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        telegram(f'📊 {SYMBOL} — אבחון שעתי\n'
                 f'דירוג תנאים (לא הסתברות הצלחה): {score}/100 ({candidate_direction})\n'
                 + ('🟠 התקרבות לתנאים — עדיין לא איתות כניסה.\n' if score >= 65 and direction is None else '') +
                 f'זמן: {timestamp}\n'
                 f'מחיר נר סגור: ${entry:.3f}\n'
                 f'גיל הנר: {age_min:.1f} דקות\n'
                 f'EMA20/50 (4h): {trend20:.3f}/{trend50:.3f}\n'
                 f'נפח ביחס לממוצע: פי {volume_ratio:.2f}\n'
                 + 'סיבות/מצב: ' + ('; '.join(reasons) if reasons else 'לא זוהתה סיבה') +
                 '\nℹ️ צילום מצב נוכחי בלבד, לא סיכום כל הסריקות ולא איתות מסחר.')
        print('Diagnostic sent: ' + '; '.join(reasons))
        return
    if not 0.25 <= stop_pct <= 1.5:
        print(f'Stop distance {stop_pct:.2f}% outside filter')
        return
    target = entry + (2 * abs(entry - stop) * (1 if direction == 'LONG' else -1))
    # $40 capital, max 2x, $1 planned risk, before fees/slippage
    notional = min(80, 1 / (stop_pct / 100))
    planned_loss = notional * stop_pct / 100
    candle_time = datetime.fromtimestamp(last['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    track_signal(candle_time, direction, entry, stop, target, score)
    telegram(f'🔔 {SYMBOL} {direction} — מועמד לבדיקה, לא הוראת מסחר\n'
             f'דירוג תנאים: {score}/100 (לא הסתברות הצלחה)\n'
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
