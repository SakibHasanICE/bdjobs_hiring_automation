# app/components/bdjobs_auth.py
from playwright.async_api import Page

class BDJobsAuth:
    """Handles BDJobs employer authentication."""
    def __init__(self, page: Page):
        self.page = page
        # Updated to the current recruiter portal URL
        self.login_url = "https://recruiter.bdjobs.com/"

    async def login(self, username: str, password: str) -> bool:
        await self.page.goto(self.login_url, timeout=30000)
        
        # Broadened selectors to catch the updated input fields
        username_selector = "input[name='username'], input[id='username'], input[type='text']"
        password_selector = "input[name='password'], input[id='password'], input[type='password']"
        submit_selector = "button[type='submit'], input[type='submit'], button:has-text('Sign In')"

        # Wait for form and input credentials
        await self.page.wait_for_selector(username_selector, state="visible", timeout=15000)
        
        # Use .first to ensure we only interact with the login inputs
        await self.page.locator(username_selector).first.fill(username)
        await self.page.locator(password_selector).first.fill(password)
        
        # Submit and wait for navigation
        await self.page.locator(submit_selector).first.click()
        await self.page.wait_for_load_state("networkidle")

        # Verify successful login by checking for the dashboard path
        if "dashboard" not in self.page.url.lower():
            raise PermissionError("Login failed. Verify credentials, check for CAPTCHA, or update selectors.")
        
        return True