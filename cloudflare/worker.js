// SignalPilot Cloudflare Worker: scheduled market research, no trade execution.
// Alerts are disabled until both Telegram secrets and SIGNAL_STATE KV are configured.
const SYMBOLS = ['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'];
const API = 'https://api.kraken.com/0/public/OHLC';
const PAIRS = {SOLUSDT:'SOLUSDT',BTCUSDT:'XBTUSDT',ETHUSDT:'ETHUSDT',XRPUSDT:'XRPUSDT'};
const RELEASE = 'kraken-news-v3';
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
export function formatScanStatus(symbol,five,four,found,now=Date.now(),news){
 const last=five.at(-1), previous=five.slice(-13,-1), volume=last.volume/avg(previous.map(b=>b.volume));
 const closes=four.map(b=>b.close), fast=ema(closes,20), slow=ema(closes,50);
 const trend=fast>slow?'עולה 📈':fast<slow?'יורדת 📉':'ללא כיוון';
 const clock=new Intl.DateTimeFormat('he-IL',{timeZone:'Asia/Jerusalem',hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
 const time=value=>clock.format(new Date(value));
 const strategies=[['BREAKOUT','פריצת מחיר'],['EMA_ADX','EMA + ADX'],['RSI_BOLL','RSI + רצועות'],['MACD_VOLUME','MACD + נפח']];
 const lines=strategies.map(([key,label])=>{
  const matched=found.filter(s=>s.strategy===key);
  return (matched.length?'✅ ':'▫️ ')+label+': '+(matched.length?'עבר ('+matched.map(s=>s.direction==='LONG'?'לונג':'שורט').join(', ')+')':'לא עבר');
 });
 return ['📊 '+symbol+' | '+(found.length?'נמצאו איתותים':'⏸ אין איתות'),
  '🕒 '+time(now)+' | נר '+time(last.time)+'–'+time(last.time+PERIOD)+' (ישראל)',
  '',
  'מחיר סגירה: $'+last.close.toFixed(5),
  'מגמת 4 שעות: '+trend,
  'נפח: '+(Number.isFinite(volume)?Math.round(volume*100)+'% מהממוצע':'לא זמין'),
  'RSI: '+rsi(five.map(b=>b.close)).toFixed(1)+' | ADX: '+adx(four).toFixed(1),
  '',
  'בדיקות כניסה — כולל סינון סטופ:',
  ...lines,
  '',
  found.length?'🔔 איתותים חדשים נשלחים בהודעה נפרדת.':'אין כניסה שעברה את תנאי הסורק.',
  'ℹ️ דוח תנאים בלבד | Kraken Spot (USDT)',
  '',formatNewsContext(news,symbol)
 ].join('\n');
}
async function send(env,msg){let r=await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:msg,disable_web_page_preview:true}),signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('Telegram HTTP '+r.status);let j=await r.json();if(!j.ok)throw Error('Telegram API rejected message');}
async function scan(symbol,env,news){let [five,four]=await Promise.all([candles(symbol,'5m',120),candles(symbol,'4h',100)]),last=five.at(-1),age=(Date.now()-(last.time+PERIOD))/60000;console.log(JSON.stringify({event:'scan',symbol,candle:new Date(last.time).toISOString(),closedAgeMinutes:+age.toFixed(2)}));if(age<0||age>7){console.warn('Skipping stale candle',symbol,age);return;}
let checks=[],found=setups(five,four,checks);console.log(JSON.stringify({event:'candidates',symbol,count:found.length,strategies:found.map(s=>s.strategy)}));for(let s of found){let key='signal:'+symbol+':'+s.candle+':'+s.strategy+':'+s.direction;if(await env.SIGNAL_STATE.get(key)){console.log('Duplicate skipped',key);continue;}
let risk=Math.abs(s.entry-s.stop),target=s.entry+(s.direction==='LONG'?2:-2)*risk;
let msg='🔔 '+symbol+' '+s.direction+' | '+s.strategy+'\nדירוג תנאים: '+s.score+'/100 (לא הסתברות הצלחה)\nנר: '+new Date(s.candle).toISOString()+'\nכניסה תיאורטית: $'+s.entry.toFixed(5)+'\nסטופ: $'+s.stop.toFixed(5)+' ('+s.stopPct.toFixed(2)+'%)\nיעד 2R: $'+target.toFixed(5)+'\n'+s.reason+'\n⚠️ מחקר בלבד. אין ביצוע מסחר אוטומטי.';
await send(env,msg+'\nמקור נתונים: Kraken Spot (USDT)\n\n'+formatNewsContext(news,symbol,2));await env.SIGNAL_STATE.put(key,'sent',{expirationTtl:86400});console.log('Alert sent',key);}
const statusKey='status:'+symbol+':'+last.time;
let statusDelivery='already_sent';
if(!await env.SIGNAL_STATE.get(statusKey)){
 const status=formatScanStatus(symbol,five,four,found,Date.now(),news);
 await send(env,status);
 await env.SIGNAL_STATE.put(statusKey,'sent',{expirationTtl:86400});
 statusDelivery='sent';
 console.log(JSON.stringify({event:'status_sent',symbol,candle:new Date(last.time).toISOString(),release:RELEASE}));
}
await notifyFreshNews(symbol,env,news);
return {symbol,candle:new Date(last.time).toISOString(),candidates:found.length,closedAgeMinutes:+age.toFixed(2),statusDelivery,newsStatus:news?.status||'unavailable',newsCount:newsForSymbol(news,symbol).length};}
export default {
 async scheduled(event,env,ctx){if(!env.TELEGRAM_BOT_TOKEN||!env.TELEGRAM_CHAT_ID||!env.SIGNAL_STATE){console.error('Missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID or SIGNAL_STATE KV; scans disabled');throw Error('Scanner configuration incomplete');}ctx.waitUntil((async()=>{const news=await loadNews(env);const results=[];for(const symbol of SYMBOLS){try{const result=await scan(symbol,env,news);if(!result)throw Error('Stale candle skipped');results.push(result);}catch(error){console.error(JSON.stringify({event:'scan_failed',release:RELEASE,symbol,message:error instanceof Error?error.message:'Scan failed'}));}}console.log(JSON.stringify({event:'scan_complete',release:RELEASE,source:'kraken',cron:event.cron,scheduledTime:event.scheduledTime,ok:results.length===SYMBOLS.length,results}));if(results.length!==SYMBOLS.length)throw Error('One or more market scans failed');})());},
 async fetch(request){return new Response(JSON.stringify({service:'SignalPilot scanner',mode:'scheduled-only',note:'No manual trading endpoint'}),{headers:{'content-type':'application/json'}});}
};
