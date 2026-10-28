// Copy-trading research: offline analysis of *real supplied closed-trade exports*.
// Never fabricate performance, attribute third-party results to SignalPilot, or place orders.
import fs from 'node:fs/promises';
import {pathToFileURL} from 'node:url';

const SOURCES=new Set(['bybit','bitget','okx','binance']);
function finite(value,name){if(value===null||value===undefined||value==='')throw Error('Missing '+name);const n=Number(value);if(!Number.isFinite(n))throw Error('Invalid '+name);return n;}
function time(value,name){const n=typeof value==='number'?value:Date.parse(value);if(!Number.isFinite(n))throw Error('Invalid '+name);return n;}
function validate(payload){
 if(!payload||typeof payload!=='object'||Array.isArray(payload))throw Error('Expected export object');
 const source=String(payload.source||'').toLowerCase();
 if(!SOURCES.has(source))throw Error('Unsupported source');
 if(typeof payload.portfolioAlias!=='string'||!/^[A-Za-z0-9_-]{1,60}$/.test(payload.portfolioAlias))throw Error('Invalid portfolioAlias');
 if(payload.evidenceType!=='closed_trade_export')throw Error('Only closed-trade exports accepted; leaderboard ROI snapshots are insufficient');
 const capital=finite(payload.startingCapitalUsdt,'startingCapitalUsdt');
 if(capital<=0)throw Error('Starting capital must be positive');
 if(!Array.isArray(payload.closedTrades)||payload.closedTrades.length===0||payload.closedTrades.length>100000)throw Error('Missing or excessive closedTrades');
 const keys=new Set(),rows=[];
 for(const t of payload.closedTrades){
  if(!t||typeof t!=='object')throw Error('Invalid trade');
  if(typeof t.tradeId!=='string'||!t.tradeId.trim()||t.tradeId.length>128||keys.has(t.tradeId))throw Error('Missing or duplicate tradeId');
  keys.add(t.tradeId);
  if(typeof t.symbol!=='string'||!/^[A-Z0-9-]{3,25}$/.test(t.symbol))throw Error('Invalid symbol');
  if(!['LONG','SHORT'].includes(t.side))throw Error('Invalid side');
  const openedAt=time(t.openedAt,'openedAt'),closedAt=time(t.closedAt,'closedAt');
  if(closedAt<openedAt)throw Error('Trade closed before opened');
  const hasNet=t.netPnlUsdt!==undefined;
  const hasGross=t.grossPnlUsdt!==undefined;
  if(hasNet===hasGross)throw Error('Specify exactly one of netPnlUsdt or grossPnlUsdt to prevent double-counting');
  const gross=hasGross?finite(t.grossPnlUsdt,'grossPnlUsdt'):null;
  const fees=t.feesUsdt===undefined?null:finite(t.feesUsdt,'feesUsdt');
  const funding=t.fundingUsdt===undefined?null:finite(t.fundingUsdt,'fundingUsdt');
  const profitShare=t.profitShareUsdt===undefined?null:finite(t.profitShareUsdt,'profitShareUsdt');
  if([fees,funding,profitShare].some(v=>v!==null&&v<0))throw Error('Costs must be nonnegative (signed funding credits must be normalized externally)');
  // A closed trade with gross PnL is not net unless ALL known cost components are present.
  const fullyCosted=hasNet||[fees,funding,profitShare].every(v=>v!==null);
  const net=hasNet?finite(t.netPnlUsdt,'netPnlUsdt'):gross-(fees??0)-(funding??0)-(profitShare??0);
  rows.push({tradeId:t.tradeId,symbol:t.symbol,side:t.side,openedAt,closedAt,netPnlUsdt:net,
   costCompleteness:fullyCosted?'net_reported_or_full_costs':'costs_missing',hasNetSource:hasNet});
 }
 rows.sort((a,b)=>a.closedAt-b.closedAt||a.tradeId.localeCompare(b.tradeId));
 return {source,portfolioAlias:payload.portfolioAlias,startingCapitalUsdt:capital,rows};
}
export function analyzeCopyTradingExports(exports){
 if(!Array.isArray(exports)||!exports.length)throw Error('Supply at least one export');
 const normalized=exports.map(validate);
 const identities=new Set(),portfolios=[];
 for(const p of normalized){
  const id=p.source+':'+p.portfolioAlias;
  if(identities.has(id))throw Error('Duplicate source/portfolio export; merge and deduplicate before analysis');
  identities.add(id);
  let equity=p.startingCapitalUsdt,peak=equity,maxDD=0,wins=0,losses=0,totalNet=0;
  let grossProfit=0,grossLoss=0,unverifiedCosts=0,bankrupt=false;
  for(const t of p.rows){
   if(t.costCompleteness==='costs_missing')unverifiedCosts++;
   totalNet+=t.netPnlUsdt;
   if(t.netPnlUsdt>0){wins++;grossProfit+=t.netPnlUsdt;}
   else if(t.netPnlUsdt<0){losses++;grossLoss-=t.netPnlUsdt;}
   equity+=t.netPnlUsdt;
   if(equity<=0)bankrupt=true;
   if(equity>peak)peak=equity;
   if(peak>0)maxDD=Math.max(maxDD,(peak-equity)/peak);
  }
  const closed=p.rows.length;
  portfolios.push({source:p.source,portfolioAlias:p.portfolioAlias,closedTrades:closed,
   firstCloseAt:new Date(p.rows[0].closedAt).toISOString(),lastCloseAt:new Date(p.rows.at(-1).closedAt).toISOString(),
   startingCapitalUsdt:p.startingCapitalUsdt,netPnlUsdt:totalNet,
   endingEquityUsdt:equity,netReturnPct:100*totalNet/p.startingCapitalUsdt,
   winRate:wins/closed,profitFactor:grossLoss>0?grossProfit/grossLoss:null,
   maxClosedTradeDrawdownPct:100*maxDD,unverifiedCostTrades:unverifiedCosts,
   capitalExhausted:bankrupt,
   warnings:[...(unverifiedCosts?['Net PnL incomplete: some funding/fees/profit share missing']:[]),
    'Closed-trade drawdown excludes intratrade equity dips and unrealized losses',
    'Copied follower results may differ due to lag, fees, profit sharing, sizing and unavailable entry prices']});
 }
 return {mode:'third_party_historical_research_only',sourceCount:portfolios.length,
  portfolios,verifiedSignalPilotTrackRecord:false,
  warning:'Third-party historical results are NOT SignalPilot returns; no backtest, live copying, ROI guarantee, or executable trade signals.'};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const files=process.argv.slice(2);
 if(!files.length){console.error('Usage: node cloudflare/copytrading-research.mjs export1.json export2.json ...');process.exitCode=2;}
 else try{
  const exports=await Promise.all(files.map(async path=>JSON.parse(await fs.readFile(path,'utf8'))));
  console.log(JSON.stringify(analyzeCopyTradingExports(exports),null,2));
 }catch(error){console.error('Copy trading import failed: '+String(error.message).slice(0,200));process.exitCode=1;}
}
