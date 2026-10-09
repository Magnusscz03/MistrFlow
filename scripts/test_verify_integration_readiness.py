import unittest

from verify_integration_readiness import (
    scan,
    scan_checkout_input,
    scan_error_boundary,
    scan_owner_ai_input,
    scan_owner_input,
    scan_sales_inquiry_input,
    scan_send_sms_input,
    scan_stripe_webhook_input,
)


SAFE = '''
const MAX_OWNER_DATA_BYTES=16384;
async function readLimitedBody(req:Request,maxBytes:number){
 const reader=req.body.getReader();
 const {value}=await reader.read();
 if(value.byteLength>maxBytes){await reader.cancel();return null}
 return "{}";
}
const volaiSenderPresent=false;
ready:volaiIntegration?.status==="connected"&&volaiApiKeyPresent&&volaiWebhookSecretPresent&&volaiSenderPresent&&activeVolaiRoutes.length>0
if(!url||!pub||!secret)return json({error:"Server configuration missing"},500);
if(!auth?.startsWith("Bearer "))return json({error:"Not authenticated"},401);
const rawBody=await readLimitedBody(req,MAX_OWNER_DATA_BYTES);
if(rawBody===null)return json({error:"Požadavek je příliš dlouhý."},413);
try{JSON.parse(rawBody)}catch{return json({error:"Neplatný požadavek."},400)}
if(action==="summary")return json({});
try {} catch(e) {
 console.error("platform-owner-data",e);
 return json({error:"Správu platformy nyní nelze načíst."},500);
}
'''

SAFE_OWNER_AI = '''
const MAX_OWNER_AI_BYTES=16384;
async function readLimitedBody(req:Request,maxBytes:number){
 const reader=req.body.getReader();
 const {value}=await reader.read();
 if(value.byteLength>maxBytes){await reader.cancel();return null}
 return "{}";
}
Deno.serve(async req=>{
 const auth=req.headers.get("authorization")||"";
 if(!auth.startsWith("Bearer "))return json({error:"Přihlaste se do aplikace."},401);
 if(roleError||!owner)return json({error:"Přístup pouze pro vlastníka platformy."},403);
 const raw=await readLimitedBody(req,MAX_OWNER_AI_BYTES);
 if(raw===null)return json({error:"Požadavek je příliš dlouhý."},413);
 try{JSON.parse(raw)}catch{return json({error:"Neplatný požadavek."},400)}
 return json({error:"AI služba ještě není připojená."},503);
});
try {} catch(e) {
 console.error("owner-ai",e);
 return json({error:"AI služba není dostupná."},500);
}
'''

SAFE_CHECKOUT = '''
const MAX_CHECKOUT_BYTES=4096;
async function readLimitedBody(req:Request,maxBytes:number){
 const reader=req.body.getReader();
 const {value}=await reader.read();
 if(value.byteLength>maxBytes){await reader.cancel();return null}
 return "{}";
}
const rawBody=await readLimitedBody(req,MAX_CHECKOUT_BYTES);
if(rawBody===null)return json({error:"Požadavek je příliš dlouhý."},413);
try{const parsed=JSON.parse(rawBody);if(!parsed)return json({error:"Neplatný požadavek."},400);}catch{return json({error:"Neplatný požadavek."},400)}
if(!uuidPattern.test(orgId))return json({error:"Neplatná firma."},400);
admin.from("organization_memberships")
try {} catch(e) {
 console.error("create-checkout",e);
 return json({error:"Platbu nyní nelze připravit."},500);
}
'''

SAFE_STRIPE_WEBHOOK = '''
const MAX_WEBHOOK_BYTES=1024*1024;
async function readWebhookBody(req:Request,maxBytes:number){
 const reader=req.body.getReader();
 const {value}=await reader.read();
 if(value.byteLength>maxBytes){await reader.cancel();return null}
 return "{}";
}
Deno.serve(async(req:Request)=>{
 const raw=await readWebhookBody(req,MAX_WEBHOOK_BYTES);
 if(raw===null)return new Response("payload too large",{status:413});
 const admin=db();
 if(!(await verifyStripe(raw,req.headers.get("stripe-signature"),webhookSecret)))return new Response("invalid signature",{status:401});
 const event=JSON.parse(raw);
});
'''

