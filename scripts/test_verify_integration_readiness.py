import unittest

from verify_integration_readiness import (
    scan,
    scan_checkout_input,
    scan_error_boundary,
    scan_owner_input,
    scan_stripe_webhook_input,
)


SAFE = '''
const volaiSenderPresent=false;
ready:volaiIntegration?.status==="connected"&&volaiApiKeyPresent&&volaiWebhookSecretPresent&&volaiSenderPresent&&activeVolaiRoutes.length>0
if(!url||!pub||!secret)return json({error:"Server configuration missing"},500);
if(!auth?.startsWith("Bearer "))return json({error:"Not authenticated"},401);
const rawBody=await req.text();
if(new TextEncoder().encode(rawBody).byteLength>16384)return json({error:"Požadavek je příliš dlouhý."},413);
try{JSON.parse(rawBody)}catch{return json({error:"Neplatný požadavek."},400)}
if(action==="summary")return json({});
try {} catch(e) {
 console.error("platform-owner-data",e);
 return json({error:"Správu platformy nyní nelze načíst."},500);
}
'''

SAFE_OWNER_AI = '''
try {} catch(e) {
 console.error("owner-ai",e);
 return json({error:"AI služba není dostupná."},500);
}
'''

SAFE_CHECKOUT = '''
const rawBody=await req.text();
if(new TextEncoder().encode(rawBody).byteLength>4096)return json({error:"Požadavek je příliš dlouhý."},413);
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


class IntegrationReadinessTests(unittest.TestCase):
    def test_safe_backend_passes(self):
        self.assertEqual(scan(SAFE), [])

    def test_owner_input_guards_pass(self):
        self.assertEqual(scan_owner_input(SAFE), [])

    def test_owner_body_limit_is_required(self):
        failures = scan_owner_input(SAFE.replace(
            'if(new TextEncoder().encode(rawBody).byteLength>16384)return json({error:"Požadavek je příliš dlouhý."},413);',
            "",
        ))
        self.assertIn("owner request bodies must be capped before summary queries", failures)

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
            'if(new TextEncoder().encode(rawBody).byteLength>4096)return json({error:"Požadavek je příliš dlouhý."},413);',
            "",
        ))
        self.assertIn("checkout request bodies must be capped before privileged queries", failures)

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
