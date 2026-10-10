import re
from ast import literal_eval
from pathlib import Path
root=Path(__file__).resolve().parents[1]/'dist'
s=(root/'sw.js').read_text(encoding='utf-8')
assert "request.method !== 'GET'" in s
assert "request.mode === 'navigate'" in s
assert "url.origin !== self.location.origin" in s
assert "ASSETS.includes(url.pathname)" in s
assert "mistrflow-shell-v13" in s
match = re.search(r'const ASSETS = (\[[^;]+\]);', s)
assert match
assets = literal_eval(match.group(1))
assert assets
for asset in assets:
    assert isinstance(asset, str) and asset.startswith('/')
    assert not asset.startswith(('/api/', '/app/', '/auth/'))
    assert (root / asset.lstrip('/')).is_file()
print(f'PASS: service worker caches {len(assets)} public assets; no navigations, API or tenant data')
