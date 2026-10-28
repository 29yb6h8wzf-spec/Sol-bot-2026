import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('./worker.js',import.meta.url),'utf8');
const {candles,fetchKrakenOHLC,parseNewsFeed,newsForSymbol,formatNewsContext,loadNews,tradePlan,tradeMessage,processTelegramAccess,readBinancePositions,monitorBinanceAccount,sendResearch,rsi,testBroadcast,evaluatePaperSignal,recordResearchSignal,filterAndLimitSetups,deliverResearchCandidates,scanAuditReport,sendDailyHeartbeat,setups,fetchMarketTimeframes,scoreWatchProgress,watchCandidates,sendWatchDigest,default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const now=Date.now, originalFetch=globalThis.fetch;
const fixed=1800000000000;
let telegramMessages=[], telegramStatus=200, newsXML='<rss><channel></channel></rss>';
function payload(minutes=5){const duration=minutes*60,end=Math.floor(fixed/1000/duration)*duration;return {error:[],result:{TESTPAIR:Array.from({length:121},(_,i)=>[end-(120-i)*duration,'100','102','99','101','100','42',5]),last:end}};}
async function withData(body,fn,status=200){Date.now=()=>fixed;globalThis.fetch=async (u,options)=>{if(['https://www.coindesk.com/arc/outboundfeeds/rss/','https://cointelegraph.com/rss'].includes(String(u)))return new Response(newsXML);if(String(u).startsWith('https://api.telegram.org/')){telegramMessages.push(JSON.parse(options.body));return new Response(JSON.stringify({ok:telegramStatus===200}),{status:telegramStatus});}assert.equal(u.origin,'https://api.kraken.com');assert.ok(['5','240'].includes(u.searchParams.get('interval')));return new Response(JSON.stringify(typeof body==='function'?body(u):body),{status});};try{await fn();}finally{Date.now=now;globalThis.fetch=originalFetch;}}

test('Kraken retries transient HTTP 429 then succeeds, without stale fallback',async()=>{
 const saved=globalThis.fetch;let attempts=0;
 globalThis.fetch=async()=>{attempts++;return attempts===1?new Response('',{status:429}):new Response(JSON.stringify(payload()));};
 try{const result=await fetchKrakenOHLC(new URL('https://api.kraken.com/0/public/OHLC'),'BTCUSDT','5m');assert.ok(result.result.TESTPAIR);assert.equal(attempts,2);}finally{globalThis.fetch=saved;}
});
test('Kraken retries temporary API errors but rejects invalid pairs immediately',async()=>{
 const saved=globalThis.fetch;let attempts=0;
 globalThis.fetch=async()=>{attempts++;return new Response(JSON.stringify(attempts===1?{error:['EAPI:Rate limit exceeded']}:{error:[],result:{TESTPAIR:[]}}));};
 try{await fetchKrakenOHLC(new URL('https://api.kraken.com/0/public/OHLC'),'SOLUSDT','5m');assert.equal(attempts,2);}finally{globalThis.fetch=saved;}
 attempts=0;globalThis.fetch=async()=>{attempts++;return new Response(JSON.stringify({error:['EQuery:Unknown asset pair']}));};
 try{await assert.rejects(fetchKrakenOHLC(new URL('https://api.kraken.com/0/public/OHLC'),'SOLUSDT','5m'),/non-retryable/);assert.equal(attempts,1);}finally{globalThis.fetch=saved;}
});

test('Kraken maps seconds and base volume and excludes open candle',async()=>{await withData(payload(),async()=>{const bars=await candles('BTCUSDT','5m',120);assert.equal(bars.length,119);assert.equal(bars.at(-1).time,fixed-300000);assert.equal(bars[0].volume,42);});});
test('4h freshness uses its own interval rather than the 5m age limit',async()=>{await withData(payload(240),async()=>{Date.now=()=>fixed+90*60000;assert.equal((await candles('SOLUSDT','4h',100)).length,99);});});
test('rejects API errors, malformed prices, gaps, stale data and HTTP failures',async()=>{await withData({error:['EQuery:Unknown asset pair']},()=>assert.rejects(candles('SOLUSDT','5m',120),/API rejected/));for(const mutate of [b=>b.result.TESTPAIR[100][4]='NaN',b=>b.result.TESTPAIR.splice(90,1),b=>b.result.TESTPAIR.forEach(r=>r[0]-=3600)]){let b=payload();mutate(b);await withData(b,()=>assert.rejects(candles('ETHUSDT','5m',120)));}await withData({},()=>assert.rejects(candles('XRPUSDT','5m',120),/HTTP 403/),403);});
test('five-minute scans stay silent without setups and send only one hourly news digest',async()=>{
 const logs=[],oldLog=console.log,state=new Map();console.log=(...args)=>logs.push(args);telegramMessages=[];
 const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
  async function run(){let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});await work;}
  await run();assert.equal(telegramMessages.length,1);
  assert.equal(telegramMessages.filter(m=>m.text.startsWith('📰 SignalPilot | עדכון חדשות שעתי')).length,1);
  const result=logs.map(a=>{try{return JSON.parse(a[0]);}catch{return {};}}).find(x=>x.event==='scan_complete');
  assert.equal(result.ok,true);assert.equal(result.results.length,4);
  assert.ok(result.results.every(x=>x.statusDelivery==='suppressed_no_signal'&&x.candidates===0));
  await run();assert.equal(telegramMessages.length,1);
 });}finally{console.log=oldLog;}
});
test('Telegram rejection for breaking news does not mark news as delivered',async()=>{
 const state=new Map(),oldLog=console.log,oldError=console.error;console.log=()=>{};console.error=()=>{};telegramStatus=403;
 newsXML='<rss><channel><item><title>Bitcoin network update</title><link>https://www.coindesk.com/news/bitcoin-update</link><pubDate>'+new Date(fixed-60000).toUTCString()+'</pubDate></item></channel></rss>';
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
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
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
  const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
  async function run(){let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});await work;}
  await run();const alerts=telegramMessages.filter(m=>m.text.startsWith('📰 BTCUSDT'));assert.equal(alerts.length,1);assert.ok(alerts[0].text.includes('BTCUSDT'));assert.ok(alerts[0].text.includes('https://www.coindesk.com/news/bitcoin-update'));assert.equal(telegramMessages.length,2);
  await run();assert.equal(telegramMessages.length,2);
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
 for(const term of ['טווח כניסה','סטופ','יעד','תוקף','ביטול','Kraken Spot','סיכון'])assert.ok(msg.includes(term),term);
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
 for(const term of ['XRP','2X','ביטחונות','עמלה','החלקה','funding','Kraken Spot'])assert.ok(text.includes(term),term);
 const withHighFees=tradePlan(short,bars,base,{riskBudget:1.5,leverage:2,feeRate:0.005,slippageRate:0.0025,minNetR:1.25});
 assert.equal(withHighFees,null);
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

