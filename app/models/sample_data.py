# app/models/sample_data.py
"""Sample JobPosting used while the automation is still being developed and
tested against the real bdjobs form. This is the same data that used to be
the `mock_internal_job` dict literal inside main.py - swap this factory out
for real data (loaded from a DB, spreadsheet, or an internal API) once the
automation is ready for production use.
"""
from models.job_posting import (
    AgeRange,
    CompensationBenefits,
    ExperienceRequirement,
    HRContact,
    JobPosting,
    SalaryRange,
)


def build_sample_job_posting() -> JobPosting:
    return JobPosting(
        job_id="JOB-2026-00129",
        title="Senior Software Engineer (Python)",
        category="IT/Telecommunication",
        specialization="Software Development",
        vacancies=2,
        employment_status="Full Time",
        workplace="Work From Office",
        deadline="09/25/2026",
        resume_receiver_email="hr@company.com",
        education_level="Bachelor of Science (BSc)",
        # drives the "Select Degree Level" native <select>; education_level
        # above is the second, cascading "Select Degree Name" <select>.
        degree_level="Bachelor/Honors",
        degree_title="Computer Science & Engineering",
        experience=ExperienceRequirement(required=True, min=3, max=6, freshers_can_apply=False),
        age=AgeRange(min=24, max=38),
        gender="Only Male",
        preferred_industries=["Software", "Garments", "Textile", "Spinning"],
        skills=["Python", "Django", "FastAPI", "PostgreSQL", "Docker"],
        job_context="We are looking for an experienced Python developer to scale our core platform.",
        job_responsibilities=(
            "- Build scalable backend REST APIs using FastAPI/Django\n"
            "- Optimize PostgreSQL databases\n"
            "- Collaborate with frontend and mobile teams\n"
            "- Write unit and integration tests"
        ),
        additional_requirements=(
            "- 3+ years experience with Python & PostgreSQL\n"
            "- Experience with Docker and CI/CD pipelines\n"
            "- Strong problem-solving skills and comfortable working in "
            "an agile, fast-paced team environment"
        ),
        salary=SalaryRange(type="Negotiable", min=60000, max=90000),
        compensation_benefits=CompensationBenefits(
            benefits=["Insurance", "Provident fund", "Performance bonus"],
            lunch_facility="Full Subsidize",
            salary_review="Yearly",
            festival_bonus="2",
            other_benefits="Annual team retreat and a learning stipend for courses and certifications.",
        ),
        job_location="Dhaka",
        restrict_age=True,
        restrict_gender=True,
        restrict_experience=True,
        # Placeholder HR/recruitment contact for the final "Related
        # Recruitment/HR person for this circular" card - replace with the
        # real contact before running against a real posting.
        hr_contact=HRContact(
            name="Nusrat Jahan",
            designation="HR Executive",
            email="hr@company.com",
            mobile="01711223344",
        ),
    )