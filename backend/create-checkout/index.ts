import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {createClient} from "npm:@supabase/supabase-js@2.57.4";
const json=(data:unknown,status=200)=>new Response(JSON.stringify(data),{status,headers:{"Content-Type":"application/json","Cache-Control":"no-store"}});
function secret(){const k=Deno.env.get("SUPABASE_SECRET_KEY")||Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");if(k)return k;try{return JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS")||"{}").default}catch{return ""}}
Deno.serve(async req=>{
 if(req.method!=="POST")return json({error:"Method not allowed"},405);
 try{
  const auth=req.headers.get("authorization")||"";
  if(!auth.startsWith("Bearer "))return json({error:"Nejdřív se přihlaste."},401);
  const admin=createClient(Deno.env.get("SUPABASE_URL")!,secret(),{auth:{persistSession:false,autoRefreshToken:false}});
  const {data:{user},error:authError}=await admin.auth.getUser(auth.slice(7));
  if(authError||!user)return json({error:"Přihlášení vypršelo."},401);
  const b=await req.json();const orgId=String(b.organization_id||"");
  const {data:m,error:me}=await admin.from("organization_memberships").select("role").eq("user_id",user.id).eq("organization_id",orgId).maybeSingle();
  if(me||!m||!["owner","admin"].includes(m.role))return json({error:"Předplatné může spravovat vlastník nebo správce firmy."},403);
  const {data:sub,error:se}=await admin.from("subscriptions").select("*").eq("organization_id",orgId).maybeSingle();
  if(se||!sub)return json({error:"Předplatné firmy nebylo nalezeno."},404);
  if(sub.is_comped)return json({error:"Tato firma má interní plán a nevyžaduje platbu."},409);
  const [{data:key,error:ke},{data:webhook}]=await Promise.all([admin.rpc("integration_secret_get",{p_name:"stripe_secret_key"}),admin.rpc("integration_secret_exists",{p_name:"stripe_webhook_secret"})]);
  if(ke||!key||!webhook)return json({error:"Platby ještě nejsou aktivované. Vraťte se k nabídce a odešlete nezávazný zájem.",code:"PAYMENTS_NOT_CONFIGURED"},503);
  const portal=b.action==="portal"||sub.provider==="stripe"&&["active","trialing","past_due","incomplete"].includes(sub.status)&&sub.provider_subscription_id;
  let path="checkout/sessions",form=new URLSearchParams();
  if(portal){
   if(!sub.provider_customer_id)return json({error:"Platební účet ještě není vytvořený."},409);
   path="billing_portal/sessions";form.set("customer",sub.provider_customer_id);form.set("return_url","https://mistrflow.vercel.app/tarify");
  }else{
   const planCode=String(b.plan_code||""),interval=b.interval==="annual"?"annual":"monthly";
   const {data:plan,error:pe}=await admin.from("plan_catalog").select("*").eq("code",planCode).eq("active",true).eq("is_public",true).maybeSingle();
   if(pe||!plan)return json({error:"Neplatný tarif."},400);
   form=new URLSearchParams({"mode":"subscription","locale":"cs","client_reference_id":orgId,"success_url":"https://mistrflow.vercel.app/tarify?success=1","cancel_url":"https://mistrflow.vercel.app/tarify?cancelled=1","line_items[0][quantity]":"1","line_items[0][price_data][currency]":plan.currency.toLowerCase(),"line_items[0][price_data][unit_amount]":String(interval==="annual"?plan.annual_cents:plan.monthly_cents),"line_items[0][price_data][recurring][interval]":interval==="annual"?"year":"month","line_items[0][price_data][product_data][name]":"MistrFlow "+plan.name,"subscription_data[metadata][organization_id]":orgId,"subscription_data[metadata][plan_code]":planCode,"metadata[organization_id]":orgId,"metadata[plan_code]":planCode});
   if(sub.provider_customer_id)form.set("customer",sub.provider_customer_id);else if(user.email)form.set("customer_email",user.email);
  }
  const idem="mistrflow-"+orgId+"-"+path.replace("/","-")+"-"+String(b.plan_code||"")+"-"+String(b.interval||"")+"-"+Math.floor(Date.now()/1800000);
  const r=await fetch("https://api.stripe.com/v1/"+path,{method:"POST",headers:{"Authorization":"Bearer "+key,"Content-Type":"application/x-www-form-urlencoded","Idempotency-Key":idem},body:form});
  const session=await r.json();
  if(!r.ok||!session.url)return json({error:"Platební stránku se nepodařilo připravit. Zkuste to znovu."},502);
  const target=new URL(session.url);if(target.protocol!=="https:"||!["checkout.stripe.com","billing.stripe.com"].includes(target.hostname))return json({error:"Neplatná platební adresa."},502);
  await admin.from("audit_logs").insert({organization_id:orgId,actor_user_id:user.id,action:portal?"billing.portal_opened":"billing.checkout_created",entity_type:"subscription",entity_id:sub.id,details:{session_id:session.id,plan_code:b.plan_code||null}});
  return json({url:session.url});
 }catch{return json({error:"Platbu nyní nelze připravit."},500)}
});