test('owner-only testsignal delivers a clearly fake example without notifying approved subscribers',async()=>{
 const saved=globalThis.fetch,kv=new Map([['tg:approved','["200"]']]),sent=[],queue=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 globalThis.fetch=async(url,options)=>{
  const method=String(url).split('/').at(-1),body=JSON.parse(options.body);
  if(method==='getUpdates')return new Response(JSON.stringify({ok:true,result:queue.filter(x=>x.update_id>=body.offset)}));
  if(method==='sendMessage'){sent.push(body);return new Response(JSON.stringify({ok:true,result:{message_id:1}}));}
  throw Error('Unexpected Telegram method '+method);
 };
 const msg=(n,id,from,text)=>({update_id:n,message:{chat:{id,type:'private'},from:{id:from},text}});
 try{
  queue.push(msg(1,200,200,'/testsignal'));await processTelegramAccess(env);
  assert.equal(sent.length,1);
  assert.ok(!sent[0].text.includes('TEST SIGNAL'));
  queue.push(msg(2,100,300,'/testsignal'));await processTelegramAccess(env);
  assert.equal(sent.length,1);
  queue.push(msg(3,100,100,'/testsignal'));await processTelegramAccess(env);
  assert.equal(sent.length,2);
  assert.equal(String(sent[1].chat_id),'100');
  assert.match(sent[1].text,/TEST SIGNAL/);
  assert.match(sent[1].text,/DEMO/);
  assert.match(sent[1].text,/לא אות שוק/);
  assert.match(sent[1].text,/אינה מאשרת שהסורק/);
  assert.ok(!sent.some(x=>String(x.chat_id)==='200'&&x.text.includes('TEST SIGNAL')));
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),['200']);
 }finally{globalThis.fetch=saved;}
});

