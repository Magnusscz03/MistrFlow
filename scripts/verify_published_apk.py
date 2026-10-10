"""Download and verify the APK referenced by android-release.json."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PATH = ROOT / "android-release.json"
EXPECTED_HOST = "dxpzqepbkkhcbpqmnokn.supabase.co"
MAX_APK_BYTES = 20_000_000


def fail(message):
    print(f"FAIL: {message}")
    return 1


def valid_release_url(url):
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and parsed.hostname == EXPECTED_HOST
        and parsed.path.startswith(
            "/storage/v1/object/public/mistrflow-releases/android/"
        )
        and not parsed.username
        and not parsed.password
    )


def main():
    try:
        release = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
        url = release["download_url"]
        expected_size = int(release["size_bytes"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        return fail(f"invalid Android release record: {error}")

    if not isinstance(url, str) or not valid_release_url(url):
        return fail(f"download URL must use the expected public Supabase path: {url!r}")
    if expected_size <= 0 or expected_size > MAX_APK_BYTES:
        return fail(
            f"recorded size {expected_size} is outside the allowed range "
            f"1..{MAX_APK_BYTES} bytes"
        )

    request = Request(
        url,
        headers={"User-Agent": "MistrFlow-release-verifier/1.0"},
    )
    try:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "MistrFlow.apk"
            with urlopen(request, timeout=30) as response:
                final_url = response.geturl()
                if response.status != 200:
                    return fail(f"download returned HTTP {response.status}")
                if not valid_release_url(final_url):
                    return fail(f"download redirected outside expected Supabase path: {final_url}")

                declared_length = response.headers.get("Content-Length")
                if declared_length is not None and int(declared_length) != expected_size:
                    return fail(
                        f"Content-Length: expected {expected_size}, got {declared_length}"
                    )

                downloaded = 0
                with target.open("wb") as apk:
                    while chunk := response.read(64 * 1024):
                        downloaded += len(chunk)
                        if downloaded > expected_size or downloaded > MAX_APK_BYTES:
                            return fail(
                                f"download exceeded expected size {expected_size} bytes"
                            )
                        apk.write(chunk)

            if downloaded != expected_size:
                return fail(f"download size: expected {expected_size}, got {downloaded}")

            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "verify_apk.py"), str(target)],
                check=False,
            )
            if result.returncode:
                return result.returncode
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
        return fail(f"APK download failed: {error}")

    print(f"Published APK verified at {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
