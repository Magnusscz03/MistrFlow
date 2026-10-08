import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "npm:@supabase/supabase-js@2.57.4";

const TABLES=[
"sales_inquiries","ai_change_requests","ai_usage_events","app_releases","appointments","attachments","audit_logs","calls","customers",
"intake_sessions","integrations","invoice_items","invoice_sequences","invoices","lead_notes","leads",
"messages","money_events","organization_feature_overrides","organization_invites","organization_memberships",
"organization_usage","organizations","phone_routes","plan_catalog","plan_entitlements","platform_admins",
"pricing_rules","profiles","role_capabilities","subscriptions","webhook_events"
];

function json(data:unknown,status=200){return new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}})}
function secretKey(){
 const d=Deno.env.get("SUPABASE_SECRET_KEY")||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
 if(d)return d;
 try{return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default||null}catch{return null}
}
function scrub(value:any,key=""):any{
 if(/password|secret|token|api.?key|authorization|signature|encrypted|hash|verifier|challenge/i.test(key))return "[hidden]";
 if(Array.isArray(value))return value.map(v=>scrub(v));
 if(value&&typeof value==="object"){const out:any={};for(const [k,v] of Object.entries(value))out[k]=scrub(v,k);return out}
 return value;
}
async function countRows(admin:any,table:string){
 const {count,error}=await admin.from(table).select("*",{count:"exact",head:true});
 return error?null:(count??0);
}
async function authCount(admin:any){
 let total=0;
 for(let page=1;page<=50;page++){
  const {data,error}=await admin.auth.admin.listUsers({page,perPage:1000});
  if(error)throw error;
  const n=(data.users||[]).length;total+=n;if(n<1000)break;
 }
 return total;
}
function uuidish(v:string){return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v)}
function phone(v:string){return /^\+[1-9]\d{7,14}$/.test(v)}