test('owner /status reflects actual KV receipt, denies subscriber access and never exposes Binance data',async()=>{
 const saved=globalThis.fetch, nowBefore=Date.now, kv=new Map(),sent=[],queue=[];
 const nowTime=1800000000000;
 Date.now=()=>nowTime;
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 globalThis.fetch=async(url,options)=>{
  const method=String(url).split('/').at(-1),body=JSON.parse(options.body);
  if(method==='getUpdates')return new Response(JSON.stringify({ok:true,result:queue.filter(x=>x.update_id>=body.offset)}));
  if(method==='sendMessage'){sent.push(body);return new Response(JSON.stringify({ok:true,result:{message_id:1}}));}
  throw Error('Unexpected Telegram method '+method);
 };
 const msg=(n,id,text)=>({update_id:n,message:{chat:{id,type:'private'},from:{id},text}});
 try{
  queue.push(msg(1,200,'/status'));await processTelegramAccess(env);
  assert.equal(sent.length,1);assert.equal(String(sent[0].chat_id),'200');
  assert.doesNotMatch(sent[0].text,/מצב הסורק החי/);
  queue.push(msg(2,100,'/status'));await processTelegramAccess(env);
  assert.match(sent.at(-1).text,/אין קבלת סריקה חיה/);
  const latestTime=nowTime-300000;
  const receipt=(scheduledTime,candle)=>({release:'kraken-stable-v9',cron:'*/5 * * * *',ok:true,recordedAt:nowTime,scheduledTime,source:'kraken_spot',results:['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'].map(symbol=>({symbol,source:'kraken_spot',candle:new Date(candle).toISOString(),closedAgeMinutes:5,candidates:0,statusDelivery:'suppressed_no_signal'})),failures:[]});
  const current=receipt(latestTime,nowTime-600000),previous=receipt(latestTime-300000,nowTime-900000);
  kv.set('health:latest',JSON.stringify(current));
  queue.push(msg(3,100,'/status'));await processTelegramAccess(env);
  assert.match(sent.at(-1).text,/ארבעת המטבעות נסרקו בהצלחה/);
  assert.match(sent.at(-1).text,/Kraken Spot/);
  assert.match(sent.at(-1).text,/קבלת ה-cron הקודמת חסרה/);
  kv.set('health:cron:'+(latestTime-300000),JSON.stringify(previous));
  queue.push(msg(5,100,'/status'));await processTelegramAccess(env);
  assert.match(sent.at(-1).text,/שתי קבלות cron רצופות אומתו/);
  assert.doesNotMatch(sent.at(-1).text,/entryPrice|positionAmt|unrealizedPnl|API_KEY/);
  kv.set('health:cron:'+(latestTime-300000),JSON.stringify(receipt(latestTime-300000,nowTime-600000)));
  queue.push(msg(6,100,'/status'));await processTelegramAccess(env);
  assert.match(sent.at(-1).text,/הנרות לא התקדמו/);
  kv.set('health:cron:'+(latestTime-300000),JSON.stringify({...previous,ok:false,failures:[{symbol:'SOLUSDT',reason:'secret'}]}));
  queue.push(msg(7,100,'/status'));await processTelegramAccess(env);
  assert.match(sent.at(-1).text,/הקודמת נכשלה או אינה תקינה/);
  assert.doesNotMatch(sent.at(-1).text,/secret/);
  kv.set('health:latest',JSON.stringify({ok:false,recordedAt:nowTime-1800000,source:'kraken_spot',results:[],failures:[{symbol:'SOLUSDT',reason:'secret'}]}));
  queue.push(msg(8,100,'/status'));await processTelegramAccess(env);
  assert.match(sent.at(-1).text,/סריקה חלקית, כושלת או לא עדכנית/);
  assert.doesNotMatch(sent.at(-1).text,/secret/);
 }finally{globalThis.fetch=saved;Date.now=nowBefore;}
});

test('RSI reports neutral 50 on flat candles and 100 on uninterrupted gains',()=>{
 assert.equal(rsi(Array(30).fill(100)),50);
 assert.equal(rsi(Array.from({length:30},(_,i)=>100+i)),100);
 assert.ok(rsi(Array.from({length:30},(_,i)=>100-i))<=1);
});

test('signal delivery retains per-recipient receipts; subscriber failure never completes the whole signal',async()=>{
 const saved=globalThis.fetch, kv=new Map([['tg:approved','["200","300"]']]),calls=[],failed=new Set(['300']);
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async key=>kv.get(key)||null,put:async(key,value)=>kv.set(key,value)}};
 globalThis.fetch=async(url,options)=>{
  const action=String(url).split('/').at(-1);
  assert.equal(action,'sendMessage');
  const body=JSON.parse(options.body);
  calls.push(String(body.chat_id));
  if(failed.has(String(body.chat_id)))return new Response(JSON.stringify({ok:false,description:'temporary test'}),{status:429});
  return new Response(JSON.stringify({ok:true,result:{message_id:5}}));
 };
 try{
  await assert.rejects(sendResearch(env,'DEMO ALERT','signal:test-event'),/deliveries incomplete/);
  assert.deepEqual(calls,['100','200','300','300']);
  assert.equal(kv.get('signal:test-event:delivered:100'),'sent');
  assert.equal(kv.get('signal:test-event:delivered:200'),'sent');
  assert.equal(kv.has('signal:test-event:delivered:300'),false);
  failed.clear();
  await sendResearch(env,'DEMO ALERT','signal:test-event');
  assert.deepEqual(calls,['100','200','300','300','300']);
  assert.equal(kv.get('signal:test-event:delivered:300'),'sent');
  await sendResearch(env,'DEMO ALERT','signal:test-event');
  assert.equal(calls.length,5);
 }finally{globalThis.fetch=saved;}
});

