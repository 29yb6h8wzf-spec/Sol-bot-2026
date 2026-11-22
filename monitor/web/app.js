'use strict';
const $=id=>document.getElementById(id),zone='Asia/Jerusalem';
const fmt=(opts)=>new Intl.DateTimeFormat('he-IL',{timeZone:zone,hourCycle:'h23',...opts});
const time=fmt({hour:'2-digit',minute:'2-digit',second:'2-digit'}),stamp=fmt({day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const labels={no_candidate:['לא נמצא מועמד לכניסה','הריצה הסתיימה בלי מועמד לכניסה לפי תנאי המנוע.'],holding_protected_position:['ניהול עסקה עם הגנות','המנוע דיווח על פוזיציה עם הגנות בריצה הזו.'],halt_unresolved_execution:['עצירה: מצב ביצוע לא פתור','המנוע דיווח על חסימה. נדרשת בדיקה של רישומי הביצוע לפני חזרה לפעילות רגילה.'],existing_exposure:['קיימת חשיפה בחשבון','המנוע דילג על כניסה נוספת בגלל חשיפה קיימת.'],outside_scheduled_minute:['מחוץ לדקה המתוכננת','הכניסה לא נבדקה בריצה הזו.'],waiting_for_decision:['ממתין לנר הבא','המנוע ממתין למועד ההחלטה.'],risk_limit:['עצירה במגבלת הסיכון','מגבלת הסיכון חסמה כניסה בריצה הזו.'],protected:['כניסה עם הגנות אושרה','המנוע דיווח על ביצוע כניסה עם הוראות הגנה.'],blocked:['הריצה נחסמה','המנוע דיווח על שגיאה או חסימה.'],unknown:['מצב לא מזוהה','התקבל מצב שאינו מוכר למסך הניטור.']};
const bad=r=>['halt_unresolved_execution','blocked','risk_limit','unknown'].includes(r.status);
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
let data=null,failed=false,busy=false,selected=null,limit=15,fetched=0;
function freshness(){
 $('clock').textContent=time.format(Date.now());
 const last=data?.runs.at(-1),old=data&&(Date.now()-data.collected_at>120000||!last||Date.now()-last.at>180000);
 $('connection').textContent=failed?'הרענון נכשל':!data?'מתחבר':old?'נתונים ישנים':'ניטור מחובר';
 $('connection').className='badge '+(failed||old?'bad':data?'ok':'');
 const issues=[];if(failed)issues.push('החיבור נכשל. נתונים קודמים, אם קיימים, נשארים על המסך.');if(old)issues.push('הנתונים אינם עדכניים. אין להסיק מהם את מצב הבוט כרגע.');if(data?.errors.length)issues.push('חלק מיומני הביצוע לא זמינים.');
 $('notice').textContent=issues.join(' ');$('notice').hidden=!issues.length;
 if(fetched)$('refreshed').textContent='משיכה אחרונה '+time.format(fetched)+' · רענון כל 30 שניות';
}
function detail(r){
 $('runDetail').replaceChildren();if(!r){$('runDetail').textContent='אין דיווח ריצה לדקה הזו.';return;}
 const [title,description]=labels[r.status]||labels.unknown;
 $('runDetail').append(node('strong',stamp.format(r.at)+' · '+title),node('div',description),node('bdi',r.status+(r.error_type?' / '+r.error_type:'')));
}
function timeline(){
 const latest=data.runs.at(-1);$('timeline').replaceChildren();if(!latest)return detail(null);
 const end=Math.floor(latest.at/60000)*60000,byMinute=new Map(data.runs.map(r=>[Math.floor(r.at/60000)*60000,r]));
 for(let i=119;i>=0;i--){const at=end-i*60000,r=byMinute.get(at),b=node('button',null,'pulse '+(!r?'gap':bad(r)?'bad':'ok'));b.title=time.format(at)+' · '+(r?(labels[r.status]||labels.unknown)[0]:'חסר ביומן');b.setAttribute('aria-label',b.title);b.setAttribute('aria-pressed',String((selected??latest.at)===r?.at));b.onclick=()=>{selected=r?.at??at;timeline();detail(r);};$('timeline').append(b);}
 detail(selected===null?latest:data.runs.find(r=>r.at===selected));
}
function fills(){
 const rows=data.fills.filter(f=>(!$('symbol').value||f.symbol===$('symbol').value)&&(!$('event').value||f.event===$('event').value));$('fills').replaceChildren();
 for(const f of rows.slice(0,limit)){const tr=node('tr');const values=[node('time',stamp.format(f.fill_ms)),node('bdi',f.symbol),node('span',(f.event==='OPEN'?'פתיחה':'סגירה')+(f.direction?' · '+f.direction:''),'badge '+(f.event==='OPEN'?'ok':'')),node('bdi',Number(f.price).toLocaleString('en-US',{maximumFractionDigits:6})),node('span',f.delivery==='delivered'?'נשלח לפי היומן':'לא אושר')];for(const value of values){const td=node('td');td.append(value);tr.append(td);}$('fills').append(tr);}
 $('fillCount').textContent=rows.length+' אירועים';$('empty').hidden=!!rows.length;$('more').hidden=rows.length<=limit;
}
function render(){
 const last=data.runs.at(-1);$('count').textContent=data.runs.length;$('latest').textContent=last?stamp.format(last.at):'אין דיווח';$('collected').textContent=stamp.format(data.collected_at);
 $('latency').textContent=last?.completed_after_ms!=null?(last.completed_after_ms/1000).toFixed(2)+'s':'—';$('opens').textContent=data.errors.includes('fills_unavailable')?'—':data.fills.filter(f=>f.event==='OPEN').length;$('closes').textContent=data.errors.includes('fills_unavailable')?'—':data.fills.filter(f=>f.event==='CLOSE').length;
 $('engineCode').textContent=last?.status??'NO REPORT';$('engineStatus').textContent=last?(labels[last.status]||labels.unknown)[0]:'אין דיווח מהמנוע';$('engineDescription').textContent=last?(labels[last.status]||labels.unknown)[1]:'לא התקבלו ריצות בשעתיים האחרונות.';document.querySelector('.engine').classList.toggle('blocked',!last||bad(last));
 timeline();fills();$('entries').replaceChildren(...data.entries.slice(0,8).map(e=>{const row=node('div',null,'entry');row.append(node('bdi',e.id),node('span',e.state));return row;}));if(!data.entries.length)$('entries').textContent=data.errors.includes('entries_unavailable')?'יומן הביצוע לא זמין':'אין רישומים ביומן';freshness();
}
async function refresh(){if(busy)return;busy=true;$('refresh').disabled=true;try{const r=await fetch('/api/scans',{cache:'no-store',signal:AbortSignal.timeout(18000)});if(!r.ok)throw Error();const v=await r.json();if(v.source!=='binance_usdm_live'||!Number.isSafeInteger(v.collected_at)||!Array.isArray(v.runs)||!Array.isArray(v.fills)||!Array.isArray(v.entries)||!Array.isArray(v.errors))throw Error();data=v;failed=false;fetched=Date.now();render();}catch{failed=true;}finally{busy=false;$('refresh').disabled=false;freshness();}}
$('refresh').onclick=refresh;$('live').onclick=()=>{selected=null;if(data)timeline();};for(const id of ['symbol','event'])$(id).onchange=()=>{limit=15;if(data)fills();};$('more').onclick=()=>{limit+=20;fills();};document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});freshness();refresh();setInterval(freshness,1000);setInterval(()=>{if(!document.hidden)refresh();},30000);
