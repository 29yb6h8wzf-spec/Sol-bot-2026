import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('./worker.js',import.meta.url),'utf8');
const {candles,parseNewsFeed,newsForSymbol,formatNewsContext,loadNews,tradePlan,tradeMessage,processTelegramAccess,readBinancePositions,monitorBinanceAccount,default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const now=Date.now, originalFetch=globalThis.fetch;
const fixed=1800000000000;
let telegramMessages=[], telegramStatus=200, newsXML='<rss><channel></channel></rss>';
function payload(minutes=5){const duration=minutes*60,end=Math.floor(fixed/1000/duration)*duration;return {error:[],result:{TESTPAIR:Array.from({length:121},(_,i)=>[end-(120-i)*duration,'100','102','99','101','100','42',5]),last:end}};}
async function withData(body,fn,status=200){Date.now=()=>fixed;globalThis.fetch=async (u,options)=>{if(['https://www.coindesk.com/arc/outboundfeeds/rss/','https://cointelegraph.com/rss'].includes(String(u)))return new Response(newsXML);if(String(u).startsWith('https://api.telegram.org/')){telegramMessages.push(JSON.parse(options.body));return new Response(JSON.stringify({ok:telegramStatus===200}),{status:telegramStatus});}assert.equal(u.origin,'https://api.kraken.com');assert.ok(['5','240'].includes(u.searchParams.get('interval')));return new Response(JSON.stringify(typeof body==='function'?body(u):body),{status});};try{await fn();}finally{Date.now=now;globalThis.fetch=originalFetch;}}
test('Kraken maps seconds and base volume and excludes open candle',async()=>{await withData(payload(),async()=>{const bars=await candles('BTCUSDT','5m',120);assert.equal(bars.length,119);assert.equal(bars.at(-1).time,fixed-300000);assert.equal(bars[0].volume,42);});});
test('4h freshness uses its own interval rather than the 5m age limit',async()=>{await withData(payload(240),async()=>{Date.now=()=>fixed+90*60000;assert.equal((await candles('SOLUSDT','4h',100)).length,99);});});
test('rejects API errors, malformed prices, gaps, stale data and HTTP failures',async()=>{await withData({error:['EQuery:Unknown asset pair']},()=>assert.rejects(candles('SOLUSDT','5m',120),/API rejected/));for(const mutate of [b=>b.result.TESTPAIR[100][4]='NaN',b=>b.result.TESTPAIR.splice(90,1),b=>b.result.TESTPAIR.forEach(r=>r[0]-=3600)]){let b=payload();mutate(b);await withData(b,()=>assert.rejects(candles('ETHUSDT','5m',120)));}await withData({},()=>assert.rejects(candles('XRPUSDT','5m',120),/HTTP 403/),403);});
test('scheduled scans remain silent without setups, but still scan all four markets',async()=>{
 const logs=[],oldLog=console.log,state=new Map();console.log=(...args)=>logs.push(args);telegramMessages=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
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
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
  let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},{TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}},{waitUntil:p=>work=p});
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
  const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
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