test('owner-only testbroadcast reaches approved subscribers and saves privacy-safe result',async()=>{
 const saved=globalThis.fetch,kv=new Map([['tg:approved','["200","300"]']]),sent=[],queue=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 globalThis.fetch=async(url,options)=>{
  const method=String(url).split('/').at(-1),body=JSON.parse(options.body);
  if(method==='getUpdates')return new Response(JSON.stringify({ok:true,result:queue.filter(x=>x.update_id>=body.offset)}));
  if(method==='sendMessage'){
   sent.push(body);
   if(String(body.chat_id)==='300')return new Response(JSON.stringify({ok:false}),{status:403});
   return new Response(JSON.stringify({ok:true,result:{message_id:1}}));
  }
  throw Error('Unexpected Telegram method '+method);
 };
 const msg=(n,id,from,text)=>({update_id:n,message:{chat:{id,type:'private'},from:{id:from},text}});
 try{
  queue.push(msg(1,200,200,'/testbroadcast'));await processTelegramAccess(env);
  assert.equal(sent.length,1);
  assert.ok(!sent[0].text.includes('TEST BROADCAST'));
  queue.push(msg(2,100,300,'/testbroadcast'));await processTelegramAccess(env);
  assert.equal(sent.length,1);
  queue.push(msg(3,100,100,'/testbroadcast'));await processTelegramAccess(env);
  assert.deepEqual(sent.slice(1).map(x=>String(x.chat_id)),['200','300','100']);
  assert.match(sent[1].text,/TEST BROADCAST/);
  assert.match(sent[2].text,/TEST BROADCAST/);
  assert.match(sent[3].text,/נמסרו: 1/);
  assert.ok(sent[3].text.includes(String.fromCharCode(10)+'✅ נמסרו: 1'));
  assert.equal(sent[3].text.split(String.fromCharCode(10)).length,6);
  assert.equal(sent[3].text.includes(String.fromCharCode(92)+'n'),false);
  assert.match(sent[3].text,/נכשלו: 1/);
  const report=JSON.parse(kv.get('tg:broadcast:last'));
  assert.deepEqual({approvedCount:report.approvedCount,delivered:report.delivered,failed:report.failed,kind:report.kind},{approvedCount:2,delivered:1,failed:1,kind:'demo_only'});
  assert.deepEqual(Object.keys(report).sort(),['approvedCount','checkedAt','delivered','failed','kind'].sort()); // No recipient-ID fields; timestamps may legitimately contain 200/300.
  assert.deepEqual(JSON.parse(kv.get('tg:approved')),['200','300']);
 }finally{globalThis.fetch=saved;}
});

test('paper evaluator is conservative: target, stop, ambiguous both, expiry and pending',()=>{
 const base={direction:'LONG',entry:100,low:99.9,high:100.1,stop:99,target:102,candle:1000000,expires:2200000};
 const candle=(time,low,high)=>({time,low,high});
 assert.equal(evaluatePaperSignal(base,[candle(1300000,99.9,102.1)]).status,'target');
 assert.equal(evaluatePaperSignal(base,[candle(1300000,98.8,102.1)]).status,'stop');
 assert.equal(evaluatePaperSignal(base,[candle(1300000,98.8,102.1)]).ambiguous,true);
 assert.equal(evaluatePaperSignal(base,[candle(1300000,100.5,101),candle(2200000,99.9,100.1)]).status,'expired');
 assert.equal(evaluatePaperSignal(base,[candle(1300000,101,101.5)]).status,'pending');
 assert.equal(evaluatePaperSignal({...base,direction:'SHORT',stop:101,target:98,low:99.9,high:100.1},[candle(1300000,97.9,100.1)]).status,'target');
 assert.equal(evaluatePaperSignal({...base,direction:'SHORT',stop:101,target:98,low:99.9,high:100.1},[candle(1300000,97.9,101.1)]).status,'stop');
 assert.equal(evaluatePaperSignal({...base,stop:101},[]).status,'invalid');
});

test('research journal records only paper candidate and delivery status, not Binance account data',async()=>{
 const saved=Date.now;Date.now=()=>1800000000000;
 const kv=new Map(),env={SIGNAL_STATE:{put:async(k,v)=>kv.set(k,v)}};
 try{
  const setup={strategy:'BREAKOUT',direction:'LONG',candle:1799999400000,entry:100,stop:99};
  const plan={low:99.9,high:100.1,target:102,expires:1800000600000,feeRate:0.0005,slippageRate:0.00025};
  const x=await recordResearchSignal(env,'signal:kraken_spot:BTCUSDT:test','BTCUSDT',setup,plan,'incomplete');
  assert.equal(x.delivery,'incomplete');
  assert.equal(x.status,'not_evaluated');
  assert.equal(x.source,'kraken_spot');
  assert.equal(x.target,102);
  assert.ok(kv.has('journal:signal:kraken_spot:BTCUSDT:test'));
  assert.doesNotMatch(JSON.stringify(x),/BINANCE_API|unrealizedPnl|account:positions/);
 }finally{Date.now=saved;}
});

