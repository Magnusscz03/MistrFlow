"""Static safety checks for versioned Supabase SQL migrations."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


IDENTIFIER = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'
CREATE_TABLE = re.compile(
    rf"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?public\.({IDENTIFIER})",
    re.IGNORECASE,
)
CREATE_ROUTINE = re.compile(
    rf"\bCREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+"
    rf"(?:(public)\.)?({IDENTIFIER})",
    re.IGNORECASE,
)
CREATE_POLICY = re.compile(r"\bCREATE\s+POLICY\b.*?;", re.IGNORECASE | re.DOTALL)


def strip_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def plain_identifier(identifier: str) -> str:
    return identifier.strip('"').lower()


def role_decision(sql: str, table: str, role: str) -> bool:
    pattern = rf"\b(?:GRANT|REVOKE)\b[^;]*\bON\s+(?:TABLE\s+)?public\.{re.escape(table)}\b[^;]*\b(?:TO|FROM)\s+[^;]*\b{role}\b"
    return re.search(pattern, sql, re.IGNORECASE) is not None


def check_sql(path: Path, sql: str) -> list[str]:
    cleaned = strip_comments(sql)
    failures: list[str] = []

    for match in CREATE_TABLE.finditer(cleaned):
        table = plain_identifier(match.group(1))
        escaped = re.escape(table)
        rls = rf"\bALTER\s+TABLE\s+(?:ONLY\s+)?public\.{escaped}\s+ENABLE\s+ROW\s+LEVEL\s+SECURITY\b"
        if re.search(rls, cleaned, re.IGNORECASE) is None:
            failures.append(f"{path}: public.{table} is created without ENABLE ROW LEVEL SECURITY")
        for role in ("anon", "authenticated"):
            if not role_decision(cleaned, table, role):
                failures.append(
                    f"{path}: public.{table} has no explicit GRANT or REVOKE for {role}"
                )

    lowered = cleaned.lower()
    if re.search(r"\bauth\.role\s*\(", cleaned, re.IGNORECASE):
        failures.append(f"{path}: auth.role() is deprecated; use policy TO clauses")
    for unsafe_claim in ("raw_user_meta_data", "user_metadata"):
        if unsafe_claim in lowered:
            failures.append(
                f"{path}: {unsafe_claim} must not be used for database authorization"
            )

    routines = list(CREATE_ROUTINE.finditer(cleaned))
    for index, routine in enumerate(routines):
        end = routines[index + 1].start() if index + 1 < len(routines) else len(cleaned)
        definition = cleaned[routine.start() : end]
        if routine.group(1) and re.search(r"\bSECURITY\s+DEFINER\b", definition, re.IGNORECASE):
            name = plain_identifier(routine.group(2))
            failures.append(
                f"{path}: public.{name} is SECURITY DEFINER in an exposed schema"
            )

    for policy_match in CREATE_POLICY.finditer(cleaned):
        policy = policy_match.group(0)
        action_match = re.search(
            r"\bFOR\s+(ALL|SELECT|INSERT|UPDATE|DELETE)\b", policy, re.IGNORECASE
        )
        action = action_match.group(1).upper() if action_match else "ALL"
        has_using = re.search(r"\bUSING\s*\(", policy, re.IGNORECASE) is not None
        has_check = re.search(r"\bWITH\s+CHECK\s*\(", policy, re.IGNORECASE) is not None
        if action in {"ALL", "SELECT", "UPDATE", "DELETE"} and not has_using:
            failures.append(f"{path}: {action} policy is missing USING")
        if action in {"ALL", "INSERT", "UPDATE"} and not has_check:
            failures.append(f"{path}: {action} policy is missing WITH CHECK")

    return failures


def verify(root: Path) -> tuple[int, list[str]]:
    migration_dir = root / "migrations"
    files = sorted(migration_dir.glob("*.sql")) if migration_dir.is_dir() else []
    if not files:
        return 0, [f"{migration_dir}: no SQL migrations found"]
    failures: list[str] = []
    for path in files:
        try:
            sql = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"{path}: migration is not UTF-8")
            continue
        failures.extend(check_sql(path.relative_to(root), sql))
    return len(files), failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    checked, failures = verify(args.root.resolve())
    for failure in failures:
        print("FAIL:", failure)
    print(f"{checked} Supabase migration files checked; {len(failures)} failures.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
