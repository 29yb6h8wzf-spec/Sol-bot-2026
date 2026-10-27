import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('./worker.js',import.meta.url),'utf8');
const {candles,parseNewsFeed,newsForSymbol,formatNewsContext,loadNews,tradePlan,tradeMessage,readBinancePositions,monitorBinanceAccount,processTelegramAccess,default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const now=Date.now, originalFetch=globalThis.fetch;
const fixed=Math.floor(Date.now()/14400000)*14400000;
let telegramMessages=[], telegramStatus=200, newsXML='<rss><channel></channel></rss>';
function payload(minutes=5){
 const duration=minutes*60000,end=Math.floor(fixed/duration)*duration,count=minutes===240?101:121;
 return Array.from({length:count},(_,i)=>{
  const open=end-(count-1-i)*duration;
  return [open,'100','102','99','101','42',open+duration-1,'4200',100,'21','2100','0'];
 });
}
async function withData(body,fn,status=200){Date.now=()=>fixed;globalThis.fetch=async (u,options)=>{if(['https://www.coindesk.com/arc/outboundfeeds/rss/','https://cointelegraph.com/rss'].includes(String(u)))return new Response(newsXML);if(String(u).startsWith('https://api.telegram.org/')){telegramMessages.push(JSON.parse(options.body));return new Response(JSON.stringify({ok:telegramStatus===200}),{status:telegramStatus});}assert.equal(u.origin,'https://fapi.binance.com');assert.equal(u.pathname,'/fapi/v1/klines');assert.ok(['5m','4h'].includes(u.searchParams.get('interval')));assert.ok(['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'].includes(u.searchParams.get('symbol')));return new Response(JSON.stringify(typeof body==='function'?body(u):body),{status});};try{await fn();}finally{Date.now=now;globalThis.fetch=originalFetch;}}
test('Binance Futures maps milliseconds and base volume and excludes open candle',async()=>{await withData(payload(),async()=>{const bars=await candles('BTCUSDT','5m',120);assert.equal(bars.length,120);assert.equal(bars.at(-1).time,fixed-300000);assert.equal(bars[0].volume,42);});});
test('4h freshness uses its own interval rather than the 5m age limit',async()=>{await withData(payload(240),async()=>{Date.now=()=>fixed+90*60000;assert.equal((await candles('SOLUSDT','4h',100)).length,100);});});
test('rejects API errors, malformed prices, gaps, stale data and HTTP failures',async()=>{await withData({code:-1121,msg:'Invalid symbol'},()=>assert.rejects(candles('SOLUSDT','5m',120),/Invalid Binance Futures klines response/));for(const mutate of [b=>b[100][4]='NaN',b=>b.splice(90,1),b=>b.forEach(r=>r[0]-=3600000)]){let b=payload();mutate(b);await withData(b,()=>assert.rejects(candles('ETHUSDT','5m',120)));}await withData({},()=>assert.rejects(candles('XRPUSDT','5m',120),/HTTP 403/),403);});
test('scheduled scans remain silent without setups, but still scan all four markets',async()=>{
 const logs=[],oldLog=console.log,state=new Map();console.log=(...args)=>logs.push(args);telegramMessages=[];
 const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
 try{await withData(u=>payload(u.searchParams.get('interval')==='4h'?240:5),async()=>{
  async function run(){let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});await work;}
  await run();assert.equal(telegramMessages.length,0);
  const result=logs.map(a=>{try{return JSON.parse(a[0]);}catch{return {};}}).find(x=>x.event==='scan_complete');
  assert.equal(result.ok,true);assert.equal(result.results.length,4);
  assert.ok(result.results.every(x=>x.statusDelivery==='suppressed_no_signal'&&x.candidates===0));
  await run();assert.equal(telegramMessages.length,0);
 });}finally{console.log=oldLog;}
});
test('Telegram rejection for breaking news does not mark news as delivered',async()=>{
 const state=new Map(),oldLog=console.log,oldError=console.error;console.log=()=>{};console.error=()=>{};telegramStatus=403;
 newsXML='<rss><channel><item><title>Bitcoin network update</title><link>https://www.coindesk.com/news/bitcoin-update</link><pubDate>'+new Date(fixed-60000).toUTCString()+'</pubDate></item></channel></rss>';
 try{await withData(u=>payload(u.searchParams.get('interval')==='4h'?240:5),async()=>{
  let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},{TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}},{waitUntil:p=>work=p});
  await assert.rejects(work,/market scans failed/);
  assert.equal([...state.keys()].filter(k=>k.startsWith('news:sent:')).length,0);
 });}finally{console.log=oldLog;console.error=oldError;telegramStatus=200;newsXML='<rss><channel></channel></rss>';}
});
test('news parses safe publisher links and dates, filters each coin, and labels outages',()=>{
 const feed={name:'CoinDesk',host:'coindesk.com'};
 const item=(title,url,date)=>'<item><title><![CDATA['+title+']]></title><link>'+url+'</link><pubDate>'+new Date(date).toUTCString()+'</pubDate></item>';
 const xml='<rss><channel>'+item('Bitcoin &amp; Ethereum update','https://www.coindesk.com/test',fixed-60000)+item('Solana old update','https://www.coindesk.com/old',fixed-90000000)+item('XRP fake','https://malicious.test/x',fixed-60000)+item('Solana future','https://www.coindesk.com/future',fixed+3600000)+'</channel></rss>';
 const items=parseNewsFeed(xml,feed,fixed);assert.equal(items.length,1);assert.equal(items[0].title,'Bitcoin & Ethereum update');
 assert.equal(newsForSymbol({items},'BTCUSDT',fixed).length,1);assert.equal(newsForSymbol({items},'SOLUSDT',fixed).length,0);
 assert.match(formatNewsContext({status:'unavailable'},'XRPUSDT'),/לא זמינים/);
 assert.match(formatNewsContext({status:'stale',fetchedAt:fixed,items:[]},'XRPUSDT'),/לא עדכני/);
 assert.throws(()=>parseNewsFeed('<html>blocked</html>',feed,fixed),/Invalid news/);
});
test('news source outages are explicit and do not claim there are no headlines',async()=>{
 const saved=globalThis.fetch;globalThis.fetch=async()=>new Response('',{status:503});
 try{const state=await loadNews({SIGNAL_STATE:{get:async()=>null,put:async()=>{}}},fixed);assert.equal(state.status,'unavailable');assert.match(formatNewsContext(state,'BTCUSDT'),/לא נבדק סיכון חדשותי/);}finally{globalThis.fetch=saved;}
});

