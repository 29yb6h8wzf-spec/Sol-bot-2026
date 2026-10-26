// SignalPilot Cloudflare Worker: scheduled market research, no trade execution.
// Alerts are disabled until both Telegram secrets and SIGNAL_STATE KV are configured.
const SYMBOLS = ['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'];
const API = 'https://api.kraken.com/0/public/OHLC';
const PAIRS = {SOLUSDT:'SOLUSDT',BTCUSDT:'XBTUSDT',ETHUSDT:'ETHUSDT',XRPUSDT:'XRPUSDT'};
const RELEASE = 'kraken-ohlc-v1';
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
function setups(five,four) {let last=five.at(-1),cl=five.map(x=>x.close),fc=four.map(x=>x.close),e20=ema(fc,20),e50=ema(fc,50),prev=five.slice(-13,-1),high=Math.max(...prev.map(x=>x.high)),low=Math.min(...prev.map(x=>x.low)),vr=last.volume/avg(prev.map(x=>x.volume)),out=[];
let direction=e20>e50&&last.close>high&&vr>=1.5?'LONG':e20<e50&&last.close<low&&vr>=1.5?'SHORT':null;
if(direction){let stop=direction==='LONG'?low:high;out.push({strategy:'BREAKOUT',direction,stop,score:75,reason:'12-candle breakout; volume x'+vr.toFixed(2)});}
let strength=adx(four),volatility=atr(five),momentum=rsi(cl),e9=emaSeries(cl,9),e21=emaSeries(cl,21),macd=emaSeries(cl,12).map((v,i)=>v-emaSeries(cl,26)[i]),sig=emaSeries(macd,9),[lo,hi]=bands(cl);
function add(strategy,direction,condition,score,reason){if(condition)out.push({strategy,direction,stop:direction==='LONG'?last.close-1.5*volatility:last.close+1.5*volatility,score:Math.min(95,Math.round(score)),reason});}
for(let side of ['LONG','SHORT']){let up=side==='LONG',trend=up?e20>e50:e20<e50,reclaim=up?cl.at(-2)<=e9.at(-2)&&last.close>e9.at(-1):cl.at(-2)>=e9.at(-2)&&last.close<e9.at(-1),aligned=up?e9.at(-1)>e21.at(-1):e9.at(-1)<e21.at(-1);add('EMA_ADX',side,trend&&reclaim&&aligned&&strength>=20&&vr>=0.8,60+Math.min(15,strength-20)+Math.min(15,vr*8),'4h ADX '+strength.toFixed(1)+'; EMA reclaim; volume x'+vr.toFixed(2));}
add('RSI_BOLL','LONG',strength<25&&cl.at(-2)<bands(cl.slice(0,-1))[0]&&last.close>lo&&momentum<45,65+Math.max(0,45-momentum)/3,'RSI '+momentum.toFixed(1)+'; lower band reclaim');
add('RSI_BOLL','SHORT',strength<25&&cl.at(-2)>bands(cl.slice(0,-1))[1]&&last.close<hi&&momentum>55,65+Math.max(0,momentum-55)/3,'RSI '+momentum.toFixed(1)+'; upper band reclaim');
add('MACD_VOLUME','LONG',macd.at(-2)<=sig.at(-2)&&macd.at(-1)>sig.at(-1)&&vr>=1.2&&momentum>50,65+Math.min(20,vr*10),'MACD bullish crossover; volume x'+vr.toFixed(2));
add('MACD_VOLUME','SHORT',macd.at(-2)>=sig.at(-2)&&macd.at(-1)<sig.at(-1)&&vr>=1.2&&momentum<50,65+Math.min(20,vr*10),'MACD bearish crossover; volume x'+vr.toFixed(2));
return out.slice(0,3).filter(s=>{let pct=100*Math.abs(last.close-s.stop)/last.close;return pct>=0.25&&pct<=1.5;}).map(s=>({...s,entry:last.close,stopPct:100*Math.abs(last.close-s.stop)/last.close,candle:last.time}));}
async function send(env,msg){let r=await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:msg}),signal:AbortSignal.timeout(12000)});if(!r.ok)throw Error('Telegram HTTP '+r.status);let j=await r.json();if(!j.ok)throw Error('Telegram API rejected message');}
async function scan(symbol,env){let [five,four]=await Promise.all([candles(symbol,'5m',120),candles(symbol,'4h',100)]),last=five.at(-1),age=(Date.now()-(last.time+PERIOD))/60000;console.log(JSON.stringify({event:'scan',symbol,candle:new Date(last.time).toISOString(),closedAgeMinutes:+age.toFixed(2)}));if(age<0||age>7){console.warn('Skipping stale candle',symbol,age);return;}
let found=setups(five,four);console.log(JSON.stringify({event:'candidates',symbol,count:found.length,strategies:found.map(s=>s.strategy)}));for(let s of found){let key='signal:'+symbol+':'+s.candle+':'+s.strategy+':'+s.direction;if(await env.SIGNAL_STATE.get(key)){console.log('Duplicate skipped',key);continue;}
let risk=Math.abs(s.entry-s.stop),target=s.entry+(s.direction==='LONG'?2:-2)*risk;
let msg='🔔 '+symbol+' '+s.direction+' | '+s.strategy+'\nדירוג תנאים: '+s.score+'/100 (לא הסתברות הצלחה)\nנר: '+new Date(s.candle).toISOString()+'\nכניסה תיאורטית: $'+s.entry.toFixed(5)+'\nסטופ: $'+s.stop.toFixed(5)+' ('+s.stopPct.toFixed(2)+'%)\nיעד 2R: $'+target.toFixed(5)+'\n'+s.reason+'\n⚠️ מחקר בלבד. אין ביצוע מסחר אוטומטי.';
await send(env,msg+'\nמקור נתונים: Kraken Spot (USDT)');await env.SIGNAL_STATE.put(key,'sent',{expirationTtl:86400});console.log('Alert sent',key);}return {symbol,candle:new Date(last.time).toISOString(),candidates:found.length,closedAgeMinutes:+age.toFixed(2)};}
export default {
 async scheduled(event,env,ctx){if(!env.TELEGRAM_BOT_TOKEN||!env.TELEGRAM_CHAT_ID||!env.SIGNAL_STATE){console.error('Missing TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID or SIGNAL_STATE KV; scans disabled');throw Error('Scanner configuration incomplete');}ctx.waitUntil((async()=>{const results=[];for(const symbol of SYMBOLS){try{const result=await scan(symbol,env);if(!result)throw Error('Stale candle skipped');results.push(result);}catch(error){console.error(JSON.stringify({event:'scan_failed',release:RELEASE,symbol,message:error instanceof Error?error.message:'Scan failed'}));}}console.log(JSON.stringify({event:'scan_complete',release:RELEASE,source:'kraken',cron:event.cron,scheduledTime:event.scheduledTime,ok:results.length===SYMBOLS.length,results}));if(results.length!==SYMBOLS.length)throw Error('One or more market scans failed');})());},
 async fetch(request){return new Response(JSON.stringify({service:'SignalPilot scanner',mode:'scheduled-only',note:'No manual trading endpoint'}),{headers:{'content-type':'application/json'}});}
};
