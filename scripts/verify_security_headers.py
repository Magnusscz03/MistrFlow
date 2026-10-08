"""Read-only security-header check for a deployed MistrFlow site."""
import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

REQUIRED = {
    'strict-transport-security': 'max-age=',
    'x-content-type-options': 'nosniff',
    'x-frame-options': 'DENY',
    'referrer-policy': 'strict-origin-when-cross-origin',
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='https://mistrflow.vercel.app')
    args = parser.parse_args()
    failures = []

    for path in ('/', '/app', '/intake', '/download'):
        url = urljoin(args.base_url.rstrip('/') + '/', path.lstrip('/'))
        request = Request(url, headers={'User-Agent': 'MistrFlow-security-verifier/1.0'})
        try:
            with urlopen(request, timeout=20) as response:
                status = response.status
                headers = {key.lower(): value for key, value in response.headers.items()}
        except HTTPError as error:
            status = error.code
            headers = {key.lower(): value for key, value in error.headers.items()}
        except (URLError, TimeoutError) as error:
            failures.append(f'{path}: {error}')
            continue

        print(f'GET {path}: {status}')
        if status != 200:
            failures.append(f'{path}: expected 200, got {status}')
            continue
        for header, expected in REQUIRED.items():
            actual = headers.get(header, '')
            if expected not in actual:
                failures.append(f'{path}: {header} expected {expected!r}, got {actual!r}')

    service_worker_url = urljoin(args.base_url.rstrip('/') + '/', 'sw.js')
    request = Request(service_worker_url, headers={'User-Agent': 'MistrFlow-security-verifier/1.0'})
    try:
        with urlopen(request, timeout=20) as response:
            status = response.status
            cache_control = response.headers.get('Cache-Control', '')
        print(f'GET /sw.js: {status}')
        if status != 200:
            failures.append(f'/sw.js: expected 200, got {status}')
        if 'no-store' not in cache_control.lower():
            failures.append(f'/sw.js: Cache-Control must contain no-store, got {cache_control!r}')
    except (HTTPError, URLError, TimeoutError) as error:
        failures.append(f'/sw.js: {error}')

    for failure in failures:
        print('FAIL:', failure)
    if failures:
        print(f'{len(failures)} security-header checks failed.')
        return 1
    print('Security headers verified on all public entry points.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
