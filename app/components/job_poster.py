import re
from playwright.async_api import Page

class JobPoster:
    """Navigates the employer dashboard to publish job circulars."""
    def __init__(self, page: Page):
        self.page = page

    async def navigate_to_post_job(self) -> bool:
        """Clicks the 'Post a New Job' button and waits for the form to load."""
        button_selector = "text='Post a New Job'"
        
        await self.page.wait_for_selector(button_selector, state="visible", timeout=15000)
        await self.page.locator(button_selector).first.click()
        
        await self.page.wait_for_load_state("networkidle")
        return True

    async def fill_step_1_basic_info(self, job_data: dict) -> bool:
        """Fills the initial text inputs for Step 1: Job Information."""
        title_input = "input[placeholder*='Enter Job Title']"
        vacancy_input = "input[placeholder*='Enter Vacancy No']"
        
        await self.page.wait_for_selector(title_input, state="visible", timeout=10000)
        await self.page.locator(title_input).first.fill(job_data["title"])
        
        if job_data.get("vacancies"):
            await self.page.locator(vacancy_input).first.fill(str(job_data["vacancies"]))
            
        return True

    async def fill_step_1_options(self, job_data: dict) -> bool:
        """Selects standard radio buttons and checkboxes based on their visible labels."""
        if status := job_data.get("employment_status"):
            await self.page.locator(f"label:has-text('{status}')").first.click()
            
        if workplace := job_data.get("workplace"):
            await self.page.locator(f"label:has-text('{workplace}')").first.click()
            
        return True

    async def fill_step_1_complex_fields(self, job_data: dict) -> bool:
        """Handles custom dropdowns and date pickers in Step 1."""
        
        # 1. Job Category Dropdown (Keyboard Strategy)
        if category := job_data.get("category"):
            dropdown_placeholder = "text='Choose a Job Category'"
            
            await self.page.locator(dropdown_placeholder).first.click(force=True)
            await self.page.wait_for_timeout(500)
            
            await self.page.keyboard.type(category, delay=100)
            
            await self.page.wait_for_timeout(1000)
            await self.page.keyboard.press("Enter")
            
        # 2. Select Deadline (Date Picker)
        if deadline := job_data.get("deadline"):
            deadline_input = "input[placeholder*='Select Deadline']"
            
            # Remove the 'readonly' attribute using JavaScript so Playwright can interact
            await self.page.locator(deadline_input).first.evaluate("el => el.removeAttribute('readonly')")
            
            # Fill the date and dispatch standard events
            await self.page.locator(deadline_input).first.fill(deadline)
            
            # Press Escape to dismiss the calendar popup
            await self.page.keyboard.press("Escape")
            
        return True

    async def proceed_to_next_step(self) -> bool:
        """Clicks the button to save the current step and advance the wizard."""
        
        # Target ANY element containing the text "Continue" or "Next", grabbing the last one
        continue_btn = self.page.get_by_text(re.compile("Continue|Next", re.IGNORECASE)).last
        
        # Scroll and force the click in case a sticky footer or chat widget is overlapping it
        await continue_btn.scroll_into_view_if_needed()
        await continue_btn.click(force=True)
        
        # Wait for the Step 2 UI to load and stabilize
        await self.page.wait_for_load_state("networkidle")
        await self.page.wait_for_timeout(2000)
        
        return True