"use strict";
const $ = id => document.getElementById(id);
const tz = "Asia/Jerusalem";
const formatter = options => new Intl.DateTimeFormat("he-IL", {timeZone:tz, ...options});
const hour = formatter({hour:"2-digit", minute:"2-digit", hourCycle:"h23"});
const clock = formatter({hour:"2-digit", minute:"2-digit", second:"2-digit", hourCycle:"h23"});
const day = formatter({day:"2-digit",month:"2-digit",year:"numeric"});
const short = symbol => symbol.replace(/USDT$/, "");
const names = {SOL:"Solana",BTC:"Bitcoin",ETH:"Ethereum",XRP:"XRP",BNB:"BNB"};
const glyphs = {SOL:"≋",BTC:"₿",ETH:"Ξ",XRP:"×",BNB:"◇"};
let data = null, disconnected = false, loading = false, limit = 10;
const price = v => Number.isFinite(v) ? v.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:v<2?5:2}) : "—";
const make = (tag, value, cls) => {
  const element = document.createElement(tag);
  if (value != null) element.textContent = value;
  if (cls) element.className = cls;
  return element;
};
function options(select, values, all) {
  const old = select.value;
  select.replaceChildren(...(all ? [new Option("כל המטבעות","")] : []), ...values.map(s => new Option(s,s)));
  if (values.includes(old) || (all && old==="")) select.value = old;
}
function status() {
  const now = Date.now();
  $("clock").textContent = clock.format(now);
  const latest = data?.receipts.at(-1);
  const age = latest ? now-latest.at : null;
  const stale = latest && (age>600000 || age< -60000);
  const ok = latest && !stale && !disconnected;
  const partial = latest?.rows.some(row=>row.failed);
  $("state").textContent = disconnected ? "חיבור נותק" : !latest ? "מתחבר" : stale ? "נתונים ישנים" : partial ? "סריקה חלקית" : "מחובר";
  $("state").className = "state " + (ok && !partial ? "live" : "stale");
  const warning = disconnected ? (latest ? "הרענון נכשל. מוצגת הקבלה האחרונה שהתקבלה." : "מקור הסריקות אינו זמין כרגע. החיבור ייבדק שוב אוטומטית.") :
    !latest ? "" : stale ? "הקבלה האחרונה מחוץ לחלון העדכניות. השעות המוצגות הן זמני המקור." :
    partial ? "חלק מהמטבעות נכשלו במחזור האחרון. הפירוט מופיע ביומן." : "";
  $("notice").textContent = warning;
  $("notice").hidden = !warning;
}
function renderChart() {
  const symbol = $("pair").value;
  const receipts = data.receipts;
  const points = receipts.map(r=>r?.rows.find(x=>x.symbol===symbol && !x.failed)?.price ?? null);
  const numbers = points.filter(Number.isFinite);
  const last = points.at(-1);
  $("graphSymbol").textContent = symbol;
  $("price").textContent = price(last);
  $("change").textContent = Number.isFinite(last) && numbers.length>1 && numbers[0]>0 ?
    ((last / numbers[0] - 1)*100).toLocaleString("en-US",{signDisplay:"always", maximumFractionDigits:2,minimumFractionDigits:2})+"%" : "";
  $("change").style.color = last < numbers[0] ? "#f2aaad" : "";
  const graph = $("graph");
  graph.replaceChildren();
  if (!numbers.length) {graph.append(make("p","אין מחירי סגירה בקבלות שבחלון הזה"));return;}
  const ns = "http://www.w3.org/2000/svg";
  const svg = (tag,attrs,parent) => {
    const e=document.createElementNS(ns,tag);
    for(const [k,v] of Object.entries(attrs)) e.setAttribute(k,v);
    parent.append(e);
    return e;
  };
  const chart=svg("svg",{viewBox:"0 0 680 178",preserveAspectRatio:"none",role:"img","aria-label":"מחירי סגירה של "+symbol},graph);
  const defs=svg("defs",{},chart), grad=svg("linearGradient",{id:"fill",x2:"0",y2:"1"},defs);
  svg("stop",{offset:"0%","stop-color":"#77e8b4","stop-opacity":".25"},grad);
  svg("stop",{offset:"100%","stop-color":"#77e8b4","stop-opacity":"0"},grad);
  const min=Math.min(...numbers), max=Math.max(...numbers);
  const pad=Math.max((max-min)*.15,max*.00015,.000001);
  const lo=min-pad, hi=max+pad;
  const x=i=>8+i*592/(points.length-1), y=v=>9+(hi-v)*132/(hi-lo);
  for(let i=0;i<4;i++){
    const value=hi-i*(hi-lo)/3, h=y(value);
    svg("line",{x1:8,x2:600,y1:h,y2:h,stroke:"#2b3943","stroke-dasharray":"3 5"},chart);
    svg("text",{x:609,y:h+4,fill:"#90a4b0","font-size":10,"font-family":"monospace"},chart).textContent=price(value);
  }
  const end=receipts.at(-1).slot;
  for(const i of [0,8,16,23]){
    svg("text",{x:x(i),y:166,"text-anchor":i===0?"start":i===23?"end":"middle",fill:"#90a4b0","font-size":10,"font-family":"monospace"},chart).textContent=hour.format(end-(23-i)*data.period);
  }
  let run=[];
  function flush(){
    if(!run.length) return;
    const line=run.map(([i,v],j)=>(j?"L":"M")+x(i)+" "+y(v)).join(" ");
    svg("path",{d:line+" L"+x(run.at(-1)[0])+" 143 L"+x(run[0][0])+" 143 Z",fill:"url(#fill)"},chart);
    svg("path",{d:line,fill:"none",stroke:"#98eac3","stroke-width":2.4,"vector-effect":"non-scaling-stroke"},chart);
    for(const [i,v] of run){
      const point=svg("circle",{cx:x(i),cy:y(v),r:run.length===1||i===23?3:2,fill:"#a8f4cd"},chart);
      svg("title",{},point).textContent=hour.format(receipts[i].slot)+" · "+price(v)+" USDT";
    }
    run=[];
  }
  points.forEach((v,i)=>{if(Number.isFinite(v)) run.push([i,v]);else flush();});
  flush();
}
function renderWatch(){
  const rows=data.receipts.at(-1).rows;
  $("watch").replaceChildren();
  for(const row of rows){
    const ticker=short(row.symbol);
    const button=make("button",null,"coin");
    button.setAttribute("aria-pressed",String(row.symbol===$("pair").value));
    button.onclick=()=>{$("pair").value=row.symbol;renderChart();renderWatch();};
    button.append(make("span",glyphs[ticker] || ticker[0],"icon "+ticker));
    const title=make("span");title.append(make("strong",ticker),make("small",names[ticker]||ticker));
    button.append(title,make("span",row.failed ? "כשל" : price(row.price),"price"));
    $("watch").append(button);
  }
}
const outcome=r=>r.failed?"failed":r.candidates>0?"candidate":r.candidates===0?"clear":"unknown";
const labels={failed:"כשל סריקה",candidate:"מועמד",clear:"ללא מועמד",unknown:"לא דווח"};
function details(receipt,row){
  $("detailTitle").textContent=row.symbol+" · "+labels[outcome(row)];
  $("detailTime").textContent=day.format(receipt.at)+" · "+hour.format(receipt.at)+" (ישראל)";
  $("checks").replaceChildren();
  for (const check of row.checks){
    const el=make("div",null,"check"), index=check.indexOf(":");
    if(index>=0) el.append(make("strong",check.slice(0,index)));
    el.append(make("span",check.slice(index+1).trim()));
    $("checks").append(el);
  }
  if(!row.checks.length) $("checks").append(make("p",row.failed?"הסורק דיווח על כשל עבור המטבע.":"הקבלה אינה כוללת פירוט בדיקות."));
  $("detail").showModal();
}
function renderRows(){
  const list=[];
  for (const receipt of data.receipts.slice().reverse()){
    for (const row of receipt?.rows||[]){
      if($("filter").value && row.symbol!==$("filter").value) continue;
      if($("outcome").value && outcome(row)!==$("outcome").value) continue;
      list.push([receipt,row]);
    }
  }
  $("rows").replaceChildren();
  for(const [receipt,row] of list.slice(0,limit)){
    const tr=make("tr");
    const td=(element,cls)=>{const cell=make("td",null,cls);cell.append(element);tr.append(cell);};
    td(make("time",hour.format(receipt.at)));td(make("bdi",row.symbol));
    td(make("span",labels[outcome(row)]+(row.candidates>0?" · "+row.candidates:""),"pill "+outcome(row)));
    td(make("time",Number.isFinite(Date.parse(row.candle))?hour.format(Date.parse(row.candle)):"—"),"wide");
    const btn=make("button","בדיקות ‹");btn.setAttribute("aria-label","בדיקות "+row.symbol+" "+hour.format(receipt.at));td(btn);
    tr.onclick=()=>details(receipt,row);
    $("rows").append(tr);
  }
  $("total").textContent=list.length ? "מוצגות "+Math.min(limit,list.length)+" מתוך "+list.length+" רשומות" : "אין סריקות התואמות לסינון";
  $("more").hidden=limit>=list.length;
}
function render(){
  const latest=data.receipts.at(-1), successful=latest.rows.filter(x=>!x.failed);
  $("last").textContent=hour.format(latest.at);
  $("date").textContent=day.format(latest.at)+" · ישראל";
  $("symbols").textContent=successful.length;
  $("candidates").textContent=successful.length && successful.every(r=>Number.isInteger(r.candidates)) ? successful.reduce((n,r)=>n+r.candidates,0) : "—";
  $("coverage").textContent=data.receipts.filter(Boolean).length+" / 24";
  const syms=[...new Set(data.receipts.flatMap(r=>(r?.rows||[]).map(x=>x.symbol)))];
  options($("pair"),syms,false); options($("filter"),syms,true);
  renderChart();renderWatch();renderRows();
}
async function refresh(){
  if(loading) return;
  loading=true;$("refresh").disabled=true;
  try{
    const response=await fetch("/api/scans",{cache:"no-store",signal:AbortSignal.timeout(18000)});
    if(!response.ok) throw new Error();
    const next=await response.json(), latest=next.receipts?.at(-1);
    if(next.source!=="kraken_spot" || next.receipts.length!==24 || !Array.isArray(latest?.rows) || !Number.isSafeInteger(latest.at)) throw new Error();
    data=next;disconnected=false;render();
  }catch{disconnected=true;}finally{loading=false;$("refresh").disabled=false;status();}
}
$("pair").onchange=()=>{if(data){renderChart();renderWatch();}};
for(const id of ["filter","outcome"]) $(id).onchange=()=>{limit=10;if(data) renderRows();};
$("more").onclick=()=>{limit+=20;renderRows();};
$("close").onclick=()=>$("detail").close();
$("refresh").onclick=refresh;
document.addEventListener("visibilitychange",()=>{if(!document.hidden) refresh();});
status();refresh();setInterval(status,1000);setInterval(()=>{if(!document.hidden) refresh();},30000);
