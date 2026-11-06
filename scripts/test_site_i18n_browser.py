"""Isolated institutional-site language QA. All requests use local files or are blocked."""
from pathlib import Path
from urllib.parse import urlparse
import argparse
import json
import mimetypes
import re
import os
import tempfile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DEFAULT_PUBLIC = next((path for path in (ROOT / 'candidate/public', ROOT / 'public', ROOT.parent / 'public') if path.is_dir()), ROOT.parent / 'public')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--public-dir', type=Path, default=DEFAULT_PUBLIC)
parser.add_argument('--output-dir', type=Path)
parser.add_argument('--browser-executable', default=os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE'))
args = parser.parse_args()
PUBLIC = args.public_dir.resolve()
OUT = (args.output_dir or Path(tempfile.mkdtemp(prefix='institutional-i18n-ui-'))).resolve()
OUT.mkdir(parents=True, exist_ok=True)
BASE = 'https://www.haralabs.com.br'
PAGES = sorted('/' if f.relative_to(PUBLIC).as_posix() == 'index.html' else
               '/' + f.relative_to(PUBLIC).as_posix().removesuffix('index.html')
               for f in PUBLIC.rglob('*.html'))
checks, errors, missing = [], [], []


def passed(name, detail=None):
    checks.append({'check': name, 'state': 'PASS', 'detail': detail})
    print('PASS', name, json.dumps(detail, ensure_ascii=False) if detail is not None else '', flush=True)


def make_page(browser, *, locale='pt-BR', blocked_storage=False):
    context = browser.new_context(locale=locale, viewport={'width': 1440, 'height': 1000})
    if blocked_storage:
        context.add_init_script("Object.defineProperty(window, 'localStorage', {get(){throw new DOMException('Disabled', 'SecurityError')}})")
    page = context.new_page()
    requests = []
    page.on('pageerror', lambda e: errors.append({'url': page.url, 'error': str(e)}))

    def handle(route):
        request = route.request
        parsed = urlparse(request.url)
        requests.append({'method': request.method, 'url': request.url})
        if request.method not in ('GET', 'HEAD'):
            errors.append({'url': request.url, 'error': 'Unexpected mutation ' + request.method})
            return route.abort()
        if parsed.netloc not in ('www.haralabs.com.br', 'haralabs.com.br'):
            return route.abort()
        if parsed.path == '/api/observabilidade/status':
            from datetime import datetime, timezone
            payload = json.loads((PUBLIC / 'observabilidade/status.json').read_text())
            payload['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
            return route.fulfill(status=200, content_type='application/json', body=json.dumps(payload))
        relative = parsed.path.lstrip('/') or 'index.html'
        target = (PUBLIC / relative).resolve()
        if target.is_dir():
            target /= 'index.html'
        if PUBLIC not in target.parents or not target.is_file():
            missing.append(request.url)
            return route.fulfill(status=404, body='Not found in isolated fixture')
        content_type = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if target.suffix == '.js':
            content_type = 'application/javascript'
        return route.fulfill(status=200, content_type=content_type, body=target.read_bytes())

    page.route('**/*', handle)
    return context, page, requests


def ready(page, path='/'):
    page.goto(BASE + path, wait_until='networkidle')
    page.locator('.language-switch').wait_for(state='visible')


def check_header(page, width):
    page.set_viewport_size({'width': width, 'height': 1000 if width > 760 else 844})
    page.wait_for_timeout(50)
    assert page.evaluate("document.querySelector('.neon-toggle').nextElementSibling.matches('.language-switch')")
    group = page.locator('.language-switch')
    assert group.get_attribute('role') == 'group'
    assert group.get_attribute('aria-label')
    neon = page.locator('.neon-toggle').bounding_box()
    language = group.bounding_box()
    assert neon and language, {'neon': neon, 'language': language}
    assert language['x'] >= neon['x'] + neon['width'] - 1, {'width': width, 'neon': neon, 'language': language}
    assert abs((language['y'] + language['height']/2) - (neon['y'] + neon['height']/2)) <= 3, {'width': width, 'neon': neon, 'language': language}
    assert language['x'] >= 0 and language['x'] + language['width'] <= width + 1, {'width': width, 'language': language}
    for code in ('pt', 'en'):
        button = page.locator('[data-set-language="' + code + '"]')
        assert button.get_attribute('type') == 'button'
        assert button.get_attribute('lang').startswith(code)
        assert button.get_attribute('aria-pressed') in ('true', 'false')
    return {'width': width, 'neon': neon, 'language': language}


with sync_playwright() as p:
    launch_options = {'headless': True}
    if args.browser_executable:
        launch_options['executable_path'] = args.browser_executable
    browser = p.chromium.launch(**launch_options)
    try:
        context, page, requests = make_page(browser)
        ready(page, '/?lang=pt')
        assert page.locator('html').get_attribute('lang') == 'pt-BR'
        before_text = page.locator('main').inner_text()
        before = len(requests)
        page.locator('.neon-toggle').focus()
        page.keyboard.press('Tab')
        assert page.locator('[data-set-language="pt"]').evaluate('(n) => document.activeElement === n')
        page.keyboard.press('Tab')
        assert page.locator('[data-set-language="en"]').evaluate('(n) => document.activeElement === n')
        page.keyboard.press('Enter')
        assert page.locator('html').get_attribute('lang') == 'en-US'
        assert page.locator('main').inner_text() != before_text
        assert page.locator('[data-set-language="en"]').get_attribute('aria-pressed') == 'true'
        assert page.locator('[data-set-language="pt"]').get_attribute('aria-pressed') == 'false'
        assert page.evaluate("localStorage.getItem('hara-language')") == 'en'
        assert len(requests) == before, requests[before:]
        passed('Keyboard order, Enter, ARIA state and no language-switch requests')
        page.reload(wait_until='networkidle')
        assert page.locator('html').get_attribute('lang') == 'en-US'
        passed('English persists after reload')
        page.locator('.main-nav a[href*="/solucoes/"]').click()
        page.wait_for_url(re.compile(r'/solucoes/(?:\?.*)?$'))
        page.wait_for_load_state('networkidle')
        assert page.locator('html').get_attribute('lang') == 'en-US'
        passed('An actual navigation link preserves English')

        for path in PAGES:
            ready(page, path)
            assert page.locator('html').get_attribute('lang') == 'en-US', (path, page.url)
            assert page.locator('[data-set-language="en"]').get_attribute('aria-pressed') == 'true', path
            assert page.locator('.main-nav').inner_text().strip() and not re.search(r'\b(Soluções|Arquitetura|Segurança|Produtos|Empresa)\b', page.locator('.main-nav').inner_text()), path
            title_en = page.title()
            text_en = page.locator('main').inner_text()
            literal_before = page.locator('pre, code').all_text_contents()
            contacts_before = page.locator('a[href^="mailto:"], a[href^="tel:"]').evaluate_all('(nodes) => nodes.map(n => n.getAttribute("href"))')
            before = len(requests)
            page.locator('[data-set-language="pt"]').click()
            assert page.locator('html').get_attribute('lang') == 'pt-BR'
            text_pt = page.locator('main').inner_text()
            assert text_pt != text_en, path
            page.locator('[data-set-language="en"]').click()
            assert page.locator('html').get_attribute('lang') == 'en-US'
            assert page.title() == title_en
            assert page.locator('pre, code').all_text_contents() == literal_before, path
            assert page.locator('a[href^="mailto:"], a[href^="tel:"]').evaluate_all('(nodes) => nodes.map(n => n.getAttribute("href"))') == contacts_before, path
            assert len(requests) == before, requests[before:]
            boxes = [check_header(page, width) for width in (1440, 390, 320)]
            if path in ('/', '/legal/termos/', '/contato/'):
                name = 'home' if path == '/' else path.strip('/').replace('/', '-')
                page.screenshot(path=str(OUT / (name + '-mobile-en.png')))
                page.set_viewport_size({'width': 1440, 'height': 1000})
                page.screenshot(path=str(OUT / (name + '-desktop-en.png')))
            passed('Page locale, translations, selector placement and responsive layout: ' + path,
                   {'resolved_path': urlparse(page.url).path, 'title': title_en, 'viewports': boxes})
        context.close()

        context, page, requests = make_page(browser, locale='en-US')
        ready(page)
        assert page.locator('html').get_attribute('lang') == 'en-US'
        ready(page, '/?lang=pt')
        assert page.locator('html').get_attribute('lang') == 'pt-BR'
        assert page.evaluate("localStorage.getItem('hara-language')") == 'pt'
        ready(page, '/empresa/')
        assert page.locator('html').get_attribute('lang') == 'pt-BR'
        passed('Browser preference, explicit URL override and Portuguese navigation persistence')
        context.close()

        context, page, requests = make_page(browser, locale='es-ES', blocked_storage=True)
        ready(page, '/?lang=invalid')
        assert page.locator('html').get_attribute('lang') == 'pt-BR'
        page.locator('[data-set-language="en"]').click()
        assert page.locator('html').get_attribute('lang') == 'en-US'
        passed('Unavailable storage and unsupported locale are handled')
        context.close()
    finally:
        browser.close()

assert not errors, errors
missing_code = [url for url in missing if urlparse(url).path.endswith(('.js', '.css', '.html'))]
assert not missing_code, missing_code
passed('No JavaScript exceptions, mutations or missing local code assets')
result = {'state': 'PASS', 'scope': 'isolated headless browser with all requests intercepted', 'pages': PAGES,
          'checks': checks, 'browser_errors': errors, 'missing_local_assets': sorted(set(missing))}
(OUT / 'institutional-i18n-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print('INSTITUTIONAL_I18N_BROWSER=PASS', len(checks), flush=True)
print('ARTIFACTS=' + str(OUT), flush=True)
