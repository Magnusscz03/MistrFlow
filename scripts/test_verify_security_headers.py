"""Regression tests for security-header response validation."""

import unittest

import verify_security_headers

BASE = "https://mistrflow.vercel.app"
GOOD_HEADERS = {
    "strict-transport-security": "max-age=63072000",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


class SecurityHeaderVerifierTests(unittest.TestCase):
    def test_valid_mistrflow_response_passes(self):
        self.assertEqual(
            verify_security_headers.response_failures(
                BASE,
                "/",
                200,
                GOOD_HEADERS,
                b"<html><title>MistrFlow</title></html>",
                BASE + "/",
            ),
            [],
        )

    def test_vercel_login_fails_even_with_compliant_headers(self):
        self.assertEqual(
            verify_security_headers.response_failures(
                BASE,
                "/",
                200,
                GOOD_HEADERS,
                b"<html>Log in to Vercel</html>",
                "https://vercel.com/login?next=mistrflow",
            ),
            ["/: reached Vercel Deployment Protection, not MistrFlow"],
        )

    def test_external_redirect_fails(self):
        failures = verify_security_headers.response_failures(
            BASE,
            "/download",
            200,
            GOOD_HEADERS,
            b"<html>Other site</html>",
            "https://example.com/download",
        )
        self.assertEqual(
            failures,
            [
                "/download: redirected outside expected origin "
                "to https://example.com/download"
            ],
        )

    def test_service_worker_requires_no_store(self):
        failures = verify_security_headers.response_failures(
            BASE,
            "/sw.js",
            200,
            GOOD_HEADERS,
            b"self.addEventListener('fetch', () => {})",
            BASE + "/sw.js",
        )
        self.assertEqual(
            failures,
            ["/sw.js: Cache-Control must contain no-store, got ''"],
        )


if __name__ == "__main__":
    unittest.main()
