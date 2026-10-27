// SignalPilot Cloudflare Worker: scheduled market research, no trade execution.
// Alerts are disabled until both Telegram secrets and SIGNAL_STATE KV are configured.
const SYMBOLS = ['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'];
const API = 'https://api.kraken.com/0/public/OHLC';
const PAIRS = {SOLUSDT:'SOLUSDT',BTCUSDT:'XBTUSDT',ETHUSDT:'ETHUSDT',XRPUSDT:'XRPUSDT'};
const RELEASE = 'kraken-stable-v9';
const NEWS_FEEDS=[{name:'CoinDesk',url:'https://www.coindesk.com/arc/outboundfeeds/rss/',host:'coindesk.com'},{name:'Cointelegraph',url:'https://cointelegraph.com/rss',host:'cointelegraph.com'}];
const NEWS_TERMS={SOLUSDT:/\b(solana|sol)\b/i,BTCUSDT:/\b(bitcoin|btc)\b/i,ETHUSDT:/\b(ethereum|ether|eth)\b/i,XRPUSDT:/\b(xrp|ripple|rlusd)\b/i};
function xmlText(value){return value.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g,'$1').replace(/<[^>]*>/g,'').replace(/&#(x[0-9a-f]+|\d+);/gi,(_,n)=>{const c=n[0].toLowerCase()==='x'?parseInt(n.slice(1),16):Number(n);return c>0&&c<=0x10ffff?String.fromCodePoint(c):'';}).replace(/&(amp|quot|apos|lt|gt);/g,(_,n)=>({amp:'&',quot:'"',apos:"'",lt:'<',gt:'>'}[n])).replace(/[\r\n\t]+/g,' ').trim();}
export function parseNewsFeed(xml,feed,now=Date.now()){
 if(!/<rss\b/i.test(xml)||xml.length>1000000)throw Error('Invalid news RSS');
 const field=(item,tag)=>xmlText(item.match(new RegExp('<'+tag+'(?:\\s[^>]*)?>([\\s\\S]*?)<\\/'+tag+'>','i'))?.[1]||'');
 const out=[];
 for(const match of xml.matchAll(/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/gi)){
  const item=match[1],title=field(item,'title').slice(0,220),url=field(item,'link'),publishedAt=Date.parse(field(item,'pubDate'));
  let link;try{link=new URL(url);}catch{continue;}
  if(link.protocol!=='https:'||!(link.hostname===feed.host||link.hostname.endsWith('.'+feed.host))||link.username||link.password||!title||!Number.isFinite(publishedAt)||publishedAt>now+60000||now-publishedAt>86400000)continue;
  link.hash='';out.push({title,url:link.href,publishedAt,source:feed.name});
 }
 return out;
}
export async function loadNews(env,now=Date.now()){
 let cached;try{const value=await env.SIGNAL_STATE.get('news:cache:v1');cached=typeof value==='string'?JSON.parse(value):value;}catch{}
 if(cached?.fetchedAt<=now&&now-cached.fetchedAt<240000&&cached.status!=='unavailable')return cached;
 const results=await Promise.allSettled(NEWS_FEEDS.map(async feed=>{const r=await fetch(feed.url,{signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('News source HTTP '+r.status);return {source:feed.name,items:parseNewsFeed(await r.text(),feed,now)};}));
 const good=results.filter(r=>r.status==='fulfilled').map(r=>r.value),seen=new Set();
 const items=good.flatMap(r=>r.items).sort((a,b)=>b.publishedAt-a.publishedAt).filter(x=>{const k=x.title.toLowerCase().replace(/[^a-z0-9]+/g,'');if(seen.has(x.url)||seen.has(k))return false;seen.add(x.url);seen.add(k);return true;});
 const snapshot={status:good.length===NEWS_FEEDS.length?'ready':good.length?'partial':'unavailable',fetchedAt:now,sources:good.map(r=>r.source),items};
 if(!good.length&&cached?.items&&now-cached.fetchedAt<=1800000)return {...cached,status:'stale'};
 try{await env.SIGNAL_STATE.put('news:cache:v1',JSON.stringify(snapshot),{expirationTtl:1800});}catch{console.warn('News cache write failed');}
 console.log(JSON.stringify({event:'news_checked',release:RELEASE,status:snapshot.status,sources:snapshot.sources,count:items.length}));
 return snapshot;
}
export function newsForSymbol(news,symbol,now=Date.now()){
 return (news?.items||[]).filter(x=>NEWS_TERMS[symbol]?.test(x.title)&&x.publishedAt<=now&&now-x.publishedAt<=86400000);
}
function israelTime(value){return new Intl.DateTimeFormat('he-IL',{timeZone:'Asia/Jerusalem',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));}
export function formatNewsContext(news,symbol,limit=1){
 if(!news||news.status==='unavailable')return '📰 חדשות: ⚠️ המקורות לא זמינים; לא נבדק סיכון חדשותי.';
 const warning=news.status==='stale'?'⚠️ מידע שמור ולא עדכני':news.status==='partial'?'מקור חלקי':'מקורות נבדקו';
 const items=newsForSymbol(news,symbol).slice(0,limit);
 const lines=['📰 חדשות | '+warning+' | בדיקה '+israelTime(news.fetchedAt)];
 if(!items.length)lines.push('לא נמצאו כותרות למטבע ב־24 השעות האחרונות בפידים שנבדקו.');
 for(const x of items)lines.push('• '+x.title.slice(0,150)+'\n'+x.source+' | פורסם '+new Intl.DateTimeFormat('he-IL',{timeZone:'Asia/Jerusalem',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(x.publishedAt))+'\n'+x.url);
 lines.push('כותרות מקור, ללא קביעת כיוון מסחר.');
 return lines.join('\n');
}
async function notifyFreshNews(symbol,env,news){
 if(!['ready','partial'].includes(news?.status))return;
 const latest=newsForSymbol(news,symbol).filter(x=>Date.now()-x.publishedAt<=3600000).slice(0,1);
 for(const article of latest){
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(article.url)))).map(x=>x.toString(16).padStart(2,'0')).join('');
  const key='news:sent:'+symbol+':'+hash;if(await env.SIGNAL_STATE.get(key))continue;
  await send(env,'📰 '+symbol+' | כותרת חדשה מהשעה האחרונה\n\n'+article.title+'\n\nמקור: '+article.source+' | '+israelTime(article.publishedAt)+' (ישראל)\n'+article.url+'\n\nℹ️ חדשות בלבד. הכותרת אינה איתות קנייה או מכירה.');
  await env.SIGNAL_STATE.put(key,'sent',{expirationTtl:172800});
  console.log(JSON.stringify({event:'news_sent',symbol,source:article.source,publishedAt:article.publishedAt}));
 }
}
async function sendHourlyNewsDigest(env,news,now=Date.now()){
 const hour=Math.floor(now/3600000),key='news:hourly:owner:'+hour;
 if(await env.SIGNAL_STATE.get(key))return;
 const lines=['📰 SignalPilot | עדכון חדשות שעתי','🕒 '+israelTime(now)+' (ישראל)',''];
 if(!news||news.status==='unavailable')lines.push('⚠️ מקורות החדשות לא זמינים כרגע.');
 else{
  lines.push('סטטוס: '+news.status);
  const recent=(news.items||[]).filter(x=>x.publishedAt>now-3600000&&x.publishedAt<=now).slice(0,5);
  if(!recent.length)lines.push('לא נמצאו כותרות חדשות בשעה האחרונה.');
  for(const item of recent)lines.push('• '+item.title.slice(0,130),item.source+' | '+item.url);
 }
 lines.push('','ℹ️ חדשות בלבד, לא איתות מסחר.');
 await send(env,lines.join(String.fromCharCode(10)));
 await env.SIGNAL_STATE.put(key,'sent',{expirationTtl:7200});
}
const PERIOD = 300000;
const avg = a => a.reduce((x,y)=>x+y,0)/a.length;
function ema(v,n) {let x=v[0], a=2/(n+1);for(const y of v.slice(1))x=a*y+(1-a)*x;return x;}
function emaSeries(v,n) {let x=v[0],a=2/(n+1);return v.map((y,i)=>(x=i?a*y+(1-a)*x:y));}
function rsi(v,n=14) {let d=v.slice(1).map((x,i)=>x-v[i]),g=avg(d.slice(0,n).map(x=>Math.max(x,0))),l=avg(d.slice(0,n).map(x=>Math.max(-x,0)));for(const x of d.slice(n)){g=(g*(n-1)+Math.max(x,0))/n;l=(l*(n-1)+Math.max(-x,0))/n;}return l===0?100:100-100/(1+g/l);}
function bands(v,n=20) {let a=v.slice(-n),m=avg(a),sd=Math.sqrt(avg(a.map(x=>(x-m)**2)));return [m-2*sd,m+2*sd];}
function atr(c,n=14) {return avg(c.slice(1).map((x,i)=>Math.max(x.high-x.low,Math.abs(x.high-c[i].close),Math.abs(x.low-c[i].close))).slice(-n));}
function adx(c,n=14) {if(c.length<2*n+2)return 0;let t=[],p=[],m=[];for(let i=1;i<c.length;i++){let x=c[i],y=c[i-1],up=x.high-y.high,down=y.low-x.low;p.push(up>down&&up>0?up:0);m.push(down>up&&down>0?down:0);t.push(Math.max(x.high-x.low,Math.abs(x.high-y.close),Math.abs(x.low-y.close)));}
const smooth=a=>{let o=[a.slice(0,n).reduce((x,y)=>x+y,0)];for(let x of a.slice(n))o.push(o.at(-1)-o.at(-1)/n+x);return o;};
let ts=smooth(t),ps=smooth(p),ms=smooth(m),dx=ts.map((v,i)=>{let a=v?100*ps[i]/v:0,b=v?100*ms[i]/v:0;return a+b?100*Math.abs(a-b)/(a+b):0;});let out=avg(dx.slice(0,n));for(let d of dx.slice(n))out=(out*(n-1)+d)/n;return out;}
export async function candles(symbol,interval,limit){
 const minutes = {'5m':5,'4h':240}[interval], pair = PAIRS[symbol];
 if(!minutes||!pair)throw Error('Unsupported market or interval');
 const u=new URL(API);u.searchParams.set('pair',pair);u.searchParams.set('interval',minutes);
 let r;try{r=await fetch(u,{signal:AbortSignal.timeout(12000)});}catch{throw Error('Kraken request failed');}
 if(!r.ok)throw Error('Kraken HTTP '+r.status);
 const body=await r.json();
 if(!Array.isArray(body.error)||body.error.length)throw Error('Kraken API rejected market data request');
 const entries=Object.entries(body.result||{}).filter(([key])=>key!=='last');
 if(entries.length!==1||!Array.isArray(entries[0][1]))throw Error('Invalid Kraken OHLC response');
 // Kraken timestamps are seconds; its final row is always the open candle.
 const bars=entries[0][1].slice(0,-1).slice(-(limit-1)).map(x=>({time:Number(x[0])*1000,high:+x[2],low:+x[3],close:+x[4],volume:+x[6]}));
 if(bars.length<55)throw Error('Insufficient closed candles');
 const duration=minutes*60000, now=Date.now();
 for(let i=0;i<bars.length;i++){
  const b=bars[i];
  if(!Object.values(b).every(Number.isFinite)||b.low<=0||b.high<b.low||b.close<b.low||b.close>b.high||b.volume<0||b.time%duration!==0||b.time+duration>now||(i&&b.time-bars[i-1].time!==duration))throw Error('Invalid or non-contiguous Kraken candles');
 }
 if(now-(bars.at(-1).time+duration)>duration+2*60000)throw Error('Stale Kraken '+interval+' candles');
 return bars;
}
function setups(five,four,checks=[]) {let last=five.at(-1),cl=five.map(x=>x.close),fc=four.map(x=>x.close),e20=ema(fc,20),e50=ema(fc,50),prev=five.slice(-13,-1),high=Math.max(...prev.map(x=>x.high)),low=Math.min(...prev.map(x=>x.low)),vr=last.volume/avg(prev.map(x=>x.volume)),out=[];
let direction=e20>e50&&last.close>high&&vr>=1.5?'LONG':e20<e50&&last.close<low&&vr>=1.5?'SHORT':null;
if(direction){let stop=direction==='LONG'?low:high;out.push({strategy:'BREAKOUT',direction,stop,score:75,reason:'12-candle breakout; volume x'+vr.toFixed(2)});}
checks.push('BREAKOUT: '+(direction?'תנאים עברו '+direction:'אין התאמה בין מגמה, פריצה ונפח')+'; מגמת 4h: '+(e20>e50?'עולה':e20<e50?'יורדת':'ללא כיוון')+'; טווח 12 נרות: '+low.toFixed(5)+'–'+high.toFixed(5)+'; נפח x'+vr.toFixed(2)+' (נדרש 1.50)');
let strength=adx(four),volatility=atr(five),momentum=rsi(cl),e9=emaSeries(cl,9),e21=emaSeries(cl,21),macd=emaSeries(cl,12).map((v,i)=>v-emaSeries(cl,26)[i]),sig=emaSeries(macd,9),[lo,hi]=bands(cl);
function add(strategy,direction,condition,score,reason){checks.push(strategy+' '+direction+': '+(condition?'תנאים עברו':'לא עמד בכל התנאים')+'; '+reason);if(condition)out.push({strategy,direction,stop:direction==='LONG'?last.close-1.5*volatility:last.close+1.5*volatility,score:Math.min(95,Math.round(score)),reason});}
for(let side of ['LONG','SHORT']){let up=side==='LONG',trend=up?e20>e50:e20<e50,reclaim=up?cl.at(-2)<=e9.at(-2)&&last.close>e9.at(-1):cl.at(-2)>=e9.at(-2)&&last.close<e9.at(-1),aligned=up?e9.at(-1)>e21.at(-1):e9.at(-1)<e21.at(-1);add('EMA_ADX',side,trend&&reclaim&&aligned&&strength>=20&&vr>=0.8,60+Math.min(15,strength-20)+Math.min(15,vr*8),'4h ADX '+strength.toFixed(1)+'; EMA reclaim; volume x'+vr.toFixed(2));}
add('RSI_BOLL','LONG',strength<25&&cl.at(-2)<bands(cl.slice(0,-1))[0]&&last.close>lo&&momentum<45,65+Math.max(0,45-momentum)/3,'RSI '+momentum.toFixed(1)+'; lower band reclaim');
add('RSI_BOLL','SHORT',strength<25&&cl.at(-2)>bands(cl.slice(0,-1))[1]&&last.close<hi&&momentum>55,65+Math.max(0,momentum-55)/3,'RSI '+momentum.toFixed(1)+'; upper band reclaim');
add('MACD_VOLUME','LONG',macd.at(-2)<=sig.at(-2)&&macd.at(-1)>sig.at(-1)&&vr>=1.2&&momentum>50,65+Math.min(20,vr*10),'MACD bullish crossover; volume x'+vr.toFixed(2));
add('MACD_VOLUME','SHORT',macd.at(-2)>=sig.at(-2)&&macd.at(-1)<sig.at(-1)&&vr>=1.2&&momentum<50,65+Math.min(20,vr*10),'MACD bearish crossover; volume x'+vr.toFixed(2));
return out.slice(0,3).filter(s=>{let pct=100*Math.abs(last.close-s.stop)/last.close,ok=pct>=0.25&&pct<=1.5;if(!ok)checks.push(s.strategy+' '+s.direction+': נפסל — מרחק סטופ '+pct.toFixed(2)+'% מחוץ לטווח 0.25%–1.50%');return ok;}).map(s=>({...s,entry:last.close,stopPct:100*Math.abs(last.close-s.stop)/last.close,candle:last.time}));}

// Hypothetical taker fees and slippage on both entry and exit.
// These are NOT venue quotes. Funding, spread changes and liquidation are excluded.
export const RISK_DEFAULTS=Object.freeze({riskBudget:1.5,leverage:2,feeRate:0.0005,slippageRate:0.00025,minNetR:1.25});
export function tradePlan(s,bars,now=Date.now(),config=RISK_DEFAULTS){
 const side=s.direction==='LONG'?1:s.direction==='SHORT'?-1:0;
 const risk=side*(s.entry-s.stop),vol=atr(bars);
 const {riskBudget,leverage,feeRate,slippageRate,minNetR}=config;
 if(!side||!Number.isFinite(risk)||risk<=0||!Number.isFinite(s.entry)||s.entry<=0||!Number.isFinite(vol)||vol<=0||
  ![riskBudget,leverage,feeRate,slippageRate,minNetR].every(Number.isFinite)||riskBudget<=0||leverage<1||feeRate<0||slippageRate<0||minNetR<=0)return null;
 const a=s.entry-side*Math.min(vol*.2,risk*.2);
 const b=s.entry+side*Math.min(vol*.08,risk*.08);
 const low=Math.min(a,b),high=Math.max(a,b),target=s.entry+side*2*risk;
 const expires=s.candle+4*PERIOD; // 15 minutes after the 5m signal candle closes
 const friction=feeRate+slippageRate;
 const endpoints=[low,high];
 const lossAt=p=>side*(p-s.stop)+friction*(p+s.stop);
 const profitAt=p=>side*(target-p)-friction*(p+target);
 const worstLoss=Math.max(...endpoints.map(lossAt));
 const worstProfit=Math.min(...endpoints.map(profitAt));
 const netR=worstProfit/worstLoss;
 if(![low,high,target,worstLoss,worstProfit,netR,expires].every(Number.isFinite)||low<=0||high<=0||target<=0||
  worstLoss<=0||worstProfit<=0||netR<minNetR||now>=expires)return null;
 const quantity=riskBudget/worstLoss;
 const notional=quantity*Math.max(low,high);
 const margin=notional/leverage;
 return {low,high,target,expires,netR,riskBudget,quantity,notional,margin,leverage,
  worstLoss,worstProfit,feeRate,slippageRate,source:s.source||'Kraken Spot USDT (research only)'};
}
export function tradeMessage(symbol,s,p,news){
 const money=x=>'$'+x.toFixed(x>=1000?2:5);
 const units=symbol.replace('USDT','');
 return [
  '🚨 SIGNALPILOT | '+symbol,
  (s.direction==='LONG'?'🟢 LONG':'🔴 SHORT')+' | '+s.strategy,
  '━━━━━━━━━━━━━━━━',
  '📍 טווח כניסה: '+money(p.low)+' – '+money(p.high),
  '📌 מחיר האיתות: '+money(s.entry),
  '🛑 סטופ (SL): '+money(s.stop),
  '🎯 יעד (TP): '+money(p.target),
  '⛔ אין לרדוף אחרי המחיר מחוץ לטווח',
  '⏳ תוקף: '+israelTime(p.expires)+' (ישראל)',
  '❌ ביטול לפני כניסה: פקיעת תוקף או נגיעה בסטופ (לא מנוטר אוטומטית)',
  '',
  '🛡️ ניהול סיכון — הערכה בלבד',
  '• סיכון מתוכנן: עד $'+p.riskBudget.toFixed(2)+' בתרחיש סטופ רגיל',
  '• כמות תיאורטית: '+p.quantity.toFixed(3)+' '+units,
  '• חשיפה: כ־$'+p.notional.toFixed(2),
  '• ביטחונות משוערים במינוף '+p.leverage+'X: $'+p.margin.toFixed(2),
  '• יחס רווח/סיכון נטו בקצה הגרוע: '+p.netR.toFixed(2)+'R',
  '• עלויות משוערות לכל צד: עמלה '+(p.feeRate*100).toFixed(3)+'% + החלקה '+(p.slippageRate*100).toFixed(3)+'%',
  '• לא כולל funding, גאפ, שינוי מרווח או ליקווידציה.',
  '• סטופ ב־Binance יכול להיות מופעל לפי Mark Price או Contract Price; יש לאמת הגדרת Trigger.',
  ...(!p.source.startsWith('Binance')?['🚫 רמות Kraken Spot הן למחקר בלבד — אין להשתמש בהן כפקודות Binance Futures. יש לבדוק מחירים מחדש בבורסה לפני עסקה.']:[]),
  '',
  '📊 דירוג תנאים: '+s.score+'/100 (לא הסתברות הצלחה)',
  '🔎 '+s.reason,
  '🏦 מקור מחירים: '+p.source+'. מחיר סגירת נר, לא מחיר ביצוע.',
  '⚠️ איתות מחקרי בלבד. אין ביצוע פקודות או ניטור רציף.',
  '',
  formatNewsContext(news,symbol,1)
 ].join('\n');
}
export function shouldSendScanStatus(found){return Array.isArray(found)&&found.length>0;}
export function formatScanStatus(symbol,five,four,found,now=Date.now(),news,sourceId='kraken_spot',checks=[]){
 const last=five.at(-1), previous=five.slice(-13,-1), volume=last.volume/avg(previous.map(b=>b.volume));
 const closes=four.map(b=>b.close), fast=ema(closes,20), slow=ema(closes,50);
 const trend=fast>slow?'עולה 📈':fast<slow?'יורדת 📉':'ללא כיוון';
 const clock=new Intl.DateTimeFormat('he-IL',{timeZone:'Asia/Jerusalem',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
 const time=value=>clock.format(new Date(value));
 const strategies=[['BREAKOUT','פריצת מחיר'],['EMA_ADX','EMA + ADX'],['RSI_BOLL','RSI + רצועות'],['MACD_VOLUME','MACD + נפח']];
 const levels=found.map(s=>{
  const risk=Math.abs(s.entry-s.stop);
  const target=s.entry+(s.direction==='LONG'?2:-2)*risk;
  return '🔔 '+s.strategy+' '+s.direction+' | כניסה: $'+s.entry.toFixed(5)+' | 🛑 SL: $'+s.stop.toFixed(5)+' | 🎯 TP (2R): $'+target.toFixed(5);
 });
 const lines=strategies.map(([key,label])=>{
  const matched=found.filter(s=>s.strategy===key);
  return (matched.length?'✅ ':'▫️ ')+label+': '+(matched.length?'עבר ('+matched.map(s=>s.direction==='LONG'?'לונג':'שורט').join(', ')+')':'לא עבר');
 });
 return ['📊 SignalPilot | '+symbol+' — סריקה כל 5 דקות',
  '🕒 '+time(now)+' | נר '+time(last.time)+'–'+time(last.time+PERIOD)+' (ישראל)',
  '',
  'מחיר סגירה: $'+last.close.toFixed(5),
  'מגמת 4 שעות: '+trend,
  'נפח: '+(Number.isFinite(volume)?Math.round(volume*100)+'% מהממוצע':'לא זמין'),
  'RSI: '+rsi(five.map(b=>b.close)).toFixed(1)+' | ADX: '+adx(four).toFixed(1),
  '',
  'בדיקות כניסה — כולל סינון סטופ:',
  ...lines,
  ...(checks.length?['','🔎 פירוט תנאים:',...checks.slice(0,8)]:[]),
  ...(levels.length?['','📍 רמות כניסה, סטופ וטייק פרופיט (תיאורטיות):',...levels]:[]),
  '',
  found.length?'🔔 איתותים חדשים נשלחים בהודעה נפרדת.':'אין כניסה שעברה את תנאי הסורק.',
  '🏦 מקור מחירים: '+sourceId+' (Kraken Spot, לא Futures)',
  '',formatNewsContext(news,symbol)
 ].join('\n');
}

const APPROVED='tg:approved',PENDING='tg:pending',OFFSET='tg:offset';
async function tgRequest(env,method,body){
 const response=await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/'+method,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(12000)});
 if(!response.ok)throw Error('Telegram '+method+' HTTP '+response.status);
 const result=await response.json();if(!result.ok)throw Error('Telegram '+method+' failed');
 return result.result;
}
async function tgDirect(env,id,message,buttons){
 const body={chat_id:id,text:message.slice(0,3900),disable_web_page_preview:true};
 if(buttons?.length)body.reply_markup={inline_keyboard:buttons};
 return tgRequest(env,'sendMessage',body);
}
async function tgIds(env,key){
 const value=JSON.parse(await env.SIGNAL_STATE.get(key)||'[]');
 if(!Array.isArray(value)||value.length>200||!value.every(x=>typeof x==='string'&&/^\d{1,18}$/.test(x)))throw Error('Invalid subscriber list');
 return [...new Set(value)];
}
async function tgSave(env,key,ids){await env.SIGNAL_STATE.put(key,JSON.stringify([...new Set(ids)]));}
function testSignalMessage(){
 return [
  '🧪 TEST SIGNAL — בדיקת שליחה בלבד',
  '⚠️ דוגמה מלאכותית. לא אות שוק, לא המלצת מסחר, לא מחיר חי.',
  '',
  '📊 DEMOUSDT | LONG | BREAKOUT (דוגמה)',
  '📍 כניסה מדומה: $100.00',
  '🛑 Stop Loss מדומה: $99.00',
  '🎯 Take Profit מדומה: $102.00',
  '📈 יחס R:R לדוגמה: 1:2',
  '🏦 מקור נתונים: DEMO — לא Binance, לא Bybit, לא Kraken',
  '',
  '✅ אם קיבלת את ההודעה, ערוץ השליחה למנהל פועל.',
  '❗ הבדיקה אינה מאשרת שהסורק או מקור הנתונים פעילים.',
  '🔒 ההודעה נשלחה למנהל בלבד. לא נפתחו עסקאות.'
 ].join(String.fromCharCode(10));
}
async function showLiveScannerStatus(env){
 const raw=await env.SIGNAL_STATE.get('health:latest');
 if(!raw)return '📡 SignalPilot | מצב הסורק\\n⚠️ עדיין אין קבלת סריקה חיה ב־KV.\\n/testsignal בודק טלגרם בלבד.';
 let receipt;
 try{receipt=JSON.parse(raw);}catch{return '📡 SignalPilot | מצב הסורק\\n⚠️ קבלת הסריקה האחרונה אינה תקינה.';}
 const age=Date.now()-Number(receipt.recordedAt);
 const fresh=Number.isFinite(age)&&age>=0&&age<=12*60000;
 const expected=['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'];
 const results=Array.isArray(receipt.results)?receipt.results:[];
 const passing=receipt.ok===true&&results.length===4&&expected.every(sym=>results.some(r=>r.symbol===sym&&r.source==='kraken_spot'));
 const lines=['📡 SignalPilot | מצב הסורק החי',
  '🕒 בדיקה אחרונה: '+(Number.isFinite(Number(receipt.recordedAt))?israelTime(Number(receipt.recordedAt)):'לא ידוע')+' (ישראל)',
  '📊 מקור: '+(receipt.source==='kraken_spot'?'Kraken Spot — מחקר בלבד':'לא אומת'),
  '🔍 מטבעות: '+results.map(r=>r.symbol).filter(sym=>expected.includes(sym)).join(', '),
  fresh&&passing?'✅ ארבעת המטבעות נסרקו בהצלחה לאחרונה':'⚠️ סריקה חלקית, כושלת או לא עדכנית',
  '📬 איתותים שזוהו: '+results.reduce((n,r)=>n+(Number.isInteger(r.candidates)&&r.candidates>0?r.candidates:0),0),
  '❗ בדיקת מצב בודדת אינה מאשרת שני מחזורים רצופים.',
  '🔒 לא מוצגים נתוני חשבון Binance.'];
 return lines.join(String.fromCharCode(10));
}
function ownerMenu(){return [[{text:'👥 ניהול חברים',callback_data:'access:list'}]];}
async function showAccessList(env){
 const approved=await tgIds(env,APPROVED),pending=await tgIds(env,PENDING);
 const lines=['👥 SignalPilot | ניהול חברים','','⏳ ממתינים לאישור: '+pending.length];
 for(const id of pending.slice(0,20))lines.push('• '+id);
 if(!pending.length)lines.push('אין בקשות ממתינות');
 lines.push('','✅ מאושרים: '+approved.length);
 for(const id of approved.slice(0,20))lines.push('• '+id);
 if(!approved.length)lines.push('אין חברים מאושרים');
 if(pending.length>20||approved.length>20)lines.push('מוצגים עד 20 בכל קבוצה. ניתן להשתמש בפקודות לניהול השאר.');
 lines.push('','🔒 רק המנהל יכול לאשר או להסיר חברים.');
 const buttons=[];
 for(const id of pending.slice(0,20))buttons.push([
  {text:'✅ אשר '+id,callback_data:'access:approve:'+id},
  {text:'❌ דחה '+id,callback_data:'access:remove:'+id}
 ]);
 for(const id of approved.slice(0,20))buttons.push([{text:'🚫 הסר '+id,callback_data:'access:remove:'+id}]);
 buttons.push([{text:'🔄 רענון רשימה',callback_data:'access:list'}]);
 await tgDirect(env,env.TELEGRAM_CHAT_ID,lines.join('\n'),buttons);
}
async function changeAccess(env,action,id){
 if(!/^\d{1,18}$/.test(id||''))return '⚠️ מספר משתמש לא תקין.';
 if(id===String(env.TELEGRAM_CHAT_ID))return '⚠️ לא ניתן לשנות הרשאת מנהל.';
 const pending=await tgIds(env,PENDING),approved=await tgIds(env,APPROVED);
 if(action==='approve'){
  if(!pending.includes(id))return approved.includes(id)?'ℹ️ המשתמש כבר מאושר.':'ℹ️ הבקשה כבר טופלה או אינה קיימת.';
  // Store approval before notifying; a retry must not grant duplicate permissions.
  await tgSave(env,APPROVED,[...approved,id]);
  await tgSave(env,PENDING,pending.filter(x=>x!==id));
  try{await tgDirect(env,id,'✅ בקשתך אושרה!\nמעכשיו תקבל איתותי מחקר מ־SignalPilot כאשר יהיו איתותים חדשים.\n⚠️ לא המלצת מסחר.');}catch{console.warn('Subscriber approval notice delivery failed');}
  return '✅ המשתמש '+id+' אושר בהצלחה.';
 }
 if(action==='remove'){
  if(!pending.includes(id)&&!approved.includes(id))return 'ℹ️ המשתמש כבר אינו ברשימות.';
  await tgSave(env,APPROVED,approved.filter(x=>x!==id));
  await tgSave(env,PENDING,pending.filter(x=>x!==id));
  return '🚫 הגישה למשתמש '+id+' הוסרה / הבקשה נדחתה.';
 }
 return '⚠️ פעולה לא מוכרת.';
}
async function tgAcknowledge(env,body){
 try{await tgRequest(env,'answerCallbackQuery',body);}
 catch(error){console.warn('Telegram callback acknowledgement expired or failed; continuing access processing');}
}
export async function processTelegramAccess(env){
 const offset=Number(await env.SIGNAL_STATE.get(OFFSET)||0);
 if(!Number.isSafeInteger(offset)||offset<0)throw Error('Invalid update offset');
 const updates=await tgRequest(env,'getUpdates',{offset,limit:50,timeout:0,allowed_updates:['message','callback_query']});
 if(!Array.isArray(updates))throw Error('Invalid Telegram updates response');
 let ownerMessages=0,ownerCommands=0;
 for(const update of updates){
  const m=update.message,cb=update.callback_query;
  const chat=m?.chat||cb?.message?.chat;
  const id=String(chat?.id||''),owner=id===String(env.TELEGRAM_CHAT_ID);
  const from=String(m?.from?.id||cb?.from?.id||id);
  const privateChat=chat?.type==='private'&&/^\d{1,18}$/.test(id);
  const [cmd,arg]=String(m?.text||'').trim().split(/\s+/,2);
  if(owner){ownerMessages++;if(['/users','/approve','/remove','/start','/testsignal','/status'].includes(cmd)||cb?.data?.startsWith('access:'))ownerCommands++;}
  if(cb){
   if(!privateChat||!owner||from!==id){
    await tgAcknowledge(env,{callback_query_id:cb.id,text:'אין לך הרשאה לפעולה זו.',show_alert:true});
   }else{
    const match=/^access:(list|approve|remove)(?::(\d{1,18}))?$/.exec(String(cb.data||''));
    if(!match||((match[1]==='list')!==!match[2])){
     await tgAcknowledge(env,{callback_query_id:cb.id,text:'פעולה לא תקינה'});
    }else{
     await tgAcknowledge(env,{callback_query_id:cb.id});
     if(match[1]==='list')await showAccessList(env);
     else{const result=await changeAccess(env,match[1],match[2]);await tgDirect(env,id,result);await showAccessList(env);}
    }
   }
  }else if(privateChat){
   if(owner){
    if(cmd==='/testsignal'&&from===id)await tgDirect(env,id,testSignalMessage());
    else if(cmd==='/status'&&from===id)await tgDirect(env,id,await showLiveScannerStatus(env));
    else if(cmd==='/users'||cmd==='/start'||cmd==='/menu')await showAccessList(env);
    else if(cmd==='/approve'||cmd==='/remove'){
     await tgDirect(env,id,await changeAccess(env,cmd.slice(1),arg));
     await showAccessList(env);
    }
   }else if(cmd==='/start'){
    const approved=await tgIds(env,APPROVED),pending=await tgIds(env,PENDING);
    if(approved.includes(id))await tgDirect(env,id,'✅ אתה כבר מאושר לקבלת איתותים מ־SignalPilot.');
    else{
     if(!pending.includes(id)){
      if(pending.length>=200){await tgDirect(env,id,'⚠️ כרגע לא ניתן לקבל בקשות נוספות.');}
      else{
       await tgSave(env,PENDING,[...pending,id]);
       await tgDirect(env,env.TELEGRAM_CHAT_ID,'🔔 בקשת הצטרפות חדשה ל־SignalPilot\n\n👤 משתמש: '+id+'\n\nאפשר לאשר או לדחות בלחיצה:',[[
        {text:'✅ אישור',callback_data:'access:approve:'+id},
        {text:'❌ דחייה',callback_data:'access:remove:'+id}
       ],[{text:'👥 כל החברים',callback_data:'access:list'}]]);
       await tgDirect(env,id,'⏳ בקשת ההצטרפות נשלחה למנהל.\nנעדכן אותך לאחר אישור.');
      }
     }else await tgDirect(env,id,'⏳ הבקשה שלך עדיין ממתינה לאישור.');
    }
   }else await tgDirect(env,id,'🤖 SignalPilot\nכדי לבקש גישה לאיתותים, שלח /start.\n⚠️ איתותים למחקר בלבד.');
  }
  await env.SIGNAL_STATE.put(OFFSET,String(update.update_id+1));
 }
 await env.SIGNAL_STATE.put('tg:access-health',JSON.stringify({status:'ok',checkedAt:new Date().toISOString(),updates:updates.length,ownerMessages,ownerCommands}));
}
async function sendResearch(env,msg){
 await send(env,msg);
 for(const id of await tgIds(env,APPROVED)){
  if(id===String(env.TELEGRAM_CHAT_ID))continue;
  try{await tgDirect(env,id,msg);}catch(error){console.warn('Subscriber delivery failed',String(error));}
 }
}
async function send(env,msg){let r=await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:msg,disable_web_page_preview:true}),signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('Telegram HTTP '+r.status);let j=await r.json();if(!j.ok)throw Error('Telegram API rejected message');}
async function scan(symbol,env,news){
 const [five,four]=await Promise.all([candles(symbol,'5m',120),candles(symbol,'4h',100)]);
 const source='Kraken Spot USDT (research only, NOT Binance Futures execution prices)',sourceId='kraken_spot';
 const last=five.at(-1),age=(Date.now()-(last.time+PERIOD))/60000;
 console.log(JSON.stringify({event:'scan',symbol,source:sourceId,candle:new Date(last.time).toISOString(),closedAgeMinutes:+age.toFixed(2)}));
 if(age<0||age>7){console.warn('Skipping stale candle',symbol,age);return;}
let checks=[],raw=setups(five,four,checks),found=[];
for(const setup of raw){
 const plan=tradePlan({...setup,source},five);
 if(plan)found.push({setup,plan});
 else console.log(JSON.stringify({event:'plan_filtered',symbol,strategy:setup.strategy}));
}
console.log(JSON.stringify({event:'candidates',symbol,count:found.length,rawCandidates:raw.length,strategies:found.map(x=>x.setup.strategy)}));
for(const {setup,plan} of found){
 const key='signal:'+sourceId+':'+symbol+':'+setup.candle+':'+setup.strategy+':'+setup.direction;
 if(await env.SIGNAL_STATE.get(key)){console.log('Duplicate skipped',key);continue;}
 await sendResearch(env,tradeMessage(symbol,setup,plan,news));
 await env.SIGNAL_STATE.put(key,'sent',{expirationTtl:86400});
 console.log('Alert sent',key);
}
// Market scans remain on the five-minute cron; never notify the owner unless a real setup passes.
const statusDelivery=found.length?'signal_only':'suppressed_no_signal';
await notifyFreshNews(symbol,env,news);
return {symbol,source:sourceId,candle:new Date(last.time).toISOString(),candidates:found.length,closedAgeMinutes:+age.toFixed(2),statusDelivery,newsStatus:news?.status||'unavailable',newsCount:newsForSymbol(news,symbol).length};}

// Signed GET only: read-only Binance USD-M Futures account monitoring.
// Never log API credentials, signatures, signed URLs, balances or raw responses.
export async function readBinancePositions(env){
 if(!env.BINANCE_API_KEY||!env.BINANCE_API_SECRET)throw Error('missing_credentials');
 const query='timestamp='+Date.now()+'&recvWindow=5000';
 const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(env.BINANCE_API_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const signed=await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(query));
 const signature=Array.from(new Uint8Array(signed),b=>b.toString(16).padStart(2,'0')).join('');
 let response;
 try{response=await fetch('https://fapi.binance.com/fapi/v2/positionRisk?'+query+'&signature='+signature,{
  method:'GET',headers:{'X-MBX-APIKEY':env.BINANCE_API_KEY},signal:AbortSignal.timeout(10000)
 });}catch{throw Error('network_unavailable');}
 if(!response.ok)throw Error('binance_http_'+response.status);
 let body;try{body=await response.json();}catch{throw Error('invalid_json');}
 if(!Array.isArray(body))throw Error('invalid_positions_response');
 return body.filter(p=>SYMBOLS.includes(p.symbol)&&Number.isFinite(Number(p.positionAmt))&&Number(p.positionAmt)!==0)
 .map(p=>({
  symbol:p.symbol,side:Number(p.positionAmt)<0?'SHORT':'LONG',
  quantity:Math.abs(Number(p.positionAmt)),entry:Number(p.entryPrice),mark:Number(p.markPrice),
  unrealizedPnl:Number(p.unRealizedProfit),leverage:Number(p.leverage),
  isolated:p.marginType==='isolated'
 })).filter(p=>[p.quantity,p.entry,p.mark,p.unrealizedPnl,p.leverage].every(Number.isFinite)&&p.entry>0&&p.mark>0);
}
export async function monitorBinanceAccount(env){
 if(!env.BINANCE_API_KEY||!env.BINANCE_API_SECRET)return 'not_configured';
 try{
  const positions=await readBinancePositions(env);
  const old=JSON.parse(await env.SIGNAL_STATE.get('account:positions')||'[]');
  const snapshot=positions.map(p=>({symbol:p.symbol,side:p.side,quantity:p.quantity,entry:p.entry,mark:p.mark,unrealizedPnl:p.unrealizedPnl,leverage:p.leverage,isolated:p.isolated}));
  const stateKey=p=>p.symbol+':'+p.side+':'+p.quantity+':'+p.entry;
  const before=new Set(old.map(stateKey)),after=new Set(snapshot.map(stateKey));
  const changed=snapshot.filter(p=>!before.has(stateKey(p)));
  const closed=old.filter(p=>!after.has(stateKey(p)));
  // Store state before sending to avoid repeating alerts after transient Telegram failures.
  await env.SIGNAL_STATE.put('account:positions',JSON.stringify(snapshot));
  await env.SIGNAL_STATE.put('account:health',JSON.stringify({status:'connected',checkedAt:Date.now(),openPositions:snapshot.length}),{expirationTtl:86400});
  if(changed.length||closed.length){
   const lines=['🔐 Binance Futures — עדכון פוזיציות (קריאה בלבד)'];
   for(const p of changed)lines.push('🟢 '+p.symbol+' '+p.side+' | כמות '+p.quantity+' | כניסה '+p.entry+' | PNL לא ממומש '+p.unrealizedPnl.toFixed(3)+' USDT');
   for(const p of closed)lines.push('⚪ '+p.symbol+' '+p.side+' | הפוזיציה כבר לא מופיעה ב-API; יש לבדוק היסטוריית עסקאות לתוצאה נטו');
   await send(env,lines.join('\n'));
  }
  return 'connected';
 }catch(error){
  const reason=error instanceof Error?error.message:'unknown';
  const safe=/^(missing_credentials|network_unavailable|invalid_json|invalid_positions_response|binance_http_\d{3})$/.test(reason)?reason:'monitor_failed';
  await env.SIGNAL_STATE.put('account:health',JSON.stringify({status:'error',reason:safe,checkedAt:Date.now()}),{expirationTtl:86400});
  console.warn(JSON.stringify({event:'binance_account_monitor',status:'error',reason:safe}));
  return 'error';
 }
}

export default {
 async scheduled(event,env,ctx){if(!env.TELEGRAM_BOT_TOKEN||!env.TELEGRAM_CHAT_ID||!env.SIGNAL_STATE){console.error('Missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID or SIGNAL_STATE KV; scans disabled');throw Error('Scanner configuration incomplete');}if(env.TELEGRAM_ACCESS_ENABLED!=='0')ctx.waitUntil(processTelegramAccess(env).catch(async error=>{const reason=String(error).replace(/bot[0-9]+:[A-Za-z0-9_-]+/g,'[REDACTED]').slice(0,180);console.error('Telegram access polling failed',reason);try{await env.SIGNAL_STATE.put('tg:access-health',JSON.stringify({status:'error',checkedAt:new Date().toISOString(),error:reason}));}catch{}}));ctx.waitUntil((async()=>{const news=await loadNews(env);try{await sendHourlyNewsDigest(env,news);}catch(error){console.warn('Hourly news delivery failed');}const results=[],failures=[];for(const symbol of SYMBOLS){try{const result=await scan(symbol,env,news);if(!result)throw Error('Stale candle skipped');results.push(result);}catch(error){const message=error instanceof Error?error.message:'Scan failed';failures.push({symbol,reason:message.slice(0,180)});console.error(JSON.stringify({event:'scan_failed',release:RELEASE,symbol,message}));}}const receipt={event:'scan_complete',release:RELEASE,source:'kraken_spot',cron:event.cron,scheduledTime:event.scheduledTime,recordedAt:Date.now(),ok:results.length===SYMBOLS.length,results,failures};
console.log(JSON.stringify(receipt));
await env.SIGNAL_STATE.put('health:cron:'+event.scheduledTime,JSON.stringify(receipt),{expirationTtl:86400});await env.SIGNAL_STATE.put('health:latest',JSON.stringify(receipt),{expirationTtl:86400});await monitorBinanceAccount(env);if(results.length!==SYMBOLS.length)throw Error('One or more market scans failed');})());},
 async fetch(request){return new Response(JSON.stringify({service:'SignalPilot scanner',mode:'scheduled-only',note:'No manual trading endpoint'}),{headers:{'content-type':'application/json'}});}
};
