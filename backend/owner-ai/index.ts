import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "npm:@supabase/supabase-js@2.57.4";
const MAX_OWNER_AI_BYTES=16384;
const json=(b:unknown,s=200)=>new Response(JSON.stringify(b),{status:s,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
function secret(){const k=Deno.env.get("SUPABASE_SECRET_KEY")||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");if(k)return k;try{return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default}catch{return ""}}
async function readLimitedBody(req:Request,maxBytes:number){
 const declared=req.headers.get("content-length");
 if(declared!==null){const bytes=Number(declared);if(Number.isFinite(bytes)&&bytes>maxBytes)return null}
 if(!req.body)return "";
 const reader=req.body.getReader(),chunks:Uint8Array[]=[];let total=0;
 while(true){
  const {done,value}=await reader.read();if(done)break;
  total+=value.byteLength;if(total>maxBytes){await reader.cancel();return null}
  chunks.push(value);
 }
 const combined=new Uint8Array(total);let offset=0;
 for(const chunk of chunks){combined.set(chunk,offset);offset+=chunk.byteLength}
 return new TextDecoder().decode(combined);
}
Deno.serve(async req=>{
 if(req.method!=="POST")return json({error:"Method not allowed"},405);
 try{
  const auth=req.headers.get("authorization")||"";
  if(!auth.startsWith("Bearer "))return json({error:"Přihlaste se do aplikace."},401);
  const admin=createClient(Deno.env.get("SUPABASE_URL")!,secret(),{auth:{persistSession:false,autoRefreshToken:false}});
  const {data:{user},error}=await admin.auth.getUser(auth.slice(7));
  if(error||!user)return json({error:"Přihlášení vypršelo."},401);
  const {data:owner,error:roleError}=await admin.from("platform_admins").select("user_id").eq("user_id",user.id).maybeSingle();
  if(roleError||!owner)return json({error:"Přístup pouze pro vlastníka platformy."},403);
  const raw=await readLimitedBody(req,MAX_OWNER_AI_BYTES);
  if(raw===null)return json({error:"Požadavek je příliš dlouhý."},413);
  try{const parsed=JSON.parse(raw);if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))return json({error:"Neplatný požadavek."},400)}catch{return json({error:"Neplatný požadavek."},400)}
  return json({error:"AI služba ještě není připojená. Pro skutečné odpovědi je potřeba dokončit připojení poskytovatele AI. Vaše zpráva neprovedla žádné změny."},503)
 }catch(e){console.error("owner-ai",e);return json({error:"AI služba není dostupná."},500)}
});