test('new headline notifications are coin-specific and deduplicated independently of scan reports',async()=>{
 const state=new Map(),oldLog=console.log;console.log=()=>{};telegramMessages=[];
 newsXML='<rss><channel><item><title>Bitcoin network update</title><link>https://www.coindesk.com/news/bitcoin-update</link><pubDate>'+new Date(fixed-60000).toUTCString()+'</pubDate></item></channel></rss>';
 try{await withData(u=>payload(u.searchParams.get('interval')==='4h'?240:5),async()=>{
  const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
  async function run(){let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});await work;}
  await run();const alerts=telegramMessages.filter(m=>m.text.startsWith('📰 '));assert.equal(alerts.length,1);assert.ok(alerts[0].text.includes('BTCUSDT'));assert.ok(alerts[0].text.includes('https://www.coindesk.com/news/bitcoin-update'));assert.equal(telegramMessages.length,1);
  await run();assert.equal(telegramMessages.length,1);
 });}finally{console.log=oldLog;newsXML='<rss><channel></channel></rss>';}
});

test('trade plans have directional entry zones, expiry, risk sizing and clean messages',()=>{
 const base=Date.UTC(2026,9,27,0,30);
 const bars=Array.from({length:120},(_,i)=>({time:base-(120-i)*300000,high:100.4,low:99.6,close:100,volume:100}));
 const long={strategy:'BREAKOUT',direction:'LONG',entry:100,stop:99,score:75,reason:'test',candle:base-300000};
 const p=tradePlan(long,bars,base);
 assert.ok(p);assert.ok(p.low<100&&p.high>100);assert.equal(p.target,102);
 assert.equal(p.expires,base+900000);assert.ok(p.netR>=1.25);
 const short={...long,direction:'SHORT',stop:101};
 const q=tradePlan(short,bars,base);
 assert.ok(q);assert.equal(q.target,98);
 assert.equal(tradePlan(long,bars,base+900000),null);
 assert.equal(tradePlan({...long,stop:101},bars,base),null);
 const msg=tradeMessage('BTCUSDT',short,q,{status:'unavailable'});
 for(const term of ['טווח כניסה','סטופ','יעד','תוקף','ביטול','Binance USDⓈ-M Perpetual','סיכון'])assert.ok(msg.includes(term),term);
});

