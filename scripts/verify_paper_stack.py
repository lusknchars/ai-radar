"""Exercise paper previews and real skill downloads against a local build."""
import asyncio
import io
from pathlib import Path
from zipfile import ZipFile
from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        for width in (390, 1440):
            page = await browser.new_page(viewport={"width": width, "height": 1000}, reduced_motion="reduce")
            await page.goto("http://127.0.0.1:8778/papers/2608.21223/")
            lead = page.locator('.paper-lead-image img')
            await lead.scroll_into_view_if_needed()
            await page.wait_for_function("document.querySelector('.paper-lead-image img').naturalWidth > 0")
            assert (await lead.get_attribute('src')).endswith('/page-1.jpg')
            await page.locator('.article-opening').screenshot(path=f'/tmp/paperraft-opening-{width}.png')
            assert await page.locator('.skill-download').first.evaluate("el => getComputedStyle(el).backgroundImage.includes('linear-gradient')")
            stack = page.locator(".paper-stack")
            await stack.scroll_into_view_if_needed()
            await page.wait_for_function("Array.from(document.querySelectorAll('.paper-sheet')).every(i => i.complete && i.naturalWidth > 0)")
            await stack.click()
            assert await page.locator("[data-stack-status]").inner_text() == "Page 2 of 3"
            assert (await page.locator("[data-stack-source]").get_attribute("href")).endswith("#page=2")
            await stack.press("ArrowLeft")
            assert await page.locator("[data-stack-status]").inner_text() == "Page 1 of 3"
            await page.locator("[data-stack-prev]").click()
            assert await page.locator("[data-stack-status]").inner_text() == "Page 3 of 3"
            assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            await page.locator(".paper-preview").screenshot(path=f"/tmp/paperraft-preview-{width}.png")
            async with page.expect_download() as info:
                await page.locator(".research-actions .skill-download").click()
            download = await info.value
            with ZipFile(io.BytesIO(Path(await download.path()).read_bytes())) as archive:
                assert len(archive.namelist()) == 2
                assert any(name.endswith("SKILL.md") for name in archive.namelist())
            await page.goto("http://127.0.0.1:8778/")
            assert await page.locator(".paper-entry .skill-download").count() == 20
            assert await page.locator('.entry-cover img').count() == 20
            first = page.locator('.paper-entry:visible').first
            await first.scroll_into_view_if_needed()
            await page.wait_for_function("document.querySelector('.entry-cover img').naturalWidth > 0")
            await first.screenshot(path=f'/tmp/paperraft-entry-{width}.png')
            assert await page.locator('[data-ascii-ripple]').count() == 0
            assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            await page.close()
        await browser.close()
    print("Desktop/mobile previews, navigation, source links and ZIP downloads passed")


asyncio.run(main())
