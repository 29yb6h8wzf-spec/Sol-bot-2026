import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
const source=await fs.readFile(new URL('./worker.js',import.meta.url),'utf8');
const {candles,default:worker}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const now=Date.now, originalFetch=globalThis.fetch;
const fixed=1800000000000;
let telegramMessages=[], telegramStatus=200;
function payload(minutes=5){const duration=minutes*60,end=Math.floor(fixed/1000/duration)*duration;return {error:[],result:{TESTPAIR:Array.from({length:121},(_,i)=>[end-(120-i)*duration,'100','102','99','101','100','42',5]),last:end}};}
async function withData(body,fn,status=200){Date.now=()=>fixed;globalThis.fetch=async (u,options)=>{if(String(u).startsWith('https://api.telegram.org/')){telegramMessages.push(JSON.parse(options.body));return new Response(JSON.stringify({ok:telegramStatus===200}),{status:telegramStatus});}assert.equal(u.origin,'https://api.kraken.com');assert.ok(['5','240'].includes(u.searchParams.get('interval')));return new Response(JSON.stringify(typeof body==='function'?body(u):body),{status});};try{await fn();}finally{Date.now=now;globalThis.fetch=originalFetch;}}
test('Kraken maps seconds and base volume and excludes open candle',async()=>{await withData(payload(),async()=>{const bars=await candles('BTCUSDT','5m',120);assert.equal(bars.length,119);assert.equal(bars.at(-1).time,fixed-300000);assert.equal(bars[0].volume,42);});});
test('4h freshness uses its own interval rather than the 5m age limit',async()=>{await withData(payload(240),async()=>{Date.now=()=>fixed+90*60000;assert.equal((await candles('SOLUSDT','4h',100)).length,99);});});
test('rejects API errors, malformed prices, gaps, stale data and HTTP failures',async()=>{await withData({error:['EQuery:Unknown asset pair']},()=>assert.rejects(candles('SOLUSDT','5m',120),/API rejected/));for(const mutate of [b=>b.result.TESTPAIR[100][4]='NaN',b=>b.result.TESTPAIR.splice(90,1),b=>b.result.TESTPAIR.forEach(r=>r[0]-=3600)]){let b=payload();mutate(b);await withData(b,()=>assert.rejects(candles('ETHUSDT','5m',120)));}await withData({},()=>assert.rejects(candles('XRPUSDT','5m',120),/HTTP 403/),403);});
test('scheduled scans send four no-signal reports and deduplicate repeated candles',async()=>{
 const logs=[],oldLog=console.log, state=new Map();console.log=(...args)=>logs.push(args);telegramMessages=[];
 const env={TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}};
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
  async function run(){let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},env,{waitUntil:p=>work=p});await work;}
  await run();assert.equal(telegramMessages.length,4);
  for(const symbol of ['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'])assert.ok(telegramMessages.some(m=>m.text.includes(symbol)&&m.text.includes('אין איתות')));
  assert.ok(telegramMessages.every(m=>m.chat_id==='test'&&m.text.includes('דוח תנאים בלבד')&&m.text.length<4096&&!m.text.startsWith('🔔')));
  const result=logs.map(a=>{try{return JSON.parse(a[0]);}catch{return {};}}).find(x=>x.event==='scan_complete');
  assert.equal(result.ok,true);assert.equal(result.results.length,4);assert.ok(result.results.every(x=>x.statusDelivery==='sent'));
  await run();assert.equal(telegramMessages.length,4);
 });}finally{console.log=oldLog;}
});
test('Telegram rejection fails verification and does not mark statuses delivered',async()=>{
 const state=new Map(),oldLog=console.log,oldError=console.error;console.log=()=>{};console.error=()=>{};telegramStatus=403;
 try{await withData(u=>payload(Number(u.searchParams.get('interval'))),async()=>{
  let work;await worker.scheduled({cron:'*/5 * * * *',scheduledTime:fixed},{TELEGRAM_BOT_TOKEN:'test',TELEGRAM_CHAT_ID:'test',SIGNAL_STATE:{get:async k=>state.get(k)||null,put:async(k,v)=>state.set(k,v)}},{waitUntil:p=>work=p});
  await assert.rejects(work,/market scans failed/);assert.equal(state.size,0);
 });}finally{console.log=oldLog;console.error=oldError;telegramStatus=200;}
});