test('real XRP trade fixture and futures margin math are internally consistent',()=>{
 const entry=1.3106,exit=1.3025,qty=56.1,reportedNet=0.38;
 const gross=(entry-exit)*qty;
 assert.ok(Math.abs(gross-0.45441)<1e-8);
 assert.ok(gross>reportedNet);
 const base=Date.UTC(2026,9,27,0,30);
 const bars=Array.from({length:120},(_,i)=>({time:base-(120-i)*300000,high:1.32,low:1.30,close:1.31,volume:100}));
 const short={strategy:'BREAKOUT',direction:'SHORT',entry:1.3106,stop:1.325,score:75,reason:'test',candle:base-300000};
 const plan=tradePlan(short,bars,base);
 assert.ok(plan);
 assert.equal(plan.leverage,2);
 assert.ok(Math.abs(plan.margin*2-plan.notional)<1e-8);
 assert.ok(plan.quantity*plan.worstLoss<=1.50000001);
 assert.ok(plan.netR>=1.25);
 const text=tradeMessage('XRPUSDT',short,plan,{status:'unavailable'});
 for(const term of ['XRP','2X','ביטחונות','עמלה','החלקה','funding','Binance USDⓈ-M Perpetual'])assert.ok(text.includes(term),term);
 const withHighFees=tradePlan(short,bars,base,{riskBudget:1.5,leverage:2,feeRate:0.005,slippageRate:0.0025,minNetR:1.25});
 assert.equal(withHighFees,null);
});

