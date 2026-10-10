import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "npm:@supabase/supabase-js@2.57.4";

const MAX_SMS_BYTES=8192;
const uuidPattern=/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const json=(data:unknown,status=200)=>Response.json(data,{status,headers:{"Cache-Control":"no-store"}});

function secretKey(){
 const direct=Deno.env.get("SUPABASE_SECRET_KEY")||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
 if(direct)return direct;
 try{return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default||null}catch{return null}
}
function admin(){
 const url=Deno.env.get("SUPABASE_URL"),key=secretKey();
 if(!url||!key)throw new Error("Server configuration missing");
 return createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}})
}
async function vault(client:any,name:string){
 const {data,error}=await client.rpc("integration_secret_get",{p_name:name});
 if(error)throw error;
 return String(data||"")
}
function cleanPhone(value:string){return String(value||"").replace(/[^+0-9]/g,"").slice(0,20)}
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
 return new TextDecoder().decode(combined)
}

Deno.serve(async(req:Request)=>{
 if(req.method!=="POST")return json({error:"Method not allowed"},405);
 try{
  const auth=req.headers.get("authorization")||"";
  if(!auth.startsWith("Bearer "))return json({error:"Přihlášení je vyžadováno."},401);
  const client=admin(),token=auth.slice(7);
  const {data:{user},error:userError}=await client.auth.getUser(token);
  if(userError||!user)return json({error:"Relace vypršela."},401);

  const raw=await readLimitedBody(req,MAX_SMS_BYTES);
  if(raw===null)return json({error:"Požadavek je příliš dlouhý."},413);
  let body:Record<string,unknown>;
  try{
   const parsed=JSON.parse(raw);
   if(!parsed||typeof parsed!=="object"||Array.isArray(parsed))return json({error:"Neplatný požadavek."},400);
   body=parsed as Record<string,unknown>
  }catch{return json({error:"Neplatný požadavek."},400)}

  const organizationId=String(body.organization_id||"");
  if(!uuidPattern.test(organizationId))return json({error:"Neplatná firma."},400);
  const {data:membership,error:membershipError}=await client.from("organization_memberships")
   .select("role").eq("user_id",user.id).eq("organization_id",organizationId).maybeSingle();
  if(membershipError||!membership)return json({error:"K této firmě nemáte přístup."},403);

  const to=cleanPhone(String(body.to||"")),message=String(body.message||"").trim().slice(0,1000);
  if(!/^\+?[0-9]{9,15}$/.test(to))return json({error:"Zadejte platné telefonní číslo."},400);
  if(!message)return json({error:"Zpráva je prázdná."},400);

  const {data:integration,error:integrationError}=await client.from("integrations").select("status")
   .eq("organization_id",organizationId).eq("provider","volai").maybeSingle();
  if(integrationError)throw integrationError;
  const apiKey=await vault(client,"volai_api_key");
  if(integration?.status!=="connected"||!apiKey)return json({
   error:"Volai SMS zatím není připojeno. Vlastník musí doplnit API údaje v Integracích.",
   code:"VOLAI_NOT_CONNECTED"
  },503);

  const providerResponse=await fetch("https://volai.cz/v1/messages",{
   method:"POST",
   headers:{"Authorization":"Bearer "+apiKey,"Content-Type":"application/json"},
   body:JSON.stringify({to,text:message})
  });
  const providerData=await providerResponse.json().catch(()=>({}));
  if(!providerResponse.ok)return json({error:"Volai odmítlo odeslání SMS.",providerStatus:providerResponse.status},502);
  const providerId=providerData?.id||providerData?.message_id||providerData?.data?.id||null;
  const {data:saved,error:saveError}=await client.from("messages").insert({
   organization_id:organizationId,
   provider:"volai",
   provider_message_id:providerId,
   channel:"sms",
   direction:"outbound",
   body:message,
   sent_at:new Date().toISOString()
  }).select("id,created_at,sent_at").single();
  if(saveError)throw saveError;
  return json({ok:true,messageId:saved.id,providerMessageId:providerId,sentAt:saved.sent_at})
 }catch(error){
  console.error("send-sms",error);
  return json({error:"SMS nyní nelze odeslat."},500)
 }
});
