# app/components/bdjobs_auth.py
from playwright.async_api import Page

from common.custom_exception import CustomException
from common.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class BDJobsAuth:
    """Handles BDJobs employer authentication."""

    def __init__(self, page: Page):
        self.page = page
        self.login_url = settings.BDJOBS_LOGIN_URL

    async def login(self, username: str, password: str) -> bool:
        logger.info(f"Navigating to {self.login_url} ...")
        await self.page.goto(self.login_url, timeout=30000)

        # Broadened selectors to catch the updated input fields
        username_selector = "input[name='username'], input[id='username'], input[type='text']"
        password_selector = "input[name='password'], input[id='password'], input[type='password']"
        submit_selector = "button[type='submit'], input[type='submit'], button:has-text('Sign In')"

        try:
            await self.page.wait_for_selector(username_selector, state="visible", timeout=15000)

            # Use .first to ensure we only interact with the login inputs
            await self.page.locator(username_selector).first.fill(username)
            await self.page.locator(password_selector).first.fill(password)

            await self.page.locator(submit_selector).first.click()
            await self.page.wait_for_load_state("networkidle")
        except Exception as e:
            raise CustomException("BDJobs login form interaction failed", e) from e

        # Verify successful login by checking for the dashboard path
        if "dashboard" not in self.page.url.lower():
            raise CustomException(
                "Login failed. Verify credentials, check for CAPTCHA, or update selectors.",
                PermissionError(f"Landed on unexpected URL: {self.page.url}"),
            )

        logger.info("Login successful.")
        return True