test('offline paper backtest evaluates stop-first, costs, expired and per-strategy summary',async()=>{
 const {analyzeBacktest}=await import('./offline-paper-backtest.mjs');
 const base={symbol:'BTCUSDT',strategy:'BREAKOUT',direction:'LONG',entry:100,low:99.9,high:100.1,stop:99,target:102,candle:1000000,expires:2200000};
 const report=analyzeBacktest({signals:[{...base,id:'win'},{...base,id:'loss',symbol:'SOLUSDT'},{...base,id:'expired',symbol:'ETHUSDT'}],
  candles:{
   BTCUSDT:[{time:1300000,low:99.9,high:102.1}],
   SOLUSDT:[{time:1300000,low:98.9,high:102.1}],
   ETHUSDT:[{time:1300000,low:100.5,high:101},{time:2200000,low:99.9,high:100.1}]
  }});
 assert.equal(report.mode,'offline_research_only');
 assert.equal(report.groups.BREAKOUT.target,1);
 assert.equal(report.groups.BREAKOUT.stop,1);
 assert.equal(report.groups.BREAKOUT.expired,1);
 assert.equal(report.groups.BREAKOUT.ambiguous,1);
 assert.equal(report.groups.BREAKOUT.closed,2);
 assert.ok(report.groups.BREAKOUT.expectancyNetR<0.5);
 assert.equal(report.outcomes.find(x=>x.id==='expired').netR,null);
 assert.throws(()=>analyzeBacktest({signals:[base],candles:{}}),/Missing historical candles/);
});

test('copy-trading research combines multiple real-export sources without claiming SignalPilot returns',async()=>{
 const {analyzeCopyTradingExports}=await import('./copytrading-research.mjs');
 const row=(tradeId,pnl)=>({tradeId,symbol:'BTCUSDT',side:'LONG',openedAt:'2026-10-01T00:00:00Z',closedAt:tradeId==='a'?'2026-10-02T00:00:00Z':'2026-10-03T00:00:00Z',netPnlUsdt:pnl});
 const first={source:'bybit',portfolioAlias:'leader_A',evidenceType:'closed_trade_export',startingCapitalUsdt:1000,closedTrades:[row('a',100),row('b',-50)]};
 const second={source:'okx',portfolioAlias:'leader_B',evidenceType:'closed_trade_export',startingCapitalUsdt:2000,closedTrades:[row('a',-200)]};
 const result=analyzeCopyTradingExports([first,second]);
 assert.equal(result.sourceCount,2);
 assert.equal(result.verifiedSignalPilotTrackRecord,false);
 assert.equal(result.portfolios[0].netPnlUsdt,50);
 assert.equal(result.portfolios[0].netReturnPct,5);
 assert.equal(result.portfolios[0].winRate,0.5);
 assert.equal(result.portfolios[1].netReturnPct,-10);
 assert.equal(result.portfolios[0].unverifiedCostTrades,0);
 assert.match(result.warning,/NOT SignalPilot/);
 assert.throws(()=>analyzeCopyTradingExports([{...first,evidenceType:'leaderboard_snapshot'}]),/closed-trade exports/);
 assert.throws(()=>analyzeCopyTradingExports([{...first,closedTrades:[row('a',100),row('a',5)]}]),/duplicate tradeId/);
 assert.throws(()=>analyzeCopyTradingExports([{...first,closedTrades:[{...row('a',100),grossPnlUsdt:100}]}]),/exactly one/);
 const incomplete=analyzeCopyTradingExports([{...first,closedTrades:[{...row('a',100),netPnlUsdt:undefined,grossPnlUsdt:100}]}]);
 assert.equal(incomplete.portfolios[0].unverifiedCostTrades,1);
 assert.equal(incomplete.portfolios[0].warnings.length,3);
});

test('candidate selection filters stops BEFORE the 3-slot cap',()=>{
 const last={time:1800000000000,close:100},audit={};
 const setups=[
  {strategy:'BAD_FIRST',direction:'LONG',stop:99.9},
  {strategy:'GOOD1',direction:'LONG',stop:99.5},
  {strategy:'GOOD2',direction:'SHORT',stop:100.5},
  {strategy:'GOOD3',direction:'LONG',stop:99.6}
 ];
 const result=filterAndLimitSetups(setups,last,[],audit);
 assert.deepEqual(result.map(s=>s.strategy),['GOOD1','GOOD2','GOOD3']);
 assert.equal(audit.rawSetups,4);
 assert.equal(audit.stopRejected,1);
 assert.equal(audit.eligibleAfterStops,3);
 assert.equal(audit.capExcluded,0);
});

