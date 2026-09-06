import asyncio
import os
from dotenv import load_dotenv
from components.browser_manager import BrowserManager
from components.bdjobs_auth import BDJobsAuth
from components.job_poster import JobPoster

load_dotenv()

async def test_workflow():
    manager = BrowserManager(headless=False)
    
    try:
        await manager.initialize()
        page = await manager.new_page()
        
        # Extends the default global timeout to 60 seconds to prevent early failures on slow connections
        page.set_default_timeout(60000)
        
        auth = BDJobsAuth(page)
        username = os.getenv("BDJOBS_USER")
        password = os.getenv("BDJOBS_PASS")
        
        await auth.login(username, password)
        print("Login successful. Navigating to job posting form...")
        
        poster = JobPoster(page)
        await poster.navigate_to_post_job()
        
        print("Filling Step 1: Job Information...")
        mock_internal_job = {
            "job_id": "JOB-2026-00128",
            "title": "Software Engineer (AI/ML)",
            "vacancies": 2,
            "employment_status": "Full Time",
            "workplace": "Work From Office",
            "category": "IT & Telecommunication",
            "deadline": "10/30/2026"
        }
        
        await poster.fill_step_1_basic_info(mock_internal_job)
        await poster.fill_step_1_options(mock_internal_job)
        await poster.fill_step_1_complex_fields(mock_internal_job)
        print("Successfully interacted with all Step 1 fields.")
        
        print("Advancing to Step 2...")
        await poster.proceed_to_next_step()
        
        # Pause so you can capture the next screen
        await asyncio.sleep(10)
        
    except Exception as e:
        print(f"Workflow test failed: {e}")
        
    finally:
        await manager.teardown()

if __name__ == "__main__":
    asyncio.run(test_workflow())