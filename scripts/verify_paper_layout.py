"""Check paper reading columns and controls in a real browser.

Run after build_vercel.py. Set --origin to check a deployed copy instead.
Screenshots are saved outside the repository for visual review.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def sample_papers():
    pages = sorted((ROOT / 'dist' / 'papers').glob('*/index.html'))
    assert pages, 'Build the static site first.'
    samples = [pages[0]]
    for marker in ('class="paper-lead-image"', 'class="equation-display"',
                   'class="exposure-source"'):
        match = next((page for page in pages if marker in page.read_text()), None)
        if match and match not in samples:
            samples.append(match)
    without_image = next((page for page in pages
                          if 'class="paper-lead-image"' not in page.read_text()), None)
    if without_image and without_image not in samples:
        samples.append(without_image)
    for page in pages:
        if 'class="benchmark-reading"' in page.read_text() and page not in samples:
            samples.append(page)
    return samples


def verify(origin, screenshots):
    screenshots.mkdir(parents=True, exist_ok=True)
    samples = sample_papers()
    with sync_playwright() as playwright:
        local_chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        browser = playwright.chromium.launch(
            **({'executable_path': str(local_chrome)} if local_chrome.exists() else {}))
        for width in (360, 768, 1024, 1440):
            page = browser.new_page(viewport={'width': width, 'height': 1000},
                                    reduced_motion='reduce')
            for paper in samples:
                response = page.goto(f'{origin}/papers/{paper.parent.name}/')
                assert response.status == 200
                page.evaluate('document.fonts.ready')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (
                    paper.parent.name, width, 'Page overflows horizontally')
                for selector in ('.article-masthead', '.article-page', '.research-page',
                                 '.research-section', '#discussion'):
                    for element in page.locator(selector).all():
                        box = element.bounding_box()
                        assert abs(box['x'] + box['width'] / 2 - width / 2) < 2, (
                            paper.parent.name, width, selector, box)
                for heading in page.locator('.research-section>.section-head').all():
                    title = heading.locator('h2').bounding_box()
                    description = heading.locator('.sub').bounding_box()
                    assert description['y'] >= title['y'] + title['height'] - 1
                assert page.locator('.skill-download').first.get_attribute('href').endswith('.zip')
                plan_link = page.locator('#try-it a[download]')
                assert plan_link.count() == 1
                plan = page.request.get(origin + plan_link.get_attribute('href'))
                assert plan.status == 200 and '## Record your result' in plan.text()
                assert 'No Paperraft experiment has been run' in plan.text()
                if page.locator('#benchmark-reading').count() and width in (360, 1440):
                    page.locator('#benchmark-reading').screenshot(
                        path=str(screenshots / f'benchmarks-{paper.parent.name}-{width}.png'))
                if page.locator('[data-paper-stack]').count():
                    page.locator('[data-stack-next]').click()
                    assert 'Page 2' in page.locator('[data-stack-status]').inner_text()
                if paper == samples[0] and width in (360, 1440):
                    page.evaluate('window.scrollTo(0, 0)')
                    page.screenshot(path=str(screenshots / f'opening-{width}.png'))
                    page.locator('#claims').scroll_into_view_if_needed()
                    page.screenshot(path=str(screenshots / f'claims-{width}.png'))
                    page.locator('#exposure').screenshot(path=str(screenshots / f'exposure-{width}.png'))
            page.close()
        browser.close()
    print(f'Centered article layout and paper controls passed for {len(samples)} papers at 4 widths.')
    print(f'Screenshots: {screenshots}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin')
    parser.add_argument('--screenshots', type=Path, default=Path('/tmp/paperraft-centered-layout'))
    args = parser.parse_args()
    server = None
    try:
        if not args.origin:
            server = ThreadingHTTPServer(('127.0.0.1', 0),
                                         partial(Handler, directory=str(ROOT / 'dist')))
            Thread(target=server.serve_forever, daemon=True).start()
        verify(args.origin or f'http://127.0.0.1:{server.server_port}', args.screenshots)
    finally:
        if server:
            server.shutdown()
            server.server_close()
