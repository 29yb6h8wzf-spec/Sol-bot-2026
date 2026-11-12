// Research-only prefilter for supplied closed-trade exports. No orders or scraping.
// Historical entry price must be supplied by the export; today's price is NOT evidence.
import {analyzeCopyTradingExports} from './copytrading-research.mjs';
export function analyzePriceWindow(exports,{minPrice=0.99,maxPrice=150}={}){
 if(!Array.isArray(exports)||!exports.length)throw Error('Missing exports');
 if(!Number.isFinite(minPrice)||!Number.isFinite(maxPrice)||minPrice<=0||maxPrice<minPrice)throw Error('Invalid price range');
 const accepted=[];const exclusions=[];
 for(const payload of exports){
  if(!payload||!Array.isArray(payload.closedTrades))throw Error('Invalid export');
  const selected=[];
  for(const trade of payload.closedTrades){
   // No inference from current tickers: historical price provenance is mandatory.
   const p=trade?.entryPriceUsdt;
   if(typeof p!=='number'||!Number.isFinite(p)||p<=0){
    exclusions.push({source:payload.source,portfolioAlias:payload.portfolioAlias,tradeId:trade?.tradeId,reason:'missing_verified_historical_entry_price'});continue;
   }
   if(p<minPrice||p>maxPrice){
    exclusions.push({source:payload.source,portfolioAlias:payload.portfolioAlias,tradeId:trade.tradeId,reason:'outside_entry_price_range'});continue;
   }
   if(trade.entryPriceEvidence!=='exchange_execution_export'){
    exclusions.push({source:payload.source,portfolioAlias:payload.portfolioAlias,tradeId:trade.tradeId,reason:'unverified_entry_price_source'});continue;
   }
   selected.push(trade);
  }
  if(selected.length)accepted.push({...payload,closedTrades:selected});
 }
 const result=accepted.length?analyzeCopyTradingExports(accepted):null;
 return {researchOnly:true,executionAuthorized:false,priceRangeUsdt:[minPrice,maxPrice],
  acceptedTrades:accepted.reduce((n,p)=>n+p.closedTrades.length,0),exclusions,
  result,profitabilityProven:false,
  warning:'Selected closed trades are not a reproducible SignalPilot strategy; exclusions and survivor bias must be reviewed.'};
}
