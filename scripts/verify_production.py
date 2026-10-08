"""Read-only production smoke test for a complete MistrFlow deployment."""
import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RELEASE = json.loads((ROOT / "android-release.json").read_text())


def origin(url):
    parsed = urlsplit(url)
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme.lower() == "https" else 80
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port


def same_origin(expected_url, actual_url):
    try:
        return origin(expected_url) == origin(actual_url)
    except ValueError:
        return False


def is_vercel_protection(final_url, body):
    parsed = urlsplit(final_url)
    hostname = (parsed.hostname or "").lower()
    if hostname in {"vercel.com", "www.vercel.com"} and parsed.path.startswith("/login"):
        return True
    sample = body[:200_000].decode("utf-8", errors="ignore").lower()
    return any(
        marker in sample
        for marker in ("log in to vercel", "vercel authentication", "_vercel_sso")
    )


def request(base_url, path, method="GET", data=None):
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    req = Request(url, method=method, data=data)
    req.add_header("User-Agent", "MistrFlow-release-verifier/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=20) as response:
            return response.status, response.read(), response.geturl()
    except HTTPError as error:
        return error.code, error.read(), error.geturl()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://mistrflow.vercel.app")
    args = parser.parse_args()
    failures = []
    bodies = {}

    checks = [
        ("/", "GET", 200, None),
        ("/intake", "GET", 200, None),
        ("/download", "GET", 200, None),
        ("/api/owner-ai", "POST", 401, b"{}"),
    ]
    for path, method, expected, data in checks:
        try:
            status, body, final_url = request(args.base_url, path, method, data)
            bodies[path] = body
            print(f"{method} {path}: {status} ({final_url})")
            if is_vercel_protection(final_url, body):
                failures.append(
                    f"{method} {path}: reached Vercel Deployment Protection, not MistrFlow"
                )
                continue
            if not same_origin(args.base_url, final_url):
                failures.append(
                    f"{method} {path}: redirected outside expected origin to {final_url}"
                )
                continue
            if status != expected:
                failures.append(
                    f"{method} {path}: expected {expected}, got {status}"
                )
        except (URLError, TimeoutError, ValueError) as error:
            failures.append(f"{method} {path}: {error}")

    download = bodies.get("/download", b"").decode("utf-8", errors="replace")
    for label, value in (
        ("version", "MistrFlow " + RELEASE["version_name"]),
        ("SHA-256", RELEASE["sha256"]),
        ("APK URL", RELEASE["download_url"]),
        ("signature warning", "odlišný podpis"),
    ):
        if value not in download:
            failures.append(f"/download: missing {label}")

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        print(
            f"{len(failures)} production checks failed; "
            "do not promote this deployment."
        )
        return 1
    print("Production smoke test passed, including Android release metadata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
