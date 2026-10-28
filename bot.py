import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = 'https://api.kraken.com/0/public/OHLC'
DATA_SOURCE = 'Kraken Spot USDT (research only, NOT Binance Futures execution prices)'
SYMBOL = os.environ.get('SYMBOL', 'SOLUSDT')
PAIRS = {'SOLUSDT': 'SOLUSDT', 'BTCUSDT': 'XBTUSDT', 'ETHUSDT': 'ETHUSDT', 'XRPUSDT': 'XRPUSDT'}
if SYMBOL not in PAIRS:
    raise ValueError('Unsupported trading pair')

def fetch(interval, limit):
    if interval not in ('5m', '4h') or limit < 3 or limit > 720:
        raise ValueError('Unsupported Kraken OHLC request')
    minutes = 5 if interval == '5m' else 240
    query = urllib.parse.urlencode({'pair': PAIRS[SYMBOL], 'interval': minutes})
    with urllib.request.urlopen(BASE + '?' + query, timeout=15) as response:
        payload = json.load(response)
    if payload.get('error') or not isinstance(payload.get('result'), dict):
        raise ValueError('Kraken OHLC unavailable')
    entries = [value for key, value in payload['result'].items() if key != 'last']
    if len(entries) != 1 or not isinstance(entries[0], list):
        raise ValueError('Invalid Kraken OHLC response')
    # Kraken always returns the current, unfinished candle as the final row.
    rows = entries[0][:-1][-limit:]
    bars = [{'time': int(x[0]) * 1000, 'high': float(x[2]), 'low': float(x[3]),
             'close': float(x[4]), 'volume': float(x[6])} for x in rows]
    duration = minutes * 60000
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if len(bars) < min(2, limit - 1):
        raise ValueError('Insufficient Kraken candles')
    for i, bar in enumerate(bars):
        if (bar['low'] <= 0 or not bar['low'] <= bar['close'] <= bar['high'] or
                bar['volume'] < 0 or bar['time'] % duration or bar['time'] + duration > now_ms or
                (i and bar['time'] - bars[i-1]['time'] != duration)):
            raise ValueError('Invalid or noncontiguous Kraken candles')
    if now_ms - (bars[-1]['time'] + duration) > duration + 120000:
        raise ValueError('Stale Kraken candles')
    return bars

def fetch_pair(five_limit):
    four, five = fetch('4h', 100), fetch('5m', five_limit)
    print('MARKET_SOURCE kraken_spot', flush=True)
    return four, five

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
                            'body': issue.get('body', '') + '\n\nPaper outcome: ' + outcome +
                            '\nConservative stop-first if both touched within one candle. No fees or slippage included.'})
                print(f"Paper result {SYMBOL}: {outcome}")
        except (ValueError, KeyError, TypeError) as exc:
            print('Could not evaluate issue:', exc)


def scan_log(event, **details):
    """Structured log for diagnosing silent scans in GitHub Actions."""
    print('SCAN_EVENT ' + json.dumps({
        'event': event, 'symbol': SYMBOL, 'source': DATA_SOURCE,
        'at_utc': datetime.now(timezone.utc).isoformat(),
        **details
    }, ensure_ascii=False, sort_keys=True), flush=True)


