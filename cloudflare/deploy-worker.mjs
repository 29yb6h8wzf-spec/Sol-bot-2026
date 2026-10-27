// Run only in trusted GitHub Actions on main. Never print credentials or raw API responses.
import fs from 'node:fs/promises';
import assert from 'node:assert/strict';

const WORKER='sol-bot-2026', RELEASE='futures-source-health-v7', CRON='*/5 * * * *';
const SYMBOLS=['SOLUSDT','BTCUSDT','ETHUSDT','XRPUSDT'];
let account=(process.env.CLOUDFLARE_ACCOUNT_ID||'').trim();
// Account confirmed by the owner via the production dashboard URL; this is not a credential.
const confirmedAccount='d0b774cf03b175507aa1584e7e8e0117';
const token=(process.env.CLOUDFLARE_API_TOKEN||'').trim();
const summary=[];
function report(message){console.log(message);summary.push(message);}
async function api(path,options={}){
 const headers={Authorization:'Bearer '+token,...options.headers};
 if(typeof options.body==='string')headers['Content-Type']='application/json';
 let response;try{response=await fetch('https://api.cloudflare.com/client/v4/accounts/'+account+'/workers/scripts/'+WORKER+path,{...options,headers,signal:AbortSignal.timeout(30000)});}catch{throw Error('Cloudflare API network failure');}
 let data;try{data=await response.json();}catch{throw Error('Cloudflare returned a non-JSON response (HTTP '+response.status+')');}
 if(!response.ok||!data.success){
  const details=JSON.stringify({errors:data.errors,error:data.error,message:data.message,messages:data.messages}).replaceAll(token,'[REDACTED]').replaceAll(account,'[ACCOUNT]').slice(0,1200);
  throw Error('Cloudflare HTTP '+response.status+'; '+details+'; check token permissions and account ID');
 }
 return data.result;
}
function bindingShape(settings){return (settings.bindings||[]).map(b=>({name:b.name,type:b.type,...(b.type==='kv_namespace'?{namespace_id:b.namespace_id}:{})})).sort((a,b)=>a.name.localeCompare(b.name));}
function scheduleList(value){return Array.isArray(value)?value:(value?.schedules||[]);}
async function main(){
 if(!token)throw Error('Missing GitHub repository secret CLOUDFLARE_API_TOKEN');
 report('Configured account ID matches owner-confirmed dashboard: '+(account===confirmedAccount)+'.');
 account=confirmedAccount;
 // Verify credential status without exporting its value or token identifier.
 for(const [label,path] of [['user','/user/tokens/verify'],['account',account?'/accounts/'+account+'/tokens/verify':null]]){
  if(!path)continue;
  try{
   const response=await fetch('https://api.cloudflare.com/client/v4'+path,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(15000)});
   const value=await response.json();
   const state=['active','disabled','expired'].includes(value.result?.status)?value.result.status:'not verified';
   report('Token validation ('+label+'): HTTP '+response.status+'; status '+state+'.');
   if(value.success&&state==='active')break;
  }catch{report('Token validation ('+label+'): unavailable.');}
 }
 if(!account){
  let response,data;
  try{response=await fetch('https://api.cloudflare.com/client/v4/accounts?per_page=50',{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(30000)});data=await response.json();}catch{throw Error('Account discovery failed; add GitHub secret CLOUDFLARE_ACCOUNT_ID');}
  if(!response.ok||!data.success||!Array.isArray(data.result))throw Error('Token cannot discover accounts; add GitHub repository secret CLOUDFLARE_ACCOUNT_ID (32-character Account ID from Cloudflare)');
  if((data.result_info?.total_pages||1)>1)throw Error('Multiple account pages; add CLOUDFLARE_ACCOUNT_ID to select the correct account');
  const matches=[];
  for(const candidate of data.result){
   if(!/^[a-f0-9]{32}$/i.test(candidate.id))continue;
   account=candidate.id;
   try{await api('/settings');matches.push(candidate.id);}catch{/* An account without access to this Worker is not a candidate. */}
  }
  if(matches.length!==1)throw Error('Could not uniquely locate sol-bot-2026; add GitHub repository secret CLOUDFLARE_ACCOUNT_ID');
  account=matches[0];report('Automatically located the single accessible account containing sol-bot-2026.');
 }
 if(!/^[a-f0-9]{32}$/i.test(account))throw Error('Invalid GitHub repository secret CLOUDFLARE_ACCOUNT_ID (expected 32 hex characters)');
 let before;
 try{before=await api('/settings');}catch(originalError){
  const configured=account;
  let response,data;
  try{response=await fetch('https://api.cloudflare.com/client/v4/accounts?per_page=50',{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(30000)});data=await response.json();}catch{throw originalError;}
  if(!response.ok||!data.success||!Array.isArray(data.result))throw originalError;
  report('Account lookup: '+data.result.length+' accessible account(s); configured ID '+(data.result.some(a=>a.id===configured)?'is present':'is not present')+'.');
  if((data.result_info?.total_pages||1)>1)throw originalError;
  const matches=[];
  for(const candidate of data.result){
   if(!/^[a-f0-9]{32}$/i.test(candidate.id)||candidate.id===configured)continue;
   account=candidate.id;
   try{const settings=await api('/settings');matches.push({id:candidate.id,settings});}catch{/* No access to the named Worker in this account. */}
  }
  if(matches.length!==1){account=configured;throw originalError;}
  account=matches[0].id;before=matches[0].settings;
  report('Located sol-bot-2026 in a single authorized account; configured account ID was incorrect.');
 }
 let restoredKV;
 if(!(before.bindings||[]).some(b=>b.name==='SIGNAL_STATE')){
  let prior=(before.bindings||[]).find(b=>b.type==='kv_namespace'&&b.name==='SIGNAL-STATE');
  if(!prior){
   const history=await api('/versions');
   const versions=Array.isArray(history)?history:(history.items||history.versions||[]);
   for(const version of versions.slice(0,20)){
    if(!version.id)continue;
    const detail=await api('/versions/'+encodeURIComponent(version.id));
    prior=(detail.resources?.bindings||[]).find(b=>b.type==='kv_namespace'&&['SIGNAL_STATE','SIGNAL-STATE'].includes(b.name));
    if(prior)break;
   }
  }
  if(prior?.namespace_id){
   restoredKV={type:'kv_namespace',name:'SIGNAL_STATE',namespace_id:prior.namespace_id};
   before.bindings=[...(before.bindings||[]),restoredKV];
   report('Recovered existing SIGNAL_STATE namespace association from the Worker configuration history.');
  }
 }
 const shape=bindingShape(before), names=new Set(shape.map(b=>b.name));
 for(const name of ['TELEGRAM_BOT_TOKEN','TELEGRAM_CHAT_ID','SIGNAL_STATE'])if(!names.has(name))throw Error('Worker is missing required binding '+name+'; no deployment performed');
 if(!shape.some(b=>b.name==='SIGNAL_STATE'&&b.type==='kv_namespace'))throw Error('SIGNAL_STATE must be a KV binding; no deployment performed');
 report('Cloudflare authentication OK; existing Telegram bindings and SIGNAL_STATE KV found.');
 const schedules=scheduleList(await api('/schedules'));
 // Keep all remote binding types without reading or exporting secret values.
 const metadata={main_module:'worker.js',keep_bindings:[...new Set(shape.map(b=>b.type))],compatibility_date:before.compatibility_date||'2026-10-01',keep_assets:true};
 if(restoredKV)metadata.bindings=[restoredKV];
 for(const field of ['compatibility_flags','limits','logpush','observability','tail_consumers','placement'])if(before[field]!=null)metadata[field]=before[field];
 const code=await fs.readFile(new URL('./worker.js',import.meta.url),'utf8');
 const form=new FormData();form.append('metadata',new Blob([JSON.stringify(metadata)],{type:'application/json'}),'metadata.json');form.append('worker.js',new Blob([code],{type:'application/javascript+module'}),'worker.js');
 const deployed=await api('',{method:'PUT',body:form});
 report('Worker deployed; version '+(deployed.deployment_id||deployed.id||'accepted')+'.');
 const after=await api('/settings');
 assert.deepEqual(bindingShape(after),shape,'Remote binding names, types or KV association changed');
 report('All existing bindings preserved. No secret values were printed.');
 const kv=shape.find(b=>b.name==='SIGNAL_STATE'&&b.type==='kv_namespace');
 report('SIGNAL_STATE namespace ID (non-secret): '+kv.namespace_id);
 if(!schedules.some(s=>s.cron===CRON)){
  await api('/schedules',{method:'PUT',body:JSON.stringify([...schedules.map(s=>({cron:s.cron})),{cron:CRON}])});
  report('Added five-minute cron while preserving existing schedules; propagation can take up to 15 minutes.');
 }
 const actual=scheduleList(await api('/schedules'));
 assert.ok(actual.some(s=>s.cron===CRON),'Five-minute cron not configured');
 report('Confirmed cron '+CRON+'. WARNING: GitHub scan workflows are also enabled; duplicate signal sources remain.');
 const tail=await api('/tails',{method:'POST',body:JSON.stringify({filters:[]})});
 let ws;
 try{
  const verificationStart=Date.now(), deadline=verificationStart+26*60*1000, verified=new Map();
  await new Promise((resolve,reject)=>{
   let settled=false;
   const timer=setTimeout(()=>finish(Error('Timed out: two consecutive successful scheduled scans were not verified; GitHub scans remain enabled')),deadline-Date.now());
   function finish(error){if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve();}
   // Tail URL is an ephemeral credential: keep it out of logs and artifacts.
   ws=new WebSocket(tail.url,'trace-v1');
   ws.addEventListener('open',()=>{ws.send(JSON.stringify({debug:false}));report('Listening for actual Cloudflare cron executions (not manual tests).');});
   ws.addEventListener('error',()=>finish(Error('Cloudflare live-log connection failed; deployment not verified')));
   ws.addEventListener('close',()=>{if(!settled)finish(Error('Cloudflare live-log connection closed before verification'));});
   ws.addEventListener('message',async message=>{
    try{
     const raw=typeof message.data==='string'?message.data:await message.data.text();
     const trace=JSON.parse(raw);
     if(trace.scriptName!==WORKER||trace.event?.cron!==CRON)return;
     for(const log of trace.logs||[]){for(const item of log.message||[]){
      let row;try{row=typeof item==='string'?JSON.parse(item):item;}catch{continue;}
      if(row?.release!==RELEASE)continue;
      if(row.event==='scan_failed'){
       // Only emit bounded, structured diagnostics. No request URLs, tokens or response bodies.
       const market=SYMBOLS.includes(row.symbol)?row.symbol:'unknown';
       const reason=String(row.message||'unknown').replace(/[^a-zA-Z0-9 _.:/-]/g,'?').slice(0,160);
       report('Market scan failed: '+market+'; '+reason);
       continue;
      }
      if(row.event!=='scan_complete')continue;
      const seen=new Set((row.results||[]).map(r=>r.symbol));
      const sources=(row.results||[]).map(r=>r.symbol+':'+r.source).join(',');
      const valid=trace.outcome==='ok'&&!(trace.exceptions||[]).length&&row.ok===true&&row.source==='futures_perpetual'&&row.cron===CRON&&SYMBOLS.every(s=>seen.has(s))&&seen.size===4&&row.results.every(r=>Number.isFinite(r.closedAgeMinutes)&&r.closedAgeMinutes>=0&&r.closedAgeMinutes<=7&&['binance_usdm','bybit_linear'].includes(r.source)&&Number.isInteger(r.candidates)&&r.candidates>=0&&(r.candidates===0?r.statusDelivery==='suppressed_no_signal':r.statusDelivery==='signal_only')&&['ready','partial','unavailable','stale'].includes(r.newsStatus));
      const time=Number(row.scheduledTime);
      if(!Number.isFinite(time)||time<verificationStart-60000)continue;
      report('Scheduled '+new Date(time).toISOString()+' ['+sources+']: '+(valid?'PASS (SOL, BTC, ETH, XRP; fresh perpetual futures candles (Binance or labeled Bybit proxy); Telegram delivery checked only when signals exist; silent scans verified; news status recorded)':'FAIL (scan errors, incomplete markets or inconsistent signal delivery)'));
      if(!valid){verified.clear();continue;}
      const prior=verified.get(time-300000);
      verified.set(time,row);
      if(prior&&row.results.every(r=>Date.parse(r.candle)-Date.parse(prior.results.find(p=>p.symbol===r.symbol).candle)===300000)){
       report('VERIFIED: two consecutive automatic scans exactly five minutes apart; all four markets advanced to the next closed candle.');finish();
      }
     }}
    }catch{finish(Error('Could not validate a Cloudflare scheduled log message'));}
   });
  });
 }finally{
  ws?.close();
  try{await api('/tails/'+encodeURIComponent(tail.id),{method:'DELETE'});}catch{report('Temporary tail session cleanup failed; it will expire automatically.');}
 }
}
try{await main();}catch(error){report('FAILED: '+error.message);process.exitCode=1;}finally{
 if(process.env.GITHUB_STEP_SUMMARY)await fs.appendFile(process.env.GITHUB_STEP_SUMMARY,'## Cloudflare scanner deployment\n\n'+summary.map(x=>'- '+x).join('\n')+'\n');
}
// The built-in WebSocket can retain a closing handle after the tail was deleted.
// All deployment, verification, cleanup and summary writes have been awaited above.
process.exit(process.exitCode || 0);
