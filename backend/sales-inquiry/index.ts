import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "npm:@supabase/supabase-js@2.57.4";
const cors={"Access-Control-Allow-Origin":"https://mistrflow.vercel.app","Access-Control-Allow-Headers":"authorization,apikey,content-type","Access-Control-Allow-Methods":"POST,OPTIONS","Vary":"Origin","Cache-Control":"no-store"};
const json=(x:unknown,status=200)=>new Response(JSON.stringify(x),{status,headers:{...cors,"Content-Type":"application/json"}});
function key(){const direct=Deno.env.get("SUPABASE_SECRET_KEY")||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");if(direct)return direct;try{return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default}catch{return ""}}
Deno.serve(async req=>{
 if(req.method==="OPTIONS")return new Response(null,{status:204,headers:cors});
 if(req.method!=="POST")return json({error:"Method not allowed"},405);
 if(req.headers.get("origin") && req.headers.get("origin")!=="https://mistrflow.vercel.app")return json({error:"Nepovolený původ požadavku."},403);
 try{
  const raw=await req.text();if(raw.length>6000)return json({error:"Zpráva je příliš dlouhá."},413);
  const b=JSON.parse(raw);if(b.website)return json({ok:true});
  const name=String(b.name||"").trim(),email=String(b.email||"").trim().toLowerCase(),company=String(b.company||"").trim(),message=String(b.message||"").trim(),plan=String(b.plan_code||"start");
  if(name.length<2||name.length>120||company.length>160||email.length>254||!/^\S+@\S+\.\S+$/.test(email)||message.length>2000||!["start","pro","firma"].includes(plan)||b.consent!==true)return json({error:"Zkontrolujte jméno, e-mail a souhlas s kontaktem."},400);
  const admin=createClient(Deno.env.get("SUPABASE_URL")!,key(),{auth:{persistSession:false,autoRefreshToken:false}});
  const ip=req.headers.get("x-forwarded-for")?.split(",")[0].trim()||"unknown";
  const hash=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(ip+":"+new Date().toISOString().slice(0,10)));
  const ipHash=[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,"0")).join("");
  const since=new Date(Date.now()-3600000).toISOString();
  const [a,c]=await Promise.all([admin.from("sales_inquiries").select("id",{count:"exact",head:true}).eq("ip_hash",ipHash).gte("created_at",since),admin.from("sales_inquiries").select("id",{count:"exact",head:true}).eq("email",email).gte("created_at",since)]);
  if(a.error||c.error)return json({error:"Zprávu nyní nelze uložit."},503);
  if((a.count||0)>=5||(c.count||0)>=2)return json({error:"Požadavek už evidujeme. Zkuste to později."},429);
  const {error}=await admin.from("sales_inquiries").insert({name,email,company,message,plan_code:plan,ip_hash:ipHash});
  if(error)return json({error:"Zprávu se nepodařilo uložit. Zkuste to znovu."},503);
  return json({ok:true});
 }catch{return json({error:"Neplatný požadavek."},400)}
});

