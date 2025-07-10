# backend/browser.py
import asyncio
from playwright.async_api import async_playwright

async def launch_and_capture(url: str) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")
        img = await page.screenshot(type="png", full_page=True)
        await browser.close()
        return img
