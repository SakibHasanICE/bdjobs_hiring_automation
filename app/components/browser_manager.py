# app/components/browser_manager.py
import asyncio
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

class BrowserManager:
        """
        Manages the Playwright Chromium lifecycle as specified in the Phase 1 architecture.
        """
        def __init__(self, headless: bool = False):
            self.headless = headless
            self._playwright: Playwright | None = None
            self._browser: Browser | None = None
            self._context: BrowserContext | None = None

        async def initialize(self) -> BrowserContext:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"] 
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
            )
            return self._context

        async def new_page(self) -> Page:
            if not self._context:
                raise RuntimeError("Browser context is not initialized. Call initialize() first.")
            return await self._context.new_page()

        async def teardown(self):
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()