Deno.serve(async(req:Request)=>{
 try{
  if(req.method!=="POST")return json({error:"Method not allowed"},405);
  const url=Deno.env.get("SUPABASE_URL");
  const pub=Deno.env.get("SUPABASE_ANON_KEY")||Deno.env.get("SUPABASE_PUBLISHABLE_KEY");
  const secret=secretKey();
  const auth=req.headers.get("Authorization");
  if(!url||!pub||!secret||!auth)return json({error:"Server configuration missing"},500);

  const userClient=createClient(url,pub,{global:{headers:{Authorization:auth}},auth:{persistSession:false,autoRefreshToken:false}});
  const admin=createClient(url,secret,{auth:{persistSession:false,autoRefreshToken:false}});
  const {data:{user},error:ue}=await userClient.auth.getUser();
  if(ue||!user)return json({error:"Not authenticated"},401);
  const {data:pa}=await admin.from("platform_admins").select("user_id").eq("user_id",user.id).maybeSingle();
  if(!pa?.user_id)return json({error:"Platform Owner only"},403);

  const body=await req.json().catch(()=>({}));
  const action=String(body.action||"summary");

  if(action==="tables")return json({tables:["auth_users",...TABLES]});

  if(action==="set_phone_route"){
    const organizationId=String(body.organization_id||"");
    const number=String(body.provider_number||"").trim().replace(/\s+/g,"");
    if(!uuidish(organizationId))return json({error:"Neplatná firma."},400);
    if(!phone(number))return json({error:"Číslo musí být v mezinárodním formátu, např. +420123456789."},400);

    const {data:org,error:orgErr}=await admin.from("organizations").select("id,name").eq("id",organizationId).maybeSingle();
    if(orgErr||!org)return json({error:"Firma neexistuje."},404);

    const {data:route,error}=await admin.from("phone_routes").upsert({
      organization_id:organizationId,
      provider:"volai",
      provider_number:number,
      enabled:true
    },{onConflict:"provider,provider_number"}).select("id,organization_id,provider,provider_number,enabled").single();
    if(error)throw error;

    await admin.from("audit_logs").insert({
      organization_id:organizationId,
      actor_user_id:user.id,
      action:"platform.phone_route_upserted",
      entity_type:"phone_route",
      entity_id:route.id,
      details:{provider:"volai",provider_number:number}
    });
    return json({ok:true,route});
  }

  if(action==="disable_phone_route"){
    const id=String(body.id||"");
    if(!uuidish(id))return json({error:"Neplatná route."},400);
    const {data:route,error:readErr}=await admin.from("phone_routes").select("id,organization_id,provider_number").eq("id",id).maybeSingle();
    if(readErr||!route)return json({error:"Route nebyla nalezena."},404);
    const {error}=await admin.from("phone_routes").update({enabled:false}).eq("id",id);
    if(error)throw error;
    await admin.from("audit_logs").insert({
      organization_id:route.organization_id,
      actor_user_id:user.id,
      action:"platform.phone_route_disabled",
      entity_type:"phone_route",
      entity_id:id,
      details:{provider:"volai",provider_number:route.provider_number}
    });
    return json({ok:true});
  }

  if(action==="summary"){
   const [
    users,organizations,leads,invoices,appointments,
    organizationsRes,integrationsRes,routesRes,webhooksRes,aiRes,auditRes,subscriptionsRes,releasesRes
   ]=await Promise.all([
    authCount(admin),
    countRows(admin,"organizations"),
    countRows(admin,"leads"),
    countRows(admin,"invoices"),
    countRows(admin,"appointments"),
    admin.from("organizations").select("id,name,slug,status,created_at").order("name"),
    admin.from("integrations").select("provider,status,external_account_id,settings,updated_at,organization_id").order("provider"),
    admin.from("phone_routes").select("id,organization_id,provider,provider_number,enabled,created_at").order("created_at",{ascending:false}).limit(50),
    admin.from("webhook_events").select("id,provider,event_type,event_id,processed_at,created_at").order("created_at",{ascending:false}).limit(50),
    admin.from("ai_change_requests").select("id,request_text,risk,status,ai_summary,result,created_at,completed_at").order("created_at",{ascending:false}).limit(20),
    admin.from("audit_logs").select("id,organization_id,actor_user_id,action,entity_type,entity_id,details,created_at").order("created_at",{ascending:false}).limit(50),
    admin.from("subscriptions").select("organization_id,plan_code,status,billing_interval,trial_ends_at,cancel_at_period_end,is_comped,updated_at").order("updated_at",{ascending:false}),
    admin.from("app_releases").select("platform,channel,version_name,version_code,download_url,sha256,size_bytes,status,notes,created_at").order("created_at",{ascending:false}).limit(20)
   ]);

   const tableCounts=Object.fromEntries(await Promise.all(TABLES.map(async t=>[t,await countRows(admin,t)])));
   const organizationsList=scrub(organizationsRes.data||[]);
   const integrations=scrub(integrationsRes.data||[]);
   const phoneRoutes=scrub(routesRes.data||[]);
   const webhookEvents=scrub(webhooksRes.data||[]);
   const aiRequests=scrub(aiRes.data||[]);
   const audit=scrub(auditRes.data||[]);
   const subscriptions=scrub(subscriptionsRes.data||[]);
   const releases=scrub(releasesRes.data||[]);
   const now=Date.now();
   const recent=(x:any)=>{const t=new Date(x.created_at||x.processed_at||0).getTime();return !!t&&now-t<86400000};

   const volaiIntegration=(integrationsRes.data||[]).find((x:any)=>x.provider==="volai")||null;
   const stripeIntegration=(integrationsRes.data||[]).find((x:any)=>x.provider==="stripe")||null;
   const activeVolaiRoutes=(routesRes.data||[]).filter((x:any)=>x.provider==="volai"&&x.enabled);
   async function vaultExists(name:string){
     const {data,error}=await admin.rpc("integration_secret_exists",{p_name:name});
     if(error)return false;
     return data===true;
   }
   const [volaiApiKeyPresent,volaiWebhookSecretPresent,stripeSecretKeyPresent,stripeWebhookSecretPresent]=await Promise.all([
     vaultExists("volai_api_key"),vaultExists("volai_webhook_secret"),
     vaultExists("stripe_secret_key"),vaultExists("stripe_webhook_secret")
   ]);
   const volaiSenderPresent=true;

   return json({
    summary:{
     users,organizations,leads,invoices,appointments,
     connected_integrations:(integrationsRes.data||[]).filter((x:any)=>x.status==="connected").length,
     active_phone_routes:(routesRes.data||[]).filter((x:any)=>x.enabled).length,
     webhook_events_24h:(webhooksRes.data||[]).filter(recent).length,
     pending_ai_changes:(aiRes.data||[]).filter((x:any)=>x.status==="pending"||x.status==="approved").length,
     tables:TABLES.length+1,
     latest_android_release:(releasesRes.data||[]).find((x:any)=>x.platform==="android"&&x.status==="active")||null
    },
    readiness:{
      volai:{
        integration_connected:volaiIntegration?.status==="connected",
        api_key_present:volaiApiKeyPresent,
        webhook_secret_present:volaiWebhookSecretPresent,
        sender_present:volaiSenderPresent,
        active_phone_route:activeVolaiRoutes.length>0,
        active_phone_routes:activeVolaiRoutes.length,
        ready:volaiIntegration?.status==="connected"&&volaiApiKeyPresent&&volaiWebhookSecretPresent&&volaiSenderPresent&&activeVolaiRoutes.length>0,
        webhook_url:url+"/functions/v1/volai-webhook"
      },
      stripe:{
        integration_connected:stripeIntegration?.status==="connected",
        secret_key_present:stripeSecretKeyPresent,
        webhook_secret_present:stripeWebhookSecretPresent,
        ready:stripeIntegration?.status==="connected"&&stripeSecretKeyPresent&&stripeWebhookSecretPresent,
        webhook_url:url+"/functions/v1/stripe-webhook"
      }
    },
    organizations:organizationsList,
    integrations,phone_routes:phoneRoutes,webhook_events:webhookEvents,
    ai_change_requests:aiRequests,audit,subscriptions,app_releases:releases,
    table_counts:tableCounts,generated_at:new Date().toISOString()
   });
  }

  const table=String(body.table||"organizations");
  const limit=Math.min(Math.max(Number(body.limit)||50,1),100);
  const offset=Math.max(Number(body.offset)||0,0);

  if(table==="auth_users"){
   const page=Math.floor(offset/limit)+1;
   const {data,error}=await admin.auth.admin.listUsers({page,perPage:limit});
   if(error)throw error;
   return json({table,rows:(data.users||[]).map((u:any)=>scrub({
    id:u.id,email:u.email,phone:u.phone,email_confirmed_at:u.email_confirmed_at,last_sign_in_at:u.last_sign_in_at,
    created_at:u.created_at,updated_at:u.updated_at,user_metadata:u.user_metadata,app_metadata:u.app_metadata
   })),count:null,limit,offset});
  }

  if(!TABLES.includes(table))return json({error:"Table not allowed"},400);
  const {data,error,count}=await admin.from(table).select("*",{count:"exact"}).range(offset,offset+limit-1);
  if(error)throw error;
  return json({table,rows:scrub(data||[]),count,limit,offset});
 }catch(e){
  console.error(e);
  return json({error:e instanceof Error?e.message:"Database explorer failed"},500);
 }
});
