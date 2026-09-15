# app/components/browser_manager.py
from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

from common.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class BrowserManager:
    """Manages the Playwright Chromium lifecycle."""

    def __init__(self, headless: bool | None = None):
        # None means "use whatever settings.HEADLESS says" - callers can
        # still force a value explicitly (e.g. a test that always wants
        # headless=True regardless of the .env).
        self.headless = settings.HEADLESS if headless is None else headless
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def initialize(self) -> BrowserContext:
        logger.info(f"Launching Chromium (headless={self.headless})...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": settings.VIEWPORT_WIDTH, "height": settings.VIEWPORT_HEIGHT},
            user_agent=settings.USER_AGENT,
        )
        return self._context

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("Browser context is not initialized. Call initialize() first.")
        page = await self._context.new_page()
        # Previously set ad hoc in main.py after every new_page() call;
        # centralized here so every page created by this manager gets it
        # automatically and the timeout itself is configurable via settings.
        page.set_default_timeout(settings.DEFAULT_TIMEOUT_MS)
        return page

    async def teardown(self):
        logger.info("Tearing down browser context/browser/playwright...")
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()