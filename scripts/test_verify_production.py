"""Regression tests for production redirect and protection detection."""

import unittest
from unittest.mock import patch

import verify_production


class FakeResponse:
    status = 200

    def __init__(self, body, url):
        self.body = body
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body

    def geturl(self):
        return self.url


class ProductionVerifierTests(unittest.TestCase):
    def test_same_origin_accepts_normalized_default_https_port(self):
        self.assertTrue(
            verify_production.same_origin(
                "https://mistrflow.vercel.app",
                "https://mistrflow.vercel.app:443/download",
            )
        )

    def test_same_origin_rejects_external_redirect(self):
        self.assertFalse(
            verify_production.same_origin(
                "https://mistrflow.vercel.app",
                "https://vercel.com/login?next=mistrflow",
            )
        )

    def test_vercel_login_redirect_is_protection(self):
        self.assertTrue(
            verify_production.is_vercel_protection(
                "https://vercel.com/login?next=mistrflow",
                b"<html>Log in to Vercel</html>",
            )
        )

    def test_same_host_protection_page_is_detected(self):
        self.assertTrue(
            verify_production.is_vercel_protection(
                "https://mistrflow.vercel.app/",
                b"<html><title>Vercel Authentication</title></html>",
            )
        )

    def test_normal_mistrflow_page_is_not_protection(self):
        self.assertFalse(
            verify_production.is_vercel_protection(
                "https://mistrflow.vercel.app/download",
                b"<html><title>MistrFlow</title></html>",
            )
        )

    @patch("verify_production.urlopen")
    def test_request_exposes_final_redirect_url(self, mocked_urlopen):
        mocked_urlopen.return_value = FakeResponse(
            b"<html>Log in to Vercel</html>",
            "https://vercel.com/login?next=mistrflow",
        )
        status, body, final_url = verify_production.request(
            "https://mistrflow.vercel.app", "/"
        )
        self.assertEqual(status, 200)
        self.assertIn(b"Log in to Vercel", body)
        self.assertEqual(final_url, "https://vercel.com/login?next=mistrflow")


if __name__ == "__main__":
    unittest.main()