test('failed subscriber delivery for one signal does NOT suppress later independent candidates',async()=>{
 const saved=globalThis.fetch,kv=new Map([['tg:approved','["200"]']]),sent=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',
  SIGNAL_STATE:{get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)}};
 const base=Date.UTC(2026,9,28,8,30);
 const bars=Array.from({length:120},(_,i)=>({time:base-(120-i)*300000,high:100.4,low:99.6,close:100,volume:100}));
 const setup=(strategy)=>({strategy,direction:'LONG',entry:100,stop:99,candle:base-300000,score:75,reason:'fixture'});
 const plan=tradePlan(setup('BREAKOUT'),bars,base);
 assert.ok(plan);
 globalThis.fetch=async(url,options)=>{
  assert.equal(String(url).split('/').at(-1),'sendMessage');
  const body=JSON.parse(options.body);
  sent.push(body);
  if(String(body.chat_id)==='200'&&body.text.includes('BREAKOUT'))return new Response(JSON.stringify({ok:false}),{status:403});
  return new Response(JSON.stringify({ok:true,result:{message_id:7}}));
 };
 try{
  const found=[{setup:setup('BREAKOUT'),plan},{setup:setup('EMA_ADX'),plan}];
  const tally=await deliverResearchCandidates(env,found,'BTCUSDT',{status:'unavailable'});
  assert.deepEqual(tally,{duplicates:0,delivered:1,deliveryFailed:1});
  const owner=sent.filter(x=>String(x.chat_id)==='100');
  assert.equal(owner.length,2); // Previously the second candidate was never processed.
  assert.ok(owner.some(x=>x.text.includes('BREAKOUT')));
  assert.ok(owner.some(x=>x.text.includes('EMA_ADX')));
  const prefix='signal:kraken_spot:BTCUSDT:'+(base-300000)+':';
  assert.equal(kv.get(prefix+'BREAKOUT:LONG'),undefined);
  assert.equal(kv.get(prefix+'EMA_ADX:LONG'),'sent');
  assert.equal(JSON.parse(kv.get('journal:'+prefix+'BREAKOUT:LONG')).delivery,'incomplete');
  assert.equal(JSON.parse(kv.get('journal:'+prefix+'EMA_ADX:LONG')).delivery,'delivered');
 }finally{globalThis.fetch=saved;}
});

test('private audit reports rejection and delivery counts from actual KV receipts without guessing the missing data',async()=>{
 const scheduled=1800000000000,kv=new Map();
 const report=(time,stats)=>({release:'kraken-stable-v9',scheduledTime:time,
  results:[{symbol:'SOLUSDT',audit:stats}],failures:[]});
 const current=report(scheduled,{scans:1,rawSetups:2,stopRejected:1,eligibleAfterStops:1,planRejected:1,qualified:0});
 const previous=report(scheduled-300000,{scans:1,rawSetups:1,stopRejected:0,eligibleAfterStops:1,planRejected:0,qualified:1,delivered:1});
 kv.set('health:latest',JSON.stringify(current));
 kv.set('health:cron:'+scheduled,JSON.stringify(current));
 kv.set('health:cron:'+(scheduled-300000),JSON.stringify(previous));
 const env={SIGNAL_STATE:{get:async key=>kv.get(key)||null}};
 const text=await scanAuditReport(env);
 for(const phrase of ['2/24','סריקות מטבע עם פירוט: 2','מועמדים גולמיים: 3','נפסלו לפי מרחק סטופ: 1','נפסלו בניהול סיכון/תוקף: 1','איתותים שנמסרו לכל היעדים: 1','חסרות 22 קבלות'])assert.ok(text.includes(phrase),phrase);
 assert.doesNotMatch(text,/TELEGRAM_CHAT_ID|BINANCE_API|200/);
});

test('setup diagnostics include exact failed conditions and thresholds without modifying trade rules',()=>{
 const five=Array.from({length:120},(_,i)=>({time:i*300000,high:100.3,low:99.7,close:100,volume:100}));
 const four=Array.from({length:100},(_,i)=>({time:i*14400000,high:101,low:99,close:100,volume:100}));
 const checks=[],audit={};
 const signals=setups(five,four,checks,audit);
 assert.deepEqual(signals,[]);
 assert.equal(audit.rawSetups,0);
 assert.ok(checks.some(x=>x.startsWith('BREAKOUT:')&&x.includes('close=100.00000')&&x.includes('minVolume=1.50')));
 assert.ok(checks.some(x=>x.startsWith('EMA_ADX LONG:')&&x.includes('trend=false')&&x.includes('adx=0.00')&&x.includes('minAdx=20')));
 assert.ok(checks.some(x=>x.startsWith('RSI_BOLL SHORT:')&&x.includes('rsi=50.00')&&x.includes('minRsi=55')));
 assert.ok(checks.some(x=>x.startsWith('MACD_VOLUME LONG:')&&x.includes('crossed=false')&&x.includes('minVolume=1.2')));
});