test('Bybit USDT perpetual fallback parses reverse-ordered candles and retains source labels',async()=>{
 const original=globalThis.fetch;Date.now=()=>fixed;
 const calls=[];
 globalThis.fetch=async u=>{
  if(String(u).startsWith('https://api.bybit.com/')){
   calls.push(String(u));
   const interval=u.searchParams.get('interval');
   const rows=payload(interval==='240'?240:5).reverse().map(x=>x.slice(0,6).map(String));
   return new Response(JSON.stringify({retCode:0,result:{category:'linear',symbol:u.searchParams.get('symbol'),list:rows}}));
  }
  throw Error('Unexpected URL');
 };
 try{
  const bars=await candles('XRPUSDT','5m',120,'bybit');
  assert.equal(bars.length,120);assert.equal(bars.at(-1).time,fixed-300000);
  assert.ok(calls[0].includes('category=linear'));
  assert.equal((await candles('XRPUSDT','4h',100,'bybit')).length,100);
 }finally{globalThis.fetch=original;Date.now=now;}
});
test('when Binance is down, scans use only Bybit perpetual candles and label their proxy source',async()=>{
 const original=globalThis.fetch;Date.now=()=>fixed;const oldLog=console.log,oldWarn=console.warn;const logs=[];
 console.log=(...a)=>logs.push(a.join(' '));console.warn=()=>{};
 globalThis.fetch=async u=>{
  if(String(u).startsWith('https://fapi.binance.com/'))return new Response('Unavailable',{status:451});
  if(String(u).startsWith('https://api.bybit.com/')){
   const interval=u.searchParams.get('interval'),rows=payload(interval==='240'?240:5).reverse().map(x=>x.slice(0,6).map(String));
   return new Response(JSON.stringify({retCode:0,result:{category:'linear',symbol:u.searchParams.get('symbol'),list:rows}}));
  }
  if(String(u).startsWith('https://api.telegram.org/'))return new Response(JSON.stringify({ok:true}));
  return new Response(newsXML);
 };
 try{
  let work;const state=new Map();
  await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},{TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}},{waitUntil:p=>work=p});
  await work;
  const complete=logs.map(x=>{try{return JSON.parse(x)}catch{return null}}).find(x=>x?.event==='scan_complete');
  assert.equal(complete.ok,true);
  assert.ok(complete.results.every(x=>x.source==='bybit_linear'));
 }finally{Date.now=now;globalThis.fetch=original;console.log=oldLog;console.warn=oldWarn;}
});
test('OKX USDT SWAP fallback validates closed candles, UTC 4h bars and underlying volume',async()=>{
 const oldFetch=globalThis.fetch;Date.now=()=>fixed;
 const seen=[];
 globalThis.fetch=async u=>{
  seen.push(String(u));
  assert.equal(u.origin,'https://www.okx.com');
  assert.match(u.searchParams.get('instId'),/^(SOL|BTC|ETH|XRP)-USDT-SWAP$/);
  const interval=u.searchParams.get('bar'),minutes=interval==='4Hutc'?240:5;
  assert.ok(interval==='4Hutc'||interval==='5m');
  const rows=payload(minutes).slice(-Number(u.searchParams.get('limit'))).reverse().map(x=>[String(x[0]),x[1],x[2],x[3],x[4],'4','42','4200',String(x[0]+minutes*60000<=fixed?'1':'0')]);
  return new Response(JSON.stringify({code:'0',data:rows}));
 };
 try{
  const five=await candles('ETHUSDT','5m',120,'okx');
  assert.equal(five.length,99);assert.equal(five.at(-1).volume,42);
  assert.equal((await candles('ETHUSDT','4h',100,'okx')).length,99);
  assert.ok(seen.some(x=>x.includes('bar=4Hutc')));
 }finally{globalThis.fetch=oldFetch;Date.now=now;}
});
test('Binance 451 and Bybit 403 fall back to isolated OKX research-only market data',async()=>{
 const oldFetch=globalThis.fetch,oldLog=console.log,oldWarn=console.warn;Date.now=()=>fixed;const logs=[];
 console.log=(...a)=>logs.push(a.join(' '));console.warn=()=>{};
 globalThis.fetch=async u=>{
  if(String(u).startsWith('https://fapi.binance.com/'))return new Response('Unavailable',{status:451});
  if(String(u).startsWith('https://api.bybit.com/'))return new Response('Forbidden',{status:403});
  if(String(u).startsWith('https://www.okx.com/')){
   const minutes=u.searchParams.get('bar')==='4Hutc'?240:5;
   return new Response(JSON.stringify({code:'0',data:payload(minutes).slice(-Number(u.searchParams.get('limit'))).reverse().map(x=>[String(x[0]),x[1],x[2],x[3],x[4],'4','42','4200',String(x[0]+minutes*60000<=fixed?'1':'0')])}));
  }
  if(String(u).startsWith('https://api.telegram.org/'))return new Response(JSON.stringify({ok:true}));
  return new Response(newsXML);
 };
 try{
  let work;const state=new Map();
  await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},{TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}},{waitUntil:p=>work=p});
  await work;
  const receipt=JSON.parse(state.get('health:cron:'+fixed));
  assert.equal(receipt.ok,true);
  assert.ok(receipt.results.every(x=>x.source==='okx_swap'));
 }finally{globalThis.fetch=oldFetch;Date.now=now;console.log=oldLog;console.warn=oldWarn;}
});
test('Binance Futures rejects unavailable endpoint, spot fallback, malformed and future candles',async()=>{
 await withData({code:-1003,msg:'rate limit'},()=>assert.rejects(candles('BTCUSDT','5m',120),/Invalid Binance Futures/));
 const future=payload();future.forEach(x=>x[0]+=86400000);
 await withData(future,()=>assert.rejects(candles('BTCUSDT','5m',120),/Invalid|Stale|Insufficient/));
 const bad=payload();bad[90][5]='NaN';
 await withData(bad,()=>assert.rejects(candles('BTCUSDT','5m',120),/Invalid or non-contiguous/));
});

test('scheduled worker persists durable KV receipt with all four futures sources',async()=>{
 const logs=[],stored=new Map(),oldLog=console.log;console.log=(...args)=>logs.push(args);
 try{await withData(u=>payload(u.searchParams.get('interval')==='4h'?240:5),async()=>{
  let work;
  const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>stored.get(k)||null,put:async(k,v)=>stored.set(k,v)}};
  await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});await work;
  const receipt=JSON.parse(stored.get('health:cron:'+fixed));
  assert.equal(receipt.ok,true);assert.equal(receipt.release,'futures-source-okx-cap-v8');
  assert.equal(receipt.results.length,4);assert.equal(receipt.failures.length,0);
  assert.ok(receipt.results.every(x=>x.source==='binance_usdm'));
 });}finally{console.log=oldLog;}
});
test('scheduled worker persists failure receipt for debugging without suppressing failure',async()=>{
 const stored=new Map(),oldError=console.error,oldLog=console.log;console.error=()=>{};console.log=()=>{};
 try{await withData({},async()=>{
  let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},{TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>stored.get(k)||null,put:async(k,v)=>stored.set(k,v)}},{waitUntil:p=>work=p});
  await assert.rejects(work,/market scans failed/);
  const receipt=JSON.parse(stored.get('health:cron:'+fixed));
  assert.equal(receipt.ok,false);assert.equal(receipt.failures.length,4);
 });}finally{console.error=oldError;console.log=oldLog;}
});

