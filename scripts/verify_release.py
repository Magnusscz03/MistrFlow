"""Read-only release check. Run from any directory with Python 3."""
import hashlib
import json
import re
import struct
from ast import literal_eval
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
RELEASE = json.loads((ROOT / 'android-release.json').read_text())
errors = []
class Assets(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        values = [attrs.get('src')] if tag in ('script', 'img') else []
        if tag == 'link' and attrs.get('rel') in ('stylesheet', 'manifest', 'icon'):
            values.append(attrs.get('href'))
        for value in filter(None, values):
            url = urlsplit(value)
            if url.hostname and (url.hostname == 'floot.com' or url.hostname.endswith('.floot.app')):
                errors.append('External Floot dependency: ' + value)
            if value.startswith('/') and not value.startswith('//'):
                target = (DIST / unquote(url.path).lstrip('/')).resolve()
                if not target.is_relative_to(DIST.resolve()) or not target.is_file():
                    errors.append('Missing asset: ' + value)

for required in ('index.html', 'app/index.html', 'intake/index.html', 'download/index.html',
                 'connectivity.css', 'connectivity.js', 'icon-192.png', 'icon-512.png',
                 'icon-maskable-512.png', 'manifest.webmanifest', 'vercel.json'):
    if not (DIST / required).is_file():
        errors.append('Missing required file: ' + required)
for required in ('scripts/audit_supabase_security.sql',
                 'scripts/audit_supabase_data_api_access.sql'):
    if not (ROOT / required).is_file():
        errors.append('Missing required audit: ' + required)
pricing_migration = (ROOT / 'migrations/20261007_public_pricing.sql').read_text().upper()
if 'GRANT SELECT' not in pricing_migration or 'ON PUBLIC.PLAN_CATALOG TO ANON' not in pricing_migration:
    errors.append('Public pricing migration must explicitly grant SELECT to anon')
sales_migration = (ROOT / 'migrations/20261007_sales_inquiries.sql').read_text().upper()
if 'REVOKE ALL ON PUBLIC.SALES_INQUIRIES FROM ANON' not in sales_migration:
    errors.append('Sales inquiries migration must explicitly deny anon table access')
for page in DIST.rglob('*.html'):
    Assets().feed(page.read_text())
brand_assets = {
    'brand/mark.png': (96, 96),
    'brand/favicon.png': (48, 48),
    'brand/apple-touch-icon.png': (180, 180),
    'brand/mistrflow-profile.png': (1254, 1254),
}
for name, dimensions in brand_assets.items():
    path = DIST / name
    if not path.is_file():
        errors.append('Missing brand asset: ' + name)
        continue
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', data[16:24]) != dimensions:
        errors.append(f'Invalid brand asset dimensions: {name}, expected {dimensions[0]}x{dimensions[1]}')
for page in DIST.rglob('*.html'):
    relative = str(page.relative_to(DIST))
    html = page.read_text()
    for expected in (
        '/brand/brand.css',
        '/brand/favicon.png',
        '/brand/apple-touch-icon.png',
        'https://mistrflow.vercel.app/brand/mistrflow-profile.png',
    ):
        if expected not in html:
            errors.append(f'{relative}: missing brand reference {expected}')
brand_css = (DIST / 'brand/brand.css').read_text()
if ".brand span.logo" not in brand_css or "/brand/mark.png" not in brand_css:
    errors.append('Brand stylesheet does not connect the recovered app header to the new mark')
app_scripts = ''.join(path.read_text(errors='ignore') for path in
                      (DIST / '_next/static/restored-v1/chunks').glob('*.js'))
if 'className:"brand"' not in app_scripts:
    errors.append('Recovered application no longer renders the shared brand component')
for page_name in ('app/index.html', 'intake/index.html'):
    page_html = (DIST / page_name).read_text()
    for asset in ('/connectivity.css', '/connectivity.js'):
        if asset not in page_html:
            errors.append(f'{page_name}: missing {asset}')
download_html = (DIST / 'download/index.html').read_text()
for expected in (
    'MistrFlow ' + RELEASE['version_name'],
    RELEASE['sha256'],
    RELEASE['download_url'],
    'Máte verzi 0.1.0?',
    'odlišný podpis',
):
    if expected not in download_html:
        errors.append('Missing Android release information: ' + expected)
vercel = json.loads((DIST / 'vercel.json').read_text())
header_rules = {rule['source']: {item['key'].lower(): item['value'] for item in rule['headers']}
                for rule in vercel.get('headers', [])}
global_headers = header_rules.get('/(.*)', {})
for header, expected in {
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'strict-origin-when-cross-origin',
}.items():
    if global_headers.get(header) != expected:
        errors.append(f'vercel.json: missing security header {header}')
service_worker_headers = header_rules.get('/sw.js', {})
if service_worker_headers.get('cache-control') != 'no-store':
    errors.append('vercel.json: service worker must use Cache-Control no-store')
service_worker = (DIST / 'sw.js').read_text()
for required in ("request.method !== 'GET'", "request.mode === 'navigate'",
                 "url.origin !== self.location.origin", "ASSETS.includes(url.pathname)",
                 "mistrflow-shell-v13"):
    if required not in service_worker:
        errors.append('Unsafe or incomplete service worker guard: ' + required)
assets_match = re.search(r'const ASSETS = (\[[^;]+\]);', service_worker)
if not assets_match:
    errors.append('Service worker public asset allowlist is missing')
else:
    try:
        cached_assets = literal_eval(assets_match.group(1))
    except (SyntaxError, ValueError):
        cached_assets = []
        errors.append('Service worker public asset allowlist is invalid')
    for asset in cached_assets:
        if not isinstance(asset, str) or not asset.startswith('/') or asset.startswith(('/api/', '/app/', '/auth/')):
            errors.append('Service worker may cache private or invalid path: ' + repr(asset))
        elif not (DIST / asset.lstrip('/')).is_file():
            errors.append('Service worker references missing public asset: ' + asset)
webmanifest = json.loads((DIST / 'manifest.webmanifest').read_text())
for key, value in {'id': '/app', 'start_url': '/app', 'scope': '/', 'lang': 'cs', 'display': 'standalone'}.items():
    if webmanifest.get(key) != value:
        errors.append(f'Invalid PWA manifest field {key}: expected {value}')
expected_icons = {
    '/icon-192.png': ('192x192', 'any', (192, 192)),
    '/icon-512.png': ('512x512', 'any', (512, 512)),
    '/icon-maskable-512.png': ('512x512', 'maskable', (512, 512)),
}
manifest_icons = {icon.get('src'): icon for icon in webmanifest.get('icons', [])}
for src, (sizes, purpose, dimensions) in expected_icons.items():
    icon = manifest_icons.get(src)
    if not icon or icon.get('type') != 'image/png' or icon.get('sizes') != sizes or icon.get('purpose') != purpose:
        errors.append('Invalid PWA icon declaration: ' + src)
        continue
    data = (DIST / src.lstrip('/')).read_bytes()
    if len(data) < 24 or data[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', data[16:24]) != dimensions:
        errors.append('Invalid PWA icon dimensions: ' + src)
shortcut_urls = {shortcut.get('url') for shortcut in webmanifest.get('shortcuts', [])}
if shortcut_urls != {'/app', '/intake'}:
    errors.append('Invalid PWA shortcuts')
manifest = json.loads((ROOT / 'deployment-manifest.json').read_text())
actual = {str(p.relative_to(DIST)): p for p in DIST.rglob('*') if p.is_file()}
listed = {entry['file']: entry for entry in manifest['files']}
if actual.keys() != listed.keys():
    errors.append('Deployment manifest does not include exactly all dist files')
for name in actual.keys() & listed.keys():
    data = actual[name].read_bytes()
    if hashlib.sha1(data).hexdigest() != listed[name]['sha'] or len(data) != listed[name]['size']:
        errors.append('Manifest mismatch: ' + name)
for error in errors:
    print('FAIL:', error)
print(f'{len(actual)} files checked; {len(errors)} failures. Local package only; not a production or login test.')
raise SystemExit(bool(errors))
