"""Read-only live execution telemetry. Never imports or invokes the trading engine."""
import json
import sqlite3
import subprocess
import time
import urllib.request
import boto3

ENDPOINT = 'https://signalpilot-scan-desk-feed.29yb6h8wzf.workers.dev/v1/live'

def query(path, sql):
    connection = sqlite3.connect('file:' + path + '?mode=ro', uri=True, timeout=2)
    try:
        return connection.execute(sql).fetchall()
    finally:
        connection.close()

def snapshot():
    raw = subprocess.check_output(['journalctl', '-u', 'signalpilot-breakout-live.service', '--since', '2 hours ago', '-n', '2500', '-o', 'json', '--no-pager'], timeout=8, text=True)
    runs = []
    for line in raw.splitlines():
        try:
            record = json.loads(line)
            item = json.loads(record.get('MESSAGE', ''))
            if not isinstance(item, dict) or not isinstance(item.get('status'), str):
                continue
            runs.append({'at': int(record['__REALTIME_TIMESTAMP']) // 1000, 'status': item['status'][:80], 'scheduled_ms': item.get('scheduled_ms'), 'completed_after_ms': item.get('completed_after_ms'), 'error_type': item.get('error_type')})
        except (ValueError, TypeError, KeyError):
            continue
    errors = []
    fills = []
    entries = []
    try:
        rows = query('/var/lib/private/signalpilot-fill-notifications/events.sqlite', 'SELECT symbol,event,payload,state FROM notices ORDER BY rowid DESC LIMIT 100')
        for symbol, event, payload, delivery in rows:
            p = json.loads(payload)
            if symbol in ('SOLUSDT', 'XRPUSDT') and event in ('OPEN', 'CLOSE'):
                fills.append({**{k: p.get(k) for k in ('direction', 'fill_ms', 'price')}, 'symbol': symbol, 'event': event, 'delivery': delivery})
    except (sqlite3.Error, ValueError):
        errors.append('fills_unavailable')
    try:
        entries = [{'id': a, 'state': b} for a, b in query('/var/lib/private/signalpilot-breakout-live/state.sqlite', 'SELECT id,state FROM entries ORDER BY rowid DESC LIMIT 30')]
    except sqlite3.Error:
        errors.append('entries_unavailable')
    return {'source': 'binance_usdm_live', 'collected_at': int(time.time()*1000), 'runs': runs[-120:], 'fills': fills, 'entries': entries, 'errors': errors}

def main():
    data = snapshot()
    token = boto3.client('ssm', region_name='il-central-1').get_parameter(Name='/signalpilot/dashboard/ingest', WithDecryption=True)['Parameter']['Value']
    req = urllib.request.Request(ENDPOINT, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json', 'User-Agent': 'SignalPilot-Dashboard/1.0', 'X-Live-Ingest': token}, method='POST')
    with urllib.request.urlopen(req, timeout=12) as response:
        print(json.dumps({'published': response.status == 200, 'runs': len(data['runs']), 'fills': len(data['fills']), 'collected_at': data['collected_at']}))

if __name__ == '__main__':
    main()
