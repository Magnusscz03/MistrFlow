"""Tests for the high-confidence tracked-secret scanner."""

import base64
import json
import unittest

import verify_no_secrets


def service_role_jwt():
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"role": "service_role"}).encode("utf-8")
    ).rstrip(b"=")
    signature = b"A" * 16
    return b".".join((header, payload, signature)).decode("ascii")


class SecretScannerTests(unittest.TestCase):
    def test_public_supabase_key_name_is_allowed(self):
        text = "NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJpublic.example.value"
        self.assertEqual(verify_no_secrets.scan_text(text), [])

    def test_environment_lookup_is_allowed(self):
        text = 'Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")'
        self.assertEqual(verify_no_secrets.scan_text(text), [])

    def test_stripe_secret_is_detected_without_returning_value(self):
        secret = "sk_" + "live_" + "A" * 24
        findings = verify_no_secrets.scan_text("token=" + secret)
        self.assertEqual(findings, [(1, "Stripe secret")])
        self.assertNotIn(secret, repr(findings))

    def test_literal_sensitive_assignment_is_detected(self):
        value = "actual-" + "B" * 24
        findings = verify_no_secrets.scan_text(
            'VOLAI_API_KEY="' + value + '"'
        )
        self.assertEqual(
            findings,
            [(1, "literal value assigned to VOLAI_API_KEY")],
        )
        self.assertNotIn(value, repr(findings))

    def test_service_role_jwt_is_detected(self):
        findings = verify_no_secrets.scan_text(service_role_jwt())
        self.assertEqual(findings, [(1, "Supabase service_role JWT")])

    def test_placeholder_assignment_is_allowed(self):
        text = 'STRIPE_SECRET_KEY="your_stripe_secret_here"'
        self.assertEqual(verify_no_secrets.scan_text(text), [])


if __name__ == "__main__":
    unittest.main()
