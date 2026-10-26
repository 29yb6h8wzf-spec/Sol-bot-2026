"""Daily crypto news digest. Keyword tone is not a trading signal."""
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone

QUERIES = {
 'BTCUSDT': '"bitcoin" sourcelang:english',
 'ETHUSDT': '"ethereum" sourcelang:english',
 'SOLUSDT': '"solana" sourcelang:english',
 'XRPUSDT': '"ripple" sourcelang:english'
}
RELEVANCE = {
 'BTCUSDT': (r'\\bbitcoin\\b', r'\\bbtc\\b'),
 'ETHUSDT': (r'\\bethereum\\b', r'\\beth\\b', r'\\bether\\b'),
 'SOLUSDT': (r'\\bsolana\\b', r'\\bsol\\b'),
 'XRPUSDT': (r'\\bxrp\\b', r'\\bripple\\b', r'\\brlUSD\\b')
}

def relevant(symbol, article):
    title = article.get('title', '')
    return any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in RELEVANCE[symbol])

POS = ('approval','approved','adoption','inflow','partnership','upgrade','growth','rally','record','launch')
NEG = ('hack','exploit','lawsuit','ban','outflow','fraud','breach','liquidation','crash','attack')

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent':'CryptoAlertsResearch/1.0'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)

def articles(symbol):
    q = urllib.parse.urlencode({'query':QUERIES[symbol], 'mode':'artlist','format':'json',
                               'timespan':'24h','maxrecords':10,'sort':'datedesc'})
    result = get_json('https://api.gdeltproject.org/api/v2/doc/doc?' + q)
    items = [{'title':x.get('title',''),'url':x.get('url',''),'domain':x.get('domain',''),
              'source':'GDELT'} for x in result.get('articles',[])]
    token = os.environ.get('CRYPTOPANIC_API_KEY','').strip()
    plan = os.environ.get('CRYPTOPANIC_PLAN','developer').strip()
    if token and plan in ('developer','growth','enterprise'):
        url = ('https://cryptopanic.com/api/' + plan + '/v2/posts/?' +
               urllib.parse.urlencode({'auth_token':token,'currencies':symbol.replace('USDT',''),
                                       'kind':'news','regions':'en'}))
        try:
            cp = get_json(url)
            items.extend({'title':x.get('title',''),'url':x.get('url',''),
                          'domain':'CryptoPanic','source':'CryptoPanic'}
                         for x in cp.get('results',[]))
        except Exception as exc:
            print('CryptoPanic optional source unavailable:',exc)
    unique, seen = [], set()
    for x in items:
        if not x['title'] or not x['url'] or x['url'] in seen or not relevant(symbol, x):
            continue
        seen.add(x['url'])
        unique.append(x)
    return unique[:5]

def tone(title):
    s = title.lower()
    positive = sum(w in s for w in POS)
    negative = sum(w in s for w in NEG)
    return 'חיובי לכאורה' if positive > negative else 'שלילי לכאורה' if negative > positive else 'ניטרלי/לא ברור'

def telegram(message):
    payload = urllib.parse.urlencode({'chat_id':os.environ['TELEGRAM_CHAT_ID'],
                                     'text':message,'disable_web_page_preview':'true'}).encode()
    token = os.environ['TELEGRAM_BOT_TOKEN']
    req = urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',data=payload,method='POST')
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.load(r)

def main():
    symbol = os.environ.get('SYMBOL','SOLUSDT')
    if symbol not in QUERIES:
        raise ValueError('Unsupported symbol')
    try:
        items = articles(symbol)
    except Exception as exc:
        print('News provider unavailable:',exc)
        telegram(f'📰 {symbol} — עדכון חדשות\n⚠️ מקור החדשות לא זמין כרגע. לא ניתן לאמת כותרות חדשות.\nאין איתות מסחר.')
        return
    if not items:
        print('No relevant news found for',symbol)
        telegram(f'📰 {symbol} — עדכון חדשות\nלא נמצאו כותרות רלוונטיות ב-24 השעות האחרונות שעברו את סינון המטבע.\nאין איתות מסחר.')
        return
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    lines = [f'📰 {symbol} — חדשות ב-24 שעות האחרונות',f'זמן: {stamp}']
    for x in items[:3]:
        lines.append(f"• {x['title'][:150]}\n  {tone(x['title'])} | {x['domain'] or x['source']}\n  {x['url']}")
    lines.append('⚠️ סיווג מילות מפתח בלבד, לא ניתוח AI מאומת. יש לפתוח את המקור ולבדוק. אין איתות מסחר.')
    telegram('\n\n'.join(lines))
    print('News digest sent for',symbol)

if __name__ == '__main__':
    main()
