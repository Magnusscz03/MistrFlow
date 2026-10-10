"""Fail CI when tracked files contain high-confidence secret material."""

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 5_000_000

PATTERNS = (
    (
        "private key",
        re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
    ),
    (
        "GitHub token",
        re.compile(r"\bgh(?:p|o|u|s|r)_[A-Za-z0-9]{30,}\b"),
    ),
    (
        "Stripe secret",
        re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b"),
    ),
    (
        "Supabase secret key",
        re.compile(r"\bsb_secret_[A-Za-z0-9._-]{16,}\b"),
    ),
    (
        "OpenAI API key",
        re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    ),
    (
        "AWS access key",
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    ),
)

SENSITIVE_ASSIGNMENT = re.compile(
    r"""(?ix)
    \b(
        SUPABASE_SERVICE_ROLE_KEY|
        SUPABASE_SECRET_KEY|
        STRIPE_SECRET_KEY|
        STRIPE_WEBHOOK_SECRET|
        OPENAI_API_KEY|
        VOLAI_API_KEY|
        VERCEL_TOKEN|
        TWILIO_AUTH_TOKEN
    )\b
    \s*[:=]\s*
    ["']([^"'\r\n]{12,})["']
    """
)

JWT = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)

PLACEHOLDERS = (
    "example",
    "placeholder",
    "change_me",
    "changeme",
    "your_",
    "<",
    "$",
)


def line_number(text, offset):
    return text.count("\n", 0, offset) + 1


def is_placeholder(value):
    lowered = value.lower()
    return any(marker in lowered for marker in PLACEHOLDERS)


def jwt_role(token):
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded)
    except (ValueError, UnicodeError, json.JSONDecodeError):
        return None
    return data.get("role")


def scan_text(text):
    findings = []
    for label, pattern in PATTERNS:
        for match in pattern.finditer(text):
            findings.append((line_number(text, match.start()), label))

    for match in SENSITIVE_ASSIGNMENT.finditer(text):
        value = match.group(2)
        if not is_placeholder(value):
            findings.append(
                (
                    line_number(text, match.start()),
                    f"literal value assigned to {match.group(1)}",
                )
            )

    for match in JWT.finditer(text):
        if jwt_role(match.group(0)) == "service_role":
            findings.append(
                (line_number(text, match.start()), "Supabase service_role JWT")
            )
    return findings


def tracked_files():
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [
        ROOT / entry.decode("utf-8")
        for entry in result.stdout.split(b"\0")
        if entry
    ]


def main():
    findings = []
    checked = 0
    skipped = 0

    try:
        files = tracked_files()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as error:
        print(f"FAIL: cannot enumerate tracked files: {error}")
        return 1

    for path in files:
        try:
            data = path.read_bytes()
        except OSError as error:
            print(f"FAIL: cannot read {path.relative_to(ROOT)}: {error}")
            return 1
        if len(data) > MAX_TEXT_BYTES or b"\0" in data:
            skipped += 1
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue

        checked += 1
        for line, label in scan_text(text):
            findings.append((path.relative_to(ROOT), line, label))

    for path, line, label in findings:
        print(f"FAIL: {path}:{line}: detected {label}; value withheld")
    if findings:
        print(
            f"{len(findings)} potential secrets found; "
            "remove and rotate them before merging."
        )
        return 1

    print(
        f"{checked} tracked text files checked for high-confidence secrets; "
        f"{skipped} binary or oversized files skipped; 0 findings."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
