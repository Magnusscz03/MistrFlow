"""Read-only security-header check for a deployed MistrFlow site."""
import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from verify_production import is_vercel_protection, same_origin

REQUIRED = {
    "strict-transport-security": "max-age=",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "strict-origin-when-cross-origin",
}


def fetch(url):
    request = Request(
        url, headers={"User-Agent": "MistrFlow-security-verifier/1.0"}
    )
    try:
        with urlopen(request, timeout=20) as response:
            return (
                response.status,
                {key.lower(): value for key, value in response.headers.items()},
                response.read(200_000),
                response.geturl(),
            )
    except HTTPError as error:
        return (
            error.code,
            {key.lower(): value for key, value in error.headers.items()},
            error.read(200_000),
            error.geturl(),
        )


def response_failures(base_url, path, status, headers, body, final_url):
    failures = []
    if is_vercel_protection(final_url, body):
        return [f"{path}: reached Vercel Deployment Protection, not MistrFlow"]
    if not same_origin(base_url, final_url):
        return [f"{path}: redirected outside expected origin to {final_url}"]
    if status != 200:
        return [f"{path}: expected 200, got {status}"]

    for header, expected in REQUIRED.items():
        actual = headers.get(header, "")
        if expected not in actual:
            failures.append(
                f"{path}: {header} expected {expected!r}, got {actual!r}"
            )
    if path == "/sw.js":
        cache_control = headers.get("cache-control", "")
        if "no-store" not in cache_control.lower():
            failures.append(
                f"/sw.js: Cache-Control must contain no-store, got {cache_control!r}"
            )
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://mistrflow.vercel.app")
    args = parser.parse_args()
    failures = []

    for path in ("/", "/app", "/intake", "/download", "/sw.js"):
        url = urljoin(args.base_url.rstrip("/") + "/", path.lstrip("/"))
        try:
            status, headers, body, final_url = fetch(url)
        except (URLError, TimeoutError, ValueError) as error:
            failures.append(f"{path}: {error}")
            continue

        print(f"GET {path}: {status} ({final_url})")
        failures.extend(
            response_failures(
                args.base_url, path, status, headers, body, final_url
            )
        )

    for failure in failures:
        print("FAIL:", failure)
    if failures:
        print(f"{len(failures)} security-header checks failed.")
        return 1
    print("Security headers verified on all public entry points.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
