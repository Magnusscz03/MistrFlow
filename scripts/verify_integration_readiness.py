"""Reject optimistic integration readiness and leaked backend errors."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER_BACKEND = ROOT / "backend/platform-owner-data/index.ts"


def scan(source: str) -> list[str]:
    failures: list[str] = []
    optimistic = re.compile(
        r"\b(?:const|let)\s+[A-Za-z0-9_]*(?:sender|secret|key|token|connected|present)"
        r"[A-Za-z0-9_]*\s*=\s*true\b",
        re.IGNORECASE,
    )
    if optimistic.search(source):
        failures.append("integration evidence must not be hard-coded to true")
    if re.search(r"return\s+json\s*\(\s*\{\s*error\s*:\s*[^}]*\.message", source):
        failures.append("internal exception messages must not be returned to clients")
    if 'console.error("platform-owner-data",e)' not in source:
        failures.append("owner backend must keep a server-side error log")
    if 'error:"Správu platformy nyní nelze načíst."' not in source:
        failures.append("owner backend must return the approved generic error")
    required_volai_gate = (
        'ready:volaiIntegration?.status==="connected"&&volaiApiKeyPresent&&'
        'volaiWebhookSecretPresent&&volaiSenderPresent&&activeVolaiRoutes.length>0'
    )
    if required_volai_gate not in source:
        failures.append("Volai readiness must require every connected-state signal")
    return failures


def main() -> int:
    try:
        source = OWNER_BACKEND.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"FAIL: cannot read {OWNER_BACKEND.relative_to(ROOT)}: {error}")
        return 1
    failures = scan(source)
    for failure in failures:
        print("FAIL:", failure)
    print(f"Owner integration readiness checked; {len(failures)} failures.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
