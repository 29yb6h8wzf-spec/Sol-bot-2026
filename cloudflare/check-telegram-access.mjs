// Read-only diagnostics: never log Telegram IDs, bot token, messages or Cloudflare credentials.
const token=process.env.TELEGRAM_BOT_TOKEN,cloud=process.env.CLOUDFLARE_API_TOKEN;
const account='d0b774cf03b175507aa1584e7e8e0117',namespace='26692b7aceb64495a3b1de123c1aa628';
if(!token||!cloud)throw Error('Missing Telegram or Cloudflare secret');
const hook=await fetch('https://api.telegram.org/bot'+token+'/getWebhookInfo',{signal:AbortSignal.timeout(15000)});
const info=await hook.json();
if(!hook.ok||!info.ok)throw Error('Telegram webhook status check failed (HTTP '+hook.status+')');
console.log('Telegram webhook configured:',Boolean(info.result?.url));
console.log('Telegram pending updates:',Number(info.result?.pending_update_count||0));
if(info.result?.last_error_date)console.log('Telegram webhook has a recent delivery error');
for(const key of ['tg:offset','tg:access-health']){
 const url='https://api.cloudflare.com/client/v4/accounts/'+account+'/storage/kv/namespaces/'+namespace+'/values/'+encodeURIComponent(key);
 const res=await fetch(url,{headers:{Authorization:'Bearer '+cloud},signal:AbortSignal.timeout(15000)});
 if(res.status===404){console.log(key+': not yet present');continue;}
 if(!res.ok)throw Error('Cloudflare KV '+key+' HTTP '+res.status);
 const value=await res.text();
 if(key==='tg:offset'){const n=Number(value);console.log('Telegram polling offset initialized:',Number.isSafeInteger(n)&&n>0);}
 else{let obj;try{obj=JSON.parse(value);}catch{throw Error('Invalid access health JSON');}
 console.log('Telegram polling last check:',obj.checkedAt||'unknown','status:',obj.status||'unknown','updates:',Number(obj.updates||0),'error:',obj.error||'none');
 }
}
if(info.result?.url)throw Error('Telegram webhook is active; getUpdates polling cannot work concurrently');
