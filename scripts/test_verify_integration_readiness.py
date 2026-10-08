import unittest

from verify_integration_readiness import scan


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


if __name__ == "__main__":
    unittest.main()
