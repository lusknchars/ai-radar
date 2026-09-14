"""Verify cross-page search, query links, filters, and responsive search controls."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def verify_beam(page, engine):
    field = page.locator('.paper-search')
    border = field.locator('.beam-border')
    assert border.evaluate('el => getComputedStyle(el).animationName') == 'none'
    assert border.evaluate('el => getComputedStyle(el).pointerEvents') == 'none'
    # The decoration must not intercept padding clicks or cover keyboard focus.
    field.click(position={'x': 4, 'y': field.bounding_box()['height'] / 2})
    assert field.locator('input').evaluate('el => el === document.activeElement')
    # macOS WebKit includes buttons in the Option+Tab traversal.
    page.keyboard.press('Alt+Tab' if engine == 'webkit' else 'Tab')
    button = field.locator('button')
    assert button.evaluate('el => el === document.activeElement')
    assert button.locator('.beam-arrow').evaluate('el => getComputedStyle(el).opacity') == '1'
    assert button.evaluate('el => parseFloat(getComputedStyle(el).outlineWidth)') >= 2
    page.emulate_media(reduced_motion='no-preference')
    assert border.evaluate('el => getComputedStyle(el).animationDuration') == '5s'
    before = border.evaluate('el => getComputedStyle(el).backgroundImage')
    page.wait_for_function(
        "before => getComputedStyle(document.querySelector('.paper-search .beam-border')).backgroundImage !== before",
        arg=before)
    assert border.evaluate('el => getComputedStyle(el).maskImage') != 'none'
    page.emulate_media(reduced_motion='reduce')
    assert border.evaluate('el => getComputedStyle(el).animationName') == 'none'
    assert button.locator('.beam-arrow').evaluate('el => getComputedStyle(el).transitionDuration') == '0s'


def verify(origin, engine):
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch(**(
            {'executable_path': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}
            if engine == 'chromium' else {}))
        for width in (360, 768, 1440):
            page = browser.new_page(viewport={'width': width, 'height': 1000},
                                    reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin)
            entries = page.locator('.paper-entry')
            total = entries.count()
            paper = entries.last
            paper_id = paper.get_attribute('data-id')
            paper_url = paper.locator('h3 a').get_attribute('href')
            page.goto(origin + paper_url)
            search = page.get_by_role('searchbox', name='Search all papers')
            search.fill(paper_id)
            search.press('Enter')
            page.wait_for_url('**/?q=*#acervo')
            assert page.locator('.paper-entry:visible').count() == 1
            assert page.locator('.paper-entry:visible').get_attribute('data-id') == paper_id
            local = page.get_by_role('searchbox', name='Search this index')
            assert local.input_value() == paper_id
            assert page.locator('#contador').inner_text() == f'1 of {total}'
            page.reload()
            assert page.locator('.paper-entry:visible').count() == 1
            family = page.locator('.paper-entry:visible').get_attribute('data-familia')
            local.fill('')
            page.locator('#f-familia').select_option(family)
            filtered = page.locator('.paper-entry:visible').count()
            assert filtered > 0
            local.fill(paper_id)
            assert page.locator('.paper-entry:visible').count() == 1
            page.locator('#f-familia').select_option('')
            local.fill('CACHE    kv')
            assert page.locator('.paper-entry:visible').count() > 0
            local.fill('cáché kv')
            assert page.locator('.paper-entry:visible').count() > 0
            query = '<script>alert("paper")</script> & impossible-paper-404'
            local.fill(query)
            page.wait_for_url(lambda url: parse_qs(urlsplit(url).query).get('q') == [query])
            assert parse_qs(urlsplit(page.url).query)['q'] == [query]
            page.reload()
            assert page.locator('.paper-entry:visible').count() == 0
            assert page.get_by_text('No papers match your search.', exact=True).is_visible()
            page.get_by_role('button', name='Clear search and filters').click()
            page.wait_for_url(lambda url: 'q' not in parse_qs(urlsplit(url).query))
            assert local.input_value() == ''
            assert search.input_value() == ''
            assert 'q' not in parse_qs(urlsplit(page.url).query)
            assert page.locator('.paper-entry:visible').count() > 0
            assert local.evaluate('el => el === document.activeElement')
            page.goto(origin + '/about.html')
            search.fill(paper_id)
            page.get_by_role('button', name='Search', exact=True).click()
            page.wait_for_url('**/?q=*#acervo')
            assert page.locator('.paper-entry:visible').count() == 1
            page.evaluate('window.scrollTo(0, 0)')
            page.evaluate('document.fonts.ready')
            box = page.locator('.paper-search').bounding_box()
            assert abs(box['x'] + box['width'] / 2 - width / 2) < 2
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            verify_beam(page, engine)
            page.screenshot(path=f'/tmp/paperraft-search-{engine}-{width}.png')
            assert not errors, errors
            page.close()
        browser.close()
    print(f'{engine}: search and beam animation passed at 360, 768, and 1440px, including reduced motion and keyboard focus.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin')
    parser.add_argument('--browser', choices=('chromium', 'webkit'), default='chromium')
    args = parser.parse_args()
    server = None
    try:
        if not args.origin:
            server = ThreadingHTTPServer(('127.0.0.1', 0),
                                         partial(Handler, directory=str(ROOT / 'dist')))
            Thread(target=server.serve_forever, daemon=True).start()
        verify(args.origin or f'http://127.0.0.1:{server.server_port}', args.browser)
    finally:
        if server:
            server.shutdown()
            server.server_close()