def missed_closed_candles(candles, max_age_minutes=60):
    """Report recently closed candles for which a delayed run could miss signals.

    Observation only: never replay a historical signal as a live trade.
    """
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    recent = [c for c in candles if 0 <= (now_ms - (c['time'] + 300000)) / 60000 <= max_age_minutes]
    return [datetime.fromtimestamp(c['time']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            for c in recent[:-1]]


def log_candle_coverage(candles):
    """Expose gaps without issuing stale trading alerts."""
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    recent = [c for c in candles if 0 <= now_ms - (c['time'] + 300000) <= 3600000]
    scan_log('candle_coverage', closed_candles_last_hour=len(recent),
             candle_open_times=[datetime.fromtimestamp(c['time']/1000, tz=timezone.utc)
                                .strftime('%H:%M UTC') for c in recent])


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
            raise RuntimeError(f'Kraken Spot candle data is stale or inconsistent: {age_min:.1f} minutes')
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        telegram(f'🟢 Crypto Alert Bot — בדיקת תקינות יומית\n'
                 f'זמן בדיקה: {timestamp}\n'
                 f'{SYMBOL} (נר סגור אחרון): ${last["close"]:.3f}\n'
                 f'גיל הנתונים: {max(age_min, 0):.1f} דקות\n'
                 f'מקור נתונים: {DATA_SOURCE}\n'
                  '✅ נרות Kraken Spot זמינים והבוט מצליח לשלוח לטלגרם. הנתונים למחקר בלבד, לא לביצוע Futures.\n'
                 'ℹ️ זו בדיקת תקינות נקודתית, לא אישור שכל הסריקות במהלך היום הצליחו. אין כאן איתות מסחר.')
        print('Daily status message sent')
        return
    if '--multi' in sys.argv:
        from strategies import candidates
        four, five = fetch_pair(120)
        log_candle_coverage(five)
        last = five[-1]
        age = (datetime.now(timezone.utc).timestamp() * 1000 - last['time']) / 60000
        if not 5 <= age <= 12:
            scan_log('skip_stale_multi', candle_age_minutes=round(age, 2),
                     recent_closed_candles=missed_closed_candles(five))
            return
        setups, metrics = candidates(five, four)
        candle_time = datetime.fromtimestamp(last['time']/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        scan_log('multi_candidates', count=len(setups), candle_time=candle_time,
                 adx=round(metrics['adx'], 2), rsi=round(metrics['rsi'], 2),
                 volume_ratio=round(metrics['volume'], 2),
                 strategies=[x['strategy'] + ':' + x['direction'] for x in setups])
        for s in setups[:2]:
            entry = last['close']
            distance = 1.5 * s['atr']
            stop = entry - distance if s['direction'] == 'LONG' else entry + distance
            stop_pct = 100 * distance / entry
            if not 0.25 <= stop_pct <= 1.5:
                scan_log('skip_multi_risk', strategy=s['strategy'], stop_pct=round(stop_pct, 3))
                continue
            target = entry + 2*distance if s['direction'] == 'LONG' else entry - 2*distance
            unique_title = f'[SIGNAL] {SYMBOL} {s["direction"]} {candle_time} {s["strategy"]}'
            try:
                existing = github_api('GET', '/issues?state=all&per_page=100') or []
                if any(i.get('title') == unique_title for i in existing):
                    print('Duplicate signal skipped:', unique_title)
                    continue
                github_api('POST', '/issues', {'title':unique_title,
                    'body':json.dumps({'symbol':SYMBOL,'direction':s['direction'],'entry':entry,
                        'stop':stop,'target':target,'score':s['score'],'strategy':s['strategy'],
                        'candle_time':candle_time})})
            except Exception as exc:
                print('Could not persist signal; skipping to avoid duplicates:', exc)
                continue
            notional = min(80, 1/(stop_pct/100))
            telegram(f'🔔 {SYMBOL} {s["direction"]} | {s["strategy"]}\n'
                     f'דירוג תנאים: {s["score"]}/100 (לא הסתברות הצלחה)\n'
                     f'נר: {candle_time}\n'
                     f'כניסה תיאורטית: ${entry:.5f}\n'
                     f'סטופ ATR: ${stop:.5f} ({stop_pct:.2f}%)\n'
                     f'יעד 2R: ${target:.5f}\n'
                     f'חשיפה לדוגמה: ${notional:.2f}, סיכון לפני עמלות עד $1\n'
                     f'{s["reason"]}\n'
                     f'מקור נתונים: {DATA_SOURCE}\n'
                      '⚠️ איתות מחקר בלבד; אין ביצוע אוטומטי או הבטחת רווח.')
        return
    if '--diagnostic' in sys.argv:
        try:
            evaluate_signals()
        except Exception as exc:
            print('Paper evaluation failed; continuing diagnostics:', exc)
    four, five = fetch_pair(50)
    log_candle_coverage(five)
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
        scan_log('skip_stale_breakout', candle_age_minutes=round(age_min, 2),
                 recent_closed_candles=missed_closed_candles(five))
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
        scan_log('no_breakout_setup', candle_age_minutes=round(age_min, 2),
                 volume_ratio=round(volume_ratio, 2), reasons=reasons)
        return
    entry = last['close']
    stop_pct = abs(entry - stop) / entry * 100 if direction else None
    if '--diagnostic' in sys.argv:
        if direction is not None and not 0.25 <= stop_pct <= 1.5:
            reasons.append(f'מרחק סטופ {stop_pct:.2f}% מחוץ לטווח 0.25%-1.5%')
        elif direction is not None:
            reasons.append('התנאים מתקיימים בנר הנבדק (לא אות כניסה בזמן אמת)')
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        if os.environ.get('SILENT_DIAGNOSTIC') != '1':
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
        print('Diagnostic '+('logged silently' if os.environ.get('SILENT_DIAGNOSTIC') == '1' else 'sent')+': ' + '; '.join(reasons))
        return
    if not 0.25 <= stop_pct <= 1.5:
        scan_log('skip_breakout_risk', stop_pct=round(stop_pct, 3))
        return
    target = entry + (2 * abs(entry - stop) * (1 if direction == 'LONG' else -1))
    # $40 capital, max 2x, $1 planned risk, before fees/slippage
    notional = min(80, 1 / (stop_pct / 100))
    planned_loss = notional * stop_pct / 100
    candle_time = datetime.fromtimestamp(last['time'] / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    try:
        track_signal(candle_time, direction, entry, stop, target, score)
    except Exception as exc:
        print('Tracking failed; continuing with Telegram alert:', exc)
    telegram(f'🔔 {SYMBOL} {direction} — מועמד לבדיקה, לא הוראת מסחר\n'
             f'דירוג תנאים: {score}/100 (לא הסתברות הצלחה)\n'
             f'נר 5 דקות: {candle_time}\n'
             f'כניסה תיאורטית: ${entry:.3f}\n'
             f'סטופ תיאורטי: ${stop:.3f} ({stop_pct:.2f}%)\n'
             f'יעד 2R: ${target:.3f}\n'
             f'חשיפה מרבית לדוגמה: ${notional:.2f}\n'
             f'הפסד מתוכנן לפני עמלות: ${planned_loss:.2f}\n'
             f'EMA20/50 4h: {trend20:.3f}/{trend50:.3f}\n'
             f'מקור נתונים: {DATA_SOURCE}\n'
              '⚠️ לא נבדקה נזילות, Funding או חדשות. אין ביצוע אוטומטי.')
    scan_log('breakout_alert_sent', direction=direction, candle_time=candle_time, score=score)

if __name__ == '__main__':
    main()
