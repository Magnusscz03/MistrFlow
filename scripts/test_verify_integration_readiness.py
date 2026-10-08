import unittest

from verify_integration_readiness import scan, scan_checkout_input, scan_error_boundary


SAFE = '''
const volaiSenderPresent=false;
ready:volaiIntegration?.status==="connected"&&volaiApiKeyPresent&&volaiWebhookSecretPresent&&volaiSenderPresent&&activeVolaiRoutes.length>0
if(!url||!pub||!secret)return json({error:"Server configuration missing"},500);
if(!auth?.startsWith("Bearer "))return json({error:"Not authenticated"},401);
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


class IntegrationReadinessTests(unittest.TestCase):
    def test_safe_backend_passes(self):
        self.assertEqual(scan(SAFE), [])

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
