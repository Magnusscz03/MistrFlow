import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "npm:@supabase/supabase-js@2.57.4";

const PROCESSING_TTL_MS=120000;
const MAX_WEBHOOK_BYTES=1024*1024;
const HANDLED=new Set([
  "charge.succeeded","charge.refunded","payout.paid",
  "customer.subscription.created","customer.subscription.updated","customer.subscription.deleted"
]);

function secretKey(){
  const direct=Deno.env.get("SUPABASE_SECRET_KEY")||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if(direct)return direct;
  try{return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default||null}catch{return null}
}
function db(){
  const url=Deno.env.get("SUPABASE_URL"),key=secretKey();
  if(!url||!key)throw new Error("Supabase admin configuration missing");
  return createClient(url,key,{auth:{persistSession:false,autoRefreshToken:false}});
}
async function hmacHex(secret:string,payload:string){
  const key=await crypto.subtle.importKey("raw",new TextEncoder().encode(secret),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
  const sig=await crypto.subtle.sign("HMAC",key,new TextEncoder().encode(payload));
  return [...new Uint8Array(sig)].map(b=>b.toString(16).padStart(2,"0")).join("");
}
function secureEqual(a:string,b:string){
  if(a.length!==b.length)return false;
  let out=0;for(let i=0;i<a.length;i++)out|=a.charCodeAt(i)^b.charCodeAt(i);
  return out===0;
}
async function readWebhookBody(req:Request,maxBytes:number){
  const declared=req.headers.get("content-length");
  if(declared!==null){
    const bytes=Number(declared);
    if(Number.isFinite(bytes)&&bytes>maxBytes)return null;
  }
  if(!req.body)return "";
  const reader=req.body.getReader(),chunks:Uint8Array[]=[];
  let total=0;
  while(true){
    const {done,value}=await reader.read();
    if(done)break;
    total+=value.byteLength;
    if(total>maxBytes){await reader.cancel();return null}
    chunks.push(value);
  }
  const combined=new Uint8Array(total);
  let offset=0;
  for(const chunk of chunks){combined.set(chunk,offset);offset+=chunk.byteLength}
  return new TextDecoder().decode(combined);
}
async function verifyStripe(raw:string,header:string|null,secret:string){
  if(!header)return false;
  let t="";const signatures:string[]=[];
  for(const part of header.split(",")){
    const i=part.indexOf("=");if(i<1)continue;
    const k=part.slice(0,i),v=part.slice(i+1);
    if(k==="t")t=v;if(k==="v1"&&v)signatures.push(v);
  }
  const ts=Number(t);
  if(!t||!Number.isFinite(ts)||Math.abs(Date.now()/1000-ts)>300)return false;
  const expected=await hmacHex(secret,t+"."+raw);
  return signatures.some(sig=>secureEqual(expected,sig));
}
async function beginWebhook(admin:any,event:any){
  const eventId=String(event?.id||"");
  if(!eventId)throw new Error("Stripe event id missing");
  const {data:existing,error}=await admin.from("webhook_events")
    .select("id,status,attempts,updated_at").eq("provider","stripe").eq("event_id",eventId).maybeSingle();
  if(error)throw error;
  const now=new Date();
  if(existing){
    if(existing.status==="processed"||existing.status==="ignored"){
      return {id:existing.id,eventId,done:true,status:existing.status};
    }
    const updated=new Date(existing.updated_at||0).getTime();
    if(existing.status==="processing"&&updated&&Date.now()-updated<PROCESSING_TTL_MS){
      return {id:existing.id,eventId,done:true,status:"processing"};
    }
    const {error:u}=await admin.from("webhook_events").update({
      status:"processing",error:null,attempts:Number(existing.attempts||1)+1,updated_at:now.toISOString(),payload:event,event_type:String(event.type||"unknown")
    }).eq("id",existing.id);
    if(u)throw u;
    return {id:existing.id,eventId,done:false,status:"processing"};
  }
  const {data:row,error:ins}=await admin.from("webhook_events").insert({
    provider:"stripe",event_id:eventId,event_type:String(event.type||"unknown"),payload:event,
    status:"processing",error:null,attempts:1,processed_at:now.toISOString(),updated_at:now.toISOString()
  }).select("id").single();
  if(ins){
    if(String(ins.code||"")==="23505"){
      const {data:race,error:r}=await admin.from("webhook_events").select("id,status")
        .eq("provider","stripe").eq("event_id",eventId).maybeSingle();
      if(r)throw r;
      return {id:race?.id,eventId,done:true,status:race?.status||"processing"};
    }
    throw ins;
  }
  return {id:row.id,eventId,done:false,status:"processing"};
}
async function finishWebhook(admin:any,id:any,status:"processed"|"failed"|"ignored",error:string|null=null){
  const now=new Date().toISOString();
  const {error:e}=await admin.from("webhook_events").update({
    status,error:error?error.slice(0,2000):null,processed_at:now,updated_at:now
  }).eq("id",id);
  if(e)console.error("webhook state update failed",e);
}
async function lookupOrg(admin:any,object:any,event:any){
  const metadataOrg=object?.metadata?.organization_id;
  if(metadataOrg)return String(metadataOrg);

  const customerId=typeof object?.customer==="string"?object.customer:object?.customer?.id||null;
  if(customerId){
    const {data,error}=await admin.from("subscriptions").select("organization_id")
      .eq("provider","stripe").eq("provider_customer_id",customerId).limit(1).maybeSingle();
    if(error)throw error;
    if(data?.organization_id)return data.organization_id;
  }
  if(event?.account){
    const {data,error}=await admin.from("integrations").select("organization_id")
      .eq("provider","stripe").eq("external_account_id",event.account).eq("status","connected").limit(1).maybeSingle();
    if(error)throw error;
    if(data?.organization_id)return data.organization_id;
  }
  return null;
}
async function vaultGet(admin:any,name:string){
  const {data,error}=await admin.rpc("integration_secret_get",{p_name:name});
  if(error)throw error;
  return String(data||"");
}
async function stripeGet(admin:any,path:string,account?:string|null){
  const key=await vaultGet(admin,"stripe_secret_key");
  if(!key)throw new Error("Stripe secret key is not configured");
  const headers:Record<string,string>={"Authorization":"Bearer "+key};
  if(account)headers["Stripe-Account"]=account;
  const r=await fetch("https://api.stripe.com/v1/"+path,{headers});
  if(!r.ok)throw new Error("Stripe API "+r.status+" for "+path);
  return await r.json();
}
async function insertMoneyEvent(admin:any,row:any){
  const {error}=await admin.from("money_events").insert(row);
  if(error&&String(error.code||"")!=="23505")throw error;
}
async function updateStripeIntegration(admin:any,orgId:string,event:any){
  const patch:any={status:"connected",updated_at:new Date().toISOString()};
  if(event?.account)patch.external_account_id=event.account;
  const {error}=await admin.from("integrations").update(patch)
    .eq("organization_id",orgId).eq("provider","stripe");
  if(error)throw error;
}

Deno.serve(async(req:Request)=>{
  if(req.method!=="POST")return new Response("method not allowed",{status:405});
  let raw:string|null;
  try{raw=await readWebhookBody(req,MAX_WEBHOOK_BYTES)}
  catch(e){console.error("stripe-webhook",e);return new Response("processing failed",{status:500})}
  if(raw===null)return new Response("payload too large",{status:413});
  const admin=db();
  const webhookSecret=await vaultGet(admin,"stripe_webhook_secret");
  const stripeKey=await vaultGet(admin,"stripe_secret_key");
  if(!webhookSecret||!stripeKey)return new Response("stripe not configured",{status:503});

  if(!(await verifyStripe(raw,req.headers.get("stripe-signature"),webhookSecret))){
    return new Response("invalid signature",{status:401});
  }
  let event:any;
  try{event=JSON.parse(raw)}catch{return new Response("invalid json",{status:400})}

  const state=await beginWebhook(admin,event);
  if(state.done)return Response.json({received:true,deduplicated:true,status:state.status});

  try{
    if(!HANDLED.has(String(event.type||""))){
      await finishWebhook(admin,state.id,"ignored");
      return Response.json({received:true,ignored:true});
    }

    const object=event?.data?.object||{};
    const orgId=await lookupOrg(admin,object,event);
    if(!orgId)throw new Error("No MistrFlow organization mapping for Stripe event");

    if(event.type==="charge.succeeded"){
      const balanceId=typeof object.balance_transaction==="string"?object.balance_transaction:object.balance_transaction?.id||null;
      const balance=balanceId?await stripeGet(admin,"balance_transactions/"+encodeURIComponent(balanceId),event.account):null;
      const gross=Number(balance?.amount??object.amount??0);
      const providerFee=Number(balance?.fee??0);
      const platformFee=Number(object.application_fee_amount??0);
      const net=Number(balance?.net??(gross-providerFee));
      await insertMoneyEvent(admin,{
        organization_id:orgId,provider:"stripe",provider_event_id:event.id,provider_reference:object.id,
        type:"payment",status:"posted",gross_cents:gross,provider_fee_cents:providerFee,
        platform_fee_cents:platformFee,net_cents:net,
        currency:String(balance?.currency||object.currency||"czk").toUpperCase(),
        destination:typeof object.transfer_data?.destination==="string"?object.transfer_data.destination:event.account||null,
        description:object.description||"Stripe payment",
        occurred_at:new Date(Number(event.created)*1000).toISOString(),
        metadata:{event_type:event.type,stripe_account:event.account||null}
      });
    }

    if(event.type==="charge.refunded"){
      const amount=Number(object.amount_refunded??0);
      await insertMoneyEvent(admin,{
        organization_id:orgId,provider:"stripe",provider_event_id:event.id,provider_reference:object.id,
        type:"refund",status:"posted",gross_cents:-amount,provider_fee_cents:0,platform_fee_cents:0,net_cents:-amount,
        currency:String(object.currency||"czk").toUpperCase(),destination:event.account||null,
        description:"Stripe refund",occurred_at:new Date(Number(event.created)*1000).toISOString(),
        metadata:{event_type:event.type,stripe_account:event.account||null}
      });
    }

    if(event.type==="payout.paid"){
      const amount=Number(object.amount??0);
      await insertMoneyEvent(admin,{
        organization_id:orgId,provider:"stripe",provider_event_id:event.id,provider_reference:object.id,
        type:"payout",status:"posted",gross_cents:-amount,provider_fee_cents:0,platform_fee_cents:0,net_cents:-amount,
        currency:String(object.currency||"czk").toUpperCase(),
        destination:typeof object.destination==="string"?object.destination:object.destination?.id||null,
        description:object.description||"Stripe payout",
        occurred_at:new Date(Number(event.created)*1000).toISOString(),
        metadata:{event_type:event.type,stripe_account:event.account||null}
      });
    }

    if(String(event.type).startsWith("customer.subscription.")){
      const price=object.items?.data?.[0]?.price;
      const status=String(object.status||(event.type.endsWith("deleted")?"canceled":"inactive"));
      const patch={
        provider:"stripe",
        is_comped:false,
        ...(object.metadata?.plan_code && ["start","pro","firma"].includes(object.metadata.plan_code) ? {plan_code:object.metadata.plan_code} : {}),
        provider_customer_id:typeof object.customer==="string"?object.customer:object.customer?.id||null,
        provider_subscription_id:object.id,
        status,
        recurring_cents:Number(price?.unit_amount??0),
        currency:String(price?.currency||"czk").toUpperCase(),
        billing_interval:price?.recurring?.interval==="year"?"annual":"monthly",
        current_period_end:object.current_period_end?new Date(Number(object.current_period_end)*1000).toISOString():null,
        cancel_at_period_end:!!object.cancel_at_period_end,
        stripe_price_id:price?.id||null,
        updated_at:new Date().toISOString()
      };
      const {data:rows,error}=await admin.from("subscriptions").update(patch)
        .eq("organization_id",orgId).select("id");
      if(error)throw error;
      if(!rows?.length)throw new Error("Stripe subscription row missing for organization");
    }

    await updateStripeIntegration(admin,orgId,event);
    await finishWebhook(admin,state.id,"processed");
    return Response.json({received:true});
  }catch(e){
    const message=e instanceof Error?e.message:String(e);
    console.error("stripe-webhook",e);
    await finishWebhook(admin,state.id,"failed",message);
    return new Response("processing failed",{status:500});
  }
});
