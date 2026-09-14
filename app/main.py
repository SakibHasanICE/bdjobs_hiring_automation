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
        
        # Updated with data extracted from BDjobs_Posting_Template.xlsx
        #
        # NOTE on coverage: every key below IS actually read and filled by a
        # JobPoster method (confirmed against job_poster.py's job_data.get(...)
        # calls) - EXCEPT these four, which are kept here as reference/context
        # only because no fill method currently targets them on the real form:
        #   - job_id                (internal tracking id, not a form field)
        #   - specialization        (no fill_* step wires this to any input yet)
        #   - resume_receiver_email (no fill_* step wires this to any input yet)
        #   - job_context           (no fill_* step wires this to any input yet)
        # If the real form has inputs for specialization / resume receiver
        # email / job context, JobPoster needs new fill methods for them
        # first - adding the key here alone won't make them appear on screen.
        mock_internal_job = {
            "job_id": "JOB-2026-00129",
            "title": "Senior Software Engineer (Python)",
            "category": "IT/Telecommunication",
            "specialization": "Software Development",
            "vacancies": 2,
            "employment_status": "Full Time",
            "workplace": "Work From Office", 
            "deadline": "09/25/2026", 
            "resume_receiver_email": "hr@company.com",
            "education_level": "Bachelor of Science (BSc)",
            "degree_level": "Bachelor/Honors",  # drives the "Select Degree Level" native <select>; "education_level" above is the second cascading "Select Degree Name" <select>
            "degree_title": "Computer Science & Engineering",
            "experience": {
                "required": True,
                "min": 3,
                "max": 6,
                "freshers_can_apply": False
            },
            "age": {"min": 24, "max": 38},
            "gender": "Only Male",  #
            "preferred_industries": ["Software", "Garments", "Textile", "Spinning"],
            "skills": ["Python", "Django", "FastAPI", "PostgreSQL", "Docker"],
            "job_context": "We are looking for an experienced Python developer to scale our core platform.",
            "job_responsibilities": "- Build scalable backend REST APIs using FastAPI/Django\n- Optimize PostgreSQL databases\n- Collaborate with frontend and mobile teams\n- Write unit and integration tests",
            # BUG FIX: "additional_requirements" was previously defined TWICE
            # in this dict (once here, once further down). Python dict
            # literals silently keep only the LAST occurrence of a repeated
            # key, so the first sentence ("Must have strong problem-solving
            # skills...") was being thrown away with no warning - it never
            # reached the form at all. Merged into one value so both parts
            # actually get typed into the Additional Requirements editor.
            "additional_requirements": (
                "- 3+ years experience with Python & PostgreSQL\n"
                "- Experience with Docker and CI/CD pipelines\n"
                "- Strong problem-solving skills and comfortable working in "
                "an agile, fast-paced team environment"
            ),
            "salary": {
                "type": "Negotiable",
                "min": 60000,
                "max": 90000
            },
            "compensation_benefits": {
                "benefits": ["Insurance", "Provident fund", "Performance bonus"],
                "lunch_facility": "Full Subsidize",
                "salary_review": "Yearly",
                "festival_bonus": "2",
                "other_benefits": "Annual team retreat and a learning stipend for courses and certifications."
            },
            "job_location": "Dhaka",
            # Step 3 - Applicant Restriction: each of these is a plain
            # boolean toggle (Restrict on/off), not a value to type. True
            # switches it ON; False/omitted leaves it exactly as the form
            # already has it (off by default) - see
            # JobPoster.fill_step_3_matching_restrictions for the logic.
            "restrict_age": True,
            "restrict_gender": True,
            "restrict_experience": True,
        }
        
        # Each step is run independently: if one throws, we log it, save a
        # screenshot of exactly that failure, and still attempt the rest -
        # instead of one bad locator silently cancelling everything downstream.
        step_sequence = [
            ("Basic Info", poster.fill_step_1_basic_info),
            ("Options", poster.fill_step_1_options),
            ("Complex Fields (Category/Location/Deadline)", poster.fill_step_1_complex_fields),
            ("Details (Responsibilities & Salary)", poster.fill_step_1_details),
            ("Compensation & Benefits", poster.fill_compensation_and_benefits),
        ]

        for step_name, step_fn in step_sequence:
            try:
                print(f"Filling: {step_name}...")
                await step_fn(mock_internal_job)
                print(f"Done: {step_name}")
            except Exception as step_error:
                print(f"Step FAILED ({step_name}): {step_error}")
                safe_name = step_name.split(" ")[0].lower()
                await page.screenshot(path=f"error_{safe_name}.png", full_page=True)
                print(f"Saved screenshot: error_{safe_name}.png")

        print("Finished attempting all Step 1 fields (see log above for any failures).")
        
        print("Advancing to Step 2...")
        # wait_for_text verifies the click actually landed on Step 2 (rather than,
        # say, a modal from Step 1 swallowing it) before we try to fill anything.
        await poster.proceed_to_next_step(wait_for_text="Preferred Gender")

        print("Filling Step 2: Candidate Requirements...")
        await poster.fill_step_2_candidate_requirements(mock_internal_job)
        print("Successfully interacted with Step 2 fields.")

        print("Advancing to Step 3...")
        # Same "verify, don't trust the click blindly" pattern used for the
        # Step 1 -> 2 transition above: confirm Step 3's own content is
        # actually on screen before we try to interact with it.
        await poster.proceed_to_next_step(wait_for_text="Applicant Restriction")

        print("Filling Step 3: Matching & Restrictions...")
        await poster.fill_step_3_matching_restrictions(mock_internal_job)
        print("Done: Matching & Restrictions")

        # Pause so you can capture the next screen
        await asyncio.sleep(10)
        
    except Exception as e:
        print(f"Workflow test failed: {e}")
        try:
            await page.screenshot(path="error_state.png", full_page=True)
            print("Saved failure screenshot to error_state.png")
        except Exception:
            pass
        
    finally:
        await manager.teardown()

if __name__ == "__main__":
    asyncio.run(test_workflow())