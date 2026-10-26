"""Telegram inline menu, polled by GitHub Actions every five minutes."""
import json, os, urllib.parse, urllib.request
from datetime import datetime, timezone

TOKEN=os.environ['TELEGRAM_BOT_TOKEN']
CHAT=str(os.environ['TELEGRAM_CHAT_ID'])
REPO=os.environ.get('GITHUB_REPOSITORY','')
GH=os.environ.get('GH_TOKEN','')
SYMBOLS=('BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT')
STATE_TITLE='[BOT_MENU_STATE]'

def tg(method, params):
    url='https://api.telegram.org/bot'+TOKEN+'/'+method
    data=json.dumps(params).encode()
    req=urllib.request.Request(url,data=data,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=25) as r:
        result=json.load(r)
    if not result.get('ok'):
        raise RuntimeError('Telegram request failed')
    return result['result']

def api(method,path,data=None):
    if not GH or not REPO:
        raise RuntimeError('GitHub credentials required for durable polling')
    url='https://api.github.com/repos/'+REPO+path
    req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,
        method=method,headers={'Authorization':'Bearer '+GH,'Accept':'application/vnd.github+json',
                               'Content-Type':'application/json','User-Agent':'crypto-bot-menu'})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.load(r)

def state():
    issues=api('GET','/issues?state=all&per_page=100')
    for issue in issues:
        if issue.get('title')==STATE_TITLE:
            try:
                return issue['number'],json.loads(issue.get('body') or '{}')
            except (ValueError,TypeError):
                return issue['number'],{}
    issue=api('POST','/issues',{'title':STATE_TITLE,'body':json.dumps({'offset':0})})
    return issue['number'],{'offset':0}

def menu():
    return {'inline_keyboard':[
      [{'text':'📊 סטטוס','callback_data':'status'},{'text':'🔎 סריקה','callback_data':'scan'}],
      [{'text':'📰 חדשות','callback_data':'news'},{'text':'📈 איתותים','callback_data':'signals'}],
      [{'text':'ℹ️ עזרה','callback_data':'help'}]]}

def send(text,keyboard=False):
    args={'chat_id':CHAT,'text':text[:3900], 'disable_web_page_preview':True}
    if keyboard: args['reply_markup']=menu()
    return tg('sendMessage',args)

def get_market(symbol):
    q=urllib.parse.urlencode({'symbol':symbol,'interval':'5m','limit':3})
    with urllib.request.urlopen('https://data-api.binance.vision/api/v3/klines?'+q,timeout=15) as r:
        candles=json.load(r)
    return float(candles[-2][4])

def dispatch(command):
    if command in ('start','menu','help'):
        send('🤖 תפריט הבוט שלך\nבחר פעולה בכפתורים למטה.\nפקודות: /menu /status /scan /news /signals\n⏱ הבקשות נבדקות בערך כל 5 דקות; אין ביצוע עסקאות.',True)
    elif command=='status':
        prices=[]
        for symbol in SYMBOLS:
            try: prices.append(f'{symbol}: ${get_market(symbol):,.5f}')
            except Exception: prices.append(symbol+': נתונים לא זמינים')
        send('🟢 סטטוס מחירים (נר 5 דקות סגור)\n'+'\n'.join(prices)+'\nהסריקות המתוזמנות ממשיכות ב-GitHub.',True)
    elif command=='scan':
        from strategies import candidates
        from bot import fetch
        lines=['🔎 סריקה ידנית — מצב השוק כרגע','זו בדיקה בלבד, לא איתות כניסה בזמן אמת.']
        for symbol in SYMBOLS:
            os.environ['SYMBOL']=symbol
            import bot
            bot.SYMBOL=symbol
            try:
                found,stats=candidates(fetch('5m',120),fetch('4h',100))
                top=', '.join(f"{x['strategy']} {x['direction']} {x['score']}/100" for x in found[:3]) or 'אין תנאים'
                lines.append(f"{symbol}: RSI {stats['rsi']:.0f}, ADX {stats['adx']:.0f} | {top}")
            except Exception as exc:
                lines.append(symbol+': שגיאת נתונים')
        send('\n'.join(lines),True)
    elif command=='news':
        from news import articles,tone
        lines=['📰 חדשות אחרונות — כותרות בלבד']
        for symbol in SYMBOLS:
            try:
                items=articles(symbol)
                if items:
                    x=items[0]
                    lines.append(f"{symbol}: {x['title'][:100]} ({tone(x['title'])})\n{x['url']}")
                else: lines.append(symbol+': אין כתבות רלוונטיות')
            except Exception:
                lines.append(symbol+': מקור חדשות לא זמין')
        send('\n\n'.join(lines)+'\n⚠️ לא המלצת מסחר.',True)
    elif command=='signals':
        issues=api('GET','/issues?state=all&per_page=100')
        signals=[x for x in issues if x.get('title','').startswith('[SIGNAL]')]
        lines=['📈 איתותים אחרונים (תיאורטיים)']
        for issue in signals[:6]:
            lines.append(('✅ סגור' if issue.get('state')=='closed' else '⏳ במעקב')+' '+issue['title'].replace('[SIGNAL] ',''))
        send('\n'.join(lines) if signals else 'עדיין אין איתותים שמורים.',True)
    else:
        send('לא זיהיתי את הפעולה. שלח /menu',True)

def main():
    number,stored=state()
    offset=int(stored.get('offset',0))
    updates=tg('getUpdates',{'offset':offset,'timeout':0,'limit':30,'allowed_updates':['message','callback_query']})
    for item in updates:
        uid=item['update_id']
        message=item.get('message') or item.get('callback_query',{}).get('message') or {}
        chat=str(message.get('chat',{}).get('id',''))
        cb=item.get('callback_query')
        if cb:
            tg('answerCallbackQuery',{'callback_query_id':cb['id']})
        if chat==CHAT:
            command=(cb.get('data','') if cb else message.get('text','').strip().split('@')[0].lstrip('/')).lower()
            if command in ('start','menu','status','scan','news','signals','help'):
                try: dispatch(command)
                except Exception as exc: send('⚠️ הפעולה נכשלה זמנית. נסה שוב בעוד כמה דקות.')
        offset=uid+1
        api('PATCH',f'/issues/{number}',{'body':json.dumps({'offset':offset})})
    print('Processed',len(updates),'updates')

if __name__=='__main__':
    main()
