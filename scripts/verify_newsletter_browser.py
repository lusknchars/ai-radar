"""Browser smoke check against the generated 20-paper sample archive.

Install Playwright separately, serve site/, then pass its URL. The default
browser executable is the macOS Chrome installation used during development.
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8766/')
    parser.add_argument('--browser', default='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    parser.add_argument('--out', type=Path, default=Path('/tmp/ai-radar-browser'))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=args.browser, headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000}, reduced_motion='reduce')
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(args.url, wait_until='networkidle')
            assert page.locator('[data-collection-mode="sample"]').is_visible()
            page.get_by_role('button', name='newest', exact=True).click()
            dates = page.locator('.paper-entry:visible').evaluate_all(
                '(rows) => rows.map(row => row.dataset.publicado)')
            assert dates == sorted(dates, reverse=True)
            page.get_by_role('searchbox').fill('CommitKV')
            assert page.locator('.paper-entry:visible').count() == 1
            assert page.locator('#contador').inner_text() == '1 of 20'
            page.get_by_role('searchbox').fill('')
            assert page.locator('.paper-entry:visible').count() == 20
            for width in (390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 900})
                page.goto(args.url, wait_until='networkidle')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                page.screenshot(path=str(args.out / f'archive-{width}.png'))
            assert not errors, errors
        finally:
            browser.close()
    print('Browser smoke check passed')


if __name__ == '__main__':
    main()
