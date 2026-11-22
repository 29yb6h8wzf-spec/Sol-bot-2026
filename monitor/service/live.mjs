const statuses=new Set(['no_candidate','holding_protected_position','halt_unresolved_execution','existing_exposure','outside_scheduled_minute','waiting_for_decision','risk_limit','protected','blocked']);
const int=v=>Number.isSafeInteger(v)&&v>=0;
export function normalizeLive(v,now=Date.now()){
 if(v?.source!=='binance_usdm_live'||!int(v.collected_at)||Math.abs(now-v.collected_at)>120000||!Array.isArray(v.runs)||v.runs.length>120||!Array.isArray(v.fills)||v.fills.length>100||!Array.isArray(v.entries)||v.entries.length>30)throw Error('Invalid snapshot');
 const runs=v.runs.map(r=>{if(!int(r.at)||r.at>now+60000||typeof r.status!=='string')throw Error('Invalid run');return {at:r.at,status:statuses.has(r.status)?r.status:'unknown',scheduled_ms:int(r.scheduled_ms)?r.scheduled_ms:null,completed_after_ms:int(r.completed_after_ms)?r.completed_after_ms:null,error_type:typeof r.error_type==='string'?r.error_type.slice(0,80):null};}).sort((a,b)=>a.at-b.at);
 const fills=v.fills.map(f=>{if(!['SOLUSDT','XRPUSDT'].includes(f.symbol)||!['OPEN','CLOSE'].includes(f.event)||!int(f.fill_ms)||!Number.isFinite(Number(f.price))||Number(f.price)<=0)throw Error('Invalid fill');return {symbol:f.symbol,event:f.event,fill_ms:f.fill_ms,price:String(f.price).slice(0,30),direction:['LONG','SHORT','long','short','BUY','SELL'].includes(f.direction)?f.direction:null,delivery:f.delivery==='delivered'?'delivered':'not_confirmed'};}).sort((a,b)=>b.fill_ms-a.fill_ms);
 const entries=v.entries.map(e=>{if(typeof e.id!=='string'||!/^vb-(SOLUSDT|XRPUSDT)-\d+$/.test(e.id)||typeof e.state!=='string')throw Error('Invalid entry');return {id:e.id,state:e.state.slice(0,80)};});
 return {source:v.source,collected_at:v.collected_at,runs,fills,entries,errors:(v.errors||[]).filter(e=>['fills_unavailable','entries_unavailable'].includes(e))};
}
export async function liveRoute(request,env){
 const write=request.method==='POST',token=request.headers.get(write?'X-Live-Ingest':'X-Scan-Reader'),secret=write?env.LIVE_INGEST_TOKEN:env.READER_TOKEN;
 if(!['GET','POST'].includes(request.method))return new Response(null,{status:405});
 if(!token||!secret||token.length>256)return new Response(null,{status:403});
 const digest=v=>crypto.subtle.digest('SHA-256',new TextEncoder().encode(v));
 const [a,b]=await Promise.all([digest(token),digest(secret)]);
 if(!crypto.subtle.timingSafeEqual(a,b))return new Response(null,{status:403});
 if(write){
  const raw=await request.text();if(raw.length>100000)return new Response(null,{status:413});
  let data;try{data=normalizeLive(JSON.parse(raw));}catch{return new Response('Invalid telemetry',{status:400});}
  await env.SIGNAL_STATE.put('dashboard:binance:live',JSON.stringify(data),{expirationTtl:86400});return Response.json({ok:true});
 }
 const data=await env.SIGNAL_STATE.get('dashboard:binance:live','json');
 return data?Response.json(data,{headers:{'Cache-Control':'private, no-store'}}):new Response('Live telemetry unavailable',{status:503});
}
