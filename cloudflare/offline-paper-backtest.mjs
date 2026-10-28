// Offline research-only evaluation. Input is historical signals + closed OHLC bars.
// No network calls, credentials, live orders, optimization, or fabricated returns.
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const workerSource=await fs.readFile(new URL('./worker.js',import.meta.url),'utf8');
const {evaluatePaperSignal}=await import('data:text/javascript;base64,'+Buffer.from(workerSource).toString('base64'));
function timestamp(value){const n=typeof value==='number'?value:Date.parse(value);if(!Number.isFinite(n))throw Error('Invalid timestamp');return n;}
export function analyzeBacktest(payload){
 if(!payload||!Array.isArray(payload.signals)||!payload.candles||typeof payload.candles!=='object')throw Error('Expected signals array and candles by symbol');
 if(payload.signals.length>100000)throw Error('Too many signals');
 const outcomes=[];
 for(const signal of payload.signals){
  const bars=payload.candles[signal.symbol];
  if(!Array.isArray(bars))throw Error('Missing historical candles for '+String(signal.symbol).slice(0,20));
  const normalized={...signal,candle:timestamp(signal.candle),expires:timestamp(signal.expires)};
  const candles=bars.map(b=>({...b,time:timestamp(b.time)}));
  const outcome=evaluatePaperSignal(normalized,candles);
  const risk=Math.abs(normalized.entry-normalized.stop);
  const fee=Number(signal.feeRate??signal.costAssumptions?.feeRate??0.0005);
  const slip=Number(signal.slippageRate??signal.costAssumptions?.slippageRate??0.00025);
  if(!Number.isFinite(fee)||!Number.isFinite(slip)||fee<0||slip<0)throw Error('Invalid cost assumptions');
  let netR=null;
  if(['target','stop'].includes(outcome.status)){
   if(!(risk>0))throw Error('Invalid stop distance');
   const exit=outcome.status==='stop'?normalized.stop:normalized.target;
   const friction=(fee+slip)*(Math.abs(normalized.entry)+Math.abs(exit))/risk;
   netR=outcome.r-friction;
  }
  outcomes.push({id:signal.id??null,symbol:signal.symbol,strategy:signal.strategy,status:outcome.status,ambiguous:!!outcome.ambiguous,netR});
 }
 const groups={};
 for(const row of outcomes){
  const key=row.strategy||'UNKNOWN',g=groups[key]??={total:0,target:0,stop:0,expired:0,pending:0,open:0,invalid:0,ambiguous:0,closed:0,sumNetR:0};
  g.total++;g[row.status]=(g[row.status]??0)+1;
  if(row.ambiguous)g.ambiguous++;
  if(row.netR!==null){g.closed++;g.sumNetR+=row.netR;}
 }
 for(const g of Object.values(groups)){
  g.expectancyNetR=g.closed?g.sumNetR/g.closed:null;
  g.winRate=g.closed?g.target/g.closed:null;
  delete g.sumNetR;
 }
 return {mode:'offline_research_only',count:outcomes.length,groups,outcomes,warning:'Only provided signals evaluated; not a historical strategy backtest. No fill assurance; ambiguous stops are loss-first; costs estimated. No performance claim.'};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const file=process.argv[2];
 if(!file){console.error('Usage: node cloudflare/offline-paper-backtest.mjs historical-input.json');process.exitCode=2;}
 else try{console.log(JSON.stringify(analyzeBacktest(JSON.parse(await fs.readFile(file,'utf8'))),null,2));}
 catch(error){console.error('Backtest input error: '+String(error.message).slice(0,200));process.exitCode=1;}
}
