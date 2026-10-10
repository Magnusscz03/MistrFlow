"""Verify that deployable MistrFlow runtime uses only the intended Supabase project."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_REF = "dxpzqepbkkhcbpqmnokn"
EXPECTED_ORIGIN = f"https://{EXPECTED_REF}.supabase.co"
TEXT_SUFFIXES = {
    ".css", ".html", ".js", ".json", ".mjs", ".ts", ".tsx", ".webmanifest"
}
RUNTIME_ROOTS = (ROOT / "dist", ROOT / "backend", ROOT / "app")
ROOT_FILES = (ROOT / "vercel.json", ROOT / "android-release.json", ROOT / ".env.example")
SUPABASE_HOST = re.compile(r"https://([a-z0-9]{20})\.supabase\.co", re.IGNORECASE)
FLOOT_HOST = re.compile(
    r"https?://[^\s\"'<>]*(?:floot\.com|floot\.app)",
    re.IGNORECASE,
)

errors = []
checked = 0


def check_text(path: Path) -> None:
    global checked
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        errors.append(f"{path.relative_to(ROOT)}: deployable text file is not UTF-8")
        return
    checked += 1
    relative = path.relative_to(ROOT)
    for match in FLOOT_HOST.finditer(text):
        errors.append(f"{relative}: Floot runtime endpoint found: {match.group(0)}")
    for match in SUPABASE_HOST.finditer(text):
        ref = match.group(1).lower()
        if ref != EXPECTED_REF:
            errors.append(f"{relative}: foreign Supabase project reference: {ref}")


for runtime_root in RUNTIME_ROOTS:
    if not runtime_root.is_dir():
        errors.append(f"Missing runtime directory: {runtime_root.relative_to(ROOT)}")
        continue
    for candidate in runtime_root.rglob("*"):
        check_text(candidate)
for candidate in ROOT_FILES:
    if not candidate.is_file():
        errors.append(f"Missing runtime configuration: {candidate.relative_to(ROOT)}")
    else:
        check_text(candidate)

vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
rewrites = {item.get("source"): item.get("destination") for item in vercel.get("rewrites", [])}
expected_rewrites = {
    "/api/owner-ai": f"{EXPECTED_ORIGIN}/functions/v1/owner-ai",
    "/supabase/functions/v1/:path*": f"{EXPECTED_ORIGIN}/functions/v1/:path*",
}
for source, destination in expected_rewrites.items():
    if rewrites.get(source) != destination:
        errors.append(
            f"vercel.json: {source} must target {destination}, got {rewrites.get(source)!r}"
        )

android = json.loads((ROOT / "android-release.json").read_text(encoding="utf-8"))
download_url = str(android.get("download_url", ""))
if not download_url.startswith(f"{EXPECTED_ORIGIN}/storage/v1/object/"):
    errors.append("android-release.json: download_url must use the intended Supabase Storage")

for error in errors:
    print("FAIL:", error)
print(
    f"{checked} runtime text files checked; expected Supabase project {EXPECTED_REF}; "
    f"{len(errors)} failures."
)
raise SystemExit(bool(errors))
