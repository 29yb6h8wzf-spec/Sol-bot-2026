// Cloudflare Worker: private waitlist storage (KV) + Telegram notification.
// Required secrets: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
// Required KV binding: WAITLIST
// Required var: ALLOWED_ORIGIN = https://29yb6h8wzf-spec.github.io
export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowed = env.ALLOWED_ORIGIN || 'https://29yb6h8wzf-spec.github.io';
    const cors = { 'Access-Control-Allow-Origin': allowed, 'Access-Control-Allow-Methods':'POST, OPTIONS','Access-Control-Allow-Headers':'Content-Type','Vary':'Origin' };
    if (origin !== allowed) return new Response('Forbidden',{status:403});
    if (request.method === 'OPTIONS') return new Response(null,{status:204,headers:cors});
    if (request.method !== 'POST') return new Response('Method not allowed',{status:405,headers:cors});
    if (!env.WAITLIST || !env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) return new Response('Not configured',{status:503,headers:cors});
    if (Number(request.headers.get('content-length')||0)>4000) return new Response('Too large',{status:413,headers:cors});
    let data;
    try { data=await request.json(); } catch {return new Response('Invalid JSON',{status:400,headers:cors});}
    const name=String(data.name||'').trim().slice(0,80);
    const email=String(data.email||'').trim().toLowerCase().slice(0,254);
    const lang=data.language==='he'?'he':'en';
    if (!data.consent || name.length<2 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || data.website) return new Response('Invalid submission',{status:400,headers:cors});
    // Key uses a SHA-256 digest so email addresses are not exposed in KV keys.
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(email));
    const key='lead:'+Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('');
    const previous=await env.WAITLIST.get(key);
    if (!previous) {
      await env.WAITLIST.put(key,JSON.stringify({name,email,lang,consentAt:new Date().toISOString()}));
      const message='📥 SignalPilot — New waitlist lead\nName: '+name+'\nEmail: '+email+'\nLanguage: '+lang;
      const result=await fetch('https://api.telegram.org/bot'+env.TELEGRAM_BOT_TOKEN+'/sendMessage',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({chat_id:env.TELEGRAM_CHAT_ID,text:message})});
      if (!result.ok) console.error('Telegram notification failed',result.status);
    }
    return new Response(JSON.stringify({ok:true}),{status:200,headers:{...cors,'Content-Type':'application/json'}});
  }
};
