"""Browser smoke check against the generated 20-paper sample archive.

Install Playwright separately, run python -m radar.preview, then pass its URL. The default
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
            failed_resources = []
            page.on('response', lambda response: failed_resources.append(
                f'{response.status} {response.url}') if response.status >= 400 else None)
            page.goto(args.url, wait_until='networkidle')
            assert page.locator('.publication-name').inner_text() == 'Paperraft'
            assert page.locator('footer').count() == 1
            assert page.locator('[data-ascii-ripple]').count() == 0
            assert 'Paperraft' in page.title()
            newest = page.get_by_role('button', name='newest', exact=True)
            newest.focus()
            assert newest.evaluate('(el) => el.matches(":focus-visible")')
            assert newest.evaluate('(el) => parseFloat(getComputedStyle(el).outlineWidth)') >= 2
            assert newest.evaluate('(el) => getComputedStyle(el).transitionDuration') == '0s'
            page.emulate_media(reduced_motion='no-preference')
            assert newest.evaluate('(el) => getComputedStyle(el).transitionDuration') != '0s'
            page.emulate_media(reduced_motion='reduce')
            assert page.locator('.collection-status').count() == 0
            page.get_by_role('button', name='newest', exact=True).click()
            dates = page.locator('.paper-entry:visible').evaluate_all(
                '(rows) => rows.map(row => row.dataset.publicado)')
            assert dates == sorted(dates, reverse=True)
            search = page.get_by_role('searchbox', name='Search this index')
            search.fill('CommitKV')
            assert page.locator('.paper-entry:visible').count() == 1
            assert page.locator('#contador').inner_text() == '1 of 20'
            search.fill('')
            assert page.locator('.paper-entry:visible').count() == 20
            search.fill('not-a-real-research-topic-404')
            assert page.locator('.paper-entry:visible').count() == 0
            assert page.get_by_text('No papers match your search.', exact=True).is_visible()
            page.get_by_role('button', name='Clear search and filters').click()
            assert search.input_value() == ''
            assert page.locator('.paper-entry:visible').count() == 20
            assert search.evaluate('(element) => element === document.activeElement')
            search.fill('speculative decoding')
            assert page.locator('.paper-entry[data-familia="decodificacao_especulativa"]:visible').count() > 0
            search.fill('')
            assert page.locator('meta[property="og:image"]').get_attribute('content').endswith('/assets/social-card.png')
            for label in ('title', 'action'):
                entry = page.locator('.paper-entry:visible').first
                link = entry.locator('h3 a' if label == 'title' else '.entry-action .report-action')
                with page.expect_navigation() as navigation:
                    link.click()
                assert navigation.value.status == 200, page.url
                assert page.locator('h1').is_visible()
                assert page.locator('[data-content-kind="editorial-guidance"]').count() == 1
                assert not page.locator('#equations').get_attribute('open')
                page.locator('#equations summary').click()
                assert page.locator('#equations').evaluate('(element) => element.open')
                for article_width in (390, 1440):
                    page.set_viewport_size({'width': article_width, 'height': 900})
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(args.out / f'paper-{label}.png'), full_page=True)
                assert page.get_by_role('link', name='View page data (JSON)').is_visible()
                page.get_by_role('link', name='Back to research index', exact=False).click()
                assert page.locator('.paper-entry:visible').count() > 0
            for width in (390, 768, 1440):
                page.set_viewport_size({'width': width, 'height': 900})
                page.goto(args.url, wait_until='networkidle')
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                page.screenshot(path=str(args.out / f'archive-{width}.png'))
            assert not errors, errors
            assert not failed_resources, failed_resources
            paper_url = args.url.rstrip('/') + '/papers/2608.21223/'
            page.goto(paper_url, wait_until='networkidle')
            assert page.locator('.equation-display math').count() == 2
            assert page.locator('.equation-evidence').count() == 2
            assert page.locator('.research-signal').count() == 0
            assert page.locator('.research-signal-note').count() == 1
            exposures = page.locator('#exposure')
            assert exposures.locator('.exposure-item').count() == 8
            assert exposures.locator('[data-basis="source_linked"]').count() == 4
            assert exposures.locator('[data-basis="inferred"]').count() == 1
            assert exposures.locator('[data-basis="not_evaluated"]').count() == 3
            assert exposures.locator('.exposure-source').count() == 5
            source = exposures.locator('.exposure-source').first
            source.locator('summary').click()
            assert source.locator('blockquote').is_visible()
            assert source.locator('a').get_attribute('href') == 'https://arxiv.org/pdf/2608.21223v1#page=9'
            source.locator('summary').click()
            for width in (390, 1440):
                page.set_viewport_size({'width': width, 'height': 1000})
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), width
                page.locator('#equations').screenshot(path=str(args.out / f'equations-{width}.png'))
                exposures.screenshot(path=str(args.out / f'exposures-{width}.png'))
            assert not errors, errors
            assert not failed_resources, failed_resources
        finally:
            browser.close()
    print('Browser smoke check passed')


if __name__ == '__main__':
    main()