test('live cron heartbeat sends one truthful owner-only daily message in Israel morning; retries after Telegram failure',async()=>{
 const saved=globalThis.fetch,kv=new Map(),sent=[];
 let fail=true;
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',SIGNAL_STATE:{
  get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)
 }};
 const receipt={ok:true,results:['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'].map(symbol=>({symbol,candidates:0})),failures:[]};
 globalThis.fetch=async(url,options)=>{
  assert.match(String(url),/sendMessage/);
  sent.push(JSON.parse(options.body));
  return fail?new Response(JSON.stringify({ok:false}),{status:502}):new Response(JSON.stringify({ok:true,result:{message_id:21}}));
 };
 const morning=Date.UTC(2026,9,28,7,0);
 try{
  assert.equal(await sendDailyHeartbeat(env,receipt,morning-60*60000),'not_due');
  assert.equal(sent.length,0);
  await assert.rejects(sendDailyHeartbeat(env,receipt,morning),/Telegram HTTP 502/);
  assert.equal(sent.length,1);
  assert.equal([...kv.keys()].filter(x=>x.startsWith('heartbeat:daily:')).length,0);
  fail=false;
  assert.equal(await sendDailyHeartbeat(env,receipt,morning+300000),'sent');
  assert.equal(await sendDailyHeartbeat(env,receipt,morning+600000),'already_sent');
  assert.equal(sent.length,2);
  assert.ok(sent.every(m=>String(m.chat_id)==='100'));
  assert.match(sent.at(-1).text,/4\/4/);
  assert.match(sent.at(-1).text,/Kraken Spot/);
  assert.doesNotMatch(sent.at(-1).text,/Binance Futures נגיש/);
  assert.equal(await sendDailyHeartbeat(env,receipt,morning+2*60*60000),'not_due');
 }finally{globalThis.fetch=saved;}
});

test('audit displays sample reasons and recorded values for the latest market scan',async()=>{
 const time=1800000000000,kv=new Map(),latest={scheduledTime:time,release:'kraken-stable-v9',
  results:[{symbol:'SOLUSDT',audit:{scans:1,checks:[
   'BREAKOUT: אין התאמה בין מגמה, פריצה ונפח; close=100.00000 volume=0.45 minVolume=1.50',
   'EMA_ADX LONG: לא עמד בכל התנאים; adx=17.00 minAdx=20'
  ]}}],failures:[]};
 kv.set('health:latest',JSON.stringify(latest));
 kv.set('health:cron:'+time,JSON.stringify(latest));
 const output=await scanAuditReport({SIGNAL_STATE:{get:async key=>kv.get(key)||null}});
 assert.match(output,/SOLUSDT/);
 assert.match(output,/volume=0.45/);
 assert.match(output,/minVolume=1.50/);
});

test('Kraken warning-only responses with real candles are accepted, while hard errors still reject',async()=>{
 const nonfatal=payload();nonfatal.error=['WGeneral:Information only'];
 await withData(nonfatal,async()=>{
  const bars=await candles('SOLUSDT','5m',120);
  assert.equal(bars.length,119);
  assert.equal(bars.at(-1).close,101);
 });
 await withData({error:['WGeneral:Information only']},
  ()=>assert.rejects(candles('SOLUSDT','5m',120),/Invalid Kraken warning-only OHLC response/));
});

test('Kraken pair-level concurrency is avoided: 5m and 4h requests are sequential and paced',async()=>{
 const calls=[],started=process.hrtime.bigint();
 await withData(u=>{
  calls.push({interval:u.searchParams.get('interval'),elapsedMs:Number(process.hrtime.bigint()-started)/1e6});
  return payload(Number(u.searchParams.get('interval')));
 },async()=>{
  const [five,four]=await fetchMarketTimeframes('SOLUSDT',30);
  assert.equal(five.length,119);
  assert.equal(four.length,99);
 });
 assert.deepEqual(calls.map(x=>x.interval),['5','240']);
 assert.ok(calls[1].elapsedMs-calls[0].elapsedMs>=25);
 await assert.rejects(fetchMarketTimeframes('SOLUSDT',-1),/Invalid Kraken pair pacing/);
});

test('Kraken EGeneral:Too many requests is transient, retried and never used as stale fallback',async()=>{
 const saved=globalThis.fetch,oldWarn=console.warn;
 let attempts=0;
 console.warn=()=>{};
 globalThis.fetch=async()=>{
  attempts++;
  return new Response(JSON.stringify(attempts<=2?{error:['EGeneral:Too many requests']}:
   payload()));
 };
 try{
  const body=await fetchKrakenOHLC(new URL('https://api.kraken.com/0/public/OHLC'),'BTCUSDT','5m');
  assert.equal(attempts,3);
  assert.ok(body.result?.TESTPAIR);
 }finally{globalThis.fetch=saved;console.warn=oldWarn;}
});

test('watch progress uses percentage of the original binary criteria, strictly over 50',()=>{
 assert.deepEqual(scoreWatchProgress([['trend',true],['breakout',false],['volume',true]]),
  {score:67,passed:2,total:3,missing:['breakout']});
 assert.equal(scoreWatchProgress([['a',true],['b',false]]).score,50);
 assert.throws(()=>scoreWatchProgress([['a','true']]),/Invalid watch requirements/);
});