SAFE_SALES_INQUIRY = '''
const MAX_INQUIRY_BYTES=8192;
async function readLimitedBody(req:Request,maxBytes:number){
 const reader=req.body.getReader();
 const {value}=await reader.read();
 if(value.byteLength>maxBytes){await reader.cancel();return null}
 return "{}";
}
Deno.serve(async req=>{
 const raw=await readLimitedBody(req,MAX_INQUIRY_BYTES);
 if(raw===null||raw.length>6000)return json({error:"Zpráva je příliš dlouhá."},413);
 try{JSON.parse(raw)}catch{return json({error:"Neplatný požadavek."},400)}
 const admin=createClient(url,key);
 try{}catch(error){
  console.error("sales-inquiry",error);
  return json({error:"Zprávu nyní nelze uložit."},500);
 }
});
'''

SAFE_SEND_SMS = '''
const MAX_SMS_BYTES=8192;
async function readLimitedBody(req:Request,maxBytes:number){
 const reader=req.body.getReader();
 const {value}=await reader.read();
 if(value.byteLength>maxBytes){await reader.cancel();return null}
 return "{}";
}
const raw=await readLimitedBody(req,MAX_SMS_BYTES);
if(raw===null)return json({error:"Požadavek je příliš dlouhý."},413);
try{JSON.parse(raw)}catch{return json({error:"Neplatný požadavek."},400)}
if(!uuidPattern.test(organizationId))return json({error:"Neplatná firma."},400);
client.from("organization_memberships").eq("user_id",user.id).eq("organization_id",organizationId);
client.from("integrations").eq("organization_id",organizationId).eq("provider","volai");
if(integration?.status!=="connected"||!apiKey)return json({},503);
fetch("https://volai.cz/v1/messages");
try {} catch(error) {
 console.error("send-sms",error);
 return json({error:"SMS nyní nelze odeslat."},500);
}
'''


