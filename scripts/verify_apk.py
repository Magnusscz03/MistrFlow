"""Verify the downloaded Android APK against the prepared release record."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from zipfile import BadZipFile, ZipFile

ROOT = Path(__file__).resolve().parents[1]
RELEASE = json.loads((ROOT / 'android-release.json').read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('apk', type=Path, help='path to the downloaded APK')
    args = parser.parse_args()
    errors = []

    if not args.apk.is_file():
        print('FAIL: APK file not found:', args.apk)
        return 1

    data = args.apk.read_bytes()
    if len(data) != RELEASE['size_bytes']:
        errors.append(f"size: expected {RELEASE['size_bytes']}, got {len(data)}")
    digest = hashlib.sha256(data).hexdigest()
    if digest != RELEASE['sha256']:
        errors.append(f"SHA-256: expected {RELEASE['sha256']}, got {digest}")

    try:
        with ZipFile(args.apk) as apk:
            config = json.loads(apk.read('assets/capacitor.config.json'))
    except (BadZipFile, KeyError, json.JSONDecodeError) as error:
        errors.append(f'Capacitor config: {error}')
        config = {}

    server = config.get('server', {})
    android = config.get('android', {})
    checks = (
        ('appId', config.get('appId'), RELEASE['app_id']),
        ('server.url', server.get('url'), RELEASE['server_url']),
        ('server.cleartext', server.get('cleartext'), False),
        ('android.allowMixedContent', android.get('allowMixedContent'), False),
    )
    for label, actual, expected in checks:
        if actual != expected:
            errors.append(f'{label}: expected {expected!r}, got {actual!r}')

    for error in errors:
        print('FAIL:', error)
    if errors:
        print(f'{len(errors)} APK checks failed; do not distribute this file.')
        return 1
    print(f"APK {RELEASE['version_name']} verified: {len(data)} bytes, {digest}")
    print(f"App {RELEASE['app_id']} loads {RELEASE['server_url']} over HTTPS without mixed content.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
