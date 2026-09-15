# app/services/job_posting_service.py
from typing import Optional

from playwright.async_api import Page

from common.custom_exception import CustomException
from common.logger import get_logger
from components.bdjobs_auth import BDJobsAuth
from components.browser_manager import BrowserManager
from components.job_poster import JobPoster
from config.settings import settings
from models.job_posting import JobPosting

logger = get_logger(__name__)


class JobPostingService:
    """Orchestrates the end-to-end 'log in, fill the multi-step bdjobs form,
    save as draft' workflow.

    This replaces the test_workflow() coroutine that used to live directly
    in main.py: main.py should now just build a JobPosting and call
    `post_job()`, with all wiring/orchestration living here instead.
    """

    def __init__(self, browser_manager: Optional[BrowserManager] = None):
        self.browser_manager = browser_manager or BrowserManager()

    async def post_job(self, job: JobPosting) -> bool:
        job_data = job.to_legacy_dict()
        page: Optional[Page] = None

        try:
            await self.browser_manager.initialize()
            page = await self.browser_manager.new_page()

            auth = BDJobsAuth(page)
            await auth.login(settings.BDJOBS_USER, settings.BDJOBS_PASS)

            poster = JobPoster(page)
            await poster.navigate_to_post_job()

            await self._fill_step_1(poster, job_data, page)

            logger.info("Advancing to Step 2...")
            await poster.proceed_to_next_step(wait_for_text="Preferred Gender")
            logger.info("Filling Step 2: Candidate Requirements...")
            await poster.fill_step_2_candidate_requirements(job_data)

            logger.info("Advancing to Step 3...")
            await poster.proceed_to_next_step(wait_for_text="Applicant Restriction")
            logger.info("Filling Step 3: Matching & Restrictions...")
            await poster.fill_step_3_matching_restrictions(job_data)

            logger.info("Advancing to Step 4...")
            await poster.proceed_to_next_step(wait_for_text="Related Recruitment/HR person")
            logger.info("Filling Step 4: Recruitment/HR Contact Person...")
            await poster.fill_step_4_contact_persons(job_data)

            logger.info("Saving job posting as draft...")
            await poster.save_as_draft()
            logger.info("Saved as draft. Workflow complete.")
            return True

        except Exception as e:
            logger.error(f"Job posting workflow failed: {e}")
            if page is not None:
                try:
                    await page.screenshot(path="error_state.png", full_page=True)
                    logger.info("Saved failure screenshot to error_state.png")
                except Exception:
                    pass
            raise CustomException("JobPostingService.post_job failed", e) from e

        finally:
            await self.browser_manager.teardown()

    @staticmethod
    async def _fill_step_1(poster: JobPoster, job_data: dict, page: Page) -> None:
        """Each Step 1 sub-group is attempted independently: if one throws,
        it's logged with its own screenshot, and the rest still run -
        instead of one bad locator silently cancelling everything downstream.
        """
        step_sequence = [
            ("Basic Info", poster.fill_step_1_basic_info),
            ("Options", poster.fill_step_1_options),
            ("Complex Fields (Category/Location/Deadline)", poster.fill_step_1_complex_fields),
            ("Details (Responsibilities & Salary)", poster.fill_step_1_details),
            ("Compensation & Benefits", poster.fill_compensation_and_benefits),
        ]

        for step_name, step_fn in step_sequence:
            try:
                logger.info(f"Filling: {step_name}...")
                await step_fn(job_data)
                logger.info(f"Done: {step_name}")
            except Exception as step_error:
                logger.error(f"Step FAILED ({step_name}): {step_error}")
                safe_name = step_name.split(" ")[0].lower()
                await page.screenshot(path=f"error_{safe_name}.png", full_page=True)
                logger.info(f"Saved screenshot: error_{safe_name}.png")

        logger.info("Finished attempting all Step 1 fields (see log above for any failures).")