test('Binance account monitor uses signed GET and never enables trade actions',async()=>{
 const oldFetch=globalThis.fetch,oldDate=Date.now,kv=new Map(),requests=[];
 Date.now=()=>fixed;
 globalThis.fetch=async (url,options)=>{
  requests.push({url:String(url),method:options.method,headers:options.headers});
  if(String(url).includes('/fapi/v2/positionRisk?'))return new Response(JSON.stringify([
   {symbol:'XRPUSDT',positionAmt:'-75.34',entryPrice:'1.2955',markPrice:'1.2960',unRealizedProfit:'-0.03',leverage:'2',marginType:'isolated'},
   {symbol:'BTCUSDT',positionAmt:'0',entryPrice:'0',markPrice:'90000',unRealizedProfit:'0',leverage:'2',marginType:'isolated'}
  ]));
  if(String(url).includes('api.telegram.org'))return new Response(JSON.stringify({ok:true}));
  throw Error('Unexpected URL');
 };
 const env={BINANCE_API_KEY:'test-key',BINANCE_API_SECRET:'test-secret',TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 try{
  const positions=await readBinancePositions(env);
  assert.equal(positions.length,1);assert.equal(positions[0].side,'SHORT');assert.equal(positions[0].entry,1.2955);
  assert.equal(await monitorBinanceAccount(env),'connected');
  assert.equal(JSON.parse(kv.get('account:health')).status,'connected');
  assert.equal(JSON.parse(kv.get('account:positions')).length,1);
  assert.equal(await monitorBinanceAccount(env),'connected');
  assert.equal(requests.filter(x=>x.url.includes('api.telegram.org')).length,1);
  assert.ok(requests.filter(x=>x.url.includes('/positionRisk')).every(x=>x.method==='GET'&&x.headers['X-MBX-APIKEY']==='test-key'&&x.url.includes('signature=')));
  assert.ok(!JSON.stringify(kv).includes('test-secret'));
 }finally{globalThis.fetch=oldFetch;Date.now=oldDate;}
});
test('Binance monitor records inaccessible API as health error without leaking secrets or stopping scanner',async()=>{
 const oldFetch=globalThis.fetch,oldWarn=console.warn,kv=new Map(),logs=[];console.warn=(...a)=>logs.push(a.join(' '));
 globalThis.fetch=async()=>new Response('Access denied',{status:403});
 const env={BINANCE_API_KEY:'private-key',BINANCE_API_SECRET:'private-secret',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 try{
  assert.equal(await monitorBinanceAccount(env),'error');
  assert.equal(JSON.parse(kv.get('account:health')).reason,'binance_http_403');
  assert.ok(!logs.join(' ').includes('private-secret'));
  assert.ok(!logs.join(' ').includes('private-key'));
 }finally{globalThis.fetch=oldFetch;console.warn=oldWarn;}
});

test('only owner can approve private SignalPilot subscribers',async()=>{
 const saved=globalThis.fetch,kv=new Map(),sent=[],queue=[];
 const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 globalThis.fetch=async (url,options)=>{
  const method=String(url).split('/').at(-1),body=JSON.parse(options.body);
  if(method==='getUpdates')return new Response(JSON.stringify({ok:true,result:queue.filter(x=>x.update_id>=body.offset)}));
  if(method==='sendMessage'){sent.push(body);return new Response(JSON.stringify({ok:true,result:{message_id:1}}));}
  throw Error('Unexpected Telegram method '+method);
 };
 const msg=(n,id,text)=>({update_id:n,message:{chat:{id,type:'private'},text}});
 try{
  queue.push(msg(1,200,'/start'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:pending')),['200']);
  assert.ok(sent.some(x=>x.chat_id==='100'&&x.reply_markup?.inline_keyboard?.[0]?.[0]?.callback_data==='access:approve:200'));
  queue.push(msg(2,300,'/approve 200'));await processTelegramAccess(env);
  assert.equal(kv.get('tg:approved'),undefined);
  queue.push(msg(3,100,'/approve 200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),['200']);
  queue.push(msg(4,100,'/remove 200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),[]);
 }finally{globalThis.fetch=saved;}
});

test('Hebrew access dashboard supports owner-only inline approvals, rejects and removals',async()=>{
 const saved=globalThis.fetch,kv=new Map(),sent=[],answers=[],queue=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 globalThis.fetch=async(url,options)=>{
  const method=String(url).split('/').at(-1),body=JSON.parse(options.body);
  if(method==='getUpdates')return new Response(JSON.stringify({ok:true,result:queue.filter(x=>x.update_id>=body.offset)}));
  if(method==='sendMessage'){sent.push(body);return new Response(JSON.stringify({ok:true,result:{message_id:1}}));}
  if(method==='answerCallbackQuery'){answers.push(body);return new Response(JSON.stringify({ok:true,result:true}));}
  throw Error('Unexpected Telegram method '+method);
 };
 const msg=(n,id,text)=>({update_id:n,message:{chat:{id,type:'private'},from:{id},text}});
 const cb=(n,id,from,data)=>({update_id:n,callback_query:{id:'callback'+n,from:{id:from},message:{chat:{id,type:'private'}},data}});
 try{
  queue.push(msg(1,200,'/start'));await processTelegramAccess(env);
  const request=sent.find(x=>x.chat_id==='100'&&x.text.includes('בקשת הצטרפות'));
  assert.ok(request);
  assert.equal(request.reply_markup.inline_keyboard[0][0].callback_data,'access:approve:200');
  assert.equal(request.reply_markup.inline_keyboard[0][1].callback_data,'access:remove:200');
  queue.push(cb(2,100,200,'access:approve:200'));await processTelegramAccess(env);
  assert.equal(kv.get('tg:approved'),undefined);
  assert.ok(answers.at(-1).show_alert);
  queue.push(cb(3,100,100,'access:approve:200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),['200']);
  assert.ok(sent.some(x=>x.chat_id==='200'&&x.text.includes('אושרה')));
  queue.push(msg(4,100,'/users'));await processTelegramAccess(env);
  const dashboard=sent.filter(x=>x.chat_id==='100'&&x.text.includes('ניהול חברים')).at(-1);
  assert.ok(dashboard.text.includes('\n'));
  assert.ok(!dashboard.text.includes('\\n'));
  assert.ok(dashboard.reply_markup.inline_keyboard.flat().some(x=>x.callback_data==='access:remove:200'));
  queue.push(cb(5,100,100,'access:remove:200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),[]);
  queue.push(cb(6,100,100,'access:approve:200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),[]);
  queue.push(msg(7,300,'/start'));await processTelegramAccess(env);
  queue.push(cb(8,100,100,'access:remove:300'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:pending')),[]);
 }finally{globalThis.fetch=saved;}
});

test('expired Telegram callback acknowledgement does not block owner approval',async()=>{
 const saved=globalThis.fetch,kv=new Map(),sent=[],queue=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 globalThis.fetch=async(url,options)=>{
  const method=String(url).split('/').at(-1),body=JSON.parse(options.body);
  if(method==='getUpdates')return new Response(JSON.stringify({ok:true,result:queue.filter(x=>x.update_id>=body.offset)}));
  if(method==='sendMessage'){sent.push(body);return new Response(JSON.stringify({ok:true,result:{message_id:1}}));}
  if(method==='answerCallbackQuery')return new Response(JSON.stringify({ok:false,error_code:400,description:'Bad Request: query is too old and response timeout expired'}),{status:400});
  throw Error('Unexpected Telegram method '+method);
 };
 const msg=(n,id,text)=>({update_id:n,message:{chat:{id,type:'private'},from:{id},text}});
 const cb=(n,id,from,data)=>({update_id:n,callback_query:{id:'expired'+n,from:{id:from},message:{chat:{id,type:'private'}},data}});
 try{
  queue.push(msg(1,200,'/start'));await processTelegramAccess(env);
  queue.push(cb(2,100,100,'access:approve:200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),['200']);
  assert.equal(kv.get('tg:offset'),'3');
  assert.ok(sent.some(x=>x.chat_id==='200'&&x.text.includes('אושרה')));
  queue.push(cb(3,100,100,'access:remove:200'));await processTelegramAccess(env);
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),[]);
 }finally{globalThis.fetch=saved;}
});