class IntegrationReadinessTests(unittest.TestCase):
    def test_safe_backend_passes(self):
        self.assertEqual(scan(SAFE), [])

    def test_owner_input_guards_pass(self):
        self.assertEqual(scan_owner_input(SAFE), [])

    def test_owner_body_limit_is_required(self):
        failures = scan_owner_input(SAFE.replace(
            'if(rawBody===null)return json({error:"Požadavek je příliš dlouhý."},413);',
            "",
        ))
        self.assertIn("oversized owner requests must return 413", failures)

    def test_owner_stream_limit_is_required(self):
        failures = scan_owner_input(SAFE.replace("await reader.cancel();", ""))
        self.assertIn("owner body reads must stop after the byte limit", failures)

    def test_owner_malformed_json_is_rejected(self):
        failures = scan_owner_input(SAFE.replace(
            'try{JSON.parse(rawBody)}catch{return json({error:"Neplatný požadavek."},400)}',
            "const body={};",
        ))
        self.assertIn("malformed owner JSON must return 400", failures)

    def test_hard_coded_sender_is_rejected(self):
        failures = scan(SAFE.replace("volaiSenderPresent=false", "volaiSenderPresent=true"))
        self.assertIn("integration evidence must not be hard-coded to true", failures)

    def test_internal_error_message_is_rejected(self):
        failures = scan(SAFE.replace(
            'error:"Správu platformy nyní nelze načíst."',
            'error:e instanceof Error?e.message:"failed"',
        ))
        self.assertIn("internal exception messages must not be returned to clients", failures)

    def test_incomplete_readiness_gate_is_rejected(self):
        failures = scan(SAFE.replace("&&volaiSenderPresent", ""))
        self.assertIn("Volai readiness must require every connected-state signal", failures)

    def test_auth_must_not_be_treated_as_server_configuration(self):
        failures = scan(SAFE.replace(
            "if(!url||!pub||!secret)return",
            "if(!url||!pub||!secret||!auth)return",
        ))
        self.assertIn("server configuration errors must exclude request authentication", failures)

    def test_bearer_authentication_must_return_401(self):
        failures = scan(SAFE.replace(
            'if(!auth?.startsWith("Bearer "))return json({error:"Not authenticated"},401);',
            'if(!auth)return json({error:"Server configuration missing"},500);',
        ))
        self.assertIn("missing or malformed bearer authentication must return 401", failures)

    def test_owner_ai_error_boundary_passes(self):
        self.assertEqual(scan_error_boundary(
            SAFE_OWNER_AI,
            "owner AI backend",
            'console.error("owner-ai",e)',
            'error:"AI služba není dostupná."',
        ), [])

    def test_owner_ai_input_guards_pass(self):
        self.assertEqual(scan_owner_ai_input(SAFE_OWNER_AI), [])

    def test_owner_ai_stream_limit_is_required(self):
        failures = scan_owner_ai_input(SAFE_OWNER_AI.replace("await reader.cancel();", ""))
        self.assertIn("owner AI body reads must stop after the byte limit", failures)

    def test_owner_ai_auth_must_precede_body_read(self):
        unsafe = SAFE_OWNER_AI.replace(
            'if(!auth.startsWith("Bearer "))return json({error:"Přihlaste se do aplikace."},401);\n if(roleError||!owner)return json({error:"Přístup pouze pro vlastníka platformy."},403);\n const raw=await readLimitedBody(req,MAX_OWNER_AI_BYTES);',
            'const raw=await readLimitedBody(req,MAX_OWNER_AI_BYTES);\n if(!auth.startsWith("Bearer "))return json({error:"Přihlaste se do aplikace."},401);\n if(roleError||!owner)return json({error:"Přístup pouze pro vlastníka platformy."},403);',
        )
        failures = scan_owner_ai_input(unsafe)
        self.assertIn("owner AI authentication must run before reading the body", failures)

    def test_owner_ai_malformed_json_is_rejected(self):
        failures = scan_owner_ai_input(SAFE_OWNER_AI.replace(
            'try{JSON.parse(raw)}catch{return json({error:"Neplatný požadavek."},400)}',
            "const body={};",
        ))
        self.assertIn("malformed owner AI JSON must return 400", failures)

    def test_checkout_error_boundary_passes(self):
        self.assertEqual(scan_error_boundary(
            SAFE_CHECKOUT,
            "checkout backend",
            'console.error("create-checkout",e)',
            'error:"Platbu nyní nelze připravit."',
        ), [])

    def test_checkout_input_guards_pass(self):
        self.assertEqual(scan_checkout_input(SAFE_CHECKOUT), [])

    def test_checkout_body_limit_is_required(self):
        failures = scan_checkout_input(SAFE_CHECKOUT.replace(
            'if(rawBody===null)return json({error:"Požadavek je příliš dlouhý."},413);',
            "",
        ))
        self.assertIn("oversized checkout requests must return 413", failures)

    def test_checkout_stream_limit_is_required(self):
        failures = scan_checkout_input(SAFE_CHECKOUT.replace("await reader.cancel();", ""))
        self.assertIn("checkout body reads must stop after the byte limit", failures)

    def test_stripe_webhook_input_guards_pass(self):
        self.assertEqual(scan_stripe_webhook_input(SAFE_STRIPE_WEBHOOK), [])

    def test_stripe_webhook_body_limit_is_required(self):
        failures = scan_stripe_webhook_input(SAFE_STRIPE_WEBHOOK.replace(
            "const MAX_WEBHOOK_BYTES=1024*1024;",
            "",
        ))
        self.assertIn("Stripe webhook bodies must use a fixed byte limit", failures)

    def test_stripe_webhook_limit_must_precede_privileged_setup(self):
        unsafe = SAFE_STRIPE_WEBHOOK.replace(
            'if(raw===null)return new Response("payload too large",{status:413});\n const admin=db();',
            'const admin=db();\n if(raw===null)return new Response("payload too large",{status:413});',
        )
        failures = scan_stripe_webhook_input(unsafe)
        self.assertIn("Stripe webhook size rejection must run before privileged setup", failures)

    def test_stripe_webhook_signature_must_precede_json(self):
        unsafe = SAFE_STRIPE_WEBHOOK.replace(
            'if(!(await verifyStripe(raw,req.headers.get("stripe-signature"),webhookSecret)))return new Response("invalid signature",{status:401});\n const event=JSON.parse(raw);',
            'const event=JSON.parse(raw);\n if(!(await verifyStripe(raw,req.headers.get("stripe-signature"),webhookSecret)))return new Response("invalid signature",{status:401});',
        )
        failures = scan_stripe_webhook_input(unsafe)
        self.assertIn("Stripe webhook signatures must be checked before JSON parsing", failures)

    def test_sales_inquiry_input_guards_pass(self):
        self.assertEqual(scan_sales_inquiry_input(SAFE_SALES_INQUIRY), [])

    def test_sales_inquiry_malformed_json_is_rejected(self):
        failures = scan_sales_inquiry_input(SAFE_SALES_INQUIRY.replace(
            'try{JSON.parse(raw)}catch{return json({error:"Neplatný požadavek."},400)}',
            "JSON.parse(raw)",
        ))
        self.assertIn("malformed sales inquiry JSON must return 400", failures)

    def test_sales_inquiry_error_boundary_passes(self):
        self.assertEqual(scan_error_boundary(
            SAFE_SALES_INQUIRY,
            "sales inquiry backend",
            'console.error("sales-inquiry",error)',
            'error:"Zprávu nyní nelze uložit."',
        ), [])

    def test_sales_inquiry_byte_limit_is_required(self):
        failures = scan_sales_inquiry_input(SAFE_SALES_INQUIRY.replace(
            "const MAX_INQUIRY_BYTES=8192;",
            "",
        ))
        self.assertIn("sales inquiry bodies must use a fixed byte limit", failures)

    def test_sales_inquiry_limit_must_precede_privileged_setup(self):
        unsafe = SAFE_SALES_INQUIRY.replace(
            'if(raw===null||raw.length>6000)return json({error:"Zpráva je příliš dlouhá."},413);',
            'const admin=createClient(url,key);\n if(raw===null||raw.length>6000)return json({error:"Zpráva je příliš dlouhá."},413);',
        )
        failures = scan_sales_inquiry_input(unsafe)
        self.assertIn("sales inquiry size rejection must run before privileged setup", failures)

    def test_send_sms_guards_pass(self):
        self.assertEqual(scan_send_sms_input(SAFE_SEND_SMS), [])

    def test_send_sms_requires_stream_limit(self):
        failures = scan_send_sms_input(SAFE_SEND_SMS.replace("await reader.cancel();", ""))
        self.assertIn("SMS body reads must stop after the byte limit", failures)

    def test_send_sms_requires_explicit_organization_membership(self):
        failures = scan_send_sms_input(SAFE_SEND_SMS.replace(
            '.eq("user_id",user.id).eq("organization_id",organizationId)',
            '.eq("user_id",user.id).limit(1)',
        ))
        self.assertIn("SMS membership lookup must target the requested organization", failures)

    def test_send_sms_integration_must_be_tenant_scoped(self):
        failures = scan_send_sms_input(SAFE_SEND_SMS.replace(
            '.eq("organization_id",organizationId).eq("provider","volai")',
            '.eq("provider","volai")',
        ))
        self.assertIn("SMS integration lookup must target the requested organization", failures)

    def test_send_sms_connected_gate_must_precede_provider(self):
        unsafe = SAFE_SEND_SMS.replace(
            'if(integration?.status!=="connected"||!apiKey)return json({},503);\nfetch("https://volai.cz/v1/messages");',
            'fetch("https://volai.cz/v1/messages");\nif(integration?.status!=="connected"||!apiKey)return json({},503);',
        )
        failures = scan_send_sms_input(unsafe)
        self.assertIn("SMS connected-state gate must run before the provider call", failures)

    def test_checkout_organization_validation_is_required(self):
        failures = scan_checkout_input(SAFE_CHECKOUT.replace(
            'if(!uuidPattern.test(orgId))return json({error:"Neplatná firma."},400);',
            "",
        ))
        self.assertIn("checkout organization IDs must be validated", failures)

    def test_privileged_backend_without_server_log_is_rejected(self):
        failures = scan_error_boundary(
            SAFE_OWNER_AI.replace('console.error("owner-ai",e);', ""),
            "owner AI backend",
            'console.error("owner-ai",e)',
            'error:"AI služba není dostupná."',
        )
        self.assertIn("owner AI backend must keep a server-side error log", failures)


if __name__ == "__main__":
    unittest.main()
