"""Check community navigation and widget failure behavior without posting."""
import asyncio
from dataclasses import replace
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.async_api import async_playwright

from radar.community import load_community_config, render_paper_discussion


ROOT = Path(__file__).resolve().parents[1]


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/__widget_test':
            config = replace(load_community_config('lusknchars/ai-radar'), embedded=True)
            html = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                    '<link rel="stylesheet" href="/assets/site.css"></head><body>'
                    + render_paper_discussion(config, '2608.12345', '/assets/community.js')
                    + '</body></html>')
            body = html.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


async def verify(origin):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        for width in (390, 1440):
            page = await browser.new_page(viewport={'width': width, 'height': 1000}, reduced_motion='reduce')
            await page.goto(origin + '/community/')
            rows = page.locator('[data-paper]')
            count = await rows.count()
            assert count > 0
            await page.get_by_label('Find a paper').fill('2608.21223')
            assert await page.locator('[data-paper]:visible').count() == 1
            await page.get_by_label('Find a paper').fill('no-such-paper-unique')
            assert await page.locator('#community-empty').is_visible()
            await page.get_by_role('button', name='Clear search').click()
            assert await page.locator('[data-paper]:visible').count() == count
            assert await page.get_by_label('Find a paper').evaluate('el => el === document.activeElement')
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            logo = await page.locator('.publication-name').bounding_box()
            assert abs(logo['x'] + logo['width'] / 2 - width / 2) < 2
            await page.evaluate('window.scrollTo(0, 0)')
            await page.screenshot(path=f'/tmp/paperraft-community-{width}.png')
            await rows.first.locator('h3 a').click()
            assert await page.locator('#discussion').is_visible()
            await page.locator('#discussion').screenshot(path=f'/tmp/paperraft-discussion-{width}.png')
            requests = []
            async def block_widget(route):
                requests.append(route.request.url)
                await route.abort()
            await page.route('https://giscus.app/client.js', block_widget)
            await page.goto(origin + '/__widget_test')
            assert not requests
            await page.get_by_role('button', name='Load discussion').click()
            await page.get_by_text('The embedded discussion could not load.', exact=False).wait_for()
            assert len(requests) == 1
            script = page.locator('script[src="https://giscus.app/client.js"]')
            assert await script.get_attribute('data-term') == 'arXiv 2608.12345'
            assert await script.get_attribute('data-strict') == '1'
            assert await script.get_attribute('data-mapping') == 'specific'
            assert await page.get_by_role('link', name='Browse all discussions').is_visible()
            assert await page.get_by_role('button', name='Try loading again').is_enabled()
            await page.close()
        await browser.close()
    print('Community search, paper links, centered navigation and blocked-widget fallback passed on desktop/mobile.')


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(ROOT / 'dist')))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        asyncio.run(verify(f'http://127.0.0.1:{server.server_port}'))
    finally:
        server.shutdown()
        server.server_close()
