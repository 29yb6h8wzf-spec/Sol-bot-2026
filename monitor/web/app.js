"use strict";
const $=id=>document.getElementById(id);
const zone="Asia/Jerusalem";
const fmt=opts=>new Intl.DateTimeFormat("he-IL",{timeZone:zone,...opts});
const time=fmt({hour:"2-digit",minute:"2-digit",hourCycle:"h23"});
const date=fmt({day:"2-digit",month:"2-digit",year:"numeric"});
const clock=fmt({hour:"2-digit",minute:"2-digit",second:"2-digit",hourCycle:"h23"});
const price=v=>Number.isFinite(v)?v.toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:v<2?5:2}):"—";
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;if(cls)node.className=cls;return node;};
const state={data:null,follow:true,slot:null,symbol:"SOLUSDT",busy:false,failed:false,limit:10,fetchedAt:null};
const status=row=>row.failed?"failed":row.candidates>0?"candidate":row.candidates===0?"clear":"unknown";
const labels={failed:"כשל בסריקה",candidate:"מועמד",clear:"ללא מועמד",unknown:"לא דווח"};
const badgeClass=row=>row.failed?"bad":row.candidates>0?"ok":"";
function selection() {
  const latest=state.data?.receipts.at(-1);
  if(!latest) return null;
  return state.follow?latest:state.data.receipts.find(r=>r?.slot===state.slot)||null;
}
function updateStatus(){
  const now=Date.now();
  $("clock").textContent=clock.format(now);
  const latest=state.data?.receipts.at(-1);
  const stale=latest && (now-latest.at>600000 || now-latest.at< -60000);
  const partial=latest?.rows.some(row=>row.failed);
  $("connection").textContent=state.failed?"הרענון נכשל":!latest?"מתחבר":stale?"נתונים ישנים":partial?"סריקה חלקית":"נתונים עדכניים";
  $("connection").className="badge "+(state.failed||stale||partial?"warn":latest?"ok":"");
  $("notice").textContent=state.failed ? (latest?"החיבור נכשל. מוצגים הנתונים מהטעינה האחרונה.":"לא התקבלו נתונים מהסורק. ניסיון נוסף יתבצע אוטומטית.") :
    stale?"הסריקה האחרונה התקבלה ב־"+date.format(latest.at)+" "+time.format(latest.at)+". הנתונים חרגו מחלון העדכניות של 10 דקות.":"";
  $("notice").hidden=!$("notice").textContent;
  if(state.fetchedAt)$("refreshed").textContent="משיכה אחרונה "+time.format(state.fetchedAt)+" · רענון כל 30 שניות";
}
function choose(receipt,symbol){
  state.follow=false;state.slot=receipt.slot;if(symbol)state.symbol=symbol;renderSelection();renderTimeline();
}
function renderTimeline(){
  const latest=state.data.receipts.at(-1);
  $("timeline").replaceChildren(...state.data.receipts.map((r,i)=>{
    const slot=latest.slot-(23-i)*state.data.period;
    const button=el("button",null,"slot "+(!r?"missing":r.rows.some(x=>x.failed)?"partial":"received"));
    button.setAttribute("aria-label",time.format(slot)+" · "+(!r?"קבלה חסרה":r.rows.length+" מטבעות"));
    button.title=button.getAttribute("aria-label");
    button.setAttribute("aria-pressed",String((r?.slot??slot)===(state.follow?latest.slot:state.slot)));
    button.onclick=()=>{state.follow=false;state.slot=r?.slot??slot;renderTimeline();renderSelection();};
    return button;
  }));
  $("live").setAttribute("aria-pressed",String(state.follow));
}
function renderSelection(){
  const receipt=selection();
  $("selectionMode").textContent=state.follow?"מעקב אחר האחרון":"מחזור שנבחר";
  $("selectedTime").textContent=receipt?time.format(receipt.at):time.format(state.slot);
  $("coins").replaceChildren();
  if(receipt && !receipt.rows.some(r=>r.symbol===state.symbol))state.symbol=receipt.rows[0]?.symbol;
  for(const row of receipt?.rows||[]){
    const button=el("button",null,"coin");
    button.setAttribute("aria-pressed",String(row.symbol===state.symbol));
    button.setAttribute("aria-label",row.symbol+" · "+labels[status(row)]);
    const head=el("span",null,"coin-head");head.append(el("bdi",row.symbol.replace("USDT",""),"coin-name"),el("span",row.symbol.slice(0,1),"coin-icon"));
    button.append(head,el("span",price(row.price),"coin-price"),el("span",labels[status(row)]+(row.candidates>0?" · "+row.candidates:""),"coin-result"));
    button.onclick=()=>{state.symbol=row.symbol;renderSelection();};
    $("coins").append(button);
  }
  const row=receipt?.rows.find(x=>x.symbol===state.symbol);
  $("selectedSymbol").textContent=row?.symbol||"—";
  $("result").textContent=row?labels[status(row)]:"קבלה חסרה";
  $("result").className="badge "+(row?badgeClass(row):"warn");
  const validCandle=row&&Number.isFinite(Date.parse(row.candle));
  $("candle").textContent=row ? "נר שנבדק "+(validCandle?date.format(Date.parse(row.candle))+" · "+time.format(Date.parse(row.candle)):"לא דווח")+" · מקור Kraken Spot" : "המחזור שנבחר חסר או יצא מחלון הנתונים.";
  $("strategies").replaceChildren();
  for(const check of row?.checks||[]){
    const item=diagnostic(check),article=el("article",null,"strategy"),head=el("div",null,"strategy-heading");
    head.append(el("bdi",item.title,"strategy-title"),el("span",item.rejected?"תנאים לא הושלמו":"דיווח הסורק","badge "+(item.rejected?"warn":"")));
    article.append(head,el("p",item.explanation,"explanation"));
    const conditions=el("div",null,"conditions");
    for(const condition of item.conditions){const chip=el("span",null,"condition "+(condition.pass?"pass":"fail"));chip.append(el("span",condition.label),el("b",condition.value));conditions.append(chip);}
    article.append(conditions);
    const raw=el("details",null,"raw");raw.append(el("summary","הצג דיווח מקורי"),el("p",item.raw));article.append(raw);
    $("strategies").append(article);
  }
  if(!row?.checks?.length)$("strategies").append(el("p",row?.failed?"הסורק דיווח על כשל. פירוט התנאים לא התקבל.":"אין פירוט תנאים בקבלה שנבחרה.","empty"));
  $("price").textContent=price(row?.price);
  $("barTime").textContent=validCandle?time.format(Date.parse(row.candle)):"—";
  $("coinCandidates").textContent=row?.candidates??"—";
  $("delivered").textContent=row?.delivered??"—";
  drawChart();
}
function drawChart(){
  const canvas=$("chart"),width=canvas.clientWidth;
  if(!width||!state.data)return;
  const height=180,scale=devicePixelRatio||1;
  canvas.width=width*scale;canvas.height=height*scale;
  const ctx=canvas.getContext("2d");ctx.scale(scale,scale);
  const values=state.data.receipts.map(r=>r?.rows.find(x=>x.symbol===state.symbol)?.price);
  const valid=values.filter(Number.isFinite);
  if(!valid.length){ctx.fillStyle="#9cadaa";ctx.font="14px Arial";ctx.textAlign="center";ctx.fillText("אין מחירים בחלון",width/2,90);return;}
  const min=Math.min(...valid),max=Math.max(...valid),pad=Math.max((max-min)*.1,max*.0001);
  const lo=min-pad,hi=max+pad,right=width-73;
  const x=i=>14+i*(right-14)/23,y=v=>15+(hi-v)/(hi-lo)*132;
  ctx.font="11px Arial";ctx.textAlign="left";
  for(let i=0;i<4;i++){const v=hi-i*(hi-lo)/3,h=y(v);ctx.strokeStyle="#29373b";ctx.beginPath();ctx.moveTo(14,h);ctx.lineTo(right,h);ctx.stroke();ctx.fillStyle="#9cadaa";ctx.fillText(price(v),right+7,h+4);}
  ctx.strokeStyle="#b2e68c";ctx.lineWidth=2;ctx.beginPath();let connected=false;
  values.forEach((v,i)=>{if(!Number.isFinite(v)){connected=false;return;}if(connected)ctx.lineTo(x(i),y(v));else ctx.moveTo(x(i),y(v));connected=true;});ctx.stroke();
  values.forEach((v,i)=>{if(!Number.isFinite(v))return;ctx.fillStyle="#b2e68c";ctx.beginPath();ctx.arc(x(i),y(v),2,0,2*Math.PI);ctx.fill();});
  const latest=state.data.receipts.at(-1);
  ctx.fillStyle="#9cadaa";ctx.fillText(time.format(latest.slot-23*state.data.period),14,173);ctx.textAlign="right";ctx.fillText(time.format(latest.slot),right,173);
}
function renderHistory(){
  const items=state.data.receipts.slice().reverse().flatMap(receipt=>(receipt?.rows||[]).map(row=>({receipt,row}))).filter(({row})=>(!$("filter").value||row.symbol===$("filter").value)&&(!$("outcome").value||status(row)===$("outcome").value));
  $("history").replaceChildren();
  for(const {receipt,row} of items.slice(0,state.limit)){
    const tr=el("tr"),cell=node=>{const td=el("td");td.append(node);tr.append(td);};
    cell(el("time",time.format(receipt.at)));cell(el("bdi",row.symbol));cell(el("span",labels[status(row)],"badge "+badgeClass(row)));cell(el("time",Number.isFinite(Date.parse(row.candle))?time.format(Date.parse(row.candle)):"—"));
    const button=el("button","פתח");button.setAttribute("aria-label","פתח בדיקות "+row.symbol+" "+time.format(receipt.at));button.onclick=()=>{choose(receipt,row.symbol);$("selectedTime").scrollIntoView({block:"start"});};cell(button);$("history").append(tr);
  }
  $("historyCount").textContent=items.length+" רשומות";
  $("shown").textContent=items.length?"מוצגות "+Math.min(state.limit,items.length)+" מתוך "+items.length:"אין רשומות התואמות לסינון";
  $("more").hidden=state.limit>=items.length;
}
function render(){
  const latest=state.data.receipts.at(-1),rows=latest.rows.filter(r=>!r.failed);
  $("latest").textContent=time.format(latest.at);$("latestDate").textContent=date.format(latest.at)+" · ישראל";
  $("count").textContent=rows.length;
  $("candidates").textContent=rows.length&&rows.every(r=>Number.isInteger(r.candidates))?rows.reduce((n,r)=>n+r.candidates,0):"—";
  $("coverage").textContent=state.data.receipts.filter(Boolean).length+" / 24";
  const old=$("filter").value,syms=[...new Set(state.data.receipts.flatMap(r=>(r?.rows||[]).map(x=>x.symbol)))];
  $("filter").replaceChildren(new Option("כל המטבעות",""),...syms.map(s=>new Option(s,s)));if(syms.includes(old))$("filter").value=old;
  renderTimeline();renderSelection();renderHistory();updateStatus();
}
function validPayload(value){
  return value?.source==="kraken_spot"&&value.period===300000&&Array.isArray(value.receipts)&&value.receipts.length===24&&value.receipts.at(-1)&&value.receipts.every(r=>r===null||(Number.isSafeInteger(r.at)&&Number.isSafeInteger(r.slot)&&Array.isArray(r.rows)&&r.rows.every(x=>typeof x.symbol==="string"&&typeof x.failed==="boolean"&&Array.isArray(x.checks)&&x.checks.every(c=>typeof c==="string"))));
}
async function refresh(){
  if(state.busy)return;state.busy=true;$("refresh").disabled=true;
  try{
    const response=await fetch("/api/scans",{cache:"no-store",signal:AbortSignal.timeout(18000)});
    if(!response.ok)throw new Error("Feed unavailable");
    const value=await response.json();if(!validPayload(value))throw new Error("Invalid receipt");
    state.data=value;state.failed=false;state.fetchedAt=Date.now();render();
  }catch{state.failed=true;}finally{state.busy=false;$("refresh").disabled=false;updateStatus();}
}
$("refresh").onclick=refresh;
$("live").onclick=()=>{state.follow=true;if(state.data){renderTimeline();renderSelection();}};
for(const id of ["filter","outcome"])$(id).onchange=()=>{state.limit=10;if(state.data)renderHistory();};
$("more").onclick=()=>{state.limit+=20;renderHistory();};
new ResizeObserver(drawChart).observe($("chart"));
document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh();});
updateStatus();refresh();setInterval(updateStatus,1000);setInterval(()=>{if(!document.hidden)refresh();},30000);