test('partial 67/100 breakout watch is visible with exact missing condition, but not a trade setup',()=>{
 const five=Array.from({length:120},(_,i)=>({time:i*300000,high:102,low:99,close:101,volume:i===119?200:100}));
 const four=Array.from({length:100},(_,i)=>({time:i*14400000,high:105,low:95,close:95+i*.06,volume:100}));
 const checks=[];
 const eligible=setups(five,four,checks);
 assert.equal(eligible.some(s=>s.strategy==='BREAKOUT'&&s.direction==='LONG'),false);
 const watches=watchCandidates(five,four,50);
 const x=watches.find(x=>x.strategy==='BREAKOUT'&&x.direction==='LONG');
 assert.ok(x);
 assert.equal(x.score,67);
 assert.equal(x.technicalPassed,false);
 assert.deepEqual(x.missing,['פריצה מעל שיא 12 נרות']);
 assert.equal(watchCandidates(five,four,67).some(x=>x.strategy==='BREAKOUT'&&x.direction==='LONG'),false);
 assert.equal(watchCandidates(five,four,50).every(x=>x.score>50),true);
});

test('watch digest sends owner only; KV markers prevent duplicates and failed chunks can be retried',async()=>{
 const saved=globalThis.fetch,kv=new Map([['tg:approved','["200"]']]),sent=[];
 const env={TELEGRAM_CHAT_ID:'100',TELEGRAM_BOT_TOKEN:'test',SIGNAL_STATE:{
  get:async k=>kv.get(k)||null,put:async(k,v)=>kv.set(k,v)
 }};
 const row={symbol:'BTCUSDT',strategy:'BREAKOUT',direction:'LONG',score:67,passed:2,total:3,
  price:100,missing:['פריצה מעל שיא 12 נרות'],technicalPassed:false};
 let shouldFail=true;
 globalThis.fetch=async(url,options)=>{
  assert.match(String(url),/sendMessage/);
  const body=JSON.parse(options.body);sent.push(body);
  return new Response(JSON.stringify({ok:!shouldFail}),{status:shouldFail?403:200});
 };
 try{
  await assert.rejects(sendWatchDigest(env,[row],1800000000000),/Telegram sendMessage HTTP 403/);
  assert.equal([...kv.keys()].filter(x=>x.startsWith('watch:owner:')).length,0);
  shouldFail=false;
  const result=await sendWatchDigest(env,[row],1800000000000);
  assert.equal(result.count,1);
  await sendWatchDigest(env,[row],1800000000000);
  assert.equal(sent.length,2);
  assert.ok(sent.every(x=>String(x.chat_id)==='100'));
  assert.ok(sent[1].text.includes('67/100'));
  assert.match(sent[1].text,/לא איתות כניסה/);
  assert.doesNotMatch(sent[1].text,/🎯 יעד|🛑 סטופ/);
  assert.equal(await sendWatchDigest(env,[],1800000000000).then(x=>x.status),'empty');
 }finally{globalThis.fetch=saved;}
});

test('scheduled scanner groups watch candidates while keeping no-qualified-trade accounting',async()=>{
 const state=new Map(),savedLog=console.log;console.log=()=>{};telegramMessages=[];
 state.set('news:hourly:owner:'+Math.floor(fixed/3600000),'sent');
 state.set('tg:approved','["200"]');
 const env={TELEGRAM_ACCESS_ENABLED:'0',TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'100',
  SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
 const customPayload=minutes=>{
  const data=payload(minutes),rows=data.result.TESTPAIR;
  if(minutes===240)for(let i=0;i<rows.length;i++){rows[i][2]='108';rows[i][3]='93';rows[i][4]=String(95+i*.05);}
  else rows.at(-2)[6]=200;
  return data;
 };
 try{await withData(u=>customPayload(Number(u.searchParams.get('interval'))),async()=>{
  async function run(){
   let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});
   await work;
  }
  await run();
  const receipt=JSON.parse(state.get('health:latest'));
  assert.ok(receipt.ok);
  assert.ok(receipt.results.every(x=>x.candidates===0));
  assert.ok(receipt.results.every(x=>x.audit.watchAbove50>=1));
  assert.equal(receipt.watchDelivery.status,'sent');
  const messages=telegramMessages.filter(x=>x.text.startsWith('👀'));
  assert.equal(messages.length,1);
  assert.equal(String(messages[0].chat_id),'100');
  assert.ok(messages[0].text.includes('BREAKOUT | 67/100'));
  assert.equal(telegramMessages.filter(x=>String(x.chat_id)==='200').length,0);
  await run();
  assert.equal(telegramMessages.filter(x=>x.text.startsWith('👀')).length,1);
 });}finally{console.log=savedLog;}
});
